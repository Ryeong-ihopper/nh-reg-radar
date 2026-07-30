# -*- coding: utf-8 -*-
"""
청크 경계를 정하기 전에 **실제 길이 분포**를 본다.

조문 하나를 통째로 한 청크로 두면 긴 조문(별표 포함 수천 자)이 임베딩 한도를
넘고, 항(①②③) 단위로 쪼개면 조문 제목이라는 맥락이 날아간다. 어느 쪽이
문제인지는 데이터를 봐야 안다.

토큰 수는 재지 않고 **글자 수**로 본다. 온프렘에 올릴 임베딩 모델이 아직
정해지지 않아 토크나이저가 없기 때문이다. 한국어는 모델에 따라 1토큰이
1.2~2.0자 사이라, 아래 표에 환산 구간을 같이 적는다.

  python rag/chunk_stats.py            # 전체
  python rag/chunk_stats.py 은행         # 이름에 '은행'이 든 대상만
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sections

# 임베딩 모델 입력 한도(토큰)를 글자로 환산할 때 쓰는 배수.
# 보수적으로 1토큰=1.3자(짧게 잡음)와 넉넉하게 1토큰=1.8자 두 경우를 함께 본다.
CHARS_PER_TOKEN = (1.3, 1.8)
LIMITS = (512, 1024, 2048, 8192)


def pct(vals, p):
    if not vals:
        return 0
    i = int(round((len(vals) - 1) * p / 100))
    return sorted(vals)[i]


def describe(label, vals):
    if not vals:
        print(f"{label:10s} 없음")
        return
    v = sorted(vals)
    print(f"{label:10s} {len(v):>6,}개 │ 중앙 {pct(v,50):>6,} │ p75 {pct(v,75):>6,} │ "
          f"p90 {pct(v,90):>6,} │ p95 {pct(v,95):>6,} │ p99 {pct(v,99):>7,} │ "
          f"최대 {v[-1]:>7,} │ 합계 {sum(v):>9,}자")


def histogram(vals, buckets=(200, 500, 1000, 2000, 4000, 8000, 16000)):
    edges = list(buckets) + [float("inf")]
    lo = 0
    total = len(vals)
    for e in edges:
        n = sum(1 for x in vals if lo <= x < e)
        bar = "█" * max(0, round(n / total * 60)) if total else ""
        hi = "이상" if e == float("inf") else f"{e:,}"
        print(f"  {lo:>6,} ~ {hi:>7} {n:>6,} ({n/total*100:5.1f}%) {bar}")
        lo = e


def main(only=None):
    secs = sections.all_sections(only)
    if not secs:
        print("항목이 없습니다.")
        return
    lens = {t: [] for t in ("조문", "부칙", "별표")}
    for s in secs:
        lens.setdefault(s["type"], []).append(len(s["text"]))
    allv = [len(s["text"]) for s in secs]

    print("=" * 100)
    print(f"청크 후보 길이 분포 — 대상 {len(set(s['reg'] for s in secs))}건 · 항목 {len(secs):,}개")
    print("=" * 100)
    for t in ("조문", "부칙", "별표"):
        describe(t, lens.get(t, []))
    describe("전체", allv)

    print("\n[전체 길이 히스토그램]")
    histogram(allv)

    print("\n[임베딩 입력 한도를 넘는 항목]")
    print(f"  {'한도':>6} │ {'1토큰=1.3자':>18} │ {'1토큰=1.8자':>18}")
    for lim in LIMITS:
        row = []
        for cpt in CHARS_PER_TOKEN:
            cap = lim * cpt
            n = sum(1 for x in allv if x > cap)
            row.append(f"{cap:>6,.0f}자 초과 {n:>5,}개 ({n/len(allv)*100:4.1f}%)")
        print(f"  {lim:>6} │ {row[0]:>18} │ {row[1]:>18}")

    print("\n[가장 긴 항목 15개]")
    for s in sorted(secs, key=lambda x: -len(x["text"]))[:15]:
        print(f"  {len(s['text']):>7,}자  {s['type']}  {s['key']:<14} "
              f"{(s['title'] or '')[:26]:<26} {s['reg'][:32]}")

    print("\n[유형별 최장 항목]")
    for t in ("조문", "부칙", "별표"):
        pool = [s for s in secs if s["type"] == t]
        if not pool:
            continue
        s = max(pool, key=lambda x: len(x["text"]))
        print(f"  {t}  {len(s['text']):>7,}자  {s['key']} {(s['title'] or '')[:30]} — {s['reg']}")

    # 조문을 항 단위로 쪼갰다면 어땠을지: 줄 단위 길이로 근사한다
    print("\n[참고 — 긴 조문을 더 쪼갤 여지]")
    long_arts = [s for s in secs if s["type"] == "조문" and len(s["text"]) > 2000]
    if long_arts:
        subs = []
        for s in long_arts:
            subs.extend(len(l) for l in s["text"].split("\n") if l.strip())
        print(f"  2,000자 넘는 조문 {len(long_arts)}개를 줄(항/호/목) 단위로 보면 "
              f"{len(subs):,}조각 · 중앙 {pct(subs,50):,}자 · p95 {pct(subs,95):,}자")
    else:
        print("  2,000자 넘는 조문 없음")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1] if sys.argv[1:] else None)
