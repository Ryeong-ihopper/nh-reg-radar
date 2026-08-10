# -*- coding: utf-8 -*-
"""**광고문 → 걸리는 조문** 정답표. 지금까지 쓰던 gold 와 재는 것이 다르다.

    gold.json      질문 "은행의 명칭을 표시하였는가?"  →  §16조
                   ↑ 입력이 질문이다. 체크리스트를 그대로 옮긴 것

    ad_gold.json   광고문 「NC 다이노스 위풍당당적금 …」  →  §16① 5 나
                   ↑ 입력이 광고다. **심의팀이 실제로 하는 일과 같은 모양**

앞의 것은 8월 3일에 만들었다. 그때는 광고에 무엇이 걸리는지 아는 자료가 없어
체크리스트의 「질문↔근거조문」 짝을 그대로 쓴 것이다. 심의사례를 판본까지 짚어
읽고 나서야 **광고 기준 정답**이 생겼다.

정답은 심의사례의 「근거규정」 칸이다.

    광고 2026_004_예금성  ←  위풍당당적금 「만기후이율 누락」
    근거규정 「기준 §16① 5 나」  →  은행 광고심의 기준 및 세칙 제16조

**정답이 광고마다 1건뿐이라 적다.** 심의사례는 걸린 것만 적지, 안 걸린 조문을
적지 않기 때문이다. 그래서 이 표로는 **회수(정답을 후보에 넣었나)만** 잴 수 있고
정밀도는 못 잰다 — 정답에 없는 조문이 나왔다고 틀린 게 아니다.

  python rag/build_ad_gold.py
  python rag/build_ad_gold.py --measure        # 검색이 정답 조문을 회수하나
"""
import os
import re
import sys
import json
import argparse
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")
OUT = os.path.join(RAG, "ad_gold.json")

# 심의사례 지적 → 광고 판본. 판본 차이를 사람이 대조해 정했다(근거를 같이 적는다).
# rag/verify_cases.py 와 같은 표이므로 한쪽만 고치면 어긋난다 — 언젠가 한곳으로
# 모아야 한다.
CASE_AD = {
    ("위풍당당적금", "만기후이율"): ("2026_004_예금성", "그 줄이 없음"),
    ("위풍당당적금", "LMS인데"): ("2026_005_예금성", "수신거부가 앱푸시 — 무료전화 아님"),
    ("위풍당당적금", "기본이율"): ("2026_006_예금성", "기준일자 '26.3.12 vs '26.3.15"),
    ("위풍당당적금", "이자 지급제한"): ("2026_007_예금성", "압류·질권 문구 없음"),
    ("NH올원모임통장", "연'"): ("2026_003_예금성", "이자율에 「연」 표기 없음"),
    ("신나는직장인대출", "중도상환해약금"): ("2026_001_대출성", "중도상환해약금 문구 없음"),
    ("공무원을 위한 신용대출", "유의사항"): ("2026_002_대출성", "서식 — 텍스트로는 확인 불가"),
    ("공무원을 위한 신용대출", "대출금리 기준일자"): ("2026_003_대출성", "대출금리 06.18 vs 우대금리 06.10"),
    ("공무원을 위한 신용대출", "산출기준"): ("2026_004_대출성", "기준금리 3.15%→3.10%"),
    ("공무원을 위한 신용대출", "후취"): ("2026_005_대출성", "「후취」가 빠짐"),
    ("부산시 소상공인", "보증재단"): ("2026_006_대출성", "보증한도 문구 없음"),
    ("전세대출", "하나의 보증서"): ("2026_007_대출성", "008~010 에 있는 ※ 문구 없음"),
    ("전세대출", "채권양도"): ("2026_008_대출성", "「채권양도」 낱말 없음"),
    ("전세대출", "보증료율"): ("2026_009_대출성", "「보증료 : 개인별 상이」"),
    ("전세대출", "우대조건별"): ("2026_010_대출성", "카드실적 0.30%p→0.10%p"),
}


def main():
    import build_gold as BG

    ap = argparse.ArgumentParser()
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    gold = json.load(open(os.path.join(RAG, "verdict_gold.json"), encoding="utf-8"))
    chunks, by = BG.load_chunks()
    ads = {}
    for l in open(os.path.join(RAG, "ads.jsonl"), encoding="utf-8"):
        x = json.loads(l)
        ads.setdefault(x["광고id"], x)

    rows, miss = [], []
    for g in gold["지적"]:
        aid = why = None
        for (nm, kw), (ad, reason) in CASE_AD.items():
            if nm in g["광고명"] and kw in (g["추가설명"] + g["체크항목"]):
                aid, why = ad, reason
                break
        if not aid:
            miss.append(g)
            continue
        # 근거규정 문자열 → (규정, 조) 목록 → 청크 번호. build_gold 의 파서를 쓴다.
        refs = BG.parse_ref(g["근거규정"])
        ans, unresolved = [], []
        for reg, key in refs:
            hit = BG.resolve(by, reg, key) if not reg.startswith("?") else []
            (ans.extend(hit) if hit else unresolved.append(f"{reg} {key}".strip()))
        ans = sorted(set(ans))
        rows.append({
            "광고id": aid, "광고명": g["광고명"], "판본근거": why,
            "체크항목": g["체크항목"], "근거원문": g["근거규정"],
            "심의의견": g["심의의견"], "지적": g["추가설명"],
            "정답": refs, "정답청크": ans, "못이은근거": unresolved,
        })

    json.dump({"설명": "광고문 → 걸리는 조문. 심의사례 기반.", "건": rows},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"심의사례 지적 {len(gold['지적'])}건 → 광고 판본 확정 {len(rows)}건")
    ok = sum(1 for r in rows if r["정답청크"])
    print(f"  근거 조문까지 이은 것 {ok}건 · 못 이은 것 {len(rows)-ok}건")
    print(f"  광고 판본을 못 정한 것 {len(miss)}건\n")

    by = collections.Counter(r["광고id"].split("_")[-1] for r in rows)
    print("상품군별:", dict(by))
    for r in rows:
        print(f"  {r['광고id']:18s} {r['근거원문'][:22]:22s} "
              f"청크{len(r['정답청크'])}  {r['지적'][:34]}")
    if miss:
        print("\n판본 못 정함:")
        for g in miss:
            print(f"  - {g['광고명'][:18]} / {g['추가설명'][:34]}")
    print(f"\n저장: {a.out}")


if __name__ == "__main__":
    main()
