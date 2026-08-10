# -*- coding: utf-8 -*-
"""규칙리스트 전체 → 판정 규칙(checks). **7개가 아니라 전부.**

앞서 만든 검출기 7개는 목데이터 라벨 7종에 맞춘 것이었다. 목데이터를 잘 맞히려고
만든 셈이라 실물에서 무너졌고, 실물 심의사례 지적 15건은 하나도 못 잡았다.
엑셀에 규칙이 1,744건 있는데 7개만 쓸 이유가 없다.

여기서 규칙 하나하나를 판정 가능한 모양으로 바꾼다. 바꿀 수 있는 것과 없는 것을
**가른 채로** 둔다 — 못 바꾸는 것을 억지로 넘기면 근거 없는 지적이 쏟아진다.

    카테고리      판정 종류        어떻게 보나
    표시의무  →  PRESENCE      요구 문구가 광고에 있는가 (없으면 누락)
    금지     →  PROHIBIT      금지 표현이 광고에 있는가
    양식     →  STYLE/FORMAT  글자 크기·표시 모양
    절차     →  PROCESS       광고문으로는 판정 불가 (사전심의 신청 등) — 뺀다

    문구 얻는 법
      QUOTED   판단기준의 따옴표 안 문구. 자리표시자(X.XX)가 있으면 못 쓴다
      DICT     rule_patterns.json 에 사람이 적어 둔 것
      NONE     문구가 없다 → LLM 이 규칙 문장을 그대로 받아 좁게 판정

**LLM 에게 넘기는 물음이 전과 다르다.** 앞서 0/5 가 나온 것은 체크리스트 87문항을
던졌기 때문이다. 「이자율·수익률의 범위 및 산출기준을 표시하였는가?」는 너무 넓어
광고에 금리 얘기만 있으면 OK 가 나왔다. 규칙은 훨씬 좁다 —
「기간별 이율·중도해지 이율·만기 후 이율이 각각 표기되어 있는지 확인」.

개선안도 규칙마다 만든다. 지금까지 7개짜리 고정 문자열이던 것을 **요약에서
문장을 만들어** 402건 전부에 붙인다. 자리는 `compliance.recommendation` 이다.

  python rag/build_checks.py --product 예금
  python rag/build_checks.py --product 대출 --out output/_rag/checks_대출.json
"""
import os
import re
import sys
import json
import argparse
import collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import paths as P

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")
XLSX = P.dl(r"NH_광고심의_규칙리스트_조문지도, 체크리스트 통합.xlsx")

KIND = {"표시의무": "PRESENCE", "금지": "PROHIBIT",
        "양식": "STYLE", "절차": "PROCESS"}

_QUOTE = re.compile(r"[\"“”「『]([^\"“”「」『』]{2,40})[\"“”」』]")
# 따옴표 안이 문구가 아니라 **예시**인 경우. 그대로 찾으면 모든 광고가 NG 가 된다.
_PLACEHOLDER = re.compile(r"[XxOo○×]{2,}|[XxOo]\.[XxOo]|\d-[Xx]{3,}")
# 따옴표 안이 문서 이름인 경우 — 찾을 말이 아니다
_DOCNAME = re.compile(r"(지침|규정|기준|법률|매뉴얼|법)$")

# 조건부 규칙 — 「…하는 경우」로 시작하면 그 조건이 맞는 광고에만 적용한다.
_COND = re.compile(r"^([^,]{2,60}?)\s*(?:하는|인|되는)?\s*경우[,\s]")


def _s(x):
    return str(x if x is not None else "").strip()


def _words(p):
    return [w for w in re.split(r"[^가-힣A-Za-z0-9]+", str(p)) if len(w) >= 2]


def load_rules(xlsx=XLSX):
    import warnings
    warnings.filterwarnings("ignore")
    import openpyxl

    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
    it = wb["규칙"].iter_rows(values_only=True)
    head = [_s(c) for c in next(it)]
    rules = [dict(zip(head, r)) for r in it if r and r[0] is not None]
    wb.close()
    return rules


def make_pattern(rule, dict_patterns):
    """(패턴, 출처, 모드). 못 만들면 (None, "NONE", None)."""
    rid = _s(rule.get("규칙ID"))
    d = dict_patterns.get(rid)
    if d:
        return (d["values"][0] if d["type"] == "REGEX" else d["values"],
                "DICT", d.get("mode", "ALL"))
    body = _s(rule.get("판단 기준")) + " " + _s(rule.get("요약"))
    q = [x.strip() for x in _QUOTE.findall(body)]
    q = [x for x in q if len(re.sub(r"\s", "", x)) >= 2]
    if any(_PLACEHOLDER.search(x) for x in q):
        return None, "PLACEHOLDER", None      # 정규식을 사람이 붙여야 한다
    q = [x for x in q if not _DOCNAME.search(x)]
    if q:
        return q, "QUOTED", "ALL"
    return None, "NONE", None


def condition_of(rule):
    m = _COND.match(_s(rule.get("판단 기준")))
    return [w for w in _words(m.group(1))][:4] if m else []


def recommendation(rule):
    """개선안. **규칙 요약에서 만든다** — 402 건에 사람이 다 적을 수 없다.

    좋은 문장은 못 되지만 빈칸보다 낫고, 담당자가 고칠 자리가 생긴다.
    자리는 `compliance.recommendation` 이고 여기 값은 그 초안이다.
    """
    summary = _s(rule.get("요약"))
    cat = _s(rule.get("카테고리"))
    if not summary:
        return None
    body = re.sub(r"^(예금|대출|투자|공통)\s*(광고)?\s*[-–]?\s*", "", summary).strip()
    if cat == "금지":
        return f"「{body}」에 해당하는 표현을 지우거나 객관적 근거를 함께 표시하세요."
    if cat == "양식":
        return f"「{body}」 형식 요건을 맞추세요."
    return f"「{body}」를 광고에 표시하세요."


def build(rules, product, dict_patterns, scope):
    want = {product, "전체"}
    out = []
    for r in rules:
        rid = _s(r.get("규칙ID"))
        if not ({x.strip() for x in _s(r.get("상품")).split(",")} & want):
            continue
        if rid in scope:                     # 제외 예정
            continue
        kind = KIND.get(_s(r.get("카테고리")))
        if kind == "PROCESS":
            continue                          # 광고문으로 판정할 수 없다
        pat, src, mode = make_pattern(r, dict_patterns)
        out.append({
            "id": rid,
            "kind": kind if pat else "LLM",
            "pattern_source": src,
            "product_group": None if "전체" in _s(r.get("상품")) else f"{product}성",
            "title": _s(r.get("요약")),
            "criterion": _s(r.get("판단 기준")),      # LLM 에 그대로 넘길 문장
            "params": ({"pattern": pat, "mode": mode} if pat else {}),
            "condition": condition_of(r),
            "article_no": _s(r.get("근거 상세")) or None,
            "verdict_code": rid,
            "reason": _s(r.get("요약")),
            "recommendation": recommendation(r),
            "importance": _s(r.get("우선순위")),
            "violation_action": _s(r.get("위반 시")),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", default="예금")
    ap.add_argument("--xlsx", default=XLSX)
    ap.add_argument("--out")
    a = ap.parse_args()

    rules = load_rules(a.xlsx)
    dp = json.load(open(os.path.join(RAG, "rule_patterns.json"),
                        encoding="utf-8"))["규칙"]
    sp = json.load(open(os.path.join(RAG, "scope_excluded.json"),
                        encoding="utf-8"))["규칙"]
    checks = build(rules, a.product, dp, sp)

    kinds = collections.Counter(c["kind"] for c in checks)
    srcs = collections.Counter(c["pattern_source"] for c in checks)
    art = sum(1 for c in checks if c["article_no"])
    rec = sum(1 for c in checks if c["recommendation"])

    print(f"규칙 {len(rules):,}건 → {a.product}성 판정 규칙 {len(checks)}건\n")
    print("판정 종류:")
    for k, v in kinds.most_common():
        print(f"  {k:10s} {v:4d}")
    print("\n문구 출처:")
    for k, v in srcs.most_common():
        print(f"  {k:12s} {v:4d}")
    print(f"\n근거 조문 있음 {art}/{len(checks)} ({art/len(checks)*100:.0f}%)")
    print(f"개선안 있음   {rec}/{len(checks)} ({rec/len(checks)*100:.0f}%)")

    out = a.out or os.path.join(RAG, f"checks_{a.product}.json")
    json.dump({
        "_설명": f"{a.product}성 광고 판정 규칙. 규칙리스트에서 생성.",
        "_생성": "python rag/build_checks.py --product " + a.product,
        "_주의": "kind=LLM 은 문구를 못 만든 것이다. criterion 문장을 그대로 LLM 에 "
                "넘겨 좁게 묻는다. 억지로 룰로 만들면 근거 없는 지적이 쏟아진다.",
        "checks": checks,
    }, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"\n저장: {out}")

    print("\n표본 — 룰로 판정하는 것:")
    for c in [x for x in checks if x["kind"] != "LLM"][:4]:
        print(f"  {c['id']} [{c['kind']}/{c['pattern_source']}] {c['title'][:44]}")
        print(f"     찾을 것 {c['params'].get('pattern')}")
        print(f"     근거    {c['article_no']}")
        print(f"     개선안  {c['recommendation']}")
    print("\n표본 — LLM 이 판정할 것:")
    for c in [x for x in checks if x["kind"] == "LLM"][:3]:
        print(f"  {c['id']} {c['title'][:44]}")
        print(f"     물음  {c['criterion'][:80]}")
        print(f"     근거  {c['article_no']}")


if __name__ == "__main__":
    main()
