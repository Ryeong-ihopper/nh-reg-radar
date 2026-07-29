# -*- coding: utf-8 -*-
"""
운영 안전장치 검증 (네트워크 없이).

월 1회 실행이라 실패가 조용히 지나가면 그 주기의 개정을 통째로 놓친다.
여기서는 '실패했을 때 사람이 반드시 알게 되는가'를 확인한다.
"""
import os
import sys
import json
import shutil
import tempfile

sys.stdout.reconfigure(encoding="utf-8")

import db
import store

def _need_output(*names):
    """수집 결과가 있어야 돌 수 있는 테스트. 없으면 안내하고 건너뛴다."""
    missing = [n for n in names if not os.path.exists(f"output/{n}.json")]
    if missing:
        print("건너뜀 — 수집 결과가 없습니다. 먼저 실행하세요:")
        print("    python check_updates.py")
        print(f"  (필요 파일: {', '.join(missing)})")
        sys.exit(0)

_need_output("금융소비자 보호에 관한 법률")

fails = []


def check(label, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {label}{(' — ' + detail) if detail else ''}")
    if not cond:
        fails.append(label)


tmpdir = tempfile.mkdtemp(prefix="reg_res_")
try:
    con = db.init(os.path.join(tmpdir, "t.db"))

    print("[조회 실패 알림]")
    run_id = store.start_run(con, "normal", "test")
    failed = [
        {"법령명": "금융투자회사의 영업 및 업무에 관한 규정", "상태": "에러",
         "변경사유": "조회 오류"},
        {"법령명": "은행 광고심의 기준 및 세칙", "상태": "검색실패",
         "변경사유": "공식 소스 검색 결과 없음"},
    ]
    with con:
        store.notify_failures(con, run_id, failed)
    rows = con.execute("SELECT * FROM notifications WHERE change_id IS NULL").fetchall()
    check("실패 알림이 생성됨", len(rows) >= 1, f"{len(rows)}건")
    if rows:
        check("제목에 건수 표시", "2건" in rows[0]["title"], rows[0]["title"])
        check("본문에 규정명 포함",
              all(f["법령명"][:6] in rows[0]["body"] for f in failed))
        check("미읽음 상태", rows[0]["is_read"] == 0)

    print("[중복 알림 방지]")
    before = con.execute("SELECT COUNT(*) c FROM notifications").fetchone()["c"]
    with con:
        store.notify_failures(con, run_id, failed)   # 같은 실패가 또 발생
    after = con.execute("SELECT COUNT(*) c FROM notifications").fetchone()["c"]
    check("안 읽은 같은 알림은 중복 생성 안 함", before == after, f"{before}→{after}")

    print("[변경 알림과 함께 조회되는가]")
    # 변경 알림 하나를 섞어 넣고 둘 다 나오는지 (API 가 INNER JOIN 이면 실패분이 사라짐)
    base = json.load(open("output/금융소비자 보호에 관한 법률.json", encoding="utf-8"))
    with con:
        store.record_collection(con, run_id, base, "law", "금융소비자 보호에 관한 법률",
                                "신규", "최초 수집", None)
    rows = con.execute(
        """SELECT n.title, CASE WHEN n.change_id IS NULL THEN 'failure' ELSE 'change' END k
           FROM notifications n
           JOIN watch_profiles p USING(profile_id)
           LEFT JOIN regulation_changes c ON c.change_id = n.change_id
           ORDER BY n.notification_id""").fetchall()
    kinds = {r["k"] for r in rows}
    check("변경·실패 알림이 한 목록에 함께 보임", kinds == {"failure", "change"}, str(kinds))

    print("[구버전 DB 마이그레이션]")
    old = os.path.join(tmpdir, "old.db")
    c2 = db.connect(old)
    with c2:
        c2.executescript("""
            CREATE TABLE watch_profiles (profile_id INTEGER PRIMARY KEY, name TEXT,
                source_codes TEXT, regulation_names TEXT, active INTEGER DEFAULT 1,
                created_at TEXT);
            CREATE TABLE regulation_changes (change_id INTEGER PRIMARY KEY,
                created_at TEXT);
            CREATE TABLE notifications (
                notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER NOT NULL,
                change_id  INTEGER NOT NULL,
                title TEXT NOT NULL, body TEXT NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
                UNIQUE (profile_id, change_id));
        """)
    c2.close()
    c3 = db.init(old)
    nn = {r["name"]: r for r in c3.execute("PRAGMA table_info(notifications)")}
    check("change_id 가 NULL 허용으로 바뀜", nn["change_id"]["notnull"] == 0)
    c3.close()

    con.close()
finally:
    shutil.rmtree(tmpdir, ignore_errors=True)

print()
if fails:
    print(f"실패 {len(fails)}건: {', '.join(fails)}")
    sys.exit(1)
print("전부 통과")
