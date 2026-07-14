"""PostgreSQL implementation of the M3 standard repository contract."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Engine, text

from nh_ad_backend.standards import (
    EvidenceChunk,
    ReindexJob,
    Standard,
    StandardVersion,
)


class PostgresStandardRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create(
        self,
        standard: Standard,
        version: StandardVersion,
        chunks: Sequence[EvidenceChunk],
    ) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text("""
                INSERT INTO rag.standards
                (standard_id,title,evidence_type,product_group,advertisement_type,rule_type,
                 importance,effective_date,expired_date,metadata_json,current_version,is_active,
                 created_at,created_by)
                VALUES
                (:standard_id,:title,:evidence_type,:product_group,:advertisement_type,:rule_type,
                 :importance,:effective_date,:expired_date,CAST(:metadata AS jsonb),:current_version,true,
                 :created_at,:created_by)
            """),
                _standard_values(standard),
            )
            self._insert_version(connection, standard, version, chunks)

    def get_standard(self, standard_id: str) -> Standard | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text("SELECT * FROM rag.standards WHERE standard_id=:id"),
                    {"id": standard_id},
                )
                .mappings()
                .first()
            )
        return _standard(row) if row else None

    def save_standard(self, standard: Standard) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text("""
                UPDATE rag.standards
                   SET title=:title,evidence_type=:evidence_type,product_group=:product_group,
                       advertisement_type=:advertisement_type,rule_type=:rule_type,
                       importance=:importance,effective_date=:effective_date,
                       expired_date=:expired_date,metadata_json=CAST(:metadata AS jsonb),
                       current_version=:current_version,is_active=:is_active,
                       updated_at=:updated_at,updated_by=:updated_by
                 WHERE standard_id=:standard_id
            """),
                _standard_values(standard),
            )
            if not standard.is_active:
                connection.execute(
                    text("""
                    UPDATE rag.evidences SET is_active=false WHERE standard_id=:standard_id;
                    UPDATE rag.evidence_chunks
                       SET qdrant_index_status='EXCLUDED',opensearch_index_status='EXCLUDED'
                     WHERE standard_id=:standard_id
                """),
                    {"standard_id": standard.standard_id},
                )

    def add_version(self, version: StandardVersion, chunks: Sequence[EvidenceChunk]) -> None:
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    text("SELECT * FROM rag.standards WHERE standard_id=:id FOR UPDATE"),
                    {"id": version.standard_id},
                )
                .mappings()
                .one()
            )
            self._insert_version(connection, _standard(row), version, chunks)

    @staticmethod
    def _insert_version(
        connection: Any,
        standard: Standard,
        version: StandardVersion,
        chunks: Sequence[EvidenceChunk],
    ) -> None:
        connection.execute(
            text("""
            INSERT INTO rag.standard_versions
            (standard_version_id,standard_id,version,title,content,change_reason,effective_date,
             expired_date,metadata_json,created_at,created_by)
            VALUES (:standard_version_id,:standard_id,:version,:title,:content,:change_reason,
                    :effective_date,:expired_date,CAST(:metadata AS jsonb),:created_at,:created_by)
        """),
            _version_values(version),
        )
        metadata = version.metadata
        article_no = metadata.get("articleNo", metadata.get("article_no"))
        connection.execute(
            text("""
            INSERT INTO rag.evidences
            (evidence_id,standard_id,standard_version_id,evidence_type,title,article_no,content,
             content_summary,product_group,advertisement_type,rule_type,importance,effective_date,
             expired_date,metadata_json,is_active,created_at)
            VALUES (:evidence_id,:standard_id,:standard_version_id,:evidence_type,:title,
                    :article_no,:content,:content_summary,:product_group,:advertisement_type,
                    :rule_type,:importance,:effective_date,:expired_date,
                    CAST(:metadata AS jsonb),true,:created_at)
        """),
            {
                "evidence_id": version.evidence_id,
                "standard_id": standard.standard_id,
                "standard_version_id": version.standard_version_id,
                "evidence_type": standard.evidence_type,
                "title": version.title,
                "article_no": article_no,
                "content": version.content,
                "content_summary": version.content[:500],
                "product_group": standard.product_group,
                "advertisement_type": standard.advertisement_type,
                "rule_type": standard.rule_type,
                "importance": standard.importance,
                "effective_date": version.effective_date,
                "expired_date": version.expired_date,
                "metadata": json.dumps(metadata, ensure_ascii=False),
                "created_at": version.created_at,
            },
        )
        for chunk in chunks:
            connection.execute(
                text("""
                INSERT INTO rag.evidence_chunks
                (evidence_chunk_id,evidence_id,standard_id,standard_version_id,chunk_no,chunk_text,
                 token_count,section_path,article_no,source_span,structure_confidence,
                 parser_rule_version,chunking_policy_version,qdrant_point_id,qdrant_index_status,
                 qdrant_index_error_code,opensearch_doc_id,opensearch_index_status,
                 opensearch_index_error_code,embedding_model,search_schema_version,
                 opensearch_analyzer_version,synonym_version,metadata,created_at)
                VALUES (:evidence_chunk_id,:evidence_id,:standard_id,:standard_version_id,:chunk_no,
                        :chunk_text,:token_count,:section_path,:article_no,CAST(:source_span AS jsonb),1.0,
                        :parser_rule_version,:chunking_policy_version,:deterministic_index_id,
                        :qdrant_index_status,:qdrant_error_code,:deterministic_index_id,
                        :opensearch_index_status,:opensearch_error_code,:embedding_model,
                        :search_schema_version,:opensearch_analyzer_version,:synonym_version,
                        '{}'::jsonb,:created_at)
            """),
                {**_chunk_values(chunk), "created_at": version.created_at},
            )

    def get_version(self, standard_version_id: str) -> StandardVersion | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text("""
                    SELECT sv.*, e.evidence_id
                      FROM rag.standard_versions sv
                      JOIN rag.evidences e USING (standard_version_id)
                     WHERE sv.standard_version_id=:id
                """),
                    {"id": standard_version_id},
                )
                .mappings()
                .first()
            )
        return _version(row) if row else None

    def get_version_by_evidence(self, evidence_id: str) -> StandardVersion | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text("""
                    SELECT sv.*, e.evidence_id
                      FROM rag.standard_versions sv
                      JOIN rag.evidences e USING (standard_version_id)
                     WHERE e.evidence_id=:id
                """),
                    {"id": evidence_id},
                )
                .mappings()
                .first()
            )
        return _version(row) if row else None

    def histories(self, standard_id: str) -> list[StandardVersion]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text("""
                    SELECT sv.*, e.evidence_id
                      FROM rag.standard_versions sv
                      JOIN rag.evidences e USING (standard_version_id)
                     WHERE sv.standard_id=:id
                     ORDER BY sv.created_at DESC, sv.standard_version_id DESC
                """),
                    {"id": standard_id},
                )
                .mappings()
                .all()
            )
        return [_version(row) for row in rows]

    def chunks_for_version(self, standard_version_id: str) -> list[EvidenceChunk]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text("""
                    SELECT * FROM rag.evidence_chunks
                     WHERE standard_version_id=:id ORDER BY chunk_no
                """),
                    {"id": standard_version_id},
                )
                .mappings()
                .all()
            )
        return [_chunk(row) for row in rows]

    def save_chunks(self, chunks: Sequence[EvidenceChunk]) -> None:
        with self._engine.begin() as connection:
            for chunk in chunks:
                connection.execute(
                    text("""
                    UPDATE rag.evidence_chunks SET
                      parser_rule_version=:parser_rule_version,
                      chunking_policy_version=:chunking_policy_version,
                      qdrant_point_id=:deterministic_index_id,
                      qdrant_index_status=:qdrant_index_status,
                      qdrant_index_error_code=:qdrant_error_code,
                      opensearch_doc_id=:deterministic_index_id,
                      opensearch_index_status=:opensearch_index_status,
                      opensearch_index_error_code=:opensearch_error_code,
                      embedding_model=:embedding_model,search_schema_version=:search_schema_version,
                      opensearch_analyzer_version=:opensearch_analyzer_version,
                      synonym_version=:synonym_version
                    WHERE evidence_chunk_id=:evidence_chunk_id
                """),
                    _chunk_values(chunk),
                )

    def get_chunk(self, evidence_chunk_id: str) -> EvidenceChunk | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text("SELECT * FROM rag.evidence_chunks WHERE evidence_chunk_id=:id"),
                    {"id": evidence_chunk_id},
                )
                .mappings()
                .first()
            )
        return _chunk(row) if row else None

    def chunks_for_evidence(self, evidence_id: str) -> list[EvidenceChunk]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text("""
                    SELECT * FROM rag.evidence_chunks
                     WHERE evidence_id=:id ORDER BY chunk_no
                """),
                    {"id": evidence_id},
                )
                .mappings()
                .all()
            )
        return [_chunk(row) for row in rows]

    def save_reindex_job(self, job: ReindexJob) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text("""
                INSERT INTO rag.standard_reindex_jobs
                (reindex_job_id,standard_id,standard_version_id,reindex_scope,job_status,
                 reason,target_indexes,parser_rule_version,chunking_policy_version,embedding_model,
                 search_schema_version,opensearch_analyzer_version,synonym_version,
                 created_chunk_count,indexed_chunk_count,failed_reason_code,failed_reason_message,
                 requested_by,requested_at,started_at,completed_at)
                VALUES (:job_id,:standard_id,:standard_version_id,:reindex_scope,:job_status,
                        :reason,CAST(:target_indexes AS jsonb),:parser_rule_version,:chunking_policy_version,
                        :embedding_model,:search_schema_version,:opensearch_analyzer_version,
                        :synonym_version,:created_chunk_count,:indexed_chunk_count,
                        :failed_reason_code,:failed_reason_message,:requested_by,:requested_at,
                        :started_at,:completed_at)
                ON CONFLICT (reindex_job_id) DO UPDATE SET
                  job_status=EXCLUDED.job_status,indexed_chunk_count=EXCLUDED.indexed_chunk_count,
                  failed_reason_code=EXCLUDED.failed_reason_code,
                  failed_reason_message=EXCLUDED.failed_reason_message,
                  started_at=EXCLUDED.started_at,completed_at=EXCLUDED.completed_at
            """),
                {
                    **job.__dict__,
                    "target_indexes": json.dumps(list(job.target_indexes)),
                },
            )

    def get_reindex_job(self, job_id: str) -> ReindexJob | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text("SELECT * FROM rag.standard_reindex_jobs WHERE reindex_job_id=:id"),
                    {"id": job_id},
                )
                .mappings()
                .first()
            )
        if not row:
            return None
        chunks = self.chunks_for_version(row["standard_version_id"])
        return ReindexJob(
            job_id=row["reindex_job_id"],
            standard_id=row["standard_id"],
            standard_version_id=row["standard_version_id"],
            reindex_scope=row["reindex_scope"],
            job_status=row["job_status"],
            target_indexes=tuple(row["target_indexes"] or ()),
            parser_rule_version=row["parser_rule_version"] or "direct-text-v1",
            chunking_policy_version=row["chunking_policy_version"] or "reference-chunking-v1",
            embedding_model=row["embedding_model"] or "",
            search_schema_version=row["search_schema_version"] or "",
            opensearch_analyzer_version=row["opensearch_analyzer_version"] or "",
            synonym_version=row["synonym_version"] or "",
            requested_by=row["requested_by"],
            requested_at=row["requested_at"],
            reason=row["reason"],
            created_chunk_count=row["created_chunk_count"] or 0,
            indexed_chunk_count=row["indexed_chunk_count"] or 0,
            qdrant_status=_aggregate(chunk.qdrant_index_status for chunk in chunks),
            opensearch_status=_aggregate(chunk.opensearch_index_status for chunk in chunks),
            failed_reason_code=row["failed_reason_code"],
            failed_reason_message=row["failed_reason_message"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )

    def list_standards(self) -> list[Standard]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(text("SELECT * FROM rag.standards ORDER BY created_at DESC"))
                .mappings()
                .all()
            )
        return [_standard(row) for row in rows]


def _standard_values(value: Standard) -> dict[str, object]:
    result = dict(value.__dict__)
    result["metadata"] = json.dumps(result["metadata"], ensure_ascii=False)
    return result


def _standard(row: Any) -> Standard:
    return Standard(
        row["standard_id"],
        row["title"],
        row["evidence_type"],
        row["product_group"],
        row["advertisement_type"],
        row["rule_type"],
        row["importance"] or "MEDIUM",
        row["effective_date"],
        row["expired_date"],
        dict(row["metadata_json"] or {}),
        row["current_version"],
        row["is_active"],
        row["created_at"],
        row["created_by"],
        row["updated_at"],
        row["updated_by"],
    )


def _version_values(value: StandardVersion) -> dict[str, object]:
    result = dict(value.__dict__)
    result["metadata"] = json.dumps(result["metadata"], ensure_ascii=False)
    return result


def _version(row: Any) -> StandardVersion:
    return StandardVersion(
        row["standard_version_id"],
        row["standard_id"],
        row["evidence_id"],
        row["version"],
        row["title"],
        row["content"],
        row["change_reason"],
        row["effective_date"],
        row["expired_date"],
        dict(row["metadata_json"] or {}),
        row["created_at"],
        row["created_by"],
    )


def _chunk_values(value: EvidenceChunk) -> dict[str, object]:
    return {
        **value.__dict__,
        "source_span": json.dumps({"start": value.source_start, "end": value.source_end}),
    }


def _chunk(row: Any) -> EvidenceChunk:
    source_span = row["source_span"] or {}
    point_id = row["qdrant_point_id"] or row["opensearch_doc_id"]
    return EvidenceChunk(
        row["evidence_chunk_id"],
        row["evidence_id"],
        row["standard_id"],
        row["standard_version_id"],
        row["chunk_no"],
        row["chunk_text"],
        int(source_span.get("start", 0)),
        int(source_span.get("end", 0)),
        row["section_path"],
        row["article_no"],
        row["token_count"] or 0,
        row["parser_rule_version"] or "direct-text-v1",
        row["chunking_policy_version"] or "reference-chunking-v1",
        row["embedding_model"],
        row["search_schema_version"],
        row["opensearch_analyzer_version"],
        row["synonym_version"],
        point_id,
        row["qdrant_index_status"] or "PENDING",
        row["opensearch_index_status"] or "PENDING",
        row["qdrant_index_error_code"],
        row["opensearch_index_error_code"],
        row["created_at"],
    )


def _aggregate(statuses: Sequence[str] | Any) -> str:
    values = set(statuses)
    if "FAILED" in values:
        return "FAILED"
    if "ACTIVE" in values:
        return "ACTIVE"
    if "EXCLUDED" in values:
        return "EXCLUDED"
    return "PENDING"
