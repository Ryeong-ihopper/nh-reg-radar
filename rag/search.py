# -*- coding: utf-8 -*-
"""통합 색인 검색 — BM25 · 벡터 · 하이브리드(RRF).

**색인 하나로 규칙과 조문을 함께 찾는다.** `rule_index.jsonl` 앞쪽 1,744건이 규칙,
뒤쪽이 조문 청크다. 광고를 보고 「무엇이 걸리나(규칙)」와 「왜 걸리나(조문)」를 한 번에
가져오려면 나눠 둘 이유가 없다.

벡터는 Colab 에서 BGE-M3 로 만들어 `vectors.f16.npy` 로 받아 온다. GPU 는 만들 때만
필요하고, 찾는 것은 행렬 곱 한 번이라 CPU 로 충분하다.

**낡은 벡터를 쓰면 조용히 틀린다.** 청크 번호가 어긋나도 검색은 그대로 돌아가고 엉뚱한
문서가 나올 뿐이다 — 실제로 코퍼스를 43종에서 29종으로 줄이고도 예전 임베딩
(7,862×4096)이 남아 있었다. `vectors.meta.json` 의 건수·모델을 대조해 다르면 멈춘다.

  python rag/search.py "연 최고 7.0% 우대금리 제공"
  python rag/search.py --how bm25 "심의필번호"
"""
import os
import json
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")
INDEX = os.path.join(RAG, "rule_index.jsonl")
VECS = os.path.join(RAG, "vectors.f16.npy")
META = os.path.join(RAG, "vectors.meta.json")

RRF_K = 60          # 관례값. 순위를 더하므로 점수 자릿수를 맞출 필요가 없다


def load_index(path=INDEX):
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    n_rules = sum(1 for r in rows if r["evidence_id"].startswith("R-"))
    return rows, n_rules


def index_text(r):
    """색인·검색에 쓰는 문자열. 색인을 만들 때와 **반드시 같아야 한다.**"""
    return f"{r.get('title','')} {r.get('article_no','')} {r.get('content','')}"


# ── BM25 ──────────────────────────────────────────────────────────────────
_bm = {}


def bm25_index(rows, path=None):
    """색인을 만들거나 캐시에서 꺼낸다. rule_index 용은 따로 둔다."""
    import pickle
    import math
    import collections
    import bm25 as BM

    path = path or os.path.join(RAG, "bm25_index.pkl")
    stamp = {"n": len(rows)}
    if path in _bm:
        return _bm[path]
    if os.path.exists(path):
        idx = pickle.load(open(path, "rb"))
        if idx.get("stamp") == stamp:
            _bm[path] = idx
            return idx
        print(f"[다시 만듦] BM25 색인이 {idx.get('stamp')} 기준 — 지금은 {stamp}")

    docs, df = [], collections.Counter()
    for r in rows:
        tf = collections.Counter(BM.tokenize(index_text(r)))
        docs.append(tf)
        df.update(tf.keys())
    N = len(docs)
    idf = {t: math.log(1 + (N - n + 0.5) / (n + 0.5)) for t, n in df.items()}
    inv = collections.defaultdict(list)
    for i, d in enumerate(docs):
        for t, f in d.items():
            inv[t].append((i, f))
    dl = [sum(d.values()) for d in docs]
    idx = {"inv": dict(inv), "idf": idf, "dl": dl,
           "avgdl": sum(dl) / max(N, 1), "stamp": stamp}
    pickle.dump(idx, open(path, "wb"), protocol=4)
    _bm[path] = idx
    return idx


def bm25(query, rows, k=50):
    import collections
    import bm25 as BM
    idx = bm25_index(rows)
    K1, B = 1.2, 0.75
    sc = collections.defaultdict(float)
    for t in set(BM.tokenize(query)):
        post = idx["inv"].get(t)
        if not post:
            continue
        w = idx["idf"][t]
        for i, f in post:
            sc[i] += w * f * (K1 + 1) / (
                f + K1 * (1 - B + B * idx["dl"][i] / idx["avgdl"]))
    return [i for i, _ in sorted(sc.items(), key=lambda x: -x[1])[:k]]


# ── 벡터 ──────────────────────────────────────────────────────────────────
_vec = {}


def vectors(rows):
    """(행렬, 메타). 없거나 코퍼스와 어긋나면 멈춘다."""
    if "v" in _vec:
        return _vec["v"], _vec["m"]
    if not os.path.exists(VECS):
        raise FileNotFoundError(
            f"벡터가 없다: {VECS}\n"
            "  rag/index_ab_colab.ipynb 를 Colab 에서 돌려 10번 셀에서 받는다.")
    import numpy as np
    m = json.load(open(META, encoding="utf-8")) if os.path.exists(META) else {}
    v = np.load(VECS).astype("float32")
    if m.get("n") != len(rows) or v.shape[0] != len(rows):
        raise RuntimeError(
            f"벡터가 지금 색인과 다르다 — 번호가 어긋나 엉뚱한 문서가 나온다.\n"
            f"  벡터 {v.shape[0]}건(meta {m.get('n')}) · 색인 {len(rows)}건\n"
            f"  모델 {m.get('model')} · 차원 {v.shape[1]}\n"
            f"  Colab 노트북을 다시 돌려 vectors.f16.npy 를 새로 받을 것")
    _vec["v"], _vec["m"] = v, m
    return v, m


# 색인을 만든 Colab 노트북(rag/index_ab_colab.ipynb)의 SPEC 과 **같은 표**여야 한다.
# 다른 모델·다른 접두어로 질의를 임베딩하면 코사인 값이 무의미해지는데 에러는 안 난다.
MODELS = {
    "BGE-M3":    ("BAAI/bge-m3", 1024, ("", "")),
    "ME5-large": ("intfloat/multilingual-e5-large", 512, ("query: ", "passage: ")),
}


def embed_query(texts, model_name):
    """질의 임베딩. 색인과 **같은 모델·같은 접두어**로."""
    import numpy as np
    from sentence_transformers import SentenceTransformer
    if model_name not in MODELS:
        raise RuntimeError(f"모르는 모델이다: {model_name}. MODELS 에 추가할 것")
    path, maxlen, (qpre, _) = MODELS[model_name]
    if "model" not in _vec:
        m = SentenceTransformer(path)
        m.max_seq_length = maxlen
        _vec["model"] = m
    v = _vec["model"].encode([qpre + t for t in texts],
                             convert_to_numpy=True).astype("float32")
    return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)


def vector(query, rows, k=50):
    import numpy as np
    v, m = vectors(rows)
    q = embed_query([query], m.get("model"))[0]
    return np.argsort(-(v @ q))[:k].tolist()


# ── 하이브리드 ────────────────────────────────────────────────────────────
def rrf(*rankings, k=RRF_K, top=50):
    """순위를 더한다. BM25 점수(0~30)와 코사인(0~1)의 자릿수를 맞출 필요가 없다."""
    import collections
    sc = collections.defaultdict(float)
    for r in rankings:
        for pos, d in enumerate(r, 1):
            sc[d] += 1.0 / (k + pos)
    return [d for d, _ in sorted(sc.items(), key=lambda x: -x[1])[:top]]


def _passes(value, want):
    """**비어 있으면 통과시킨다.**

    「전체」 상품에 걸리는 규칙은 product_group 이 비어 있고, 조문에는 상품군도
    매체도 없다. 빈 값을 탈락시키면 의무표시사항처럼 **모든 광고에 걸리는 규칙이
    통째로 사라진다** — 걸러서 좁힌 게 아니라 정답을 버린 것이 된다.
    """
    if not value:
        return True
    got = set(value) if isinstance(value, (list, tuple, set)) else {value}
    return bool(got & want)


def _quota(order, n_rules, k, n_rule_slots):
    """규칙과 조문에 자리를 나눠 준다.

    **합친 색인에서는 규칙이 상위를 독차지한다** — 2026-08-06 실측으로 상위 10개 중
    규칙이 79~86% 였다(전체에서 규칙 비중은 21%). 규칙이 짧고 질의 어휘와 그대로
    겹치기 때문이다. 그대로 두면 「왜 걸리나」를 답할 조문이 밀려나 근거를 못 댄다.
    """
    rules = [i for i in order if i < n_rules][:n_rule_slots]
    arts = [i for i in order if i >= n_rules][:k - len(rules)]
    out = rules + arts
    # 한쪽이 모자라면 다른 쪽으로 채운다. 자리를 비워 두는 것이 더 나쁘다.
    if len(out) < k:
        out += [i for i in order if i not in set(out)][:k - len(out)]
    return sorted(out, key=order.index)


def search(query, rows=None, how="bm25", k=5, medium=None, product=None,
           rule_slots=None):
    """(순위, 항목) 목록.

    기본이 `bm25` 인 이유: **하이브리드가 BM25 단독보다 나쁘다**(2026-08-06 실측,
    R@5 59.6% vs 75.1%). RRF 는 두 검색기 실력이 비슷할 때 이기는데 지금은 벡터가
    45% 라 강한 쪽을 끌어내린다. 벡터 쪽이 나아지면 기본값을 되돌린다.

    매체 필터가 여기 있는 이유: 규칙리스트는 매체(지면·영상·온라인)로 나누는데
    스키마의 `advertisement_type` 은 광고물 종류(전단·SMS·앱푸시)로 나눈다. 축이
    달라 규칙에 광고물 종류를 달 수 없으므로 **찾을 때 뒤집어 거른다.**
    """
    rows, n_rules = (rows, sum(1 for r in rows if r["evidence_id"].startswith("R-"))) \
        if rows is not None else load_index()
    over = max(k * 10, 50)                 # 거를 것을 감안해 넉넉히 뽑는다
    if how == "bm25":
        order = bm25(query, rows, over)
    elif how == "vector":
        order = vector(query, rows, over)
    else:
        order = rrf(bm25(query, rows, over), vector(query, rows, over), top=over)

    if medium:
        want = {medium, "ALL"}
        order = [i for i in order if _passes(rows[i].get("medium"), want)]
    if product:
        want = {product}
        order = [i for i in order if _passes(rows[i].get("product_group"), want)]

    if rule_slots is None:
        rule_slots = max(1, k * 3 // 5)    # 5개면 규칙 3 + 조문 2
    order = _quota(order, n_rules, k, rule_slots)
    return [(i, rows[i]) for i in order[:k]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--how", default="hybrid", choices=("bm25", "vector", "hybrid"))
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--medium", default=None)
    ap.add_argument("--product", default=None)
    a = ap.parse_args()

    rows, n_rules = load_index()
    print(f"색인 {len(rows):,}건 (규칙 {n_rules:,} + 조문 {len(rows)-n_rules:,})\n")
    for rank, (i, r) in enumerate(search(a.query, rows, a.how, a.k, a.medium, a.product), 1):
        kind = "규칙" if i < n_rules else "조문"
        print(f"{rank}. [{kind}] {r['evidence_id']}  {r.get('title','')[:56]}")
        if r.get("article_no"):
            print(f"      {r['article_no']}")
        print(f"      {(r.get('content') or '')[:100].replace(chr(10),' ')}")


if __name__ == "__main__":
    main()
