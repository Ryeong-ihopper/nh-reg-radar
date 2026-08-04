# -*- coding: utf-8 -*-
"""광고 원문 → 조각(청크). 검색 방식 (D) 용.

규정을 조문 단위로 쪼갠 것과 같은 이유다 — 광고 하나에 쟁점이 열 개씩 들어 있는데
통째로 벡터 하나에 넣으면 전부 뭉개진다. 「연 최고 7.0%」와 「예금자보호법에 따라
1억원까지 보호」가 한 벡터 안에서 평균 내지면 둘 다 흐려진다.

**LLM 이 필요 없다는 점이 (B) 와 다르다.** 광고에는 이미 사람이 넣은 구조 표시가
있다(□ 항목, ※ 유의사항, ▶ 안내, ◾ 항목, 표의 행). 그 경계로 자르면 쟁점 하나가
조각 하나에 대체로 대응한다. (B) 는 광고를 법령체로 바꿔 쓰는 것이고 (D) 는 광고
자신의 말로 두는 것이라, 어휘 격차가 남는 대신 원문 정보가 손실되지 않는다.

  python rag/ad_chunker.py
  python rag/ad_chunker.py --min 25 --max 600
"""
import os
import re
import sys
import json
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_IN = os.path.join(ROOT, "output", "_rag", "ads.jsonl")
DEFAULT_OUT = os.path.join(ROOT, "output", "_rag", "ad_chunks.jsonl")

# 새 조각이 시작되는 표시. 광고마다 쓰는 기호가 다르다(LMS 는 □※*, 안내장은 ◾▶).
_HEAD = re.compile(r"^\s*(?:[□■▶◾◆●○*※&#8251;]|\d+\.\s|[①-⑮]|[-–]\s)")
# 표에서 온 줄은 '항목명'만 있는 짧은 줄이 앞에 오고 값이 뒤따른다(대출대상 / 공무원…).
_LABEL = re.compile(r"^[가-힣A-Za-z][가-힣A-Za-z\s및·]{1,14}$")


def split(text, min_len, max_len):
    """구조 표시를 경계로 조각낸다. 너무 짧으면 앞 조각에 붙이고, 너무 길면 문장에서 다시 자른다."""
    parts, cur = [], []
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            continue
        # 표 항목명(짧은 라벨)도 새 조각의 시작으로 본다 — 뒤에 값이 붙는 구조라
        # 라벨을 값과 같은 조각에 두어야 「대출금리: 최저 연 4.45%」가 온전해진다.
        if (_HEAD.match(s) or _LABEL.match(s)) and cur:
            parts.append("\n".join(cur))
            cur = [s]
        else:
            cur.append(s)
    if cur:
        parts.append("\n".join(cur))

    # 짧은 조각 병합 — 「가입기간」처럼 라벨만 남은 것을 혼자 두면 검색에 쓸모가 없다
    merged = []
    for p in parts:
        if merged and len(p) < min_len:
            merged[-1] += "\n" + p
        else:
            merged.append(p)

    # 긴 조각 재분할 — 문장 끝에서 자른다(마침표/※ 경계)
    out = []
    for p in merged:
        while len(p) > max_len:
            cut = max(p.rfind(". ", 0, max_len), p.rfind("※", 1, max_len),
                      p.rfind("\n", 0, max_len))
            if cut < min_len:
                cut = max_len
            out.append(p[:cut].strip())
            p = p[cut:].strip()
        if p:
            out.append(p)
    return [x for x in out if len(x) >= 10]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=DEFAULT_IN)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--min", type=int, default=25)
    ap.add_argument("--max", type=int, default=600)
    a = ap.parse_args()

    ads = [json.loads(l) for l in open(a.src, encoding="utf-8")]
    seen, rows = set(), []
    for r in ads:
        k = (r["광고id"], r["text"][:200])
        if k in seen:
            continue
        seen.add(k)
        cs = split(r["text"], a.min, a.max)
        for i, c in enumerate(cs, 1):
            # 조각에도 머리글을 붙인다 — 규정 청킹과 같은 이유. 조각만 떼어 놓으면
            # 어느 상품 광고인지 사라져 검색이 엉뚱한 상품군으로 샌다.
            head = f"[{r['상품군']} 광고] "
            rows.append({"광고id": r["광고id"], "상품군": r["상품군"],
                         "part": i, "parts": len(cs), "chars": len(c),
                         "text": head + c})
        print(f"  {r['광고id']:20s} {r['chars']:>6,}자 → 조각 {len(cs):>2}개 "
              f"(중앙 {sorted(len(x) for x in cs)[len(cs)//2]:>3}자)")

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        for x in rows:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")

    c = sorted(x["chars"] for x in rows)
    print(f"\n광고 {len(seen)}건 → 조각 {len(rows)}개")
    print(f"조각 길이: 중앙 {c[len(c)//2]}자 · 최소 {c[0]} · 최대 {c[-1]}")
    print(f"저장: {a.out}")


if __name__ == "__main__":
    main()
