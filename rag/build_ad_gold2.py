# -*- coding: utf-8 -*-
"""정답을 **규칙 하나까지** 조인다. 지금 정답셋은 헐거워서 숫자를 부풀린다.

앞 정답셋(`ad_gold.json`)은 심의사례의 「근거규정」만 썼는데, 그걸 조 단위로만
저장해서 정답으로 인정되는 행이 48~140개가 됐다.

    심의사례      기준 §16① 5 나      제16조 1항 5호 나목
    저장한 것     (은행 광고심의 기준, 제16조)
                 ↑ 「① 5 나」를 버림

제16조 안에 의무가 스무 개라, **「제16조를 근거로 다는 규칙」이면 아무거나 맞은
것으로 셌다.** R-0592(은행 명칭)가 나와도 정답이었다 — 심의사례는 이자율 얘기를
했는데.

수요사 자료를 더 쓰면 조여진다. **통합본 체크리스트가 다리다.**

    심의사례 체크항목  "이자율·수익률의 범위 및 산출기준을 표시하였는가?"
      ↓ 문장이 거의 같다 (일치도 1.00)
    통합본 CL006      같은 문장 · 근거 "은행 광고심의 기준 §16① 5 나"
      ↓ 매칭된_규칙_ID (339문항 전부 채워져 있다)
    규칙 R-0662       ← 정답 하나

**문턱을 0.75 로 둔다.** 이보다 낮으면 다른 문항에 붙을 수 있고, 정답이 틀리면
그 뒤 모든 측정이 조용히 어긋난다. 못 이은 것은 정답셋에서 뺀다 — 억지로 붙이는
것보다 건수가 주는 게 낫다.

  python rag/build_ad_gold2.py
  python rag/build_ad_gold2.py --show
"""
import os
import re
import sys
import json
import difflib
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths as P

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")
XLSX = P.dl(r"NH_광고심의_규칙리스트_조문지도, 체크리스트 통합.xlsx")
OUT = os.path.join(RAG, "ad_gold2.json")
MATCH_MIN = 0.75
NL = chr(10)


def _s(x):
    return str(x if x is not None else "").strip()


def _n(s):
    return re.sub(r"[\s()（）·ㆍ,\.\?？]", "", str(s or ""))


def load_checklist(xlsx=XLSX):
    import warnings
    warnings.filterwarnings("ignore")
    import openpyxl
    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    it = wb["체크리스트"].iter_rows(values_only=True)
    head = [_s(c) for c in next(it)]
    rows = [dict(zip(head, r)) for r in it if r and r[0] is not None]
    wb.close()
    return rows


def link(q, checklist):
    """체크항목 문장 → 통합본 문항. 못 이으면 (None, 점수)."""
    key = _n(q)
    best, sc = None, 0.0
    for c in checklist:
        r = difflib.SequenceMatcher(None, key, _n(c["체크_문구"])).ratio()
        if r > sc:
            best, sc = c, r
    return (best, sc) if sc >= MATCH_MIN else (None, sc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    import build_ad_gold as BG

    checklist = load_checklist()
    prev = json.load(open(os.path.join(RAG, "ad_gold.json"),
                          encoding="utf-8"))["건"]
    rows = [json.loads(l) for l in open(os.path.join(RAG, "rule_index.jsonl"),
                                        encoding="utf-8")]
    by_rule = {r["evidence_id"]: r for r in rows
               if r["evidence_id"].startswith("R-")}

    out, dropped = [], []
    for g in prev:
        cl, sc = link(g["체크항목"], checklist)
        if not cl:
            dropped.append((g, sc))
            continue
        rids = [x.strip() for x in re.split(r"[,\n]", _s(cl["매칭된_규칙_ID"]))
                if x.strip()]
        rids = [r for r in rids if r in by_rule]
        if not rids:
            dropped.append((g, sc))
            continue
        out.append({
            "광고id": g["광고id"],
            "광고명": g["광고명"],
            "판본근거": g["판본근거"],
            "체크항목": g["체크항목"],
            "지적": g["지적"],
            "심의의견": g["심의의견"],
            "근거원문": g["근거원문"],
            # 여기가 조인 것 — 규칙 하나(때로 둘)
            "정답규칙": rids,
            "체크리스트": _s(cl["체크리스트_ID"]),
            "일치도": round(sc, 3),
            "체크리스트근거": _s(cl["근거_법령·규정"]),
            # 참고로 옛 조 단위 정답도 남긴다. 견줄 때 쓴다.
            "정답조문_조단위": g.get("정답"),
        })

    json.dump({"설명": "광고 → 걸린 규칙. 심의사례 체크항목을 통합본 체크리스트로 "
                     "이어 규칙 ID 까지 조였다.",
               "문턱": MATCH_MIN, "건": out},
              open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"앞 정답셋 {len(prev)}건 → 조인 정답셋 {len(out)}건 "
          f"(못 이음 {len(dropped)})")
    n_one = sum(1 for x in out if len(x["정답규칙"]) == 1)
    print(f"  정답 규칙이 1개인 것 {n_one} · 2개 이상 {len(out)-n_one}")

    print("\n정답이 몇 개 행에 걸리나 — 앞과 견줌:")
    def refs(r):
        s = set()
        for b in (r.get("근거") or []):
            s.add((_s(b.get("규정")), re.sub(r"\s", "", _s(b.get("article_no")))))
        return s
    for x in out[:5]:
        want = {(str(t[0]), re.sub(r"\s", "", str(t[1])))
                for t in (x["정답조문_조단위"] or []) if isinstance(t, (list, tuple))}
        old = sum(1 for r in rows if refs(r) & want)
        print(f"  {x['광고id']:16s} 조단위 {old:4d}행 → 규칙 {len(x['정답규칙'])}개 "
              f"{x['정답규칙']}")

    if a.show:
        print("\n== 전체 ==")
        for x in out:
            print(f"  {x['광고id']:16s} {x['체크리스트']} {','.join(x['정답규칙']):10s} "
                  f"({x['일치도']:.2f})  {x['지적'][:34]}")
    if dropped:
        print("\n못 이은 것 (정답셋에서 뺌):")
        for g, sc in dropped:
            print(f"  {sc:.2f}  {g['광고id']:16s} {g['체크항목'][:40]}")

    print(f"\n저장: {a.out}")
    print("\n**앞서 낸 숫자는 이 정답셋으로 다시 재야 한다.** 헐거운 정답으로 잰")
    print("  R@10 85.7% 같은 값은 실제보다 높다.")


if __name__ == "__main__":
    main()
