# -*- coding: utf-8 -*-
"""PoC 범위 밖 규칙·체크리스트에 **표시만** 한다. 지우지 않는다.

2026-08-07 수요사 결정 — 영상 / 시계열·이력 / 외부 연계 세 갈래는 이번 범위에서
뺀다. 다만 **삭제하지 않고 「제외 예정」으로 표시**해 둔다. 나중에 쓸 수 있다.

지우면 되돌릴 수 없고, 무엇을 왜 뺐는지도 사라진다. 표시로 두면 언제든 한 줄
바꿔 되살릴 수 있고, 「그때 왜 뺐지」에 답할 수 있다.

세 갈래를 나눈 기준은 **우리 파이프라인이 그 규칙을 판정할 수 있는가**다.

  영상    입력이 텍스트라 재생·자막·시간을 볼 수 없다
  이력    같은 광고의 과거 판본·유효기간을 알아야 한다 (DB 에 이력이 아직 없다)
  외부    타사 금리·시세·제휴사 정보를 조회해야 한다 (연계가 아직 없다)

  python rag/scope.py                 # 집계
  python rag/scope.py --list 영상     # 해당 목록
  python rag/scope.py --out output/_rag/scope_excluded.json
"""
import os
import re
import json

import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import paths as P
import argparse
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAG = os.path.join(ROOT, "output", "_rag")
XLSX = P.dl(r"NH_광고심의_규칙리스트_조문지도, 체크리스트 통합.xlsx")
OUT = os.path.join(RAG, "scope_excluded.json")
MD = os.path.join(RAG, "제외예정_목록.md")

# 수요사가 준 낱말 목록 그대로 쓴다. **내가 보태지 않는다** — 범위를 정하는 것은
# 수요사이고, 내가 낱말을 하나 더하면 그 결정과 다른 목록이 조용히 만들어진다.
GROUPS = {
    "영상": r"TV|방송|배너|자막|프레임|재생",
    "이력": r"유효기간|누적|매년|보관|재광고",
    "외부": r"제휴|SNS|타사|링크|인플루언서|중개",
}
_RE = {k: re.compile(v) for k, v in GROUPS.items()}

# 매체 칸은 낱말보다 정확하다 — 담당자가 직접 적은 구조화된 값이다.
_MED_VIDEO = {"영상", "방송"}

# 수요사가 알려 준 건수. **맞추라는 목표가 아니라 어긋남을 드러내는 눈금이다.**
# 낱말만으로는 이 숫자가 안 나온다(아래 주의 참고). 규칙ID 목록을 받으면 `--ids`
# 로 넘겨 낱말 추정을 통째로 대체한다 — 그때부터 추정이 아니라 확정이다.
TARGET = {"영상": 143, "이력": 82, "외부": 129}


def _s(x):
    return str(x if x is not None else "").strip()


def load(xlsx=XLSX):
    import warnings
    warnings.filterwarnings("ignore")
    import openpyxl

    wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)

    def sheet(name):
        it = wb[name].iter_rows(values_only=True)
        head = [_s(c) for c in next(it)]
        return [dict(zip(head, r)) for r in it if r and r[0] is not None]

    rules, checks = sheet("규칙"), sheet("체크리스트")
    wb.close()
    return rules, checks


def _rule_text(r):
    return " ".join(_s(r.get(k)) for k in ("요약", "판단 기준", "원문 인용"))


def tag(text, medium=""):
    """해당하는 갈래를 전부 돌려준다. **하나만 고르지 않는다** — 한 규칙이 영상이면서
    외부 연계일 수 있고, 억지로 하나로 정하면 되살릴 때 근거가 흐려진다."""
    got = [k for k, rx in _RE.items() if rx.search(text)]
    med = {x.strip() for x in medium.split(",") if x.strip()}
    if (med & _MED_VIDEO) and "영상" not in got:
        got.append("영상")
    return got


def classify(rules, checks):
    for r in rules:
        r["_제외갈래"] = tag(_rule_text(r), _s(r.get("매체")))
    for c in checks:
        c["_제외갈래"] = tag(_s(c.get("체크_문구")) + " " + _s(c.get("근거_법령·규정")))
    return rules, checks


def summary(items, key, target=None):
    n = len(items)
    hit = [x for x in items if x["_제외갈래"]]
    cnt = collections.Counter(g for x in items for g in x["_제외갈래"])
    print(f"\n{key} {n:,}건")
    for g in GROUPS:
        gap = ""
        if target:
            d = cnt[g] - target[g]
            gap = f"   (수요사 {target[g]:4d} · 차이 {d:+d})"
        print(f"  {g}   {cnt[g]:4d}{gap}")
    only = collections.Counter(len(x["_제외갈래"]) for x in hit)
    print(f"  ─ 중복 제거  {len(hit):4d}  ({len(hit)/n*100:.0f}%) "
          f"· 남는 것 {n-len(hit):,}건")
    print(f"    (갈래 1개 {only[1]} · 2개 이상 {sum(v for k, v in only.items() if k > 1)})")
    return hit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xlsx", default=XLSX)
    ap.add_argument("--list", choices=tuple(GROUPS))
    ap.add_argument("--ids", help="수요사가 준 규칙ID 목록 JSON — {갈래: [규칙ID,…]}. "
                                  "주면 낱말 추정을 버리고 이것만 쓴다")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--md", default=MD)
    a = ap.parse_args()

    rules, checks = classify(*load(a.xlsx))

    if a.ids:
        # **확정 목록이 있으면 추정을 통째로 버린다.** 둘을 섞으면 어느 것이 수요사
        # 결정이고 어느 것이 내 추측인지 나중에 아무도 못 가린다.
        want = json.load(open(a.ids, encoding="utf-8"))
        by = collections.defaultdict(list)
        for g, ids in want.items():
            for i in ids:
                by[str(i).strip()].append(g)
        for r in rules:
            r["_제외갈래"] = by.get(_s(r.get("규칙ID")), [])
        for c in checks:
            c["_제외갈래"] = by.get(_s(c.get("체크리스트_ID")), [])
        print(f"규칙ID 목록 적용: {a.ids}  (낱말 추정 안 씀)")

    hr = summary(rules, "규칙", None if a.ids else TARGET)
    hc = summary(checks, "체크리스트")

    if not a.ids:
        print("\n※ 낱말로 고른 **추정**이다. 수요사 건수와 어긋난다 — 알려 준 낱말")
        print("  (TV·방송·배너·자막… 등)이 예시라 전체 목록이 아니기 때문으로 보인다.")
        print("  규칙ID 목록을 받으면 --ids 로 넘겨 확정으로 바꾼다.")

    if a.list:
        print(f"\n== {a.list} ==")
        for r in rules:
            if a.list in r["_제외갈래"]:
                print(f"  {_s(r.get('규칙ID')):8s} {_s(r.get('매체')):12s} "
                      f"{_s(r.get('요약'))[:58]}")

    os.makedirs(RAG, exist_ok=True)
    json.dump({
        "결정일": "2026-08-07",
        "설명": "PoC 범위 밖. 삭제하지 않고 표시만 한다.",
        "갈래": GROUPS,
        "규칙": {_s(r.get("규칙ID")): r["_제외갈래"] for r in hr},
        "체크리스트": {_s(c.get("체크리스트_ID")): c["_제외갈래"] for c in hc},
    }, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    lines = ["# 제외 예정 목록 (2026-08-07)", "",
             "**지우지 않았다.** 표시만 해 둔 것이라 언제든 되살릴 수 있다.", "",
             "| 갈래 | 왜 못 보나 | 규칙 | 체크리스트 |", "|---|---|---:|---:|"]
    why = {"영상": "입력이 텍스트라 재생·자막·시간을 볼 수 없음",
           "이력": "같은 광고의 과거 판본·유효기간을 알아야 함",
           "외부": "타사 금리·시세·제휴사 정보를 조회해야 함"}
    for g in GROUPS:
        lines.append(f"| {g} | {why[g]} | "
                     f"{sum(1 for r in hr if g in r['_제외갈래'])} | "
                     f"{sum(1 for c in hc if g in c['_제외갈래'])} |")
    lines += ["", f"중복을 뺀 합계 — 규칙 **{len(hr)}** / {len(rules):,} · "
                  f"체크리스트 **{len(hc)}** / {len(checks)}", ""]
    for g in GROUPS:
        lines += [f"## {g}", "", "| 규칙ID | 매체 | 요약 |", "|---|---|---|"]
        for r in hr:
            if g in r["_제외갈래"]:
                lines.append(f"| {_s(r.get('규칙ID'))} | {_s(r.get('매체'))} | "
                             f"{_s(r.get('요약'))} |")
        lines.append("")
    open(a.md, "w", encoding="utf-8").write("\n".join(lines))

    print(f"\n저장: {a.out}\n      {a.md}")


if __name__ == "__main__":
    main()
