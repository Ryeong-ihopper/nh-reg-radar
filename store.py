# -*- coding: utf-8 -*-
"""
파이프라인 실행 중 DB 기록 (실행 이력 · 변경 · 알림).

check_updates.py 가 감지/수집을 하고, 그 결과를 이 모듈이 DB에 남긴다.
DB 사용이 불가능한 상황(파일 잠김 등)에서도 감지 자체는 계속 돌아야 하므로
호출부에서 예외를 잡아 경고만 내고 진행하도록 설계했다.
"""
import json

import db
import ingest


def start_run(con, run_mode, trigger="manual"):
    cur = con.execute(
        "INSERT INTO collection_runs (started_at, run_mode, trigger, status)"
        " VALUES (?,?,?,'running')", (db.now_iso(), run_mode, trigger))
    return cur.lastrowid


def finish_run(con, run_id, summary, report, status="success"):
    con.execute(
        "UPDATE collection_runs SET finished_at=?, total_count=?, unchanged_count=?,"
        " new_count=?, changed_count=?, error_count=?, status=?, report=? WHERE run_id=?",
        (db.now_iso(), summary.get("전체", 0), summary.get("동일", 0), summary.get("신규", 0),
         summary.get("변경", 0), summary.get("에러", 0), status,
         json.dumps(report, ensure_ascii=False), run_id))


def current_version_id(con, name, kind):
    """변경 전 현재본 version_id (없으면 None)."""
    sid = db.source_id(con, kind)
    row = con.execute(
        "SELECT v.version_id FROM regulation_versions v JOIN regulations r USING(regulation_id)"
        " WHERE r.source_id=? AND r.name=? AND v.is_current=1", (sid, name)).fetchone()
    return row["version_id"] if row else None


def record_collection(con, run_id, record, kind, safe_name, status, reason, old_vid):
    """수집 결과를 버전으로 적재하고, 변경이면 change/section_change/알림까지 생성.
    change_id (변경 없으면 None) 반환."""
    new_vid, is_new = ingest.ingest_version(con, record, kind, safe_name)
    if not is_new or new_vid == old_vid:
        return None

    rid = con.execute("SELECT regulation_id FROM regulation_versions WHERE version_id=?",
                      (new_vid,)).fetchone()["regulation_id"]
    cur = con.execute(
        "INSERT INTO regulation_changes (run_id, regulation_id, old_version_id, new_version_id,"
        " change_reason, created_at) VALUES (?,?,?,?,?,?)"
        " ON CONFLICT(old_version_id, new_version_id) DO NOTHING",
        (run_id, rid, old_vid, new_vid, reason or status, db.now_iso()))
    if not cur.lastrowid:
        return None
    change_id = cur.lastrowid

    if old_vid is None:
        # 최초 수집: 비교 대상이 없다. 전 조문을 '신설'로 쏟아내면 노이즈만 되므로
        # 변경 이벤트는 남기되 섹션 diff 는 만들지 않는다.
        n = con.execute("SELECT COUNT(*) c FROM regulation_sections WHERE version_id=?",
                        (new_vid,)).fetchone()["c"]
        summary = f"최초 수집 (섹션 {n}개)"
        con.execute("UPDATE regulation_changes SET summary=? WHERE change_id=?",
                    (summary, change_id))
    else:
        added, removed, modified = ingest.record_section_diff(con, change_id, old_vid, new_vid)
        summary = f"신설 {added} · 삭제 {removed} · 변경 {modified}"
        con.execute(
            "UPDATE regulation_changes SET changed_section_count=?, added_section_count=?,"
            " removed_section_count=?, summary=? WHERE change_id=?",
            (modified, added, removed, summary, change_id))

    fan_out_notifications(con, change_id, record.get("법령명", safe_name), kind, status, summary)
    return change_id


def notify_failures(con, run_id, failures):
    """조회 실패를 알림으로 남긴다.

    협회 사이트는 간헐적으로 접속이 끊긴다(금투협은 실측 3회 중 1회). 월 1회
    실행에서 실패가 조용히 지나가면 **그 규정의 개정을 한 달 동안 놓친다**.
    변경 알림과 같은 곳에 쌓아 사람이 반드시 보게 한다.
    """
    if not failures:
        return 0
    body = " · ".join(f"{f['법령명']}({f.get('변경사유') or f.get('상태')})"
                      for f in failures)
    title = f"[확인 필요] 규정 {len(failures)}건 조회 실패"
    n = 0
    for p in con.execute("SELECT profile_id FROM watch_profiles WHERE active=1"):
        con.execute(
            "INSERT INTO notifications (profile_id, change_id, title, body, created_at)"
            " SELECT ?, NULL, ?, ?, ? WHERE NOT EXISTS ("
            "  SELECT 1 FROM notifications WHERE profile_id=? AND change_id IS NULL"
            "   AND title=? AND is_read=0)",
            (p["profile_id"], title, body, db.now_iso(), p["profile_id"], title))
        n += 1
    return n


def fan_out_notifications(con, change_id, name, kind, status, summary):
    """구독 조건에 맞는 감시 프로파일에 알림 생성 (빈 필터 = 전체 구독)."""
    code = db.SOURCE_SEED[kind][0]
    for p in con.execute("SELECT * FROM watch_profiles WHERE active=1"):
        codes = db.jload(p["source_codes"], [])
        names = db.jload(p["regulation_names"], [])
        if codes and code not in codes:
            continue
        if names and name not in names:
            continue
        con.execute(
            "INSERT OR IGNORE INTO notifications (profile_id, change_id, title, body,"
            " created_at) VALUES (?,?,?,?,?)",
            (p["profile_id"], change_id, f"[{status}] {name}", summary, db.now_iso()))
