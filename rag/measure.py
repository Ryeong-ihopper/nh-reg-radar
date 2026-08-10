# -*- coding: utf-8 -*-
"""검색을 **한 색인·한 조건**으로 측정한다. 지금까지 숫자가 셋이었다.

    R@5 75.1%   질문 → 조문   조문만 색인 6,565      evaluate.py
    R@5 14.4%   질문 → 조문   규칙+조문 색인 8,309   search.py  ← 규칙을 오답으로 셈
    R@5 33.3%   광고 → 조문   규칙+조문 색인 8,309

**셋 다 다른 것을 쟀다.** 색인이 두 벌이라 「측정한 것」과 「실제로 검색하는 것」이
달랐고, 그래서 보고한 숫자가 실제 성능이 아니었다.

여기서 하나로 맞춘다.

    색인    rule_index.jsonl 하나 (규칙 1,744 + 조문 6,565 + 매뉴얼 1,026 = 9,335)
    질의    광고에서 뽑은 것 — 심의팀이 하는 일과 같은 출발점
    정답    심의사례 15건 (사람이 적은 것)
    방식    BM25 · 벡터 · 하이브리드(RRF) 각각, 리랭커 붙이고/떼고

**규칙이 정답 근거를 달고 나오면 맞은 것으로 센다.** 「조문만 정답」으로 세면
질의의 쌍둥이 규칙이 1위에 와도 오답이 되어 14.4% 같은 숫자가 나온다.

  python rag/measure.py                    # 리랭커 없이 (빠름)
  python rag/measure.py --rerank           # 리랭커까지 (CPU 30쌍 50초)
"""
import os
import re
import sys
import json
import math
import time
import argparse
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import llm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")
INDEX = os.path.join(RAG, "rule_index.jsonl")
VECS = os.path.join(RAG, "vectors.f16.npy")

RRF_K = 60


def load():
    rows = [json.loads(l) for l in open(INDEX, encoding="utf-8")]
    n_rules = sum(1 for r in rows if r["evidence_id"].startswith("R-"))
    return rows, n_rules


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
        self.avgdl = sum(self.dl)/n

    def __call__(self, q, k=50, allow=None):
        K1, B = 1.2, 0.75
        sc = collections.defaultdict(float)
        for t in set(tokenize(q)):
            post = self.inv.get(t)
            if not post:
                continue
            w = self.idf[t]
            for i, f in post:
                if allow is not None and not allow[i]:
                    continue
                sc[i] += w*f*(K1+1)/(f+K1*(1-B+B*self.dl[i]/self.avgdl))
        return [i for i, _ in sorted(sc.items(), key=lambda x: -x[1])[:k]]


def rrf(*rankings, top=50):
    sc = collections.defaultdict(float)
    for rank in rankings:
        for r, i in enumerate(rank, 1):
            sc[i] += 1.0/(RRF_K+r)
    return [i for i, _ in sorted(sc.items(), key=lambda x: -x[1])[:top]]


def refs_of(row):
    """이 색인 행이 가리키는 (규정, 조) 집합. 규칙은 근거를, 조문은 자기 자신을."""
    out = set()
    for b in (row.get("근거") or []):
        out.add((str(b.get("규정") or ""), str(b.get("article_no") or "")))
    c = row.get("content") or ""
    m = re.match(r"\[([^\]]+)\]\s*(제\s*\d+조(?:의\s*\d+)?)", c)
    if m:
        out.add((m.group(1).strip(), re.sub(r"\s", "", m.group(2))))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rerank", action="store_true")
    ap.add_argument("-k", type=int, nargs="*", default=[1, 3, 5, 10])
    a = ap.parse_args()

    rows, n_rules = load()
    n_man = sum(1 for r in rows if r["evidence_id"].startswith("M-"))
    print(f"색인 {len(rows):,} = 규칙 {n_rules:,} + 조문 "
          f"{len(rows)-n_rules-n_man:,} + 매뉴얼 {n_man:,}")

    gold = json.load(open(os.path.join(RAG, "ad_gold.json"), encoding="utf-8"))["건"]
    ads = {}
    for l in open(os.path.join(RAG, "ads.jsonl"), encoding="utf-8"):
        x = json.loads(l)
        ads.setdefault(x["광고id"], x)
    print(f"정답 {len(gold)}건 (심의사례 기반)\n")

    bm = BM25(rows)

    import numpy as np
    V = None
    if os.path.exists(VECS):
        V = np.load(VECS).astype("float32")
        if V.shape[0] != len(rows):
            print(f"※ 벡터 {V.shape[0]:,} 가 색인 {len(rows):,} 와 다르다 — "
                  f"벡터 검색을 건너뛴다")
            V = None
    if V is not None:
        import torch
        torch.set_num_threads(os.cpu_count() or 4)
        from sentence_transformers import SentenceTransformer
        EMB = SentenceTransformer("BAAI/bge-m3")

    RR = None
    if a.rerank:
        from sentence_transformers import CrossEncoder
        RR = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=512)

    def vec(q, k=50):
        qv = EMB.encode([q], normalize_embeddings=True).astype("float32")[0]
        return list(np.argsort(-(V @ qv))[:k])

    def run(q, how, k):
        if how == "bm25":
            cand = bm(q, 50)
        elif how == "vector":
            cand = vec(q, 50)
        else:
            cand = rrf(bm(q, 50), vec(q, 50), top=50)
        if RR:
            cand = cand[:30]
            pairs = [[q, index_text(rows[i])[:900]] for i in cand]
            cand = [i for i, _ in sorted(zip(cand, RR.predict(pairs)),
                                         key=lambda x: -x[1])]
        return cand[:k]

    KL = a.k
    ways = ["bm25"] + (["vector", "hybrid"] if V is not None else [])
    print(f"{'방식':10s} " + "  ".join(f"R@{k:<4d}" for k in KL) +
          ("   (리랭커 붙임)" if RR else ""))
    for how in ways:
        hit = {k: 0 for k in KL}
        n = 0
        t0 = time.time()
        for g in gold:
            # 정답은 [규정명, 조문키] 쌍의 목록이다(사전이 아니다).
            want = {(str(x[0]), re.sub(r"\s", "", str(x[1])))
                    for x in (g.get("정답") or []) if isinstance(x, (list, tuple))
                    and len(x) >= 2 and not str(x[0]).startswith("?")}
            ansc = {c + n_rules for c in g["정답청크"]}
            if not want and not ansc:
                continue
            n += 1
            # 질의는 **광고에서** 나온다. 심의사례 체크항목을 그대로 쓰면
            # 정답 문장을 질의로 주는 셈이라 너무 쉬워진다.
            #
            # 광고 원문을 통째로 넣으면 안 된다 — 실측 R@10 0.0%. 광고는 마케팅
            # 말투이고 규정은 법률 말투라 글자가 안 겹친다. 규칙 기반으로 규정
            # 어휘의 질의를 만들어 던지고 RRF 로 합친다(LLM 안 씀).
            qs = llm.mock_queries(ads[g["광고id"]]["text"], 8)
            ranks = [run(q, how, max(KL)) for q in qs]
            merged = rrf(*ranks, top=max(KL)) if len(ranks) > 1 else ranks[0]
            pos = None
            for r, i in enumerate(merged, 1):
                if i in ansc or (refs_of(rows[i]) & want):
                    pos = r
                    break
            for k in KL:
                if pos and pos <= k:
                    hit[k] += 1
        print(f"{how:10s} " + "  ".join(f"{hit[k]/n*100:5.1f}%" for k in KL) +
              f"   n={n} · {time.time()-t0:.0f}초")

    print("\n※ 정답은 광고당 1건뿐이라 **회수만** 잰다. 정답에 없는 근거가 나왔다고")
    print("  틀린 게 아니다. 보고 지표인 EVIDENCE_PRECISION(근거 매칭 적정성)은")
    print("  사람이 근거를 O/X 로 봐줘야 나온다.")


if __name__ == "__main__":
    main()
