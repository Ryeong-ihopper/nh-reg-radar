# -*- coding: utf-8 -*-
"""두 방향을 광고 하나의 판정으로 합친다.

    광고 → 조문   pipeline.py / 12번 셀   **쓰면 안 될 것을 썼다**(오기·오표기)
                  검색이 필요한 자리. 광고를 읽어야 발견된다.
    조문 → 광고   detect.py  / 13번 셀    **써야 할 것을 안 썼다**(누락)
                  검색이 아니라 조회. 광고를 보기 전에 요구가 정해진다.

**한 방향만으로는 절반밖에 못 잡는다.** 정답셋 15건을 지적 사유로 갈라 보면

    누락형 9건   광고에 그 문구가 없으니, 광고에서 뽑은 어떤 질의도 그 조문을
                 안 가져온다 — 광고→조문 검색으로는 **원리적으로** 못 잡는다
    오기형 6건   광고→조문 검색이 잡을 수 있는 자리

그래서 광고→조문 단방향인 지금 파이프라인은 구조상 상한이 6/15 다(실측 4/15).
누락 9건을 판정에 넣으려면 조문→광고 결과를 같이 세워야 한다.

이 파일은 **`full_colab.ipynb` 에도 같은 코드가 들어간다** — 노트북 생성기가
여기 함수 원문을 그대로 읽어다 넣는다. 두 벌로 갈라져 서로 달라지는 것을 막는다.
"""


# ── 아래 두 함수는 노트북에 그대로 복사된다 (MERGE_BEGIN ~ MERGE_END) ──
# MERGE_BEGIN
def merge_findings(item, rule_findings):
    """광고 하나 — 양방향 지적을 합쳐 하나의 판정으로.

    `item`          pipeline/12번 셀 결과 한 건 (광고→조문)
    `rule_findings` detect/13번 셀이 그 광고에 낸 지적 목록 (조문→광고)

    **판정은 「지적이 하나라도 있으면 부적합」이다.** 두 방향 중 하나만 걸려도
    실무에서는 보완 대상이다. 어느 방향이 잡았는지는 지적마다 남긴다 —
    나중에 방향별 성능을 따로 볼 수 있어야 한다.
    """
    out = []
    v = item.get("판정") or {}
    if v.get("판정") == "부적합":
        out.append({
            "유형": "오기",
            "규칙": None,
            "사유": v.get("사유"),
            "인용": v.get("인용"),
            "근거": [e.get("evidence_id") for e in (item.get("근거") or [])],
            "_출처": "광고→조문(LLM)",
        })
    for f in (rule_findings or []):
        out.append({
            "유형": "누락",
            "규칙": f.get("check_id"),
            "사유": f.get("사유"),
            "인용": f.get("인용"),
            "근거": [f.get("근거규정")] if f.get("근거규정") else [],
            "_출처": f"조문→광고({f.get('판정근거', 'RULE')})",
        })
    return {
        "광고id": item.get("광고id"),
        "판정": "부적합" if out else "적합",
        "지적": out,
        "_방향별": {"오기": sum(1 for x in out if x["유형"] == "오기"),
                    "누락": sum(1 for x in out if x["유형"] == "누락")},
        "_판정출처": (item.get("판정") or {}).get("_source"),
    }


def score(merged, gold, rows_of_rule, evidence_row):
    """정답셋 채점 — **「지적했나」가 아니라 「그 조문에 닿았나」로 센다.**

    `rows_of_rule(rule_id)`  규칙 id → 그 규칙이 가리키는 색인 행 집합
    `evidence_row(ev_id)`    evidence_id → 색인 행 번호(없으면 None)

    지적 문구가 정답과 글자로 같기를 바랄 수 없다. 대신 **우리가 낸 지적이
    정답이 지목한 조문에 닿는가**를 본다. 두 방향이 각각 몇 건을 잡는지
    따로 세어, 합치는 것이 실제로 이득인지 확인한다.
    """
    by_ad = {m["광고id"]: m for m in merged}
    tot = ok = only_a = only_b = both = 0
    detail = []
    for g in gold:
        aid = g.get("광고id")
        ans = set(g.get("정답행") or [])
        if not ans or aid not in by_ad:
            continue
        tot += 1
        hit_a = hit_b = False
        for f in by_ad[aid]["지적"]:
            rows = set()
            if f.get("규칙"):
                rows |= set(rows_of_rule(f["규칙"]) or [])
            for ev in (f.get("근거") or []):
                r = evidence_row(ev)
                if r is not None:
                    rows.add(r)
            if rows & ans:
                if f["유형"] == "오기":
                    hit_a = True
                else:
                    hit_b = True
        if hit_a and hit_b:
            both += 1
        elif hit_a:
            only_a += 1
        elif hit_b:
            only_b += 1
        if hit_a or hit_b:
            ok += 1
        detail.append((aid, hit_a, hit_b, g.get("지적", "")[:40]))
    return {"정답": tot, "잡음": ok,
            "광고→조문만": only_a, "조문→광고만": only_b, "둘 다": both,
            "상세": detail}
# MERGE_END


def _self_test():
    """모양이 맞는지만 본다(자료 없이 돈다)."""
    item = {"광고id": "X", "근거": [{"evidence_id": "C-1"}],
            "판정": {"판정": "부적합", "사유": "s", "인용": "q", "_source": "llm"}}
    m = merge_findings(item, [{"check_id": "R-9", "근거규정": "제16조",
                               "사유": "누락", "판정근거": "LLM"}])
    assert m["판정"] == "부적합" and m["_방향별"] == {"오기": 1, "누락": 1}, m
    got = score([m], [{"광고id": "X", "정답행": [7], "지적": "t"}],
                lambda r: {7} if r == "R-9" else set(),
                lambda e: 3 if e == "C-1" else None)
    assert got["잡음"] == 1 and got["조문→광고만"] == 1, got
    print("merge 자체검사 통과 —", got)


if __name__ == "__main__":
    _self_test()
