# -*- coding: utf-8 -*-
"""검색 성능 측정 — gold 103건 대비 Recall / MRR.

**검색기가 무엇이든 같은 잣대로 잰다.** BM25·벡터·하이브리드·리랭커를 각각 다른
방식으로 평가하면 비교가 성립하지 않는다. 여기에 `이름 → (질의 → 청크번호 순위)`
함수만 넘기면 나머지는 동일하게 처리된다.

지표를 둘 쓰는 이유:

  Recall@k  정답이 상위 k 안에 **들어오기라도 하는가.** 사람이 검토할 후보를
            뽑는 단계(1차 검색)에서 중요하다. 여기서 빠지면 뒤에서 못 살린다.
  MRR       정답이 **몇 위에 오는가**(1위면 1.0, 5위면 0.2). 리랭커처럼 순서를
            고치는 단계의 값어치는 Recall 로는 안 보이고 MRR 로만 보인다.

정답은 조문 단위인데 청크는 조문이 길면 쪼개진다(`제22조#1`, `#2`…). 그래서
**같은 조문의 어느 조각이든 맞으면 맞은 것**으로 센다 — 사람은 조문을 찾는 것이지
조각을 찾는 것이 아니다.

  python rag/evaluate.py --bm25
  python rag/evaluate.py --bm25 --k 5 10 20
"""
import os
import sys
import json
import argparse
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = os.path.join(ROOT, "output", "_rag", "gold.json")
CHUNKS = os.path.join(ROOT, "output", "_rag", "chunks.jsonl")


def load():
    gold = json.load(open(GOLD, encoding="utf-8"))
    rows = [json.loads(l) for l in open(CHUNKS, encoding="utf-8")]
    return gold, rows


def score(gold, ranked, ks=(1, 5, 10, 20)):
    """ranked: {gold_id: [청크번호 순위]} → 지표 dict."""
    out = {f"R@{k}": 0 for k in ks}
    mrr = 0.0
    n = 0
    misses = []
    for g in gold:
        r = ranked.get(g["id"])
        if r is None:
            continue
        n += 1
        ans = set(g["정답청크"])
        pos = next((i for i, c in enumerate(r, 1) if c in ans), None)
        for k in ks:
            if pos and pos <= k:
                out[f"R@{k}"] += 1
        mrr += 1.0 / pos if pos else 0.0
        if not pos or pos > 10:
            misses.append((g["id"], g["q"][:52], g["근거원문"]))
    return ({k: v / n for k, v in out.items()} | {"MRR": mrr / n, "n": n}), misses


def report(name, gold, ranked, ks, show_miss=8):
    m, misses = score(gold, ranked, ks)
    head = " · ".join(f"{k} {m[k]*100:5.1f}%" for k in m if k.startswith("R@"))
    print(f"\n== {name} ==  (n={m['n']})")
    print(f"  {head} · MRR {m['MRR']:.3f}")

    # 출처·상품유형별로 나눠 본다 — 체크리스트는 일반론, 심의사례는 구체 상황이라
    # 성격이 다르고, 한쪽만 잘 되는 경우가 실제로 있다.
    for field in ("출처", "상품유형"):
        buckets = collections.defaultdict(list)
        for g in gold:
            buckets[g.get(field, "?")].append(g)
        parts = []
        for key, gs in sorted(buckets.items()):
            mm, _ = score(gs, ranked, ks)
            parts.append(f"{key} R@10 {mm['R@10']*100:.0f}% MRR {mm['MRR']:.2f}")
        print(f"  {field}: " + " | ".join(parts))

    if misses and show_miss:
        print(f"  상위10 실패 {len(misses)}건:")
        for i, (gid, q, ref) in enumerate(misses[:show_miss]):
            print(f"    {gid:16s} {q:54s} ← {ref}")
    return m


def run_bm25(gold, k=50):
    import pickle
    import bm25 as BM
    idx = pickle.load(open(os.path.join(ROOT, "output", "_rag", "bm25.pkl"), "rb"))
    return {g["id"]: [i for i, _ in BM.search(g["q"], k, idx)] for g in gold}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bm25", action="store_true")
    ap.add_argument("--k", nargs="*", type=int, default=[1, 5, 10, 20])
    ap.add_argument("--miss", type=int, default=8)
    a = ap.parse_args()

    gold, rows = load()
    print(f"gold {len(gold)}건 · 청크 {len(rows):,}")

    if a.bm25:
        report("BM25 단독", gold, run_bm25(gold, max(a.k)), tuple(a.k), a.miss)
    else:
        ap.error("--bm25 를 주세요 (벡터·리랭커는 GPU 가 필요해 Colab 노트북에서 잽니다)")


if __name__ == "__main__":
    main()
