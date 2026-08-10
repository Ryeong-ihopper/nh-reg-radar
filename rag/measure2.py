# -*- coding: utf-8 -*-
"""**바로잡은 것을 다 넣고** 검색을 측정한다. 앞 숫자들은 못 쓴다.

지금까지 낸 숫자가 왜 못 쓰는지 셋이다.

    정답이 헐거웠다   「제16조」 아무 데나 걸리면 맞음 → 정답 행 48~140개
    광고가 통짜였다   HWP 를 긁어 문자열 하나. 표 셀·글자크기·좌표가 없었다
    색인이 조 단위    §16 안의 의무 스무 개가 청크 하나

셋 다 고쳤다.

    정답   ad_gold4    엑셀 주소를 항·호·목까지 따라감 → 정답 행 1~3개
    광고   ads_parsed  파서 DocIR → 청크 169개(중앙) · 글자크기 95% · 표 셀 행·열
    색인   호 단위      35,961 · ho_path 로 「5 나」를 가리킴

**질의를 넷으로 견준다.** 지금까지 이기던 것이 손으로 쓴 낱말 14개라, 그게
파서 청크에 밀리는지 보는 것이 이 측정의 요점이다.

    원문      광고 전문
    임의청크   통짜를 500자씩 자른 것        ← 지금까지 「청크별」이라 부르던 것
    파서청크   파서가 준 표 셀 단위 청크      ← 새것
    규칙질의   손으로 쓴 낱말 14개          ← 편향 있음. 견주려고 넣음

  python rag/measure2.py
  python rag/measure2.py --rerank
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
NL = chr(10)
RRF_K = 60

INDEXES = {
    "조단위": ("rule_index.jsonl", "vectors.f16.npy"),
    "호단위": ("rule_index_ho.jsonl", "vectors_ho.f16.npy"),
}


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


def rrf(*rankings, top=50):
    sc = collections.defaultdict(float)
    for rank in rankings:
        for r, i in enumerate(rank, 1):
            sc[i] += 1.0/(RRF_K+r)
    return [i for i, _ in sorted(sc.items(), key=lambda x: -x[1])[:top]]


def chunk_by_len(text, size=500):
    out, buf = [], []
    for line in text.split(NL):
        line = line.strip()
        if not line:
            continue
        buf.append(line)
        if len(NL.join(buf)) >= size:
            out.append(NL.join(buf))
            buf = []
    if buf:
        out.append(NL.join(buf))
    return [c for c in out if len(c) >= 25] or [text[:500]]


def queries(ad, mode, limit=14):
    """질의 만들기. **개수를 맞춘다** — 질의가 많으면 RRF 점수가 흩어져 불리하다.
    파서 청크는 169개나 되므로 그대로 던지면 방식 차이가 아니라 개수 차이를 잰다."""
    text = ad["text"]
    if mode == "원문":
        return [text[:1500]]
    if mode == "임의청크":
        return chunk_by_len(text)[:limit]
    if mode == "파서청크":
        cs = [c["text"] for c in (ad.get("청크") or []) if len(c["text"]) >= 15]
        # 긴 것부터 — 짧은 셀(「가입대상」 한 낱말)은 질의로 값어치가 낮다
        cs.sort(key=len, reverse=True)
        return cs[:limit] or [text[:500]]
    if mode == "규칙질의":
        return llm.mock_queries(text, 8)
    raise ValueError(mode)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rerank", action="store_true")
    ap.add_argument("--limit", type=int, default=14)
    ap.add_argument("-k", type=int, nargs="*", default=[1, 3, 5, 10])
    a = ap.parse_args()

    import numpy as np

    gold = json.load(open(os.path.join(RAG, "ad_gold4.json"),
                          encoding="utf-8"))["건"]
    gold = [g for g in gold if g.get("정답행")]
    ads = {}
    for l in open(os.path.join(RAG, "ads_parsed.jsonl"), encoding="utf-8"):
        x = json.loads(l)
        ads.setdefault(x["광고id"], x)
    gold = [g for g in gold if g["광고id"] in ads]

    print(f"정답 {len(gold)}건 (ad_gold4 · 주소 그대로) · "
          f"광고 {len(ads)}건 (파서 청크)")
    n_ch = [len(ads[g['광고id']].get('청크') or []) for g in gold]
    print(f"광고당 파서 청크 중앙 {sorted(n_ch)[len(n_ch)//2]}개 · "
          f"질의는 {a.limit}개로 맞춤\n")

    RR = None
    if a.rerank:
        from sentence_transformers import CrossEncoder
        RR = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=512)

    EMB = None
    KL = a.k
    for iname, (ifile, vfile) in INDEXES.items():
        ip = os.path.join(RAG, ifile)
        vp = os.path.join(RAG, vfile)
        if not os.path.exists(ip):
            continue
        rows = [json.loads(l) for l in open(ip, encoding="utf-8")]
        V = None
        if os.path.exists(vp):
            V = np.load(vp).astype("float32")
            if V.shape[0] != len(rows):
                V = None
        # **정답 행번호는 호 단위 색인 기준이다.** 조 단위에서는 같은 조문의
        # 조각을 찾아 옮겨야 한다. 안 옮기면 조 단위가 무조건 0% 로 나온다.
        if iname == "호단위":
            ansof = {g["광고id"]: set(g["정답행"]) for g in gold}
        else:
            ho = [json.loads(l) for l in
                  open(os.path.join(RAG, "rule_index_ho.jsonl"), encoding="utf-8")]
            key2row = collections.defaultdict(list)
            for i, r in enumerate(rows):
                m = re.match(r"\[([^\]]+)\]\s*", r.get("content") or "")
                if m:
                    key2row[(m.group(1).strip(),
                             re.sub(r"\s", "", r.get("article_no") or ""))].append(i)
            ansof = {}
            for g in gold:
                s = set()
                for i in g["정답행"]:
                    r = ho[i]
                    m = re.match(r"\[([^\]]+)\]\s*", r.get("content") or "")
                    if m:
                        s |= set(key2row.get((m.group(1).strip(),
                                              re.sub(r"\s", "",
                                                     r.get("article_no") or "")), []))
                ansof[g["광고id"]] = s

        if V is not None and EMB is None:
            import torch
            torch.set_num_threads(os.cpu_count() or 4)
            from sentence_transformers import SentenceTransformer
            EMB = SentenceTransformer("BAAI/bge-m3")
        bm = BM25(rows)
        QC = {}

        def qvec(q):
            if q not in QC:
                QC[q] = EMB.encode([q], normalize_embeddings=True).astype("float32")[0]
            return QC[q]

        print(f"== {iname} ==  색인 {len(rows):,} · "
              f"벡터 {'있음' if V is not None else '없음'}")
        hows = ["bm25"] + (["vector", "hybrid"] if V is not None else [])
        print(f"{'질의':10s} {'검색':8s} " + "  ".join(f"R@{k:<4d}" for k in KL) +
              ("   리랭커" if RR else ""))
        for qm in ("원문", "임의청크", "파서청크", "규칙질의"):
            for how in hows:
                hit = {k: 0 for k in KL}
                n = 0
                t0 = time.time()
                for g in gold:
                    ans = ansof.get(g["광고id"]) or set()
                    if not ans:
                        continue
                    n += 1
                    qs = queries(ads[g["광고id"]], qm, a.limit)
                    ranks = []
                    for q in qs:
                        if how in ("bm25", "hybrid"):
                            ranks.append(bm(q, 50))
                        if how in ("vector", "hybrid"):
                            s = V @ qvec(q)
                            ranks.append(list(np.argsort(-s)[:50]))
                    merged = rrf(*ranks, top=50) if len(ranks) > 1 else ranks[0]
                    if RR:
                        cand = merged[:30]
                        pairs = [[ads[g["광고id"]]["text"][:1000],
                                  index_text(rows[i])[:900]] for i in cand]
                        merged = [i for i, _ in sorted(zip(cand, RR.predict(pairs)),
                                                       key=lambda x: -x[1])]
                    pos = next((r for r, i in enumerate(merged[:max(KL)], 1)
                                if i in ans), None)
                    for k in KL:
                        if pos and pos <= k:
                            hit[k] += 1
                print(f"{qm:10s} {how:8s} " +
                      "  ".join(f"{hit[k]/max(n,1)*100:5.1f}%" for k in KL) +
                      f"  {time.time()-t0:4.0f}초 n={n}")
        print()

    print("※ 정답이 1~3행뿐이라 앞 숫자(48~140행 정답)보다 낮게 나오는 것이 정상이다.")
    print("  낮아진 게 아니라 **이제야 제대로 세는 것**이다.")


if __name__ == "__main__":
    main()
