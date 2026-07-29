# -*- coding: utf-8 -*-
"""
규정 저장소 (SQLite).

sql/regulation_schema.sql 의 PostgreSQL 설계를 SQLite 로 그대로 옮긴 것.
운영에서 PostgreSQL 로 갈아탈 때 테이블/컬럼명이 같도록 유지한다
(BIGSERIAL→INTEGER AUTOINCREMENT, JSONB→TEXT(JSON), TIMESTAMPTZ→TEXT(ISO8601)).

로컬에서 별도 DB 서버 설치 없이 바로 돌아가는 것이 목적이라 기본은 SQLite,
REGULATION_DB 환경변수로 파일 경로를 바꿀 수 있다.
"""
import os
import json
import sqlite3
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("REGULATION_DB", os.path.join(ROOT, "output", "regulations.db"))

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS regulation_sources (
    source_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    source_code       TEXT NOT NULL UNIQUE,
    source_name       TEXT NOT NULL,
    source_type       TEXT NOT NULL,
    base_url          TEXT,
    collection_method TEXT NOT NULL,
    active            INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS regulations (
    regulation_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id          INTEGER NOT NULL REFERENCES regulation_sources(source_id),
    external_id        TEXT,
    name               TEXT NOT NULL,
    document_type      TEXT NOT NULL,
    jurisdiction       TEXT NOT NULL DEFAULT 'KR',
    current_version_id INTEGER REFERENCES regulation_versions(version_id),
    active             INTEGER NOT NULL DEFAULT 1,
    UNIQUE (source_id, name)
);

CREATE TABLE IF NOT EXISTS regulation_versions (
    version_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    regulation_id        INTEGER NOT NULL REFERENCES regulations(regulation_id),
    official_version_key TEXT NOT NULL,
    content_hash         TEXT,
    promulgation_no      TEXT,
    promulgated_at       TEXT,
    effective_at         TEXT,
    collected_at         TEXT NOT NULL,
    raw_format           TEXT,
    source_url           TEXT,
    parsed_content       TEXT NOT NULL,
    plain_text           TEXT NOT NULL,
    is_current           INTEGER NOT NULL DEFAULT 0,
    validation_status    TEXT NOT NULL DEFAULT 'pending',
    UNIQUE (regulation_id, official_version_key, content_hash)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_regulation_one_current
    ON regulation_versions (regulation_id) WHERE is_current = 1;
CREATE INDEX IF NOT EXISTS idx_versions_effective
    ON regulation_versions (regulation_id, effective_at DESC);

CREATE TABLE IF NOT EXISTS regulation_sections (
    section_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id   INTEGER NOT NULL REFERENCES regulation_versions(version_id) ON DELETE CASCADE,
    section_key  TEXT NOT NULL,
    section_type TEXT NOT NULL,
    parent_key   TEXT,
    sequence_no  INTEGER NOT NULL,
    title        TEXT,
    content      TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    metadata     TEXT NOT NULL DEFAULT '{}',
    UNIQUE (version_id, section_key)
);
CREATE INDEX IF NOT EXISTS idx_sections_version
    ON regulation_sections (version_id, sequence_no);

CREATE TABLE IF NOT EXISTS collection_runs (
    run_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    run_mode        TEXT NOT NULL,
    trigger         TEXT NOT NULL DEFAULT 'manual',
    total_count     INTEGER NOT NULL DEFAULT 0,
    unchanged_count INTEGER NOT NULL DEFAULT 0,
    new_count       INTEGER NOT NULL DEFAULT 0,
    changed_count   INTEGER NOT NULL DEFAULT 0,
    error_count     INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'running',
    report          TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS regulation_changes (
    change_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                INTEGER NOT NULL REFERENCES collection_runs(run_id),
    regulation_id         INTEGER NOT NULL REFERENCES regulations(regulation_id),
    old_version_id        INTEGER REFERENCES regulation_versions(version_id),
    new_version_id        INTEGER REFERENCES regulation_versions(version_id),
    change_reason         TEXT NOT NULL,
    changed_section_count INTEGER NOT NULL DEFAULT 0,
    added_section_count   INTEGER NOT NULL DEFAULT 0,
    removed_section_count INTEGER NOT NULL DEFAULT 0,
    summary               TEXT,
    created_at            TEXT NOT NULL,
    UNIQUE (old_version_id, new_version_id)
);
CREATE INDEX IF NOT EXISTS idx_changes_created ON regulation_changes (created_at DESC);

CREATE TABLE IF NOT EXISTS regulation_section_changes (
    section_change_id INTEGER PRIMARY KEY AUTOINCREMENT,
    change_id   INTEGER NOT NULL REFERENCES regulation_changes(change_id) ON DELETE CASCADE,
    section_key TEXT NOT NULL,
    change_type TEXT NOT NULL,
    old_content TEXT,
    new_content TEXT,
    diff        TEXT
);
CREATE INDEX IF NOT EXISTS idx_section_changes_change
    ON regulation_section_changes (change_id);

CREATE TABLE IF NOT EXISTS regulation_artifacts (
    artifact_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id    INTEGER NOT NULL REFERENCES regulation_versions(version_id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL,
    file_name     TEXT NOT NULL,
    storage_path  TEXT NOT NULL,
    file_hash     TEXT,
    file_size     INTEGER,
    metadata      TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_artifacts_version ON regulation_artifacts (version_id);

-- 알림: 관심 규정만 구독해서 변경 시 통지받는다
CREATE TABLE IF NOT EXISTS watch_profiles (
    profile_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL UNIQUE,
    source_codes TEXT NOT NULL DEFAULT '[]',   -- 빈 배열이면 전체 소스
    regulation_names TEXT NOT NULL DEFAULT '[]', -- 빈 배열이면 전체 규정
    active       INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL
);

-- change_id 는 NULL 을 허용한다: 변경 알림 외에 '조회 실패' 알림도 같은 곳에 쌓아야
-- 사람이 한 곳만 보면 되기 때문이다(실패를 놓치면 그 달 개정을 통째로 놓친다).
CREATE TABLE IF NOT EXISTS notifications (
    notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES watch_profiles(profile_id) ON DELETE CASCADE,
    change_id  INTEGER REFERENCES regulation_changes(change_id) ON DELETE CASCADE,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL,
    is_read    INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE (profile_id, change_id)
);
CREATE INDEX IF NOT EXISTS idx_notifications_unread
    ON notifications (profile_id, is_read, created_at DESC);
"""

# targets.json 의 kind → 출처 메타. DB 의 regulation_sources 시드로 쓴다.
SOURCE_SEED = {
    "law":    ("lawgo",  "국가법령정보센터(법제처)", "government", "https://www.law.go.kr", "open_api"),
    "admrul": ("lawgo",  "국가법령정보센터(법제처)", "government", "https://www.law.go.kr", "open_api"),
    "kofia":  ("kofia",  "금융투자협회",           "association", "https://law.kofia.or.kr", "web_scrape"),
    "crefia": ("crefia", "여신금융협회",           "association", "https://www.crefia.or.kr", "file_download"),
    "kfb":    ("kfb",    "전국은행연합회",         "association", "https://www.kfb.or.kr", "file_download"),
}

DOCUMENT_TYPE = {
    "law": "법령", "admrul": "행정규칙", "kofia": "자율규제규정",
    "crefia": "자율규제규정", "kfb": "자율규제규정",
}


def now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def connect(path=None):
    os.makedirs(os.path.dirname(path or DB_PATH), exist_ok=True)
    con = sqlite3.connect(path or DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def _migrate(con):
    """기존 DB 를 현재 스키마에 맞춘다(여러 번 실행해도 안전)."""
    cols = {r["name"]: r for r in con.execute("PRAGMA table_info(notifications)")}
    # change_id 가 NOT NULL 이던 구버전: '조회 실패' 알림(change_id 없음)을 못 넣는다.
    if cols and cols.get("change_id", {})["notnull"]:
        con.executescript("""
            ALTER TABLE notifications RENAME TO notifications_old;
            CREATE TABLE notifications (
                notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER NOT NULL REFERENCES watch_profiles(profile_id) ON DELETE CASCADE,
                change_id  INTEGER REFERENCES regulation_changes(change_id) ON DELETE CASCADE,
                title      TEXT NOT NULL, body TEXT NOT NULL,
                is_read    INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
                UNIQUE (profile_id, change_id));
            INSERT INTO notifications SELECT * FROM notifications_old;
            DROP TABLE notifications_old;
        """)
        print("  DB 마이그레이션: notifications.change_id 를 NULL 허용으로 변경")


def init(path=None):
    """스키마 생성 + 출처 시드. 여러 번 실행해도 안전(IF NOT EXISTS/UPSERT)."""
    con = connect(path)
    with con:
        con.executescript(SCHEMA)
        _migrate(con)
        for code, name, stype, url, method in {v[0]: v for v in SOURCE_SEED.values()}.values():
            con.execute(
                "INSERT INTO regulation_sources (source_code, source_name, source_type,"
                " base_url, collection_method) VALUES (?,?,?,?,?)"
                " ON CONFLICT(source_code) DO UPDATE SET source_name=excluded.source_name",
                (code, name, stype, url, method))
        # 기본 감시 프로파일(전체 구독) 하나는 있어야 알림이 실제로 쌓인다
        con.execute(
            "INSERT OR IGNORE INTO watch_profiles (name, source_codes, regulation_names,"
            " created_at) VALUES ('전체', '[]', '[]', ?)", (now_iso(),))
    return con


def source_id(con, kind):
    code = SOURCE_SEED[kind][0]
    row = con.execute("SELECT source_id FROM regulation_sources WHERE source_code=?",
                      (code,)).fetchone()
    return row["source_id"] if row else None


def jload(s, default=None):
    try:
        return json.loads(s) if s else (default if default is not None else {})
    except (TypeError, ValueError):
        return default if default is not None else {}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    con = init()
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    print(f"DB 초기화 완료: {DB_PATH}")
    print("테이블:", ", ".join(tables))
