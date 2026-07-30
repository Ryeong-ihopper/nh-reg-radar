# -*- coding: utf-8 -*-
"""
연혁을 제공하지 않는 소스(행정규칙·여신협·은행연)에 **가상 과거본**을 넣어
변경 감지·조문 diff 화면을 검수할 수 있게 한다.

주의 — 데이터 오염을 막기 위한 설계
  · 가짜는 항상 **과거본**으로만 넣는다. 현재본은 실제 수집 결과 그대로 유지된다.
  · 변경 사유에 "시뮬레이션"을 명시해 화면에서 진짜 개정과 구분된다.
  · `--clear` 로 언제든 되돌릴 수 있다(가상 이력만 지우고 현재본은 남긴다).

  python seed_demo.py           # 대상 전체에 가상 과거본 적재
  python seed_demo.py --clear   # 가상 이력 제거
"""
import os
import sys

# 파이프라인 모듈은 src/ 에 있다. 이 스크립트는 한 단계 아래 폴더에서 직접 실행되므로
# import 경로에 src/ 를 먼저 넣어 준다.
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import os
import re
import sys
import json
import copy
import hashlib

sys.stdout.reconfigure(encoding="utf-8")

import db
import store
import law_scraper as L
from content_hash import sha256_structure

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "output")
REASON = "시뮬레이션 — 실제 개정 아님(검수용 가상 과거본)"

# 연혁을 제공하지 않아 실제 과거본을 못 받는 소스
DEMO_KINDS = ("admrul", "crefia", "kfb")

# '과거에는 이랬다'고 가정할 치환 규칙. 현재본에 이 문구가 있으면 옛 표현으로 되돌린다.
# (실제 개정에서 흔한 유형: 금액 상향, 기간 연장, 기관명 변경, 단서 신설)
ROLLBACKS = [
    ("금융위원회", "금융감독위원회"),
    ("영업일", "근무일"),
    ("100분의 50", "100분의 30"),
    ("100분의 20", "100분의 10"),
    ("3년", "2년"),
    ("30일", "15일"),
    ("10일", "7일"),
    ("5일", "3일"),
    ("전자문서", "전자적 방법"),
    ("금융소비자", "금융이용자"),
]


def _rollback_text(s, budget):
    """현재 문구 일부를 '옛 표현'으로 되돌린다. budget 만큼만 바꾼다."""
    n = 0
    for new, old in ROLLBACKS:
        if budget <= n:
            break
        if new in s:
            s = s.replace(new, old, 1)
            n += 1
    return s, n


def make_fake_old(record, kind):
    """현재본 → 가상 과거본. (레코드, 변경요약) 반환.
    현재본 기준으로 보면 '수정 몇 건 + 신설 1 + 삭제 1'이 감지되도록 만든다."""
    old = copy.deepcopy(record)
    notes = []

    if kind == "admrul":
        arts = old.get("조문", [])
        if len(arts) < 4:
            return None, None
        # (1) 앞쪽 조문 몇 개의 문구를 옛 표현으로 → 현재본에서 '수정'으로 잡힘
        changed = 0
        for a in arts:
            if changed >= 3:
                break
            t, n = _rollback_text(a["조문내용"], 2)
            if n:
                a["조문내용"] = t
                changed += 1
        notes.append(f"수정 {changed}")
        # (2) 현재본에 있는 조문 하나를 과거본에서 빼기 → 현재본에서 '신설'로 잡힘
        removed = arts.pop(len(arts) // 2)
        notes.append("신설 1")
        # (3) 과거본에만 있는 폐지 조문 추가 → 현재본에서 '삭제'로 잡힘
        arts.append({"조문번호": "999", "조문가지번호": "", "조문제목": "",
                     "조문내용": "제999조(경과조치) 종전 규정에 따라 처리 중인 사항은 "
                                 "종전의 예에 따른다. (이 조는 이후 개정으로 삭제되었다)",
                     "항": []})
        notes.append("삭제 1")
        old["본문해시"] = sha256_structure({
            "조문": arts, "부칙": old.get("부칙", []),
            "별표": old.get("별표", []), "첨부파일": old.get("첨부파일", [])})
        old["공식버전키"] = _older_key(record.get("공식버전키", ""))
        old["버전키"] = old["공식버전키"] + "|sha256:" + old["본문해시"]
        old["시행일자"] = _older_date(record.get("시행일자", ""))
        old["공포일자"] = _older_date(record.get("공포일자", ""))
        plain = _admrul_text(old)

    else:   # crefia / kfb — 본문이 평문 텍스트뿐
        body = old.get("본문", "")
        if len(body) < 500:
            return None, None
        lines = body.split("\n")
        changed = 0
        for i, ln in enumerate(lines):
            if changed >= 4:
                break
            t, n = _rollback_text(ln, 1)
            if n:
                lines[i] = t
                changed += 1
        notes.append(f"수정 {changed}")
        # 조문 하나를 통째로 빼서 현재본에서 '신설'로 보이게
        art_idx = [i for i, ln in enumerate(lines) if re.match(r"\s*제\s*\d+\s*조", ln)]
        if len(art_idx) >= 4:
            s = art_idx[len(art_idx) // 2]
            e = art_idx[len(art_idx) // 2 + 1]
            del lines[s:e]
            notes.append("신설 1")
        # 과거본에만 있던 조문 추가 → 현재본에서 '삭제'로 보이게
        lines += ["", "제999조(경과조치) 종전 규정에 따라 처리 중인 사항은 종전의 예에 따른다.",
                  "(이 조는 이후 개정으로 삭제되었다)"]
        notes.append("삭제 1")
        old["본문"] = "\n".join(lines)
        old["sha256"] = hashlib.sha256(old["본문"].encode("utf-8")).hexdigest()
        old["버전키"] = "sha256:" + old["sha256"]
        old.pop("공식버전키", None)
        old["시행일자"] = _older_date(record.get("시행일자", ""))
        plain = (f"{old['법령명']}\n[{old.get('발행기관','')}] "
                 f"시행 {old['시행일자']} · (시뮬레이션 가상 과거본)\n"
                 + "=" * 70 + "\n\n" + old["본문"])

    return (old, plain), " · ".join(notes)


def _admrul_text(rec):
    return L.to_text(
        f"{rec['법령명']}\n[{rec.get('법종구분','')}] 공포 {rec.get('공포일자','?')} · "
        f"시행 {rec.get('시행일자','?')} · (시뮬레이션 가상 과거본)",
        rec.get("조문", []), rec.get("부칙", []), rec.get("별표", []),
        rec.get("첨부파일", []))


def _older_date(d):
    """시행일을 1년 앞으로 (가상 과거본 표시용)."""
    if re.fullmatch(r"\d{8}", d or ""):
        return f"{int(d[:4]) - 1}{d[4:]}"
    return d


def _older_key(k):
    parts = (k or "").split("|")
    if len(parts) == 3:
        return f"{parts[0]}D|{_older_date(parts[1])}|{parts[2]}"
    return (k or "DEMO") + "|DEMO-OLD"


# ── 적재 / 제거 ─────────────────────────────────────────────────────────
def clear(con):
    """가상 이력 제거. 현재본(실제 수집 결과)은 그대로 둔다.

    적재할 때 규정마다 기록을 **둘** 만든다(가상 과거본 적재 + 변경).
    시뮬레이션 표시가 붙은 쪽만 지우면 나머지가 과거본 버전을 계속 참조해
    외래키 제약에 걸린다. 그래서 해당 규정의 기록을 통째로 정리한다.
    (가상 이력은 연혁을 제공하지 않는 소스에만 넣으므로, 실제 과거 버전과
     섞일 일이 없다 — seed_history 는 law/kofia 만 다룬다)
    """
    rids = [r["regulation_id"] for r in con.execute(
        "SELECT DISTINCT regulation_id FROM regulation_changes WHERE change_reason=?",
        (REASON,))]
    if not rids:
        print("제거할 가상 이력이 없습니다.")
        return 0
    n = 0
    for rid in rids:
        con.execute("DELETE FROM regulation_section_changes WHERE change_id IN"
                    " (SELECT change_id FROM regulation_changes WHERE regulation_id=?)", (rid,))
        n += con.execute("DELETE FROM regulation_changes WHERE regulation_id=?",
                         (rid,)).rowcount
        # 현재본이 아닌(=가상 과거본) 버전만 삭제
        for v in con.execute("SELECT version_id FROM regulation_versions"
                             " WHERE regulation_id=? AND is_current=0", (rid,)).fetchall():
            con.execute("DELETE FROM regulation_sections WHERE version_id=?", (v["version_id"],))
            con.execute("DELETE FROM regulation_versions WHERE version_id=?", (v["version_id"],))
    print(f"가상 이력 제거: 규정 {len(rids)}건 · 변경기록 {n}건 (현재본은 유지)")
    return n


def seed_one(con, run_id, name, kind):
    safe = L._safe(name)
    p = os.path.join(OUT_DIR, safe + ".json")
    if not os.path.exists(p):
        print("  건너뜀 — 현재본 수집 결과 없음")
        return False
    new_rec = json.load(open(p, encoding="utf-8"))
    built, notes = make_fake_old(new_rec, kind)
    if not built:
        print("  건너뜀 — 본문이 너무 짧아 가상 과거본을 만들 수 없음")
        return False
    old_rec, old_plain = built

    sid = db.source_id(con, kind)
    row = con.execute("SELECT regulation_id FROM regulations WHERE source_id=? AND name=?",
                      (sid, name)).fetchone()
    if row:
        rid = row["regulation_id"]
        con.execute("UPDATE regulations SET current_version_id=NULL WHERE regulation_id=?", (rid,))
        con.execute("DELETE FROM regulation_section_changes WHERE change_id IN"
                    " (SELECT change_id FROM regulation_changes WHERE regulation_id=?)", (rid,))
        con.execute("DELETE FROM regulation_changes WHERE regulation_id=?", (rid,))
        con.execute("DELETE FROM regulation_versions WHERE regulation_id=?", (rid,))

    tmp_name = safe + ".__demo__"
    tmp = os.path.join(OUT_DIR, tmp_name + ".txt")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(old_plain)
    try:
        store.record_collection(con, run_id, dict(old_rec, 법령명=name), kind,
                                tmp_name, "신규", "가상 과거본 적재", None)
    finally:
        os.remove(tmp)

    old_vid = store.current_version_id(con, name, kind)
    cid = store.record_collection(con, run_id, new_rec, kind, safe, "변경", REASON, old_vid)
    if not cid:
        print("  변경이 감지되지 않음(치환 대상 문구가 없었을 수 있음)")
        return False
    ch = con.execute("SELECT summary FROM regulation_changes WHERE change_id=?",
                     (cid,)).fetchone()
    print(f"  → change #{cid} · {ch['summary']}  (의도: {notes})")
    return True


def main():
    con = db.init()
    if "--clear" in sys.argv[1:]:
        with con:
            clear(con)
        con.close()
        return 0

    targets = [t for t in json.load(open(os.path.join(ROOT, "targets.json"), encoding="utf-8"))
               if t["kind"] in DEMO_KINDS]
    run_id = store.start_run(con, "demo-seed", "manual")
    n = 0
    print("가상 과거본 적재 (현재본은 실제 데이터 그대로 유지)")
    with con:
        for t in targets:
            print(f"[{t['kind']}] {t['name']}")
            try:
                n += seed_one(con, run_id, t["name"], t["kind"])
            except Exception as e:
                print(f"  실패: {e}")
        store.finish_run(con, run_id, {"전체": len(targets), "변경": n, "신규": 0,
                                       "동일": len(targets) - n, "에러": 0}, {})
    con.close()
    print(f"\n가상 개정 이력 {n}건 생성 — 되돌리려면: python seed_demo.py --clear")
    return 0


if __name__ == "__main__":
    sys.exit(main())
