-- 금융 광고심의 규정 버전 관리 스키마 초안 (PostgreSQL 기준)

CREATE TABLE regulation_sources (
    source_id           BIGSERIAL PRIMARY KEY,
    source_code         VARCHAR(30) NOT NULL UNIQUE,
    source_name         VARCHAR(100) NOT NULL,
    source_type         VARCHAR(30) NOT NULL,
    base_url            TEXT,
    collection_method   VARCHAR(30) NOT NULL,
    active              BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE regulations (
    regulation_id       BIGSERIAL PRIMARY KEY,
    source_id           BIGINT NOT NULL REFERENCES regulation_sources(source_id),
    external_id         VARCHAR(100),
    name                TEXT NOT NULL,
    document_type       VARCHAR(50) NOT NULL,
    jurisdiction        VARCHAR(50) NOT NULL DEFAULT 'KR',
    current_version_id  BIGINT,
    active              BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (source_id, name)
);

CREATE TABLE regulation_versions (
    version_id          BIGSERIAL PRIMARY KEY,
    regulation_id       BIGINT NOT NULL REFERENCES regulations(regulation_id),
    official_version_key TEXT NOT NULL,
    content_hash        CHAR(64),
    promulgation_no     VARCHAR(100),
    promulgated_at      DATE,
    effective_at        DATE,
    collected_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    raw_format          VARCHAR(20),
    raw_content         TEXT,
    parsed_content      JSONB NOT NULL,
    plain_text          TEXT NOT NULL,
    is_current          BOOLEAN NOT NULL DEFAULT FALSE,
    validation_status   VARCHAR(20) NOT NULL DEFAULT 'pending',
    UNIQUE (regulation_id, official_version_key, content_hash)
);

ALTER TABLE regulations
    ADD CONSTRAINT fk_regulations_current_version
    FOREIGN KEY (current_version_id) REFERENCES regulation_versions(version_id);

CREATE UNIQUE INDEX uq_regulation_one_current
    ON regulation_versions (regulation_id)
    WHERE is_current = TRUE;

CREATE INDEX idx_regulation_versions_effective
    ON regulation_versions (regulation_id, effective_at DESC);

CREATE TABLE regulation_sections (
    section_id          BIGSERIAL PRIMARY KEY,
    version_id          BIGINT NOT NULL REFERENCES regulation_versions(version_id) ON DELETE CASCADE,
    section_key         VARCHAR(100) NOT NULL,
    section_type        VARCHAR(30) NOT NULL,
    parent_key          VARCHAR(100),
    sequence_no         INTEGER NOT NULL,
    title               TEXT,
    content             TEXT NOT NULL,
    content_hash        CHAR(64) NOT NULL,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (version_id, section_key)
);

CREATE INDEX idx_regulation_sections_version
    ON regulation_sections (version_id, sequence_no);

CREATE TABLE collection_runs (
    run_id              BIGSERIAL PRIMARY KEY,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at         TIMESTAMPTZ,
    run_mode            VARCHAR(20) NOT NULL,
    total_count         INTEGER NOT NULL DEFAULT 0,
    unchanged_count     INTEGER NOT NULL DEFAULT 0,
    new_count           INTEGER NOT NULL DEFAULT 0,
    changed_count       INTEGER NOT NULL DEFAULT 0,
    error_count         INTEGER NOT NULL DEFAULT 0,
    status              VARCHAR(20) NOT NULL DEFAULT 'running',
    report              JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE regulation_changes (
    change_id           BIGSERIAL PRIMARY KEY,
    run_id              BIGINT NOT NULL REFERENCES collection_runs(run_id),
    regulation_id       BIGINT NOT NULL REFERENCES regulations(regulation_id),
    old_version_id      BIGINT REFERENCES regulation_versions(version_id),
    new_version_id      BIGINT REFERENCES regulation_versions(version_id),
    change_reason       VARCHAR(50) NOT NULL,
    changed_section_count INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (old_version_id, new_version_id)
);

CREATE TABLE regulation_section_changes (
    section_change_id   BIGSERIAL PRIMARY KEY,
    change_id           BIGINT NOT NULL REFERENCES regulation_changes(change_id) ON DELETE CASCADE,
    section_key         VARCHAR(100) NOT NULL,
    change_type         VARCHAR(20) NOT NULL,
    old_content         TEXT,
    new_content         TEXT
);

CREATE INDEX idx_section_changes_change
    ON regulation_section_changes (change_id);

CREATE TABLE regulation_artifacts (
    artifact_id         BIGSERIAL PRIMARY KEY,
    version_id          BIGINT NOT NULL REFERENCES regulation_versions(version_id) ON DELETE CASCADE,
    artifact_type       VARCHAR(30) NOT NULL,
    file_name           TEXT NOT NULL,
    storage_path        TEXT NOT NULL,
    file_hash           CHAR(64),
    file_size           BIGINT,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb
);
