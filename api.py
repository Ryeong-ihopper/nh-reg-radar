# -*- coding: utf-8 -*-
"""
규정 변경 감지 REST API (FastAPI).

실행:  uvicorn api:app --reload --port 8000
문서:  http://localhost:8000/docs

엔드포인트
  GET  /api/health
  GET  /api/regulations                          규정 목록(현재본 요약)
  GET  /api/regulations/{regulation_id}          규정 상세 + 버전 이력
  GET  /api/versions/{version_id}/sections       특정 버전의 조문 목록
  GET  /api/regulation-changes                   변경 목록(피드)
  GET  /api/regulation-changes/{change_id}       변경 상세(섹션별 diff)
  POST /api/regulation-changes/detect            변경 감지 수동 트리거(백그라운드)
  GET  /api/runs                                 실행 이력
  GET  /api/runs/{run_id}                        실행 상세
  GET  /api/notifications                        알림 조회(profile_id, is_read 필터)
  POST /api/notifications/{id}/read              알림 읽음 처리
  GET  /api/watch-profiles                       감시 프로파일 목록
  POST /api/watch-profiles                       감시 프로파일 생성
  GET  /api/search?q=                            조문 전문 검색
"""
import os
import sys
import json
import threading
from datetime import datetime

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import db

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

app = FastAPI(
    title="규정 변경 감지 API",
    description="법제처·금융투자협회·여신금융협회·전국은행연합회 규정의 "
                "수집·버전관리·변경감지 결과를 조회한다.",
    version="1.0.0",
)

# 감지 작업은 수 분 걸리고 외부 사이트를 때리므로 동시에 두 번 돌지 않게 막는다
_detect_lock = threading.Lock()
_detect_state = {"running": False, "started_at": None, "last_run_id": None}


def q(sql, args=(), one=False):
    con = db.connect()
    try:
        rows = con.execute(sql, args).fetchall()
    finally:
        con.close()
    if one:
        return dict(rows[0]) if rows else None
    return [dict(r) for r in rows]


# ── 기본 ────────────────────────────────────────────────────────────────
@app.get("/api/health", tags=["시스템"])
def health():
    if not os.path.exists(db.DB_PATH):
        return JSONResponse({"status": "no_db", "db": db.DB_PATH}, status_code=503)
    counts = q("""SELECT
        (SELECT COUNT(*) FROM regulations)        AS regulations,
        (SELECT COUNT(*) FROM regulation_versions) AS versions,
        (SELECT COUNT(*) FROM regulation_changes)  AS changes,
        (SELECT COUNT(*) FROM collection_runs)     AS runs,
        (SELECT COUNT(*) FROM notifications WHERE is_read=0) AS unread""", one=True)
    return {"status": "ok", "db": db.DB_PATH, "counts": counts,
            "detect_running": _detect_state["running"]}


# ── 규정 / 버전 / 조문 ──────────────────────────────────────────────────
@app.get("/api/regulations", tags=["규정"])
def list_regulations(source_code: str | None = None):
    sql = """SELECT r.regulation_id, r.name, r.document_type, r.external_id,
                    s.source_code, s.source_name,
                    v.version_id AS current_version_id, v.official_version_key,
                    v.effective_at, v.content_hash, v.collected_at,
                    (SELECT COUNT(*) FROM regulation_sections WHERE version_id=v.version_id) AS section_count,
                    (SELECT COUNT(*) FROM regulation_versions WHERE regulation_id=r.regulation_id) AS version_count
             FROM regulations r
             JOIN regulation_sources s USING(source_id)
             LEFT JOIN regulation_versions v ON v.version_id = r.current_version_id
             WHERE (? IS NULL OR s.source_code = ?)
             ORDER BY s.source_code, r.name"""
    return {"items": q(sql, (source_code, source_code))}


@app.get("/api/regulations/{regulation_id}", tags=["규정"])
def get_regulation(regulation_id: int):
    reg = q("""SELECT r.*, s.source_code, s.source_name FROM regulations r
               JOIN regulation_sources s USING(source_id) WHERE regulation_id=?""",
            (regulation_id,), one=True)
    if not reg:
        raise HTTPException(404, "규정을 찾을 수 없습니다")
    reg["versions"] = q(
        """SELECT version_id, official_version_key, content_hash, effective_at,
                  collected_at, is_current, validation_status, source_url,
                  (SELECT COUNT(*) FROM regulation_sections WHERE version_id=v.version_id) AS section_count
           FROM regulation_versions v WHERE regulation_id=?
           ORDER BY version_id DESC""", (regulation_id,))
    return reg


@app.get("/api/versions/{version_id}/sections", tags=["규정"])
def get_sections(version_id: int, section_type: str | None = None,
                 include_content: bool = True):
    ver = q("SELECT version_id FROM regulation_versions WHERE version_id=?",
            (version_id,), one=True)
    if not ver:
        raise HTTPException(404, "버전을 찾을 수 없습니다")
    col = "content" if include_content else "substr(content,1,120) AS content"
    rows = q(f"""SELECT section_id, section_key, section_type, sequence_no, title,
                        {col}, content_hash, metadata
                 FROM regulation_sections WHERE version_id=?
                   AND (? IS NULL OR section_type=?)
                 ORDER BY sequence_no""", (version_id, section_type, section_type))
    for r in rows:
        r["metadata"] = db.jload(r.get("metadata"), {})
    return {"version_id": version_id, "count": len(rows), "items": rows}


# ── 변경 피드 ───────────────────────────────────────────────────────────
@app.get("/api/regulation-changes", tags=["변경"])
def list_changes(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0),
                 source_code: str | None = None, regulation_id: int | None = None):
    where = """WHERE (? IS NULL OR s.source_code = ?)
                 AND (? IS NULL OR c.regulation_id = ?)"""
    args = (source_code, source_code, regulation_id, regulation_id)
    total = q(f"""SELECT COUNT(*) AS n FROM regulation_changes c
                  JOIN regulations r USING(regulation_id)
                  JOIN regulation_sources s USING(source_id) {where}""",
              args, one=True)["n"]
    items = q(f"""SELECT c.change_id, c.run_id, c.regulation_id, r.name AS regulation_name,
                         s.source_code, s.source_name, c.old_version_id, c.new_version_id,
                         c.change_reason, c.summary, c.added_section_count,
                         c.removed_section_count, c.changed_section_count, c.created_at,
                         nv.effective_at AS new_effective_at,
                         nv.official_version_key AS new_version_key,
                         ov.official_version_key AS old_version_key
                  FROM regulation_changes c
                  JOIN regulations r USING(regulation_id)
                  JOIN regulation_sources s USING(source_id)
                  LEFT JOIN regulation_versions nv ON nv.version_id=c.new_version_id
                  LEFT JOIN regulation_versions ov ON ov.version_id=c.old_version_id
                  {where} ORDER BY c.created_at DESC, c.change_id DESC
                  LIMIT ? OFFSET ?""", args + (limit, offset))
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@app.get("/api/regulation-changes/{change_id}", tags=["변경"])
def get_change(change_id: int, max_content: int = Query(4000, ge=0, le=100000)):
    ch = q("""SELECT c.*, r.name AS regulation_name, s.source_code, s.source_name,
                     nv.official_version_key AS new_version_key, nv.effective_at AS new_effective_at,
                     ov.official_version_key AS old_version_key
              FROM regulation_changes c
              JOIN regulations r USING(regulation_id)
              JOIN regulation_sources s USING(source_id)
              LEFT JOIN regulation_versions nv ON nv.version_id=c.new_version_id
              LEFT JOIN regulation_versions ov ON ov.version_id=c.old_version_id
              WHERE change_id=?""", (change_id,), one=True)
    if not ch:
        raise HTTPException(404, "변경 내역을 찾을 수 없습니다")
    secs = q("""SELECT section_change_id, section_key, change_type, old_content,
                       new_content, diff
                FROM regulation_section_changes WHERE change_id=?
                ORDER BY section_change_id""", (change_id,))
    if max_content:
        for s in secs:
            for k in ("old_content", "new_content", "diff"):
                if s[k] and len(s[k]) > max_content:
                    s[k] = s[k][:max_content] + f"\n…({len(s[k]) - max_content}자 생략)"
    ch["sections"] = secs
    return ch


# ── 수동 트리거 ─────────────────────────────────────────────────────────
class DetectRequest(BaseModel):
    deep: bool = Field(False, description="본문 구조 해시까지 정밀 검사(느림)")
    dry: bool = Field(False, description="감지만 하고 재수집·적재는 하지 않음")


def _run_detection(deep, dry):
    import check_updates
    try:
        check_updates.run(dry=dry, deep=deep, use_db=True, trigger="api")
        row = q("SELECT MAX(run_id) AS id FROM collection_runs", one=True)
        _detect_state["last_run_id"] = row["id"] if row else None
    except Exception as e:
        print(f"[API] 감지 실행 실패: {e}")
    finally:
        _detect_state["running"] = False
        if _detect_lock.locked():
            _detect_lock.release()


@app.post("/api/regulation-changes/detect", status_code=202, tags=["변경"])
def trigger_detect(req: DetectRequest, background: BackgroundTasks):
    """변경 감지를 백그라운드로 시작한다. 수 분 걸리므로 즉시 202 를 반환하고,
    진행 상황은 GET /api/runs 로 확인한다."""
    if not _detect_lock.acquire(blocking=False):
        raise HTTPException(409, "이미 감지 작업이 실행 중입니다")
    _detect_state.update(running=True, started_at=db.now_iso())
    background.add_task(_run_detection, req.deep, req.dry)
    return {"status": "started", "started_at": _detect_state["started_at"],
            "deep": req.deep, "dry": req.dry,
            "hint": "GET /api/runs 로 진행 상황을 확인하세요"}


# ── 실행 이력 ───────────────────────────────────────────────────────────
@app.get("/api/runs", tags=["실행"])
def list_runs(limit: int = Query(20, ge=1, le=200)):
    return {"running": _detect_state["running"],
            "items": q("""SELECT run_id, started_at, finished_at, run_mode, trigger, status,
                                 total_count, unchanged_count, new_count, changed_count,
                                 error_count
                          FROM collection_runs ORDER BY run_id DESC LIMIT ?""", (limit,))}


@app.get("/api/runs/{run_id}", tags=["실행"])
def get_run(run_id: int):
    r = q("SELECT * FROM collection_runs WHERE run_id=?", (run_id,), one=True)
    if not r:
        raise HTTPException(404, "실행 이력을 찾을 수 없습니다")
    r["report"] = db.jload(r.get("report"), {})
    r["changes"] = q("""SELECT c.change_id, r2.name AS regulation_name, c.change_reason,
                               c.summary FROM regulation_changes c
                        JOIN regulations r2 USING(regulation_id)
                        WHERE c.run_id=? ORDER BY c.change_id""", (run_id,))
    return r


# ── 알림 / 감시 프로파일 ────────────────────────────────────────────────
@app.get("/api/notifications", tags=["알림"])
def list_notifications(profile_id: int | None = None, is_read: bool | None = None,
                       limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    read = None if is_read is None else int(is_read)
    where = "WHERE (? IS NULL OR n.profile_id=?) AND (? IS NULL OR n.is_read=?)"
    args = (profile_id, profile_id, read, read)
    total = q(f"SELECT COUNT(*) AS n FROM notifications n {where}", args, one=True)["n"]
    # LEFT JOIN 이어야 한다: '조회 실패' 알림은 change_id 가 없어서
    # INNER JOIN 이면 통째로 사라진다(가장 봐야 할 알림이 안 보임).
    items = q(f"""SELECT n.notification_id, n.profile_id, p.name AS profile_name,
                         n.change_id, n.title, n.body, n.is_read, n.created_at,
                         c.regulation_id, r.name AS regulation_name,
                         CASE WHEN n.change_id IS NULL THEN 'failure' ELSE 'change' END AS kind
                  FROM notifications n
                  JOIN watch_profiles p USING(profile_id)
                  LEFT JOIN regulation_changes c ON c.change_id = n.change_id
                  LEFT JOIN regulations r ON r.regulation_id = c.regulation_id
                  {where} ORDER BY n.created_at DESC, n.notification_id DESC
                  LIMIT ? OFFSET ?""", args + (limit, offset))
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@app.post("/api/notifications/{notification_id}/read", tags=["알림"])
def mark_read(notification_id: int, is_read: bool = True):
    con = db.connect()
    try:
        with con:
            cur = con.execute("UPDATE notifications SET is_read=? WHERE notification_id=?",
                              (int(is_read), notification_id))
        if not cur.rowcount:
            raise HTTPException(404, "알림을 찾을 수 없습니다")
    finally:
        con.close()
    return {"notification_id": notification_id, "is_read": is_read}


class WatchProfileIn(BaseModel):
    name: str
    source_codes: list[str] = Field(default_factory=list,
                                    description="빈 배열이면 전체 소스 구독")
    regulation_names: list[str] = Field(default_factory=list,
                                        description="빈 배열이면 전체 규정 구독")


@app.get("/api/watch-profiles", tags=["알림"])
def list_profiles():
    rows = q("SELECT * FROM watch_profiles ORDER BY profile_id")
    for r in rows:
        r["source_codes"] = db.jload(r["source_codes"], [])
        r["regulation_names"] = db.jload(r["regulation_names"], [])
    return {"items": rows}


@app.post("/api/watch-profiles", status_code=201, tags=["알림"])
def create_profile(p: WatchProfileIn):
    con = db.connect()
    try:
        with con:
            cur = con.execute(
                "INSERT INTO watch_profiles (name, source_codes, regulation_names, created_at)"
                " VALUES (?,?,?,?)",
                (p.name, json.dumps(p.source_codes, ensure_ascii=False),
                 json.dumps(p.regulation_names, ensure_ascii=False), db.now_iso()))
        return {"profile_id": cur.lastrowid, **p.model_dump()}
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(409, f"'{p.name}' 프로파일이 이미 있습니다")
        raise
    finally:
        con.close()


# ── 검색 ────────────────────────────────────────────────────────────────
@app.get("/api/search", tags=["규정"])
def search(qs: str = Query(..., alias="q", min_length=2),
           current_only: bool = True, limit: int = Query(30, ge=1, le=200)):
    """현재본 조문 전문 검색 (LIKE 기반).
    스니펫은 본문 앞부분이 아니라 '매치된 위치 주변'을 잘라 보여준다."""
    rows = q(f"""SELECT sec.section_id, sec.section_key, sec.section_type, sec.title,
                        substr(sec.content, MAX(1, instr(sec.content, ?) - 60), 240) AS snippet,
                        instr(sec.content, ?) AS match_pos,
                        v.version_id, r.regulation_id, r.name AS regulation_name,
                        s.source_code
                 FROM regulation_sections sec
                 JOIN regulation_versions v USING(version_id)
                 JOIN regulations r USING(regulation_id)
                 JOIN regulation_sources s USING(source_id)
                 WHERE sec.content LIKE ? {'AND v.is_current=1' if current_only else ''}
                 ORDER BY r.name, sec.sequence_no LIMIT ?""",
             (qs, qs, f"%{qs}%", limit))
    for r in rows:
        if r["match_pos"] and r["match_pos"] > 61:
            r["snippet"] = "…" + r["snippet"]
    return {"query": qs, "count": len(rows), "items": rows}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=False)
