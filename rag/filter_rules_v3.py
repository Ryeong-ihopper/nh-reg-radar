# -*- coding: utf-8 -*-
"""규칙리스트 v3 → 신뢰할 수 있는 규칙·조문만 걸러낸다.

v3 에는 규칙마다 「근거 상세」(어느 법 몇 조인지)와 「인용 조문 원문」(실제로 가져온
조문 본문)이 함께 들어 있다. 그런데 **둘이 어긋나는 경우가 있다.**

  근거 상세    자본시장과 금융투자업에 관한 법률 제117조의9
  인용 조문     제117조(청산) 제95조는 신탁업을 영위하는 …      ← 제117조의9 가 아니다

가지번호(의9)를 놓치고 상위 조문을 가져온 것이다. 이런 걸 그대로 쓰면 **엉뚱한 조문을
근거로 단 규칙**이 된다. 그래서 두 조건을 모두 통과한 것만 쓴다.

  1. 근거 상세가 비어 있지 않을 것
  2. 근거 상세의 조문 번호와 인용 조문 원문의 조문 번호가 **일치**할 것

v3 에 「관련성 판정」 열이 이미 있지만 그대로 믿지 않고 직접 대조한다 — 그 열이 어떤
기준으로 매겨졌는지 우리가 검증한 적이 없기 때문이다. 대신 결과를 그 열과 맞춰 보아
어긋나는 곳을 드러낸다.

  python rag/filter_rules_v3.py
  python rag/filter_rules_v3.py --out output/_rag/rules_v3_verified.json
"""
import os
import re
import sys
import json
import argparse
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XLSX = (r"C:\Users\babie\OneDrive\Desktop\씨지인사이드"
        r"\(참고용) 데이터셋 작업 과정\01_핵심데이터\중요_NH_광고심의_규칙리스트_v3.xlsx")
OUT = os.path.join(ROOT, "output", "_rag", "rules_v3_verified.json")

COL = {"규칙ID": 1, "카테고리": 2, "상품": 3, "매체": 4, "요약": 5, "판단기준": 6,
       "위반시": 7, "우선순위": 8, "원문인용": 9, "출처매뉴얼": 10, "출처페이지": 11,
       "근거종류": 12, "근거상세": 13, "인용조문원문": 18, "fetch출처": 19,
       "유사도": 21, "관련성판정": 22}

# 「제2-38조」·「제117조의9」·「제80조의2」 — 가지번호까지 잡아야 한다.
# 이걸 놓치면 제117조와 제117조의9 를 같은 것으로 보게 된다(v3 의 실제 오류 유형).
_ART = re.compile(r"제\s*(\d+)\s*(?:-\s*(\d+))?\s*조(?:\s*의\s*(\d+))?")
# 「별표 5」·「[별표 0005]」·「별표 제3호의2」
_TBL = re.compile(r"\[?\s*(별표|별지|서식)\s*(?:제)?\s*0*(\d+)(?:\s*(?:호\s*의|[-의])\s*(\d+))?")


def art_key(text, head_only=False):
    """조문 번호 → 비교용 키. head_only 면 문자열 맨 앞의 것만 본다."""
    s = str(text or "")
    m = _ART.match(s.strip()) if head_only else _ART.search(s)
    if m:
        a, b, c = m.groups()
        return f"조{a}" + (f"-{b}" if b else "") + (f"의{c}" if c else "")
    m = _TBL.match(s.strip()) if head_only else _TBL.search(s)
    if m:
        kind, no, sub = m.groups()
        return f"{kind}{int(no)}" + (f"의{sub}" if sub else "")
    return None


def law_name(basis):
    """근거 상세에서 법령명만. 「… 제2-38조」에서 조문 부분을 떼어낸다."""
    s = str(basis or "").strip()
    m = _ART.search(s) or _TBL.search(s)
    return s[:m.start()].strip(" ,·") if m else s


def verify(row):
    """(사용여부, 사유) — 사용자가 정한 두 조건."""
    basis = str(row[COL["근거상세"]] or "").strip()
    body = str(row[COL["인용조문원문"]] or "").strip()

    if not basis:
        return False, "근거상세 없음"
    if not body:
        return False, "인용조문 원문 없음"

    want = art_key(basis)                 # 근거 상세에 적힌 조문 번호
    got = art_key(body, head_only=True)   # 원문 첫머리의 실제 조문 번호
    if want is None:
        return False, "근거상세에서 조문 번호를 못 읽음"
    if got is None:
        return False, "원문 첫머리에서 조문 번호를 못 읽음"
    if want != got:
        return False, f"조문 불일치 ({want} ≠ {got})"
    return True, "일치"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default=XLSX)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--show", type=int, default=10)
    a = ap.parse_args()

    import warnings
    warnings.filterwarnings("ignore")
    import openpyxl

    wb = openpyxl.load_workbook(a.xlsx, read_only=True, data_only=True)
    rows = [r for r in wb["전체_규칙"].iter_rows(min_row=2, values_only=True)
            if r and r[COL["규칙ID"]]]
    wb.close()

    ok, drop = [], []
    reasons = collections.Counter()
    for r in rows:
        used, why = verify(r)
        reasons[why if used else why.split(" (")[0]] += 1
        rec = {k: (str(r[i]).strip() if r[i] is not None else "")
               for k, i in COL.items()}
        rec["_사유"] = why
        rec["_법령명"] = law_name(rec["근거상세"])
        rec["_조문키"] = art_key(rec["근거상세"])
        (ok if used else drop).append(rec)

    print(f"규칙 {len(rows)}건  →  사용 {len(ok)}건 · 제외 {len(drop)}건 "
          f"({len(ok)/len(rows)*100:.0f}%)\n")
    print("== 판정 사유 ==")
    for k, v in reasons.most_common():
        print(f"  {v:>5}  {k}")

    # v3 의 「관련성 판정」 열과 우리 판정을 교차해 본다. 어긋나는 칸이 확인 대상이다.
    print("\n== v3 관련성 판정 × 우리 판정 ==")
    cross = collections.Counter(
        (str(r["관련성판정"] or "(비어있음)"), "사용") for r in ok)
    cross.update((str(r["관련성판정"] or "(비어있음)"), "제외") for r in drop)
    keys = sorted({k for k, _ in cross})
    print(f"  {'v3 판정':14s} {'사용':>6s} {'제외':>6s}")
    for k in keys:
        print(f"  {k:14s} {cross[(k,'사용')]:>6} {cross[(k,'제외')]:>6}")

    print("\n== 사용 규칙의 근거 법령 (상위) ==")
    for k, v in collections.Counter(r["_법령명"] for r in ok).most_common(15):
        print(f"  {v:>4}  {k}")

    if a.show and drop:
        print(f"\n== 제외된 것 표본 ==")
        for r in [x for x in drop if "불일치" in x["_사유"]][:a.show]:
            print(f"  {r['규칙ID']}  {r['_사유']}")
            print(f"      근거: {r['근거상세'][:56]}")
            print(f"      원문: {r['인용조문원문'][:56]}")

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"사용": ok, "제외": drop}, f, ensure_ascii=False, indent=1)
    print(f"\n저장: {a.out}")


if __name__ == "__main__":
    main()
