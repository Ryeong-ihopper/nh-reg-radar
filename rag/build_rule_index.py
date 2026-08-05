# -*- coding: utf-8 -*-
"""규칙 1,744건 → 검색 인덱스 항목. `evidences` 스키마에 맞춘다.

**검색 대상은 규칙이다.** 법령 조문이나 매뉴얼을 직접 찾는 것이 아니라, 광고에서
쟁점을 뽑아 규칙을 찾고, 걸린 규칙에 붙은 근거를 함께 보여준다. 규칙리스트는
연구원이 매뉴얼 15종에서 추출한 것이라 **매뉴얼 원문을 따로 담지 않는다** — 매뉴얼이
근거인 375건은 「원문 인용」 열에 해당 대목이 이미 발췌돼 있다.

필드 이름은 `docs/database-specification.md` §9.3 `evidences` 를 따른다. 새 이름을
지어내면 적재할 때 다시 맞춰야 한다. 스키마에 없는 값(업권 등)은 만들지 않는다 —
규칙의 출처 매뉴얼로 유도할 수 있으므로 필요해지면 그때 파생한다.

근거는 세 갈래로 붙는다.

  법령 조문 지정   우리 코퍼스의 조문 본문 (1,099건)
  법령명만 지정     규정 전체를 근거로. 조문은 검색이 찾게 한다 (182건)
  매뉴얼·미특정    「원문 인용」 발췌를 그대로 (463건)

임베딩에 넣는 텍스트는 **요약 + 판단기준**이다. 근거 본문은 넣지 않는다 — 조문 원문은
법령 문어체라 광고 쟁점과 어휘가 안 겹치고(4단계 실측), 같은 조문을 근거로 둔 규칙이
여럿이면 전부 비슷해져 서로 구분되지 않는다.

  python rag/build_rule_index.py
"""
import os
import sys
import json
import re
import argparse
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MATCHED = os.path.join(ROOT, "output", "_rag", "rules_matched.json")
CHUNKS = os.path.join(ROOT, "output", "_rag", "chunks.jsonl")
OUT = os.path.join(ROOT, "output", "_rag", "rule_index.jsonl")

# ── 스키마 Enum 매핑 (database-specification.md §3.7) ──────────────────
# 규칙리스트의 「카테고리」 → evidences.rule_type
RULE_TYPE = {
    "표시의무": "REQUIRED",     # 광고에 특정 정보를 반드시 포함
    "금지": "PROHIBITED",       # 특정 표현·행위 금지
    "양식": "REQUIRED",         # 표시 방법·형태 규제 — 지키지 않으면 위반이므로 필수
    "절차": "REQUIRED",
    "참고": "REFERENCE",
}
# 규칙리스트의 「우선순위」 → evidences.importance
# 규칙리스트가 쓰는 값은 「필수 / 권장」이다(칼럼값_판단기준 시트). 「권고」로 잘못
# 적어 두어 권장 34건이 값 없이 빠져 있었다.
IMPORTANCE = {"필수": "HIGH", "권장": "MEDIUM"}

# 규칙리스트의 「상품」 → evidences.product_group
# 스키마에는 DEPOSIT/SAVINGS/DEMAND_DEPOSIT/EVENT_FINANCIAL_PRODUCT/LOAN/CARD/INVESTMENT
# 이 있는데 규칙리스트는 예금/대출/투자/보험/전체로만 나뉜다. 더 잘게는 못 나눈다.
PRODUCT = {"예금": "DEPOSIT", "대출": "LOAN", "투자": "INVESTMENT", "보험": None}

# ── 매체 ─────────────────────────────────────────────────────────────
# **분류 축이 다르다.** 규칙리스트는 「매체 종류」 6가지(지면·영상·온라인·옥외·방송·
# 전체)로 나누고, 스키마 advertisement_type 은 「광고물 형태」 10가지(LEAFLET·SMS·
# APP_PUSH…)로 나눈다. 온라인 하나가 MOBILE_BANNER·APP_PUSH·EVENT_PAGE 여럿에
# 대응하므로 규칙 쪽에서 광고물 형태를 만들어 낼 수 없다(실측: 키워드 매핑을 했더니
# 1,744건 중 0건이 걸렸다).
#
# 그래서 **방향을 뒤집는다.** 규칙에는 매체 종류를 그대로 두고, 심의할 때 들어온
# 광고의 advertisement_type 을 매체 종류로 바꿔 규칙을 거른다. 광고의 형태는 확실히
# 알 수 있으므로 이 방향은 정보 손실이 없다.
MEDIUM = {"지면": "PRINT", "영상": "VIDEO", "온라인": "ONLINE",
          "옥외": "OUTDOOR", "방송": "BROADCAST", "전체": "ALL"}

# 광고물 형태 → 매체 종류. 검색할 때 쓰라고 함께 내보낸다.
AD_TYPE_TO_MEDIUM = {
    "LEAFLET": "PRINT", "BRANCH_MEMO": "PRINT", "CUSTOMER_NOTICE": "PRINT",
    "MOBILE_BANNER": "ONLINE", "INTERNET_BANKING_BANNER": "ONLINE",
    "EVENT_PAGE": "ONLINE", "APP_PUSH": "ONLINE", "SMS": "ONLINE",
    "ALIMTALK": "ONLINE", "HTML_CAPTURE": "ONLINE",
}


def rule_type_of(rec):
    return RULE_TYPE.get((rec.get("카테고리") or "").strip(), "REFERENCE")


def importance_of(rec):
    return IMPORTANCE.get((rec.get("우선순위") or "").strip())


def products_of(rec):
    raw = rec.get("상품") or ""
    got = [v for k, v in PRODUCT.items() if k in raw and v]
    return sorted(set(got))


def mediums_of(rec):
    raw = rec.get("매체") or ""
    got = [v for k, v in MEDIUM.items() if k in raw]
    return sorted(set(got)) or ["ALL"]


# ── 근거의 출처 ───────────────────────────────────────────────────────
# 근거 상세가 **매뉴얼에 적혀 있던 것**인지 **AI 가 추론한 것**인지 가른다.
# 추출 지침(규칙_추출_지침.md)은 original_text 를 verbatim 으로 보존하게 했으므로,
# 그 안에 조문 번호가 있으면 옮긴 것이고 없으면 지어낸 것이다.
# 실측: 조문까지 명시된 것은 72건(4%)뿐이고 646건(37%)은 원문에 근거 흔적이 없다.
_ART_IN = re.compile(r"제\s*\d+(?:-\d+)?\s*조(?:의\s*\d+)?")
_LAW_KW = re.compile(r"금소법|금융소비자|자본시장|여전법|여신전문|정보통신망"
                     r"|표시.?광고|협회규정|규정\s*제|법\s*제|§")


def basis_origin(rec):
    basis = (rec.get("근거상세") or "").strip()
    orig = rec.get("원문인용") or ""
    if not basis or basis == "-":
        return "MANUAL_SELF"          # 매뉴얼 자체가 근거. 조문이 없는 것이 정상
    arts = _ART_IN.findall(basis)
    if not arts:
        return "LAW_ONLY"             # 법령명만 있고 조문 미지정
    flat = re.sub(r"\s+", "", orig)
    if any(re.sub(r"\s+", "", a) in flat for a in arts):
        return "STATED"               # 매뉴얼 원문에 조문 번호가 있었다
    if _LAW_KW.search(orig):
        return "PARTIAL"              # 법령 언급만 있고 조문은 AI 가 채움
    return "INFERRED"                 # 원문에 근거 흔적 없음. AI 추론


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matched", default=MATCHED)
    ap.add_argument("--chunks", default=CHUNKS)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    rules = json.load(open(a.matched, encoding="utf-8"))
    chunks = [json.loads(l) for l in open(a.chunks, encoding="utf-8")]

    rows, stat = [], collections.Counter()
    for r in rules:
        # 검색될 텍스트. 요약은 짧고 판단기준은 「~하였는지 확인」 형태라,
        # 둘을 이어 붙이면 광고 쟁점 질의와 어휘가 가장 많이 겹친다.
        content = "\n".join(p for p in (r["요약"], r["판단기준"]) if p).strip()
        if not content:
            stat["본문 없음"] += 1
            continue

        basis, etype = [], None
        # 매뉴얼이 근거인 규칙의 _근거 는 {출처, 페이지} 형태라 조문 정보가 없다.
        # 아래 「원문 인용」 경로로 보내야 하므로 여기서 걸러 둔다.
        refs = [h for h in (r.get("_근거") or []) if "reg" in h]
        for h in refs:
            if h.get("청크"):
                for i in h["청크"]:
                    c = chunks[i]
                    basis.append({"유형": "조문", "규정": c["reg"], "article_no": c["key"],
                                  "제목": c.get("title", ""), "본문": c["text"]})
                etype = "REGULATION"
            else:
                basis.append({"유형": "규정", "규정": h["reg"], "article_no": None,
                              "제목": "", "본문": ""})
                etype = etype or "REGULATION"
        if not basis and r.get("원문인용"):
            # 매뉴얼이 근거이거나 문서를 특정 못 한 경우. 발췌가 곧 근거다.
            basis.append({
                "유형": "발췌",
                "규정": r.get("근거상세") or r.get("출처매뉴얼"),
                "article_no": f"{r.get('출처매뉴얼','')} p.{r.get('출처페이지','')}".strip(),
                "제목": "", "본문": r["원문인용"]})
            etype = "MANUAL"
        stat[f"근거 {etype or '없음'}"] += 1

        rows.append({
            # ── evidences 대응 ──────────────────────────────────────
            "evidence_id": r["규칙ID"],
            "evidence_type": etype or "MANUAL",
            "title": r["요약"][:500],
            "article_no": (basis[0]["article_no"] if basis else None),
            "content": content,
            "content_summary": r["요약"],
            "product_group": products_of(r),
            "advertisement_type": [],   # 규칙에서는 만들 수 없다. 위 MEDIUM 주석 참고
            "medium": mediums_of(r),
            "rule_type": rule_type_of(r),
            "importance": importance_of(r),
            "is_active": True,
            # 스키마에 대응 열이 없지만 심의 결과의 실체다(반려 631 · 보완요청 1,066 ·
            # 주의 47). importance 는 1,710건이 HIGH 라 사실상 못 거른다.
            "violation_action": r.get("위반시", ""),
            # 규칙리스트 자체의 검증 상태. 「임시」는 서브에이전트가 자동 추출한 초안이고
            # 사람 검토 전이다(실측: 1,610건 92%). 이 값을 안 남기면 검증된 것처럼 쓰인다.
            "status": r.get("상태", ""),
            "basis_origin": basis_origin(r),
            # ── 스키마 열에 안 들어가는 것은 metadata_json 으로 ────────
            "metadata_json": {
                "판단기준": r["판단기준"],
                "위반시": r.get("위반시", ""),
                "카테고리_원문": r.get("카테고리", ""),
                "상품_원문": r.get("상품", ""),
                "매체_원문": r.get("매체", ""),
                "출처매뉴얼": r.get("출처매뉴얼", ""),
                "출처페이지": r.get("출처페이지", ""),
                "근거상세_원문": r.get("근거상세", ""),
            },
            "근거": basis,
            "chars": len(content),
        })

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        for x in rows:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")

    c = sorted(x["chars"] for x in rows)
    print(f"규칙 {len(rules)}건 → 인덱스 {len(rows)}건\n")
    for k, v in stat.most_common():
        print(f"  {v:>5}  {k}")
    print(f"\n검색 텍스트: 중앙 {c[len(c)//2]}자 · p90 {c[int(len(c)*.9)]} · 최대 {c[-1]}")
    print(f"rule_type:     {collections.Counter(x['rule_type'] for x in rows).most_common()}")
    print(f"importance:    {collections.Counter(x['importance'] for x in rows).most_common()}")
    print(f"evidence_type: {collections.Counter(x['evidence_type'] for x in rows).most_common()}")
    pg = collections.Counter(p for x in rows for p in x["product_group"])
    print(f"product_group: {pg.most_common()}  (미지정 {sum(1 for x in rows if not x['product_group'])}건)")
    print(f"medium:        {collections.Counter(m for x in rows for m in x['medium']).most_common()}")
    print(f"violation:     {collections.Counter(x['violation_action'] for x in rows).most_common()}")
    print(f"status:        {collections.Counter(x['status'] for x in rows).most_common()}")
    print(f"basis_origin:  {collections.Counter(x['basis_origin'] for x in rows).most_common()}")
    nb = sorted(len(x["근거"]) for x in rows)
    print(f"규칙당 근거: 중앙 {nb[len(nb)//2]} · 최대 {nb[-1]}")
    print(f"\n저장: {a.out}")


if __name__ == "__main__":
    main()
