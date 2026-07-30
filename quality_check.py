# -*- coding: utf-8 -*-
"""
수집 품질 자동 점검 — '조용히 잘못된 결과'를 규칙으로 잡아낸다.

지금까지 발견된 문제들은 전부 **에러 없이 통과하던 것**들이었다.
  · 금투협 조제목 34개가 빈 문자열 → 섹션 키가 위치 기반이 됨
  · 첨부 목록 50줄이 마지막 부칙 본문에 딸려 들어감
  · 금투협 별표 50개를 아예 수집 안 함
  · 추출 실패 메시지가 규정 본문으로 저장됨
파일 개수·해시 검사(validate_outputs.py)로는 이런 게 안 잡힌다.
그래서 **내용이 그럴듯한지**를 규칙으로 본다.

  python quality_check.py            # 전체
  python quality_check.py --live     # 원본과 대조하는 항목까지(느림, 네트워크)
  python quality_check.py 은행        # 이름에 '은행'이 든 대상만

check_updates.py 가 수집 후 자동 호출한다. 결과는 output/_reports/quality_latest.md.
"""
import os
import re
import sys
import json
import argparse

sys.stdout.reconfigure(encoding="utf-8")

import law_scraper as L

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(ROOT, "output")
REPORTS = os.path.join(OUT_DIR, "_reports")

# 본문에 있으면 파싱이 잘못됐다는 신호 (원문에는 나올 수 없는 것들)
CONTAMINANTS = [
    (r"\.hwp\b|\.pdf\b|\.hwpx\b", "첨부 파일명이 본문에 섞임"),
    (r"<(?:div|td|tr|span|table|br|a)\b", "HTML 태그가 남음"),
    (r"&nbsp;|&amp;|&lt;|&gt;", "HTML 엔티티가 남음"),
    (r"javascript:|onclick=|href=", "스크립트/링크가 남음"),
    (r"\[추출실패|\[docproc 실패|Traceback", "오류 메시지가 본문에 저장됨"),
    (r"다운로드\(새창열림\)|새창열림", "UI 문구가 본문에 섞임"),
]

SEV = {"높음": 0, "중간": 1, "낮음": 2}


class Report:
    def __init__(self):
        self.items = []

    def add(self, target, sev, rule, detail):
        self.items.append({"대상": target, "심각도": sev, "항목": rule, "내용": detail})

    def of(self, target):
        return [i for i in self.items if i["대상"] == target]


# 가지번호(제2-5조의2)까지 포함해야 한다. 안 그러면 제2-5조와 제2-5조의2 를
# 같은 조문으로 보고 '중복'이라 오탐한다. ingest.py 의 키 생성 규칙과 동일하게 맞춘다.
_ARTNO = re.compile(r"제\s*\d+(?:-\d+)?조(?:의\s*\d+)?|제\s*\d+-\d+(?:의\s*\d+)?(?=\s*\()")


def _article_no(kind, a):
    """이 조문의 '조번호'를 찾는다. 소스마다 어디에 있는지가 다르다.
      · 법제처 법령   : 조문번호 필드 (숫자)
      · 법제처 행정규칙: 필드가 비어 있고 본문 첫머리에 있음 ("제1조(목적) …")
      · 금투협        : 조제목에 있음 ("제2-5조(설명의무 등)")
    """
    if kind == "kofia":
        t = a.get("조제목") or ""
        return _ARTNO.search(t).group(0) if _ARTNO.search(t) else ""
    no = str(a.get("조문번호") or "").strip()
    if no:
        br = str(a.get("조문가지번호") or "").strip()
        return f"제{no}조" + (f"의{br}" if br and br not in ("0", "00") else "")
    m = _ARTNO.search((a.get("조문내용") or "")[:40])   # 행정규칙: 본문 첫머리
    return m.group(0) if m else ""


def _is_deleted(kind, a):
    """'제2-9조 삭제' 처럼 폐지 표시만 남은 조문 — 본문이 비는 게 정상."""
    t = (a.get("조제목") if kind == "kofia" else a.get("조문제목")) or ""
    return "삭제" in t or "삭제" in (a.get("조문내용") or "")[:40]


def _sections(rec, kind):
    """조문/부칙/별표를 (구분, 조번호, 제목, 본문, 삭제여부) 목록으로."""
    out = []
    for a in rec.get("조문", []):
        # 편/장/절 제목은 조문이 아니다(조번호가 없는 게 정상) — 검사 대상에서 제외
        if a.get("구분"):
            continue
        title = (a.get("조제목") if kind == "kofia" else a.get("조문제목")) or ""
        text = (a.get("조내용") if kind == "kofia" else a.get("조문내용")) or ""
        out.append(("조문", _article_no(kind, a), title, text, _is_deleted(kind, a)))
    for i, ad in enumerate(rec.get("부칙", []), 1):
        out.append(("부칙", str(i), ad.get("부칙명", ""), ad.get("내용", ""), False))
    for t in rec.get("별표", []):
        out.append(("별표", str(t.get("별표번호") or t.get("번호") or ""),
                    t.get("제목") or t.get("파일명", ""), t.get("내용", ""),
                    bool(t.get("삭제여부"))))
    return out


def check_record(name, kind, rec, rep):
    secs = _sections(rec, kind)
    body = rec.get("본문", "")

    # ── 1. 본문 오염 ─────────────────────────────────────────────────
    for 구분, key, title, text, _del in secs:
        if 구분 == "별표":
            continue          # 별표는 파일명을 본문에 적어두는 게 정상
        for pat, why in CONTAMINANTS:
            m = re.search(pat, text or "")
            if m:
                snippet = re.sub(r"\s+", " ", (text or "")[max(0, m.start() - 40):m.start() + 60])
                rep.add(name, "높음", why, f"{구분} {key or title}: …{snippet}…")
                break
    if body:
        for pat, why in CONTAMINANTS[1:]:   # 협회 평문은 파일명 언급이 정상일 수 있음
            m = re.search(pat, body)
            if m:
                snippet = re.sub(r"\s+", " ", body[max(0, m.start() - 40):m.start() + 60])
                rep.add(name, "높음", why, f"본문: …{snippet}…")
                break

    # ── 2. 비어 있는 항목 (폐지 조문은 비는 게 정상) ────────────────
    empty_body = [f"{g} {k or t}" for g, k, t, x, d in secs
                  if g != "별표" and not d and not (x or "").strip()]
    if empty_body:
        rep.add(name, "높음", "본문이 빈 항목", f"{len(empty_body)}개: {empty_body[:5]}")

    # ── 3. 조문 키가 안정적인가 ──────────────────────────────────────
    arts = [(k, t, d) for g, k, t, x, d in secs if g == "조문"]
    # 심사지침·예규는 조문이 아니라 'Ⅰ. 목적 / Ⅱ. 적용범위' 로 구성된다.
    # 조번호가 없는 게 정상이므로 조번호 검사에서 제외한다.
    roman = sum(1 for g, k, t, x, d in secs
                if g == "조문" and re.match(r"\s*[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\s*\.", x or ""))
    if roman >= 2:
        arts = [a for a in arts if a[0]]
    # '머리말'은 조번호가 없는 게 정상이고(제1편 앞 안내문), 이름 자체가 고정 키라
    # 가짜 변경을 만들지 않는다. 조번호 검사 대상에서 뺀다.
    unnumbered = [(t or "(제목없음)")[:26] for k, t, d in arts
                  if not k and t != "머리말"]
    if unnumbered:
        rep.add(name, "높음", "조번호를 못 뽑은 조문",
                f"{len(unnumbered)}개 — 개정 시 가짜 변경이 대량 발생할 수 있음: {unnumbered[:3]}")
    dup = [k for k in {k for k, _t, _d in arts if k}
           if sum(1 for x, _t, _d in arts if x == k) > 1]
    if dup:
        rep.add(name, "중간", "조번호가 중복됨",
                f"{len(dup)}개: {sorted(dup)[:5]} — 섹션 키에 순번 접미가 붙는다")

    # ── 4. 첨부파일 정합 ─────────────────────────────────────────────
    fdir = os.path.join(OUT_DIR, "files", L._safe(name))
    # 하위 폴더(_img/)를 섞으면 0바이트 파일로 오인한다. 파일만 센다.
    on_disk = {f for f in os.listdir(fdir)
               if os.path.isfile(os.path.join(fdir, f))} if os.path.isdir(fdir) else set()
    want = set()
    for t in rec.get("별표", []):
        for k in ("저장PDF", "저장HWP", "저장파일"):
            if t.get(k):
                want.add(L._safe(t[k]))
    missing = want - on_disk
    if missing:
        rep.add(name, "높음", "받았어야 할 첨부가 없음",
                f"{len(missing)}개: {sorted(missing)[:3]}")
    tiny = [f for f in on_disk
            if os.path.getsize(os.path.join(fdir, f)) < 1024]
    if tiny:
        rep.add(name, "높음", "첨부가 비었거나 잘림(1KB 미만)", f"{len(tiny)}개: {tiny[:3]}")

    # ── 5. 첨부 추출 상태 ────────────────────────────────────────────
    # "파일은 받았다"와 "내용을 읽어냈다"는 다르다. 여기가 없으면 추출이 실패해도
    # 조용히 넘어가 '이상 없음'이 뜬다(실제로 51건이 그 상태였다).
    import attach_audit
    aud = attach_audit.audit_dir(fdir)

    # 5-1. 추출 실패 — 같은 이름 PDF 가 있으면 그쪽으로 내용이 확보되므로 심각도를 낮춘다
    failed = [f for f, r in aud.items() if r["err"]]
    fatal = [f for f in failed
             if not os.path.exists(os.path.join(fdir, os.path.splitext(f)[0] + ".pdf"))]
    if fatal:
        rep.add(name, "높음", "첨부 내용을 못 읽음(대체 PDF도 없음)",
                f"{len(fatal)}개: {fatal[:3]} — 이 별표는 내용이 비어 있는 셈")
    if len(failed) > len(fatal):
        covered = len(failed) - len(fatal)
        rep.add(name, "낮음", "첨부 추출 실패(같은 이름 PDF로 대체됨)",
                f"{covered}개 — 법제처가 HWPX를 .hwp 확장자로 주는 경우. 실질 누락은 없음")

    # 5-2. 이미지가 있는데 본문에 반영되지 않음 → 재수집 필요
    #      (extract() 가 이미지 목록을 본문 끝에 붙이고 _img/ 에 저장한다)
    with_img = {f: r["imgs"] for f, r in aud.items() if r["imgs"]}
    if with_img:
        saved = len(os.listdir(os.path.join(fdir, "_img"))) \
            if os.path.isdir(os.path.join(fdir, "_img")) else 0
        if not saved:
            rep.add(name, "중간", "본문 이미지가 수집 결과에 없음",
                    f"{len(with_img)}개 파일·이미지 {sum(with_img.values())}개 — "
                    f"재수집하면 _img/ 에 저장되고 본문에 목록이 붙는다")
    attach_audit.save()

# 뺀 규칙 (구조적으로 발동하지 않아 유지 비용만 든다)
#  · '통계와 실제 개수 불일치' — 수집기가 `"통계": {"조문수": len(articles)}, "조문": articles`
#    처럼 같은 변수로 둘 다 쓰므로 어긋날 수가 없다.
#  · '비정상적으로 긴 항목' — 본문 오염 검사와 겹치는데 정작 실제 사례(부칙에 첨부목록
#    50줄 혼입, 1,189자)는 중앙값 기준을 넘지 못해 못 잡았다. 오염 검사가 잡는다.


def check_live(name, kind, rec, rep):
    """원본과 대조해야만 알 수 있는 것 — '아예 안 가져온 것'을 잡는다.
    (금투협 별표 50개 누락이 이 검사로 잡혔어야 했다)"""
    if kind == "kofia":
        import kofia_scraper as K
        found = K._find_in_tree(name)
        if not found:
            rep.add(name, "높음", "원본에서 규정을 못 찾음", "이름 변경 여부 확인 필요")
            return
        html = K._get(f"{K.BODY_URL}?seq={found[1]}&historySeq={found[2]}")
        src_tables = len(K.parse_attachments(html))
        got = len(rec.get("별표", []))
        if src_tables != got:
            rep.add(name, "높음", "원본 별표 수와 수집 수가 다름",
                    f"원본 {src_tables}개 vs 수집 {got}개")
        src_arts = len(re.findall(r'<div class="JO"', K._strip_attachment_block(html)))
        if src_arts and abs(src_arts - len(rec.get("조문", []))) > 0:
            rep.add(name, "중간", "원본 조문 수와 다름",
                    f"원본 {src_arts}개 vs 수집 {len(rec.get('조문', []))}개")

    elif kind in ("law", "admrul"):
        meta = L.current_meta(name, kind)
        if not meta:
            rep.add(name, "높음", "원본에서 규정을 못 찾음", "이름 변경 여부 확인 필요")
            return
        body = L.fetch_body(meta)
        pairs = [("조문", len(L.parse_articles_law(body) if kind == "law"
                             else L.parse_articles_admrul(body)), len(rec.get("조문", []))),
                 ("부칙", len(L.parse_addenda(body)), len(rec.get("부칙", []))),
                 ("별표", len(L.parse_tables(body)), len(rec.get("별표", [])))]
        for label, src, got in pairs:
            if src != got:
                rep.add(name, "중간", f"원본 {label} 수와 다름",
                        f"원본 {src}개 vs 수집 {got}개 (재수집 필요 여부 확인)")


def run(only=None, live=False):
    targets = json.load(open(os.path.join(ROOT, "targets.json"), encoding="utf-8"))
    if only:
        keys = [o.replace(" ", "") for o in only]
        targets = [t for t in targets
                   if any(k in t["name"].replace(" ", "") for k in keys)]
    rep = Report()
    checked = 0
    for t in targets:
        name, kind = t["name"], t["kind"]
        p = os.path.join(OUT_DIR, L._safe(name) + ".json")
        if not os.path.exists(p):
            rep.add(name, "중간", "수집 결과 없음", "check_updates.py 먼저 실행")
            continue
        rec = json.load(open(p, encoding="utf-8"))
        check_record(name, kind, rec, rep)
        if live:
            try:
                check_live(name, kind, rec, rep)
            except Exception as e:
                rep.add(name, "낮음", "원본 대조 실패(일시적 접속 문제일 수 있음)", str(e)[:80])
        checked += 1

    # ── 출력 ────────────────────────────────────────────────────────
    items = sorted(rep.items, key=lambda i: (SEV[i["심각도"]], i["대상"]))
    high = sum(1 for i in items if i["심각도"] == "높음")
    mid = sum(1 for i in items if i["심각도"] == "중간")
    print(f"수집 품질 점검 — 대상 {checked}건{' (원본 대조 포함)' if live else ''}")
    print("=" * 62)
    if not items:
        print("이상 없음")
    cur = None
    for i in items:
        if i["대상"] != cur:
            cur = i["대상"]
            print(f"\n[{cur}]")
        print(f"  {i['심각도']}  {i['항목']}")
        print(f"       {i['내용'][:150]}")
    print("\n" + "=" * 62)
    print(f"높음 {high} · 중간 {mid} · 낮음 {len(items) - high - mid}")

    os.makedirs(REPORTS, exist_ok=True)
    with open(os.path.join(REPORTS, "quality_latest.md"), "w", encoding="utf-8") as f:
        f.write(f"# 수집 품질 점검\n\n대상 {checked}건 · 높음 {high} · 중간 {mid}\n\n")
        f.write("| 심각도 | 대상 | 항목 | 내용 |\n|---|---|---|---|\n")
        for i in items:
            f.write(f"| {i['심각도']} | {i['대상']} | {i['항목']} | "
                    f"{i['내용'][:200].replace('|', '/')} |\n")
    return high


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("only", nargs="*")
    ap.add_argument("--live", action="store_true", help="원본과 대조(느림)")
    a = ap.parse_args()
    sys.exit(1 if run(a.only or None, a.live) else 0)
