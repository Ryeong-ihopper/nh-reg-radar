# -*- coding: utf-8 -*-
"""
별표를 「양식」과 「기준」으로 가른다.

인덱스에 넣을 것을 정하는 판정이다. 광고심의 근거로 인용되는 것은 기준·예시이고,
빈 서식은 근거가 될 수 없다. 그런데 별표는 항목 수로는 8%인데 **글자 수로는 절반**
(314만 자)이라, 서식을 그대로 넣으면 인덱스의 절반이 빈 칸과 괘선이 된다.
서식 청크는 의미가 없는데 벡터는 똑같이 만들어져 검색에서 진짜 조문을 밀어낸다.

제목으로 가르면 안 된다. 금투협은 제목 필드가 비어 있고, 「별책서식」처럼 이름에
드러나는 것은 일부다. **내용의 성질로 가른다.**

  규범 밀도   「~하여야 한다」「~할 수 있다」 등 규범 종결의 천자당 빈도
  서식 상용구 「(서명 또는 인)」「귀하」「접수번호」 등의 천자당 빈도
  괘선 비율   ┌─┐│ 같은 표 그리기 문자의 비중
  빈 줄 비율  내용이 거의 없는 줄(빈 칸을 그린 서식에서 높다)

한 지표만으로는 안 갈린다 — 「위험액 산정기준」은 괘선이 18.9%라 「별책서식」(22.5%)과
붙는다. 규범 밀도를 같이 봐야 한다.

  python rag/classify.py            # 전체 판정 + 분포
  python rag/classify.py --list 양식  # 양식으로 판정된 것 나열
"""
import os
import re
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sections

_RULE = re.compile(r"(하여야 한다|해야 한다|한다\.|할 수 있다|하지 아니한다|본다\.|말한다|"
                   r"따른다|적용한다|산정한다|정한다)")
_FORM = re.compile(r"(년\s*월\s*일|서명 또는 인|귀\s*하|신청인|접수번호|처리기간|담당자|"
                   r"연락처|\(\s*인\s*\)|앞\s*쪽|뒤\s*쪽|기재하지 않습니다|해당사항)")
_ART = re.compile(r"제\d+(?:-\d+)?조")
_BOX = "┌┐└┘├┤┬┴┼─│━┃╔╗╚╝║═▶◀"

# 이름에 성격이 드러나는 경우. 제목을 본문 첫머리에서 복원해 두었으므로
# (sections._title_from_body) 금투협도 이름을 쓸 수 있다.
_NAME_FORM = re.compile(r"(별책서식|서식|양식|신청서|신고서|보고서|계산서|대차대조표|"
                        r"명세서|확인서|동의서|신청서류|청약정보|증명서|의뢰서|"
                        r"통보서|증표|인가증|등록증|허가증|등록원부|지정명부|확인증)")
_NAME_RULE = re.compile(r"(기준|한도|범위|방법|절차|유형|요령|지침|산정|판단|분류|"
                        r"가중치|비율|위험값|평가점수|포함해야|포함되어야|사항)")
# 「(제25조제1항 관련)」 — 그 조문이 이 표를 기준으로 끌어 쓴다는 표시다.
# 법제처가 별표 제목에 붙여 주는 것이라, 붙어 있으면 인용되는 근거자료다.
_REF = re.compile(r"\(\s*(?:시행령\s*)?제\d+(?:-\d+)?조[^)]*관련\s*\)")


def _digits(text):
    """숫자 비율(%). 기준 표는 칸이 숫자로 차 있고 빈 서식은 비어 있다."""
    return len(re.findall(r"\d", text)) / max(len(text), 1) * 100


def features(text):
    n = max(len(text), 1)
    lines = [l for l in text.split("\n") if l.strip()]
    return {
        "chars": len(text),
        "rule": len(_RULE.findall(text)) / n * 1000,
        "form": len(_FORM.findall(text)) / n * 1000,
        "art": len(_ART.findall(text)) / n * 1000,
        "box": sum(text.count(c) for c in _BOX) / n * 100,
        "blank": sum(1 for l in lines if len(l.strip()) < 4) / max(len(lines), 1) * 100,
    }


def classify(sec):
    """→ ('양식'|'기준', 근거 문자열)

    이름에 성격이 드러나면 그것을 먼저 쓴다. 「과태료의 부과기준」처럼 표로 된
    기준은 괘선 비율이 서식만큼 높아서(22%) 내용 지표만으로는 서식과 안 갈린다.
    이름이 없거나 애매할 때만 내용 지표로 판정한다.

    내용 지표를 보조로 돌린 것이지 제목만 보던 예전으로 돌아간 것은 아니다 —
    제목 자체를 본문에서 복원했고, 이름이 아무 신호도 주지 않는 경우가 다수다.
    """
    f = features(sec["text"])
    title = sec.get("title") or ""
    name = re.sub(r"\s+", "", f'{title} {sec.get("key","")}')   # 「등 록 증」 대비
    is_form, is_rule = _NAME_FORM.search(name), _NAME_RULE.search(name)

    # 「등록신청서 기재사항」처럼 둘 다 걸리면 서식 쪽이 앞선다(신청서가 본체다)
    if is_form and (not is_rule or is_form.start() < is_rule.start()):
        return "양식", f"이름: {is_form.group(0)}"
    if is_rule:
        return "기준", f"이름: {is_rule.group(0)}"
    if _REF.search(title):
        return "기준", "조문이 끌어 쓰는 표 (제…조 관련)"

    if f["form"] >= 0.30:
        return "양식", f"서식 상용구 {f['form']:.2f}/천자"
    # 괘선은 서식에서만 높은 게 아니라 **숫자가 채워진 기준 표**에서도 높다.
    # 「유동화 가중치」 30% · 「영업별 위험값」 33% 가 그 경우였다. 빈 칸을 그린
    # 서식과 가르려면 칸이 비어 있는지를 봐야 한다 → 숫자 비율을 같이 본다.
    if f["box"] >= 30.0 and f["rule"] < 0.50 and _digits(sec["text"]) < 1.0:
        return "양식", f"괘선 {f['box']:.0f}% · 규범 {f['rule']:.2f} · 숫자 {_digits(sec['text']):.1f}%"
    if f["blank"] >= 30.0 and f["rule"] < 0.50:
        return "양식", f"빈 줄 {f['blank']:.0f}%"
    if f["rule"] >= 1.20:
        return "기준", f"규범 {f['rule']:.2f}/천자"
    if f["art"] >= 1.00:
        return "기준", f"조문 인용 {f['art']:.2f}/천자"
    return "기준", f"서식 신호 없음 (규범 {f['rule']:.2f} · 괘선 {f['box']:.0f}%)"


def split_tables(secs):
    """별표를 (기준, 양식) 으로 나눈다. 별표가 아닌 항목은 그대로 기준 쪽."""
    keep, drop = [], []
    for s in secs:
        if s["type"] != "별표":
            keep.append(s)
            continue
        kind, why = classify(s)
        s = {**s, "table_kind": kind, "table_why": why}
        (drop if kind == "양식" else keep).append(s)
    return keep, drop


# 이름만으로도 성격이 뚜렷한 것들. 사람이 확인할 때 뒤로 미뤄도 되는 것 표시용.
_OBVIOUS = re.compile(r"(별책서식|신청서|신고서|대차대조표|계산서|명세서|확인서|동의서|"
                      r"증명서|인가증|등록증|확인증|통보서|증표|지정명부|등록원부)")


def review_tier(s):
    """확인 우선순위. 내용 지표로만 판정한 것이 가장 틀리기 쉽다."""
    if not s["table_why"].startswith("이름:"):
        return "주의"
    return "확실" if _OBVIOUS.search(s["table_why"] + " " + (s["title"] or "")) else "보통"


def write_report(drop, path):
    """인덱스에서 뺀 것을 사람이 확인할 수 있게 마크다운으로 남긴다.
    판정 근거가 약한 순으로 정렬한다 — 위에서부터 보면 된다."""
    for s in drop:
        s["tier"] = review_tier(s)
    order = {"주의": 0, "보통": 1, "확실": 2}
    drop = sorted(drop, key=lambda s: (order[s["tier"]], -len(s["text"])))

    lines = [f"# 인덱스에서 뺀 별표 {len(drop)}개 — 수동 확인용", "",
             f"총 {sum(len(s['text']) for s in drop):,}자. "
             "**수집·변경 감지에는 그대로 있고 검색용 청크에만 안 들어갑니다.**", "",
             "원본은 뷰어에서 규정을 열고 좌측 드롭다운(또는 우측 점프 목록)에서 "
             "해당 별표를 고르면 됩니다.", "",
             "| 등급 | 뜻 | 개수 |", "|---|---|---:|"]
    desc = {"주의": "이름이 신호를 안 줘 **내용 지표로만** 판정 — 먼저 확인",
            "보통": "이름에 서식·양식·보고서 등이 있음",
            "확실": "이름에 신청서·통보서·인가증 등이 그대로 있음"}
    for t in ("주의", "보통", "확실"):
        lines.append(f"| {t} | {desc[t]} | {sum(1 for s in drop if s['tier'] == t)} |")

    cur = None
    for s in drop:
        if s["tier"] != cur:
            cur = s["tier"]
            n = sum(1 for x in drop if x["tier"] == cur)
            lines += ["", "", f"## [{cur}] {n}개", "",
                      "| 글자수 | 규정 | 별표 | 제목 | 판정 근거 |",
                      "|---:|---|---|---|---|"]
        lines.append(f"| {len(s['text']):,} | {s['reg']} | {s['key']} | "
                     f"{(s['title'] or '(제목 없음)').replace('|', '/')} | {s['table_why']} |")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return drop


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", choices=["양식", "기준"], help="해당 판정 항목 나열")
    ap.add_argument("--reg", help="이름 부분일치 대상만")
    ap.add_argument("--report", nargs="?", const=os.path.join(
        sections.OUT_DIR, "_rag", "제외_별표_목록.md"),
        help="제외 목록을 마크다운으로 저장")
    a = ap.parse_args()

    secs = sections.all_sections(a.reg)
    tb = [s for s in secs if s["type"] == "별표"]
    tot = sum(len(s["text"]) for s in secs)
    keep, drop = split_tables(secs)
    kt = [s for s in keep if s["type"] == "별표"]

    def sm(v):
        return sum(len(x["text"]) for x in v)

    print(f"전체 항목 {len(secs):,}개 · {tot:,}자")
    print(f"별표 {len(tb)}개 · {sm(tb):,}자 (전체의 {sm(tb)/tot*100:.1f}%)")
    print(f"  ├ 기준 {len(kt):3d}개 · {sm(kt):>9,}자  → 인덱스에 넣음")
    print(f"  └ 양식 {len(drop):3d}개 · {sm(drop):>9,}자  → 인덱스에서 뺌 "
          f"(전체의 {sm(drop)/tot*100:.1f}%)")
    print(f"\n인덱스 대상: {tot:,}자 → {tot - sm(drop):,}자")

    if a.report:
        write_report(drop, a.report)
        tiers = {t: sum(1 for s in drop if review_tier(s) == t)
                 for t in ("주의", "보통", "확실")}
        print(f"\n확인용 목록: {os.path.relpath(a.report, sections.ROOT)}  "
              + " · ".join(f"{k} {v}" for k, v in tiers.items()))

    if a.list:
        pool = drop if a.list == "양식" else kt
        print(f"\n[{a.list} {len(pool)}개]")
        for s in sorted(pool, key=lambda x: -len(x["text"])):
            print(f"  {len(s['text']):>8,}자  {s['key']:<14} "
                  f"{(s['title'] or '')[:34]:<34} {s['table_why']:<28} {s['reg'][:24]}")
    else:
        print("\n[양식으로 판정된 것 중 큰 것 12개]")
        for s in sorted(drop, key=lambda x: -len(x["text"]))[:12]:
            print(f"  {len(s['text']):>8,}자  {(s['title'] or s['key'])[:38]:<38} "
                  f"{s['table_why']:<30} {s['reg'][:22]}")
        print("\n[기준으로 판정된 것 중 큰 것 8개]")
        for s in sorted(kt, key=lambda x: -len(x["text"]))[:8]:
            print(f"  {len(s['text']):>8,}자  {(s['title'] or s['key'])[:38]:<38} "
                  f"{s['table_why']:<30} {s['reg'][:22]}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
