# -*- coding: utf-8 -*-
"""심의사례 20건 → **판정 정답표**.

지금까지 쓰던 gold 334건은 「질문 → 근거 조문」을 재는 것이었다. 그런데 심의팀이
하는 일은 조문 찾기가 아니라 **광고를 보고 무엇이 걸리는지 말하는 것**이다.
재는 대상이 처음부터 어긋나 있었다.

준법감시부 심의사례에는 진짜 답이 들어 있다.

    광고명            NH올원TEEN통장
    체크리스트 항목    이자율·수익률의 범위 및 산출기준을 표시하였는가?
    근거규정          기준 §16① 5 나
    심의의견          의무표시사항 누락
    추가 설명         '세전' 누락

**이것이 우리 파이프라인이 내야 할 출력 그 자체다.** 광고를 넣으면 「이 항목에
걸렸고, 근거는 이것이고, 사유는 이것」이 나와야 한다.

광고 원문은 이 엑셀에 없고 별도 파일(ads.jsonl)에 있다. **광고명으로 잇는다** —
심의사례의 「NH올원모임통장」이 우리가 파싱한 광고 본문 안에 그대로 나온다.

  python rag/build_verdict_gold.py
  python rag/build_verdict_gold.py --show 5
"""
import os
import re
import json
import argparse
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")
XLSX = r"C:\Users\babie\OneDrive\Desktop\씨지인사이드\심의사례 NH농협은행 준법감시부 1.xlsx"
ADS = os.path.join(RAG, "ads.jsonl")
OUT = os.path.join(RAG, "verdict_gold.json")

SHEETS = (("예금성 광고", "예금성"), ("대출성 광고", "대출성"))

COL = {"번호": 0, "광고명": 1, "매체": 2, "사전사후": 4, "사유": 5,
       "체크항목": 6, "근거규정": 7, "심의의견": 8, "추가설명": 9, "수정전": 10}


def _norm(s):
    """이름 대조용. 띄어쓰기·괄호를 지운다 — 엑셀과 광고 본문의 표기가 조금씩 다르다."""
    return re.sub(r"[\s()（）「」『』·ㆍ,\.]", "", str(s or ""))


def load_cases(xlsx=XLSX):
    import warnings
    warnings.filterwarnings("ignore")
    import openpyxl

    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    out = []
    for sheet, ptype in SHEETS:
        for r in wb[sheet].iter_rows(min_row=4, values_only=True):
            if not r or not r[0] or not str(r[0]).strip().isdigit():
                continue
            g = {k: str(r[i]).strip() if i < len(r) and r[i] is not None else ""
                 for k, i in COL.items()}
            g["상품군"] = ptype
            out.append(g)
    wb.close()
    return out


def link_ads(cases, ads):
    """광고명 → 광고 파일. 본문에 이름이 들어 있으면 그 광고로 본다.

    **여러 건이 걸리면 전부 후보로 남긴다.** 「공무원을 위한 신용대출」은 광고
    4건에 나오는데, 어느 판본인지는 사람이 봐야 안다. 하나를 임의로 고르면
    틀린 정답표가 되고 그 뒤 모든 측정이 조용히 어긋난다.
    """
    for g in cases:
        key = _norm(g["광고명"])
        hits = [a["광고id"] for a in ads if key and key in _norm(a["text"])]
        # 같은 광고id 의 원본/수정본이 둘 다 걸리므로 중복 제거
        g["광고후보"] = sorted(set(hits))
    return cases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default=XLSX)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--show", type=int, default=0)
    a = ap.parse_args()

    cases = load_cases(a.xlsx)
    ads = [json.loads(l) for l in open(ADS, encoding="utf-8")]
    cases = link_ads(cases, ads)

    # 광고별로 묶는다 — 한 광고에 지적이 여럿일 수 있다
    by_ad = collections.defaultdict(list)
    for g in cases:
        for aid in (g["광고후보"] or ["(연결 안 됨)"]):
            by_ad[aid].append(g)

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    json.dump({"지적": cases, "광고별": {k: v for k, v in by_ad.items()}},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    linked = sum(1 for g in cases if g["광고후보"])
    print(f"심의사례 지적 {len(cases)}건 · 광고 연결 {linked}건 "
          f"({linked/len(cases)*100:.0f}%)\n")

    print("지적 유형:")
    for k, v in collections.Counter(g["심의의견"] for g in cases).most_common():
        print(f"  {v:>3}  {k}")

    print("\n연결 상태:")
    for k, v in sorted(by_ad.items()):
        multi = " ← 후보 여럿(사람 확인)" if any(len(g["광고후보"]) > 1 for g in v) else ""
        print(f"  {k:22s} 지적 {len(v)}건{multi}")

    if a.show:
        print(f"\n== 표본 ==")
        for g in cases[:a.show]:
            print(f"  [{g['상품군']}] {g['광고명']}  →  {g['광고후보'] or '연결 안 됨'}")
            print(f"      항목  {g['체크항목'][:56]}")
            print(f"      근거  {g['근거규정']}")
            print(f"      판정  {g['심의의견']} — {g['추가설명'][:40]}")

    print(f"\n저장: {a.out}")
    print("\n**이 표가 재는 것** — 광고를 넣었을 때 파이프라인이 이 체크항목을")
    print("지적으로 올리는가. 조문을 몇 등으로 찾는가가 아니다.")


if __name__ == "__main__":
    main()
