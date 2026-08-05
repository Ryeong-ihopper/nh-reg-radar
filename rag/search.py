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


def embed_query(texts, model_name=None):
    """질의 임베딩. 색인과 **같은 모델**이어야 한다.

    로컬에 모델이 없으면 여기서 멈춘다 — 다른 모델로 만든 질의 벡터를 쓰면
    코사인 값이 무의미해지는데 에러는 안 난다.
    """
    from FlagEmbedding import BGEM3FlagModel
    import numpy as np
    if "model" not in _vec:
        _vec["model"] = BGEM3FlagModel("BAAI/bge-m3", use_fp16=False)
    v = np.asarray(_vec["model"].encode(list(texts), max_length=1024)["dense_vecs"],
                   dtype="float32")
    return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-9)


def vector(query, rows, k=50):
    import numpy as np
    v, m = vectors(rows)
    if m.get("model") and "BGE" not in m["model"].upper():
        raise RuntimeError(f"색인이 {m['model']} 로 만들어졌다 — 질의도 같은 모델로 "
                           f"임베딩해야 한다. embed_query 를 고칠 것")
    q = embed_query([query])[0]
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


def search(query, rows=None, how="hybrid", k=5, medium=None):
    """(순위, 항목) 목록. medium 을 주면 그 매체용 규칙으로 좁힌다.

    매체 필터가 여기 있는 이유: 규칙리스트는 매체(지면·영상·온라인)로 나누는데
    스키마의 `advertisement_type` 은 광고물 종류(전단·SMS·앱푸시)로 나눈다. 축이
    달라 규칙에 광고물 종류를 달 수 없으므로 **찾을 때 뒤집어 거른다.**
    """
    rows = rows if rows is not None else load_index()[0]
    over = max(k * 10, 50)                 # 거를 것을 감안해 넉넉히 뽑는다
    if how == "bm25":
        order = bm25(query, rows, over)
    elif how == "vector":
        order = vector(query, rows, over)
    else:
        order = rrf(bm25(query, rows, over), vector(query, rows, over), top=over)

    if medium:
        want = {medium, "ALL"}
        order = [i for i in order
                 if not rows[i].get("medium")            # 조문은 매체가 없다
                 or (set(rows[i]["medium"]) & want if isinstance(rows[i]["medium"], list)
                     else rows[i]["medium"] in want)]
    return [(i, rows[i]) for i in order[:k]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--how", default="hybrid", choices=("bm25", "vector", "hybrid"))
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--medium", default=None)
    a = ap.parse_args()

    rows, n_rules = load_index()
    print(f"색인 {len(rows):,}건 (규칙 {n_rules:,} + 조문 {len(rows)-n_rules:,})\n")
    for rank, (i, r) in enumerate(search(a.query, rows, a.how, a.k, a.medium), 1):
        kind = "규칙" if i < n_rules else "조문"
        print(f"{rank}. [{kind}] {r['evidence_id']}  {r.get('title','')[:56]}")
        if r.get("article_no"):
            print(f"      {r['article_no']}")
        print(f"      {(r.get('content') or '')[:100].replace(chr(10),' ')}")


if __name__ == "__main__":
    main()
