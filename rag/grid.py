# -*- coding: utf-8 -*-
"""검색 경로를 **전부 켜고 한 표에서 견준다.** 지금까지 하나씩만 재고 결론을 냈다.

그렇게 해서 틀린 결론이 둘 나왔다.

    "BM25 단독이 낫다"        벡터를 리랭커 없이 · 잘못된 채점으로 재고 버렸다.
                             켜 보니 R@10 이 40% → 80% 로 뒤집혔다
    "광고 원문 질의는 못 쓴다"  BM25 로만 재고 버렸다. 벡터로는 재본 적이 없다

여기서는 축을 다 세우고 조합을 돌린다.

    색인 대상   규정(규칙+조문+매뉴얼)  ·  광고(과거 광고 청크)   ← 광고 색인이 없었다
    청킹       조 단위  ·  호 단위  ·  둘 다(다층)
    질의       광고 원문 통째  ·  규칙기반 질의  ·  광고 청크별
    검색       BM25  ·  벡터  ·  하이브리드(RRF)
    재정렬      없음  ·  리랭커

**축 하나만 바꾸고 나머지를 고정한다.** 두 개를 같이 바꾸면 어느 쪽 때문에
좋아졌는지 못 가린다. 여태 그걸 안 지켜서 숫자가 서로 안 맞았다.

  python rag/grid.py                       # 있는 것만으로 전부 돌린다
  python rag/grid.py --rerank              # 리랭커까지 (CPU 느림)
  python rag/grid.py --only vector         # 한 축만
"""
import os
import re
import sys
import json
import math
import time
import argparse
import itertools
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import llm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")

# 색인 후보 — 파일이 있는 것만 돈다. 없으면 그 줄을 「없음」으로 표시한다.
INDEXES = {
    "조단위": ("rule_index.jsonl", "vectors.f16.npy"),
    "호단위": ("rule_index_ho.jsonl", "vectors_ho.f16.npy"),
}
RRF_K = 60
NL = chr(10)


def index_text(r):
    return f"{r.get('title','')} {r.get('article_no') or ''} {r.get('content','')}"


def tokenize(s):
    out = re.findall(r"제\s*\d+조(?:의\s*\d+)?|[A-Za-z]+|\d+", str(s or ""))
    for w in re.findall(r"[가-힣]+", str(s or "")):
        out += [w[i:i+2] for i in range(len(w)-1)] or [w]
    return out


class BM25:
    def __init__(self, rows):
        docs, df = [], collections.Counter()
        for r in rows:
            tf = collections.Counter(tokenize(index_text(r)))
            docs.append(tf)
            df.update(tf.keys())
        n = len(docs)
        self.idf = {t: math.log(1+(n-c+0.5)/(c+0.5)) for t, c in df.items()}
        self.inv = collections.defaultdict(list)
        for i, d in enumerate(docs):
            for t, f in d.items():
                self.inv[t].append((i, f))
        self.dl = [sum(d.values()) for d in docs]
        self.avgdl = sum(self.dl)/max(n, 1)

    def __call__(self, q, k=50):
        K1, B = 1.2, 0.75
        sc = collections.defaultdict(float)
        for t in set(tokenize(q)):
            post = self.inv.get(t)
            if not post:
                continue
            w = self.idf[t]
            for i, f in post:
                sc[i] += w*f*(K1+1)/(f+K1*(1-B+B*self.dl[i]/self.avgdl))
        return [i for i, _ in sorted(sc.items(), key=lambda x: -x[1])[:k]]


class Like:
    """부분 문자열 겹침. SQL 의 LIKE 에 해당한다.

    BM25 는 낱말 빈도와 문서 길이로 점수를 매기는데, LIKE 는 **그냥 들어 있나만**
    본다. 「예금자보호법」처럼 긴 고유 표현은 이게 더 정확할 수 있다 — BM25 는
    이걸 바이그램으로 쪼개 흔한 조각(「예금」)에 점수를 나눠 준다.
    """

    def __init__(self, rows):
        self.norm = [re.sub(r"[\s·ㆍ]", "", index_text(r)) for r in rows]

    def __call__(self, q, k=50):
        terms = [t for t in re.findall(r"[가-힣A-Za-z]{2,}", str(q or ""))
                 if len(t) >= 2]
        terms = sorted(set(terms), key=len, reverse=True)[:20]
        if not terms:
            return []
        sc = collections.Counter()
        for i, doc in enumerate(self.norm):
            hit = sum(len(t) for t in terms if t in doc)   # 긴 낱말에 가중
            if hit:
                sc[i] = hit
        return [i for i, _ in sc.most_common(k)]


def mmr(cand, V, lam=0.7, top=50):
    """비슷한 것끼리 몰리지 않게 고른다(Maximal Marginal Relevance).

    상위 5개가 같은 조문의 다른 조각이면 근거가 다섯 개인 척하지만 실은 하나다.
    호 단위로 잘게 쪼갤수록 이 문제가 커진다.
    """
    if V is None or not cand:
        return cand[:top]
    import numpy as np
    sel, rest = [], list(cand)
    while rest and len(sel) < top:
        if not sel:
            sel.append(rest.pop(0))
            continue
        S = V[sel]
        best, bi = None, 0
        for j, i in enumerate(rest[:60]):
            rel = 1.0 - j/len(rest)
            div = float((V[i] @ S.T).max())
            score = lam*rel - (1-lam)*div
            if best is None or score > best:
                best, bi = score, j
        sel.append(rest.pop(bi))
    return sel


def rrf(*rankings, top=50):
    """순위를 더한다. **점수를 더하지 않는다** — BM25 점수와 코사인은 자릿수가 달라
    그대로 더하면 한쪽이 묻힌다."""
    sc = collections.defaultdict(float)
    for rank in rankings:
        for r, i in enumerate(rank, 1):
            sc[i] += 1.0/(RRF_K+r)
    return [i for i, _ in sorted(sc.items(), key=lambda x: -x[1])[:top]]


def ad_queries(text, mode):
    """질의 만들기. 세 방식을 같은 자리에서 비교한다."""
    if mode == "원문":
        return [text[:1500]]
    if mode == "규칙질의":
        return llm.mock_queries(text, 8)
    if mode == "청크별":
        # 광고를 줄 단위 덩어리로 잘라 각각 질의로 쓴다. 파서가 청크를 주면
        # 그것을 쓰면 되고, 지금은 통짜 문자열이라 여기서 자른다.
        parts = [p.strip() for p in re.split(r"\n{1,}", text) if len(p.strip()) >= 20]
        return parts[:12] or [text[:1500]]
    raise ValueError(mode)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rerank", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--mmr", action="store_true", help="비슷한 것 몰림 방지")
    ap.add_argument("-k", type=int, nargs="*", default=[1, 3, 5, 10])
    a = ap.parse_args()

    import numpy as np

    gold = json.load(open(os.path.join(RAG, "ad_gold.json"), encoding="utf-8"))["건"]
    ads = {}
    for l in open(os.path.join(RAG, "ads.jsonl"), encoding="utf-8"):
        x = json.loads(l)
        ads.setdefault(x["광고id"], x)

    EMB = RR = None
    if a.rerank:
        from sentence_transformers import CrossEncoder
        RR = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=512)

    KL = a.k
    print(f"정답 {len(gold)}건 (심의사례) · k={KL}"
          + ("  · 리랭커 붙임" if RR else ""))

    for iname, (ifile, vfile) in INDEXES.items():
        ip, vp = os.path.join(RAG, ifile), os.path.join(RAG, vfile)
        if not os.path.exists(ip):
            print(f"\n== {iname} ==  색인 파일 없음 ({ifile})")
            continue
        rows = [json.loads(l) for l in open(ip, encoding="utf-8")]
        n_rules = sum(1 for r in rows if r["evidence_id"].startswith("R-"))
        V = None
        if os.path.exists(vp):
            V = np.load(vp).astype("float32")
            if V.shape[0] != len(rows):
                print(f"\n※ {iname}: 벡터 {V.shape[0]:,} ≠ 색인 {len(rows):,} — "
                      f"벡터 검색 건너뜀")
                V = None
        print(f"\n== {iname} ==  색인 {len(rows):,} · "
              f"벡터 {'있음' if V is not None else '없음'}")
        if V is not None and EMB is None:
            import torch
            torch.set_num_threads(os.cpu_count() or 4)
            from sentence_transformers import SentenceTransformer
            EMB = SentenceTransformer("BAAI/bge-m3")

        bm = BM25(rows)
        # 정답을 원본 청크 id 로 되짚는다. 청킹이 바뀌면 청크 번호가 달라지므로
        # 번호로 채점하면 두 색인을 견줄 수 없다.
        src_of = {}
        for i, r in enumerate(rows):
            md = r.get("metadata_json") or {}
            sid = md.get("src_id")
            if sid:
                src_of.setdefault(re.sub(r"#\d+$", "", sid), []).append(i)

        chunks = [json.loads(l) for l in
                  open(os.path.join(RAG, "chunks.jsonl"), encoding="utf-8")]

        def refs_of(row):
            out = set()
            for b in (row.get("근거") or []):
                out.add((str(b.get("규정") or ""), str(b.get("article_no") or "")))
            m = re.match(r"\[([^\]]+)\]\s*(제\s*\d+조(?:의\s*\d+)?)",
                         row.get("content") or "")
            if m:
                out.add((m.group(1).strip(), re.sub(r"\s", "", m.group(2))))
            return out

        def answer_rows(g):
            """이 정답이 이 색인에서 어느 행들인가.

            **규칙도 센다.** 규칙이 정답 조문을 근거로 달고 있으면 그것을 찾은 것도
            맞은 것이다. 「조문만 정답」으로 세면 질의의 쌍둥이 규칙이 1위에 와도
            오답이 되어 전부 0% 가 나온다 — 실제로 그렇게 나왔다.
            """
            out = set()
            for c in g["정답청크"]:
                if iname == "조단위":
                    out.add(c + n_rules)
                else:
                    out |= set(src_of.get(chunks[c]["id"], []))
            want = {(str(x[0]), re.sub(r"\s", "", str(x[1])))
                    for x in (g.get("정답") or [])
                    if isinstance(x, (list, tuple)) and len(x) >= 2
                    and not str(x[0]).startswith("?")}
            if want:
                for i, r in enumerate(rows):
                    if refs_of(r) & want:
                        out.add(i)
            return out

        def vec(q, k=50):
            qv = EMB.encode([q], normalize_embeddings=True).astype("float32")[0]
            return list(np.argsort(-(V @ qv))[:k])

        lk = Like(rows)

        def search(q, how, k=50):
            if how == "bm25":
                return bm(q, k)
            if how == "like":
                return lk(q, k)
            if how == "vector":
                return vec(q, k)
            if how == "hybrid":
                return rrf(bm(q, k), vec(q, k), top=k)
            if how == "hybrid3":
                # 셋 다 — 키워드 두 방식과 벡터
                return rrf(bm(q, k), lk(q, k), vec(q, k), top=k)
            raise ValueError(how)

        hows = ["bm25", "like"] + (["vector", "hybrid", "hybrid3"]
                                   if V is not None else [])
        if a.only:
            hows = [h for h in hows if h == a.only]
        qmodes = ["원문", "규칙질의", "청크별"]

        print(f"{'질의':8s} {'검색':8s} " + " ".join(f"R@{k:<4d}" for k in KL) + "  초")
        for qm, how in itertools.product(qmodes, hows):
            hit = {k: 0 for k in KL}
            n = 0
            t0 = time.time()
            for g in gold:
                ans = answer_rows(g)
                if not ans:
                    continue
                n += 1
                qs = ad_queries(ads[g["광고id"]]["text"], qm)
                ranks = [search(q, how, 50) for q in qs]
                merged = rrf(*ranks, top=50) if len(ranks) > 1 else ranks[0]
                if a.mmr:
                    merged = mmr(merged, V, top=50)
                if RR:
                    cand = merged[:30]
                    pairs = [[qs[0], index_text(rows[i])[:900]] for i in cand]
                    merged = [i for i, _ in sorted(zip(cand, RR.predict(pairs)),
                                                   key=lambda x: -x[1])]
                pos = next((r for r, i in enumerate(merged[:max(KL)], 1)
                            if i in ans), None)
                for k in KL:
                    if pos and pos <= k:
                        hit[k] += 1
            if not n:
                print(f"{qm:8s} {how:8s} 정답을 이 색인에서 못 찾음")
                continue
            print(f"{qm:8s} {how:8s} " +
                  " ".join(f"{hit[k]/n*100:5.1f}%" for k in KL) +
                  f"  {time.time()-t0:4.0f}  n={n}")

    print("\n※ 축 하나만 바꾸고 나머지는 고정했다. 두 개를 같이 바꾸면 어느 쪽")
    print("  때문인지 못 가린다.")
    print("※ 광고 색인(과거 광고·심의사례 유사검색)은 아직 없다 — 별도 작업.")


if __name__ == "__main__":
    main()
