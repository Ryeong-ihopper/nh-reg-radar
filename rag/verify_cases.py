# -*- coding: utf-8 -*-
"""심의사례 지적을 **판본까지 짚어** 정답표로 만들고, LLM 판정을 채점한다.

어제는 「심의사례는 고치기 전 광고 기준이라 대조 불가」로 접었다. 틀렸다.
판본이 전부 들어 있었고 **어느 판본인지를 안 가려낸 것**이었다.

    위풍당당적금 판본 4개  ·  심의사례 지적 4건  →  1:1 로 붙는다
      004  만기후이율 줄이 없음        ← 「만기후이율 누락」 지적
      005  수신거부가 앱푸시 방법       ← 「무료전화 아님」 지적
      006  기본이율 '26.3.12 vs 예상이자 '26.3.15  ← 「기준일자 불일치」 지적
      007  압류·질권 문구가 없음        ← 「지급제한 사유 누락」 지적

**광고 번호 하나 = 심의 접수 건 하나 = 지적 하나**가 이 자료의 구조다.

이 표가 앞서 쓰던 것보다 나은 이유는 **사람이 독립적으로 만들었다**는 데 있다.
내가 문구를 골라 만든 정답표는 「문구 매칭이 맞나」를 문구 매칭으로 채점하는
셈이라 순환이다. 이건 순환이 아니다.

  python rag/verify_cases.py
  python rag/verify_cases.py --result "C:/Users/babie/Downloads/verify_result.json"
"""
import os
import re
import sys
import json
import argparse
import difflib
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths as P

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")
RESULT = P.dl(r"verify_result.json")

# 심의사례 지적 → 광고 판본. **자동으로 못 정한다** — 지적 문구와 판본 차이를
# 사람이 대조해야 안다. 근거를 같이 적어 둔다. 근거 없이 숫자만 남으면 나중에
# 이 표가 맞는지 아무도 확인할 수 없다.
CASE_AD = {
    # (광고명, 추가설명 앞부분) → (광고id, 판본에서 확인한 근거)
    ("위풍당당적금", "만기후이율"): ("2026_004_예금성", "그 줄이 없음(005·006·007엔 있음)"),
    ("위풍당당적금", "LMS인데"): ("2026_005_예금성", "수신거부가 「올원뱅크>알림설정」 — 무료전화 아님"),
    ("위풍당당적금", "기본이율"): ("2026_006_예금성", "기본이율 '26.3.12 vs 예상이자 '26.3.15"),
    ("위풍당당적금", "이자 지급제한"): ("2026_007_예금성", "압류·질권 문구 없음"),
    ("NH올원모임통장", "연'"): ("2026_003_예금성", "이자율에 「연」 표기 없음"),
    ("ELD", "의무표시사항"): (None, "008·009 중 어느 쪽인지 지적문구로 못 가림"),
}

# 심의사례 「체크항목」과 체크리스트 「질문」은 같은 문장인데 표기가 조금씩 다르다.
# 글자 유사도로 잇되 **문턱을 낮게 두지 않는다** — 엉뚱한 문항에 붙으면 채점이
# 통째로 어긋나고, 그 사실이 겉으로 드러나지 않는다.
MATCH_MIN = 0.72


def _norm(s):
    return re.sub(r"[\s()（）「」『』·ㆍ,\.\?？]", "", str(s or ""))


def link_item(q, items):
    """체크항목 문장 → 체크리스트 문항. 못 이으면 None 을 준다(추측하지 않는다)."""
    key = _norm(q)
    best, score = None, 0.0
    for x in items:
        r = difflib.SequenceMatcher(None, key, _norm(x["질문"])).ratio()
        if r > score:
            best, score = x, r
    return (best, score) if score >= MATCH_MIN else (None, score)


def main():
    import checklist as C

    ap = argparse.ArgumentParser()
    ap.add_argument("--result", default=RESULT, help="코랩 판정 결과 JSON")
    a = ap.parse_args()

    gold = json.load(open(os.path.join(RAG, "verdict_gold.json"), encoding="utf-8"))
    items = C.for_ad(C.load(), "예금")
    got = json.load(open(a.result, encoding="utf-8")) if os.path.exists(a.result) else {}

    rows, unlinked = [], []
    for g in gold["지적"]:
        if g["상품군"] != "예금성":
            continue
        aid = why = None
        for (nm, kw), (ad, reason) in CASE_AD.items():
            if nm in g["광고명"] and kw in g["추가설명"]:
                aid, why = ad, reason
                break
        cl, score = link_item(g["체크항목"], items)
        if cl is None or aid is None:
            unlinked.append((g, cl, score, aid))
            continue
        v = next((x for x in got.get(aid, {}).get("판정", [])
                  if x["id"] == cl["id"]), None)
        rows.append({"광고": aid, "문항": cl["id"], "질문": cl["질문"],
                     "지적": g["추가설명"], "근거": why,
                     "판정": (v or {}).get("판정"), "사유": (v or {}).get("사유", "")})

    print(f"예금성 심의사례 지적 {sum(1 for g in gold['지적'] if g['상품군']=='예금성')}건")
    print(f"  판본·문항 둘 다 확정  {len(rows)}건   ← 채점 대상")
    print(f"  못 이음               {len(unlinked)}건\n")

    hit = sum(1 for r in rows if r["판정"] == "NG")
    for r in rows:
        mark = "○" if r["판정"] == "NG" else "✕"
        print(f"  {mark} {r['광고']} {r['문항']}  기대 NG → 실제 {r['판정']}")
        print(f"      지적  {r['지적'][:56]}")
        print(f"      문항  {r['질문'][:56]}")
        if r["판정"] != "NG":
            print(f"      사유  {str(r['사유'])[:66]}")
    print(f"\n심의사례 지적을 NG 로 잡은 것  {hit}/{len(rows)}"
          f"  ({hit/max(len(rows),1)*100:.0f}%)")

    if unlinked:
        print("\n못 이은 것:")
        for g, cl, score, aid in unlinked:
            why = []
            if aid is None:
                why.append("판본 미확정")
            if cl is None:
                why.append(f"문항 유사도 {score:.2f}")
            print(f"  - {g['광고명'][:16]} / {g['추가설명'][:28]}  ({' · '.join(why)})")

    out = os.path.join(RAG, "case_verify.json")
    json.dump({"채점": rows, "못이음": len(unlinked)},
              open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n저장: {out}")


if __name__ == "__main__":
    main()
