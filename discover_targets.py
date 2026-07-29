# -*- coding: utf-8 -*-
"""
수집 후보 이름을 법제처에서 실제로 찾아보고, targets.json 에 넣을 정확한 이름을 확인한다.

법령명은 띄어쓰기·조사까지 정확해야 검색이 되므로(예: "표시광고공정화에관한법률" →
"표시·광고의 공정화에 관한 법률"), 추가 전에 이 스크립트로 확인한다.

  python discover_targets.py            # 후보 조회만
  python discover_targets.py --apply    # 확인된 것을 targets.json 에 추가
"""
import os
import sys
import json

sys.stdout.reconfigure(encoding="utf-8")

import law_scraper as L

ROOT = os.path.dirname(os.path.abspath(__file__))

# (사용자가 요청한 이름, 종류) — 법령=law, 행정규칙(고시·규정·세칙)=admrul
CANDIDATES = [
    ("금융소비자 보호에 관한 법률", "law"),
    ("금융소비자 보호에 관한 법률 시행령", "law"),
    # 금소법 시행규칙은 제정된 적이 없다(법률·시행령만 존재) — 조회 확인함
    ("금융소비자 보호에 관한 감독규정", "admrul"),
    ("금융소비자보호에 관한 감독규정 시행세칙", "admrul"),

    ("자본시장과 금융투자업에 관한 법률", "law"),
    ("자본시장과 금융투자업에 관한 법률 시행령", "law"),
    ("자본시장과 금융투자업에 관한 법률 시행규칙", "law"),
    ("금융투자업규정", "admrul"),
    ("금융투자업규정 시행세칙", "admrul"),

    ("여신전문금융업법", "law"),
    ("여신전문금융업법 시행령", "law"),
    ("여신전문금융업법 시행규칙", "law"),
    ("여신전문금융업감독규정", "admrul"),
    ("여신전문금융업감독업무시행세칙", "admrul"),

    ("정보통신망 이용촉진 및 정보보호 등에 관한 법률", "law"),
    ("정보통신망 이용촉진 및 정보보호 등에 관한 법률 시행령", "law"),
    ("정보통신망 이용촉진 및 정보보호 등에 관한 법률 시행규칙", "law"),

    # 법제처 공식 표기는 가운뎃점(·, U+00B7)이 아니라 한글 기호 'ㆍ'(U+318D) 다.
    # 사람이 옮겨 적을 때 거의 항상 틀리는 부분이라 여기 고정해 둔다.
    ("표시ㆍ광고의 공정화에 관한 법률", "law"),
    ("표시ㆍ광고의 공정화에 관한 법률 시행령", "law"),
    # 표시광고법 시행규칙도 존재하지 않는다(법률·시행령만) — 조회 확인함
]


def probe(name, kind):
    """검색 결과에서 이름이 정확히 일치하는 항목을 찾는다."""
    cfg = L.KIND[kind]
    try:
        items = L.search(name, kind)
    except Exception as e:
        return {"상태": "조회실패", "메시지": str(e)[:60]}
    if not items:
        return {"상태": "없음"}
    key = name.replace(" ", "").replace("·", "")
    for it in items:
        got = it.get(cfg["name_f"], "")
        if got.replace(" ", "").replace("·", "") == key:
            return {"상태": "정확일치", "공식명": got,
                    "시행일자": it.get(cfg["eff_f"], ""),
                    "버전": it.get(cfg["ver_f"], "")}
    # 이름이 조금 다를 수 있으니 가장 비슷한 후보를 보여준다
    near = [it.get(cfg["name_f"], "") for it in items[:3]]
    return {"상태": "이름불일치", "후보": near}


def main():
    apply_ = "--apply" in sys.argv[1:]
    cur = json.load(open(os.path.join(ROOT, "targets.json"), encoding="utf-8"))
    have = {t["name"].replace(" ", "") for t in cur}

    ok, ng = [], []
    print(f"{'요청 이름':44} {'종류':7} 결과")
    print("-" * 96)
    for name, kind in CANDIDATES:
        if name.replace(" ", "") in have:
            print(f"{name[:42]:44} {kind:7} 이미 등록됨")
            continue
        r = probe(name, kind)
        if r["상태"] == "정확일치":
            print(f"{name[:42]:44} {kind:7} OK  시행 {r['시행일자']} · 버전 {r['버전']}")
            ok.append({"name": r["공식명"], "kind": kind})
        elif r["상태"] == "이름불일치":
            print(f"{name[:42]:44} {kind:7} ?   비슷한 것: {r['후보']}")
            ng.append((name, kind, r))
        else:
            print(f"{name[:42]:44} {kind:7} X   {r.get('메시지', r['상태'])}")
            ng.append((name, kind, r))

    print("-" * 96)
    print(f"추가 가능 {len(ok)}건 · 확인 필요 {len(ng)}건")

    if apply_ and ok:
        cur.extend(ok)
        with open(os.path.join(ROOT, "targets.json"), "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=2)
        print(f"targets.json 에 {len(ok)}건 추가 (전체 {len(cur)}건)")
    elif ok:
        print("추가하려면: python discover_targets.py --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
