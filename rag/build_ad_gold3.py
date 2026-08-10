# -*- coding: utf-8 -*-
"""정답을 **지적내용**으로 찾는다. 앞서는 체크항목으로 찾아 틀린 규칙을 넣었다.

심의사례 한 줄에 두 가지가 적혀 있고, 뜻이 다르다.

    체크항목   "이자율·수익률의 범위 및 산출기준을 표시하였는가?"
               → 담당자가 **어느 항목을 보다가** 발견했나
    지적내용   "만기후이율 및 중도해지이율 누락"
               → **무엇이 없었나**

앞 정답셋(`ad_gold2.json`)은 체크항목으로 이어 R-0662 를 정답에 넣었다. 그런데
R-0662 는 「이자율 범위가 표시됐나」라, 광고에 기본이율·우대이율이 있으니 OK 다.
**우리 시스템이 잡아야 할 것은 「만기후이율이 없다」이고 그건 R-0610 이다.**

    R-0662  M04 63쪽 체크리스트 표에서 나옴   "이자율·수익률 범위 산출기준 표시"
    R-0610  M04 27쪽 본문에서 나옴          "기간별·중도해지·만기후 이율 표기"

담당자는 63쪽 표를 보며 심의하다가 본문 지식으로 세부를 잡아낸 것이다. 표에는
큰 항목만 있다(전체 규칙 1,744 중 체크리스트가 가리키는 것은 231개뿐).

**낱말 겹침으로 잇는다.** 지적내용은 짧고 부정형이라 문장 유사도가 잘 안 나온다.
「만기후이율」·「중도해지」 같은 **드문 낱말**이 겹치는지를 본다.

**자동으로 하나를 고르되 후보를 함께 남긴다.** 사람이 확인해야 하고, 확인 없이
쓰면 앞과 같은 실수를 되풀이한다.

  python rag/build_ad_gold3.py
  python rag/build_ad_gold3.py --top 5      # 후보를 5개씩 보여준다
"""
import os
import re
import sys
import json
import math
import argparse
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")
OUT = os.path.join(RAG, "ad_gold3.json")
NL = chr(10)

PG = {"예금성": "DEPOSIT", "대출성": "LOAN", "투자성": "INVESTMENT"}
# 흔해서 변별력이 없는 말. 이것들이 겹쳐도 같은 규칙이라는 근거가 못 된다.
STOP = {"누락", "표시", "기재", "확인", "광고", "표기", "사항", "경우", "관련",
        "내용", "여부", "대상", "미제공", "불일치", "상이", "오류", "않음"}


def toks(s):
    """낱말이 아니라 **글자 두 개씩**(바이그램) 본다.

    「만기후이율」(붙여 씀)과 「만기 후 이율」(띄어 씀)이 낱말로는 안 겹친다.
    실제로 그래서 2026_004 가 후보 0개였다. 띄어쓰기를 지우고 두 글자씩 자르면
    「만기·기후·후이·이율」이 겹친다.

    흔한 말(누락·표시·확인…)은 바이그램으로 쪼개도 흔하니 IDF 가 알아서 낮춘다.
    """
    t = re.sub(r"[^가-힣A-Za-z0-9]", "", str(s or ""))
    if len(t) < 2:
        return []
    return [t[i:i+2] for i in range(len(t)-1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    rows = [json.loads(l) for l in open(os.path.join(RAG, "rule_index.jsonl"),
                                        encoding="utf-8")]
    rules = [r for r in rows if r["evidence_id"].startswith("R-")]
    prev = json.load(open(os.path.join(RAG, "ad_gold.json"),
                          encoding="utf-8"))["건"]

    # 낱말별 문서 빈도 → 드문 낱말에 무게를 준다. 「만기후이율」이 겹치는 것과
    # 「이자율」이 겹치는 것은 값어치가 다르다.
    df = collections.Counter()
    docs = []
    for r in rules:
        t = set(toks(r.get("title")) + toks((r.get("metadata_json") or {})
                                            .get("판단기준")))
        docs.append(t)
        df.update(t)
    n = len(rules)
    idf = {w: math.log(1 + n / (c + 1)) for w, c in df.items()}

    out, weak = [], []
    for g in prev:
        pg = PG.get("예금성" if "예금성" in g["광고id"] else "대출성")
        q = set(toks(g["지적"]))
        cand = []
        for i, r in enumerate(rules):
            p = r.get("product_group") or []
            if p and pg not in p:
                continue
            hit = q & docs[i]
            if not hit:
                continue
            # 겹친 낱말의 희소도 합. 질의 낱말 수로 나눠 길이 영향을 뺀다.
            sc = sum(idf.get(w, 0) for w in hit) / max(len(q), 1)
            cand.append((sc, r["evidence_id"], r.get("title", ""), sorted(hit)))
        cand.sort(reverse=True)
        best = cand[0] if cand else None
        row = {
            "광고id": g["광고id"], "광고명": g["광고명"],
            "판본근거": g["판본근거"], "체크항목": g["체크항목"],
            "지적": g["지적"], "심의의견": g["심의의견"],
            "근거원문": g["근거원문"],
            "정답규칙": [best[1]] if best else [],
            "정답규칙_제목": best[2] if best else None,
            "점수": round(best[0], 3) if best else 0.0,
            "겹친낱말": best[3] if best else [],
            "후보": [{"규칙": c[1], "제목": c[2], "점수": round(c[0], 3),
                    "겹친낱말": c[3]} for c in cand[:a.top]],
        }
        out.append(row)
        if not best or best[0] < 0.5:
            weak.append(row)

    json.dump({"설명": "광고 → 걸린 규칙. **지적내용**으로 규칙을 찾았다.",
               "주의": "자동으로 고른 것이다. 사람이 확인해야 한다.",
               "건": out},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"심의사례 {len(prev)}건 → 규칙 연결 {sum(1 for x in out if x['정답규칙'])}건")
    print(f"  점수가 낮아 사람 확인이 꼭 필요한 것 {len(weak)}건\n")
    for x in out:
        mark = " " if x["점수"] >= 0.5 else "?"
        print(f"{mark} {x['광고id']:16s} {x['지적'][:30]:30s}")
        for c in x["후보"]:
            star = "★" if c["규칙"] == (x["정답규칙"] or [None])[0] else " "
            print(f"     {star} {c['규칙']} {c['점수']:5.2f} {c['제목'][:40]:42s} "
                  f"{','.join(c['겹친낱말'][:3])}")
    print(f"\n저장: {a.out}")
    print("\n**★ 가 맞는지 봐 주셔야 합니다.** 앞서 체크항목으로 이었을 때는")
    print("  R-0662(이자율 범위)가 정답이 됐는데, 지적은 만기후이율이었습니다.")


if __name__ == "__main__":
    main()
