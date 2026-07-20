"""PostgreSQL job and parser-artifact persistence for M4 workers."""

from __future__ import annotations

from io import BytesIO
import json
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from typing import Any
from uuid import UUID
from uuid import uuid4

from nh_ad_parser_contracts import ArtifactMetadata, DocumentInput, NormalizedDocument
from sqlalchemy import Engine, text
from pypdf import PdfReader

from nh_ad_worker.jobs import QueueMessage, RETRY_DELAYS, WorkerJob
from nh_ad_worker.results import ReviewResultBundle
from nh_ad_worker.suggestions import SuggestionProposal


class PostgresArtifactMetadataRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @staticmethod
    def _metadata(row: Any) -> ArtifactMetadata:
        value = dict(row._mapping)
        value["review_step_id"] = str(value["review_step_id"])
        value.pop("rerun_reason_message", None)
        return ArtifactMetadata(**value)

    def add(self, item: ArtifactMetadata) -> ArtifactMetadata:
        with self._engine.begin() as connection:
            existing = connection.execute(
                text("""
                    SELECT * FROM app.parser_artifacts
                     WHERE raw_artifact_id=:raw_artifact_id
                     FOR UPDATE
                """),
                {"raw_artifact_id": item.raw_artifact_id},
            ).first()
            if existing is not None:
                canonical = self._metadata(existing)
                same_artifact = (
                    canonical.review_id == item.review_id
                    and canonical.file_id == item.file_id
                    and canonical.review_step_id == item.review_step_id
                    and canonical.artifact_type == item.artifact_type
                    and canonical.parser_name == item.parser_name
                    and canonical.parser_version == item.parser_version
                    and canonical.parser_rule_version == item.parser_rule_version
                    and canonical.ir_version == item.ir_version
                    and canonical.attempt_no == item.attempt_no
                    and canonical.is_primary_attempt == item.is_primary_attempt
                    and canonical.is_selected_output == item.is_selected_output
                    and canonical.checksum_sha256 == item.checksum_sha256
                )
                if not same_artifact:
                    raise ValueError("ARTIFACT_IDEMPOTENCY_CONFLICT")
                return canonical
            connection.execute(
                text("""
                    INSERT INTO app.parser_artifacts
                    (raw_artifact_id,review_id,file_id,review_step_id,artifact_type,
                     storage_provider,bucket,object_key,checksum_sha256,content_type,file_size,
                     parser_name,parser_version,parser_rule_version,ir_version,attempt_no,
                     is_primary_attempt,is_selected_output,rerun_reason_code,confidence_score,
                     confidence_status,created_at,retention_until,retention_hold,deleted_at)
                    VALUES (:raw_artifact_id,:review_id,:file_id,:review_step_id,:artifact_type,
                     :storage_provider,:bucket,:object_key,:checksum_sha256,:content_type,:file_size,
                     :parser_name,:parser_version,:parser_rule_version,:ir_version,:attempt_no,
                     :is_primary_attempt,:is_selected_output,:rerun_reason_code,:confidence_score,
                     :confidence_status,:created_at,:retention_until,:retention_hold,:deleted_at)
                """),
                {**item.__dict__, "review_step_id": UUID(item.review_step_id)},
            )
            return item

    def get(self, raw_artifact_id: str) -> ArtifactMetadata | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                text("SELECT * FROM app.parser_artifacts WHERE raw_artifact_id=:id"),
                {"id": raw_artifact_id},
            ).first()
        if row is None:
            return None
        return self._metadata(row)

    def replace(self, item: ArtifactMetadata) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text("""
                    UPDATE app.parser_artifacts
                       SET retention_until=:retention_until,retention_hold=:retention_hold,
                           deleted_at=:deleted_at
                     WHERE raw_artifact_id=:raw_artifact_id
                """),
                item.__dict__,
            )

    def set_retention_hold(self, raw_artifact_id: str, hold: bool) -> ArtifactMetadata:
        item = self.get(raw_artifact_id)
        if item is None:
            raise KeyError(raw_artifact_id)
        updated = replace(item, retention_hold=hold)
        self.replace(updated)
        return updated


class PostgresArtifactAudit:
    """Persist redacted artifact access/delete audit without object coordinates."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def __call__(self, event: dict[str, str]) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text("""
                    INSERT INTO audit.audit_logs
                    (audit_log_id,user_id,action_type,target_type,target_id,result,
                     metadata_json,created_at)
                    VALUES (:id,:actor,:action,'PARSER_ARTIFACT',:artifact,:result,
                     CAST(:metadata AS jsonb),now())
                """),
                {
                    "id": uuid4(),
                    "actor": event.get("actorId"),
                    "action": event["action"],
                    "artifact": event["artifactId"],
                    "result": event["result"],
                    "metadata": '{"redacted":true}',
                },
            )


class PostgresJobRepository:
    """Claim-safe source-of-truth transitions over migration 0004."""

    def __init__(
        self,
        engine: Engine,
        source_loader: Callable[[str, str], bytes],
        *,
        external_ai_allowed: bool = False,
    ) -> None:
        self._engine = engine
        self._source_loader = source_loader
        self._external_ai_allowed = external_ai_allowed

    def claim(self, message: QueueMessage, *, worker_id: str, now: datetime) -> WorkerJob | None:
        if message.idempotency_key != message.job_id:
            raise ValueError("IDEMPOTENCY_KEY_MISMATCH")
        with self._engine.begin() as connection:
            job = connection.execute(
                text("""
                    UPDATE app.review_jobs
                       SET job_status='RUNNING',locked_by=:worker,locked_at=:now,
                           heartbeat_at=:now,started_at=COALESCE(started_at,:now),
                           current_step='FILE_PREPROCESSING',progress_rate=5
                     WHERE job_id=:job_id AND review_id=:review_id
                       AND job_status IN ('PENDING','RETRY_PENDING','STALE')
                       AND (next_retry_at IS NULL OR next_retry_at<=:now)
                    RETURNING retry_count,max_retries
                """),
                {
                    "worker": worker_id,
                    "now": now,
                    "job_id": message.job_id,
                    "review_id": message.review_id,
                },
            ).first()
            if job is None:
                exists = connection.execute(
                    text("SELECT 1 FROM app.review_jobs WHERE job_id=:id AND review_id=:review_id"),
                    {"id": message.job_id, "review_id": message.review_id},
                ).scalar_one_or_none()
                if exists is None:
                    raise KeyError(message.job_id)
                return None
            connection.execute(
                text(
                    "UPDATE app.reviews SET review_status='ANALYZING',updated_at=:now WHERE review_id=:id"
                ),
                {"now": now, "id": message.review_id},
            )
            step = connection.execute(
                text("""
                    UPDATE app.review_steps
                       SET step_status='RUNNING',started_at=COALESCE(started_at,:now)
                     WHERE job_id=:job_id AND step_code='FILE_PREPROCESSING'
                    RETURNING review_step_id
                """),
                {"now": now, "job_id": message.job_id},
            ).scalar_one()
            source = (
                connection.execute(
                    text("""
                    SELECT f.file_id,f.original_file_name,f.mime_type,f.bucket,f.object_key,
                           r.include_suggestion
                      FROM app.reviews r
                      JOIN app.advertisement_files f ON f.advertisement_id=r.advertisement_id
                     WHERE r.review_id=:review_id AND f.file_type='ADVERTISEMENT'
                     ORDER BY f.created_at LIMIT 1
                """),
                    {"review_id": message.review_id},
                )
                .one()
                ._mapping
            )
        body = self._source_loader(source["bucket"], source["object_key"])
        return WorkerJob(
            job_id=message.job_id,
            review_id=message.review_id,
            document=DocumentInput(
                source_file_id=source["file_id"],
                review_id=message.review_id,
                file_name=source["original_file_name"],
                mime_type=source["mime_type"],
                body=body,
                scanned_pdf=_is_scanned_pdf(
                    file_name=str(source["original_file_name"]),
                    mime_type=str(source["mime_type"]),
                    body=body,
                ),
                external_ai_allowed=self._external_ai_allowed,
            ),
            review_step_id=str(step),
            status="RUNNING",
            retry_count=job._mapping["retry_count"],
            max_retries=job._mapping["max_retries"],
            heartbeat_at=now,
            locked_by=worker_id,
            review_status="ANALYZING",
            include_suggestion=source["include_suggestion"],
        )

    def heartbeat(self, job_id: str, *, worker_id: str, now: datetime) -> None:
        with self._engine.begin() as connection:
            updated = connection.execute(
                text("""
                    UPDATE app.review_jobs SET heartbeat_at=:now
                     WHERE job_id=:job_id AND job_status='RUNNING' AND locked_by=:worker
                    RETURNING job_id
                """),
                {"now": now, "job_id": job_id, "worker": worker_id},
            ).scalar_one_or_none()
        if updated is None:
            raise ValueError("ILLEGAL_JOB_TRANSITION")

    def advance(self, job_id: str, *, worker_id: str, now: datetime, step_code: str) -> None:
        progress_rates = {
            "FILE_PREPROCESSING": 5,
            "OCR_EXTRACTION": 25,
            "LAYOUT_ANALYSIS": 50,
            "RULE_REVIEW": 65,
            "RAG_REVIEW": 80,
            "RESULT_GENERATION": 95,
        }
        progress_rate = progress_rates.get(step_code)
        if progress_rate is None:
            raise ValueError("UNKNOWN_REVIEW_STEP")
        with self._engine.begin() as connection:
            owned = connection.execute(
                text("""
                    UPDATE app.review_jobs
                       SET current_step=:step_code,progress_rate=:progress_rate,heartbeat_at=:now
                     WHERE job_id=:job_id AND job_status='RUNNING' AND locked_by=:worker
                 RETURNING job_id
                """),
                {
                    "step_code": step_code,
                    "progress_rate": progress_rate,
                    "now": now,
                    "job_id": job_id,
                    "worker": worker_id,
                },
            ).scalar_one_or_none()
            if owned is None:
                raise ValueError("ILLEGAL_JOB_TRANSITION")
            sequence_no = connection.execute(
                text(
                    "SELECT sequence_no FROM app.review_steps WHERE job_id=:job_id AND step_code=:step_code"
                ),
                {"job_id": job_id, "step_code": step_code},
            ).scalar_one_or_none()
            if sequence_no is None:
                raise ValueError("UNKNOWN_REVIEW_STEP")
            connection.execute(
                text("""
                    UPDATE app.review_steps
                       SET step_status='COMPLETED',completed_at=COALESCE(completed_at,:now)
                     WHERE job_id=:job_id AND sequence_no<:sequence_no AND step_status<>'COMPLETED'
                """),
                {"now": now, "job_id": job_id, "sequence_no": sequence_no},
            )
            connection.execute(
                text("""
                    UPDATE app.review_steps
                       SET step_status='RUNNING',started_at=COALESCE(started_at,:now),failed_reason_code=NULL
                     WHERE job_id=:job_id AND step_code=:step_code
                """),
                {"now": now, "job_id": job_id, "step_code": step_code},
            )

    def fail_claim_error(
        self,
        message: QueueMessage,
        *,
        worker_id: str,
        now: datetime,
        reason_code: str,
    ) -> bool:
        with self._engine.begin() as connection:
            review_id = connection.execute(
                text("""
                    UPDATE app.review_jobs
                       SET job_status='FAILED_FINAL',is_retryable=false,
                           failed_reason_code=:reason,dead_lettered_at=:now,
                           locked_by=NULL,locked_at=NULL
                     WHERE job_id=:job_id AND review_id=:review_id
                       AND (
                            (job_status='RUNNING' AND locked_by=:worker)
                            OR job_status IN ('PENDING','RETRY_PENDING','STALE')
                       )
                    RETURNING review_id
                """),
                {
                    "reason": reason_code,
                    "now": now,
                    "job_id": message.job_id,
                    "review_id": message.review_id,
                    "worker": worker_id,
                },
            ).scalar_one_or_none()
            if review_id is None:
                return False
            connection.execute(
                text("""
                    UPDATE app.reviews
                       SET review_status='REVIEW_FAILED',failed_reason=:reason,updated_at=:now
                     WHERE review_id=:review_id
                """),
                {"reason": reason_code, "now": now, "review_id": review_id},
            )
            connection.execute(
                text("""
                    UPDATE app.review_steps
                       SET step_status='FAILED',completed_at=:now,failed_reason_code=:reason
                     WHERE job_id=:job_id AND step_status='RUNNING'
                """),
                {"reason": reason_code, "now": now, "job_id": message.job_id},
            )
            return True

    @staticmethod
    def _coordinate(block: object) -> dict[str, object | None]:
        coordinate = getattr(block, "coordinate")
        if coordinate is None:
            return {
                key: None
                for key in (
                    "source_width",
                    "source_height",
                    "source_unit",
                    "x",
                    "y",
                    "width",
                    "height",
                    "normalized_x",
                    "normalized_y",
                    "normalized_width",
                    "normalized_height",
                    "rotation",
                    "coordinate_confidence",
                )
            }
        return {
            "source_width": coordinate.source_width,
            "source_height": coordinate.source_height,
            "source_unit": coordinate.source_unit,
            "x": coordinate.x,
            "y": coordinate.y,
            "width": coordinate.width,
            "height": coordinate.height,
            "normalized_x": coordinate.normalized_x,
            "normalized_y": coordinate.normalized_y,
            "normalized_width": coordinate.normalized_width,
            "normalized_height": coordinate.normalized_height,
            "rotation": coordinate.rotation,
            "coordinate_confidence": coordinate.coordinate_confidence,
        }

    def persist_selected(
        self,
        job_id: str,
        document: NormalizedDocument,
        artifact: ArtifactMetadata,
        *,
        worker_id: str,
    ) -> None:
        if not artifact.is_selected_output:
            raise ValueError("UNSELECTED_OUTPUT_PERSISTENCE_FORBIDDEN")
        with self._engine.begin() as connection:
            owns_lease = connection.execute(
                text("""
                    SELECT 1 FROM app.review_jobs
                     WHERE job_id=:job_id AND job_status='RUNNING' AND locked_by=:worker
                     FOR UPDATE
                """),
                {"job_id": job_id, "worker": worker_id},
            ).scalar_one_or_none()
            if owns_lease is None:
                raise ValueError("ILLEGAL_JOB_TRANSITION")
            selected = connection.execute(
                text("""
                    SELECT raw_artifact_id FROM app.parser_artifacts
                     WHERE review_step_id=:step AND is_selected_output
                """),
                {"step": UUID(artifact.review_step_id)},
            ).scalar_one_or_none()
            if selected != artifact.raw_artifact_id:
                raise ValueError("SELECTED_ARTIFACT_MISMATCH")
            existing_text = {
                row._mapping["ocr_block_id"]: row._mapping["raw_artifact_id"]
                for row in connection.execute(
                    text("""
                        SELECT ocr_block_id,raw_artifact_id FROM app.ocr_text_blocks
                         WHERE review_id=:review_id
                    """),
                    {"review_id": artifact.review_id},
                )
            }
            existing_layout = {
                row._mapping["layout_block_id"]: row._mapping["raw_artifact_id"]
                for row in connection.execute(
                    text("""
                        SELECT layout_block_id,raw_artifact_id FROM app.layout_blocks
                         WHERE review_id=:review_id
                    """),
                    {"review_id": artifact.review_id},
                )
            }
            if existing_text or existing_layout:
                expected_text = {block.text_block_id for block in document.text_blocks}
                expected_layout = {block.layout_block_id for block in document.layout_blocks}
                same_checkpoint = (
                    set(existing_text) == expected_text
                    and set(existing_layout) == expected_layout
                    and all(value == artifact.raw_artifact_id for value in existing_text.values())
                    and all(value == artifact.raw_artifact_id for value in existing_layout.values())
                )
                if same_checkpoint:
                    return
                raise ValueError("SELECTED_OUTPUT_ALREADY_PERSISTED")
            for text_block in document.text_blocks:
                values: dict[str, Any] = {
                    "id": text_block.text_block_id,
                    "review_id": artifact.review_id,
                    "file_id": text_block.file_id,
                    "page_no": text_block.page_no,
                    "raw": text_block.raw_text,
                    "normalized": text_block.normalized_text,
                    "path": text_block.text_path,
                    "type": text_block.text_block_type,
                    "raw_start": text_block.raw_start_offset,
                    "raw_end": text_block.raw_end_offset,
                    "normalized_start": text_block.normalized_start_offset,
                    "normalized_end": text_block.normalized_end_offset,
                    "parser": text_block.parser_name,
                    "version": text_block.parser_version,
                    "rules": text_block.parser_rule_version,
                    "ir": text_block.ir_version,
                    "confidence": text_block.confidence_score,
                    "confidence_status": text_block.confidence_status.value,
                    "policy": text_block.confidence_policy_version,
                    "artifact": artifact.raw_artifact_id,
                    "created": artifact.created_at,
                    **self._coordinate(text_block),
                }
                connection.execute(
                    text("""
                        INSERT INTO app.ocr_text_blocks
                        (ocr_block_id,review_id,file_id,page_no,block_text,normalized_text,text_path,
                         text_block_type,raw_start_offset,raw_end_offset,normalized_start_offset,
                         normalized_end_offset,parser_name,parser_version,parser_rule_version,
                         ir_version,confidence_score,confidence_status,confidence_policy_version,
                         source_width,source_height,source_unit,x,y,width,height,normalized_x,normalized_y,
                         normalized_width,normalized_height,rotation,coordinate_confidence,
                         raw_artifact_id,created_at)
                        VALUES (:id,:review_id,:file_id,:page_no,:raw,:normalized,:path,:type,
                         :raw_start,:raw_end,:normalized_start,:normalized_end,:parser,:version,
                         :rules,:ir,:confidence,:confidence_status,:policy,:source_width,
                         :source_height,:source_unit,:x,:y,:width,:height,:normalized_x,
                         :normalized_y,:normalized_width,:normalized_height,:rotation,
                         :coordinate_confidence,:artifact,:created)
                    """),
                    values,
                )
            for layout_block in document.layout_blocks:
                connection.execute(
                    text("""
                        INSERT INTO app.layout_blocks
                        (layout_block_id,review_id,file_id,page_no,layout_type,source_width,
                         source_height,source_unit,x,y,width,height,normalized_x,normalized_y,normalized_width,
                         normalized_height,rotation,coordinate_confidence,related_ocr_block_ids,
                         confidence_score,raw_artifact_id,created_at)
                        VALUES (:id,:review_id,:file_id,:page_no,:type,:source_width,:source_height,
                         :source_unit,:x,:y,:width,:height,:normalized_x,:normalized_y,:normalized_width,
                         :normalized_height,:rotation,:coordinate_confidence,
                         CAST(:related AS jsonb),:confidence,:artifact,:created)
                    """),
                    {
                        "id": layout_block.layout_block_id,
                        "review_id": artifact.review_id,
                        "file_id": layout_block.file_id,
                        "page_no": layout_block.page_no,
                        "type": layout_block.layout_type,
                        "related": __import__("json").dumps(layout_block.related_text_block_ids),
                        "confidence": layout_block.confidence_score,
                        "artifact": artifact.raw_artifact_id,
                        "created": artifact.created_at,
                        **self._coordinate(layout_block),
                    },
                )

    def persist_results(self, job_id: str, results: ReviewResultBundle, *, worker_id: str) -> None:
        """Persist a complete M5 result bundle in the migration-0005 owner tables."""
        with self._engine.begin() as connection:
            review_id = connection.execute(
                text("""
                    SELECT review_id FROM app.review_jobs
                     WHERE job_id=:job_id AND job_status='RUNNING' AND locked_by=:worker
                     FOR UPDATE
                """),
                {"job_id": job_id, "worker": worker_id},
            ).scalar_one_or_none()
            if review_id is None:
                raise ValueError("ILLEGAL_JOB_TRANSITION")
            if review_id != results.review_id:
                raise ValueError("REVIEW_RESULT_SOURCE_NOT_PERSISTED")
            existing = set(
                connection.execute(
                    text("SELECT review_item_id FROM app.review_items WHERE review_id=:review_id"),
                    {"review_id": review_id},
                ).scalars()
            )
            if existing:
                expected = {item.review_item_id for item in results.items}
                if existing == expected:
                    return
                raise ValueError("REVIEW_RESULTS_ALREADY_PERSISTED")
            for item in results.items:
                connection.execute(
                    text("""
                        INSERT INTO app.review_items
                        (review_item_id,review_id,review_type,target_text,normalized_target_text,
                         result_status,risk_level,risk_policy_version,risk_reason_codes,
                         risk_score_detail,evidence_status,evidence_failure_code,reason,
                         recommendation,engine_type,engine_version,confidence_score,page_no,
                         result_json,created_at)
                        VALUES (:id,:review_id,:review_type,:target,:normalized,:result_status,
                         :risk_level,:policy,CAST(:codes AS jsonb),CAST(:score AS jsonb),
                         :evidence_status,:failure,:reason,:recommendation,:engine,:version,
                         :confidence,:page_no,CAST(:result AS jsonb),CURRENT_TIMESTAMP)
                    """),
                    {
                        "id": item.review_item_id,
                        "review_id": item.review_id,
                        "review_type": item.review_type,
                        "target": item.target_text,
                        "normalized": item.target_text.casefold(),
                        "result_status": item.result_status,
                        "risk_level": item.risk_level,
                        "policy": item.risk_policy_version,
                        "codes": json.dumps(item.risk_reason_codes),
                        "score": json.dumps(item.score_detail),
                        "evidence_status": item.evidence_status,
                        "failure": item.evidence_failure_code,
                        "reason": item.reason,
                        "recommendation": item.recommendation,
                        "engine": item.source_engine,
                        "version": item.source_version,
                        "confidence": item.confidence_score,
                        "page_no": item.page_no,
                        "result": json.dumps(
                            {
                                "schemaVersion": "review-result-v1",
                                "scoreDetail": item.score_detail,
                            }
                        ),
                    },
                )
                for evidence in item.evidences:
                    candidate = evidence.candidate
                    connection.execute(
                        text("""
                            INSERT INTO app.review_item_evidences
                            (review_item_evidence_id,review_item_id,evidence_id,
                             standard_version_id,evidence_chunk_id,matched_text,relevance_score,
                             rank_no,match_source,score_detail,created_at)
                            VALUES (:id,:item,:evidence,:version,:chunk,:matched,:score,:rank,
                             :source,CAST(:detail AS jsonb),CURRENT_TIMESTAMP)
                        """),
                        {
                            "id": uuid4(),
                            "item": item.review_item_id,
                            "evidence": candidate.evidence_id,
                            "version": candidate.standard_version_id,
                            "chunk": candidate.evidence_chunk_id,
                            "matched": candidate.matched_text,
                            "score": candidate.relevance_score,
                            "rank": evidence.rank_no,
                            "source": candidate.match_source,
                            "detail": json.dumps({"selection": "TOP_K", "rank": evidence.rank_no}),
                        },
                    )
                annotation = item.annotation
                if annotation is None:
                    continue
                coordinate = annotation.coordinate
                coordinate_values = {
                    "source_width": coordinate.source_width if coordinate else None,
                    "source_height": coordinate.source_height if coordinate else None,
                    "source_unit": coordinate.source_unit if coordinate else None,
                    "x": coordinate.x if coordinate else None,
                    "y": coordinate.y if coordinate else None,
                    "width": coordinate.width if coordinate else None,
                    "height": coordinate.height if coordinate else None,
                    "normalized_x": coordinate.normalized_x if coordinate else None,
                    "normalized_y": coordinate.normalized_y if coordinate else None,
                    "normalized_width": coordinate.normalized_width if coordinate else None,
                    "normalized_height": coordinate.normalized_height if coordinate else None,
                    "rotation": coordinate.rotation if coordinate else None,
                    "coordinate_confidence": coordinate.coordinate_confidence
                    if coordinate
                    else None,
                }
                connection.execute(
                    text("""
                        INSERT INTO app.annotations
                        (annotation_id,review_id,review_item_id,file_id,page_no,text_block_id,
                         text_path,annotation_display_mode,annotation_status,location_confidence,
                         confidence_policy_version,display_reason,annotation_type,source_width,
                         source_height,source_unit,x,y,width,height,normalized_x,normalized_y,
                         normalized_width,normalized_height,rotation,coordinate_confidence,
                         raw_start_offset,raw_end_offset,normalized_start_offset,
                         normalized_end_offset,matched_text,risk_level,review_type,display_order,
                         created_at)
                        VALUES (:id,:review_id,:item,:file,:page_no,:text_block,:text_path,:mode,
                         :status,:location_confidence,:policy,:display_reason,'REVIEW_RESULT',
                         :source_width,:source_height,:source_unit,:x,:y,:width,:height,
                         :normalized_x,:normalized_y,:normalized_width,:normalized_height,
                         :rotation,:coordinate_confidence,:raw_start,:raw_end,:normalized_start,
                         :normalized_end,:matched,:risk,:review_type,0,CURRENT_TIMESTAMP)
                    """),
                    {
                        "id": annotation.annotation_id,
                        "review_id": annotation.review_id,
                        "item": annotation.review_item_id,
                        "file": annotation.file_id,
                        "page_no": annotation.page_no,
                        "text_block": annotation.text_block_id,
                        "text_path": annotation.text_path,
                        "mode": annotation.display_mode,
                        "status": annotation.status,
                        "location_confidence": annotation.location_confidence,
                        "policy": annotation.confidence_policy_version,
                        "display_reason": annotation.display_reason,
                        "raw_start": annotation.raw_start_offset,
                        "raw_end": annotation.raw_end_offset,
                        "normalized_start": annotation.normalized_start_offset,
                        "normalized_end": annotation.normalized_end_offset,
                        "matched": annotation.matched_text,
                        "risk": annotation.risk_level,
                        "review_type": annotation.review_type,
                        **coordinate_values,
                    },
                )
            severity = {"LOW": 0, "MEDIUM": 1, "CHECK_REQUIRED": 2, "HIGH": 3}
            overall = (
                max(results.items, key=lambda item: severity[item.risk_level]).risk_level
                if results.items
                else "CHECK_REQUIRED"
            )
            connection.execute(
                text("""
                    UPDATE app.reviews
                       SET applied_standard_version_ids=CAST(:versions AS jsonb),
                           overall_risk_level=:risk,updated_at=CURRENT_TIMESTAMP
                     WHERE review_id=:review_id
                """),
                {
                    "versions": json.dumps(results.standard_version_ids),
                    "risk": overall,
                    "review_id": results.review_id,
                },
            )

    def persist_suggestions(
        self,
        job_id: str,
        suggestions: tuple[SuggestionProposal, ...],
        *,
        worker_id: str,
    ) -> None:
        """Insert deterministic Rule suggestions without overwriting human decisions."""
        with self._engine.begin() as connection:
            review_id = connection.execute(
                text("""
                    SELECT review_id FROM app.review_jobs
                     WHERE job_id=:job_id AND job_status='RUNNING' AND locked_by=:worker
                     FOR UPDATE
                """),
                {"job_id": job_id, "worker": worker_id},
            ).scalar_one_or_none()
            if review_id is None:
                raise ValueError("ILLEGAL_JOB_TRANSITION")
            for suggestion in suggestions:
                if suggestion.review_id != review_id:
                    raise ValueError("SUGGESTION_REVIEW_MISMATCH")
                connection.execute(
                    text("""
                        INSERT INTO app.suggestions
                        (suggestion_id,review_id,review_item_id,original_text,suggested_text,
                         suggestion_reason,suggestion_type,evidence_ids,decision_status,created_at)
                        VALUES (:id,:review_id,:item_id,:original,:suggested,:reason,:type,
                                CAST(:evidence_ids AS jsonb),'PENDING',CURRENT_TIMESTAMP)
                        ON CONFLICT (suggestion_id) DO NOTHING
                    """),
                    {
                        "id": suggestion.suggestion_id,
                        "review_id": suggestion.review_id,
                        "item_id": suggestion.review_item_id,
                        "original": suggestion.original_text,
                        "suggested": suggestion.suggested_text,
                        "reason": suggestion.suggestion_reason,
                        "type": suggestion.suggestion_type,
                        "evidence_ids": json.dumps(suggestion.evidence_ids),
                    },
                )

    def complete(self, job_id: str, *, worker_id: str, now: datetime, check_required: bool) -> None:
        review_status = "CHECK_REQUIRED" if check_required else "REVIEW_COMPLETED"
        with self._engine.begin() as connection:
            review_id = connection.execute(
                text("""
                    UPDATE app.review_jobs
                       SET job_status='COMPLETED',progress_rate=100,current_step=NULL,
                           completed_at=:now,heartbeat_at=:now,locked_by=NULL,locked_at=NULL,
                           is_retryable=false
                     WHERE job_id=:job_id AND job_status='RUNNING' AND locked_by=:worker
                    RETURNING review_id
                """),
                {"now": now, "job_id": job_id, "worker": worker_id},
            ).scalar_one_or_none()
            if review_id is None:
                raise ValueError("ILLEGAL_JOB_TRANSITION")
            connection.execute(
                text("""
                    UPDATE app.review_steps SET step_status='COMPLETED',completed_at=:now
                     WHERE job_id=:job_id AND step_code IN
                           ('FILE_PREPROCESSING','OCR_EXTRACTION','LAYOUT_ANALYSIS','RULE_REVIEW','RAG_REVIEW',
                            'RESULT_GENERATION')
                """),
                {"now": now, "job_id": job_id},
            )
            advertisement_id = connection.execute(
                text("""
                    UPDATE app.reviews SET review_status=:status,completed_at=:now,updated_at=:now
                     WHERE review_id=:review_id RETURNING advertisement_id
                """),
                {"status": review_status, "now": now, "review_id": review_id},
            ).scalar_one()
            connection.execute(
                text(
                    "UPDATE app.advertisements SET review_status=:status,updated_at=:now WHERE advertisement_id=:id"
                ),
                {"status": review_status, "now": now, "id": advertisement_id},
            )

    def retry_or_dead_letter(
        self, job_id: str, *, worker_id: str, now: datetime, reason_code: str
    ) -> bool:
        with self._engine.begin() as connection:
            found = connection.execute(
                text("""
                    SELECT review_id,retry_count,max_retries FROM app.review_jobs
                     WHERE job_id=:id AND job_status='RUNNING' AND locked_by=:worker
                     FOR UPDATE
                """),
                {"id": job_id, "worker": worker_id},
            ).first()
            if found is None:
                raise ValueError("ILLEGAL_JOB_TRANSITION")
            row = found._mapping
            if row["retry_count"] >= row["max_retries"]:
                connection.execute(
                    text("""
                        UPDATE app.review_jobs SET job_status='FAILED_FINAL',is_retryable=false,
                         failed_reason_code=:reason,dead_lettered_at=:now,
                         locked_by=NULL,locked_at=NULL
                         WHERE job_id=:id AND job_status='RUNNING' AND locked_by=:worker
                    """),
                    {"reason": reason_code, "now": now, "id": job_id, "worker": worker_id},
                )
                connection.execute(
                    text(
                        "UPDATE app.reviews SET review_status='REVIEW_FAILED',failed_reason=:reason,updated_at=:now WHERE review_id=:id"
                    ),
                    {"reason": reason_code, "now": now, "id": row["review_id"]},
                )
                connection.execute(
                    text("""
                        UPDATE app.review_steps
                           SET step_status='FAILED',completed_at=:now,failed_reason_code=:reason
                         WHERE job_id=:id AND step_status='RUNNING'
                    """),
                    {"reason": reason_code, "now": now, "id": job_id},
                )
                return False
            count = row["retry_count"] + 1
            next_retry = now + RETRY_DELAYS[count - 1]
            connection.execute(
                text("""
                    UPDATE app.review_jobs SET job_status='RETRY_PENDING',retry_count=:count,
                     next_retry_at=:next_retry,failed_reason_code=:reason,locked_by=NULL,
                     locked_at=NULL,enqueued_at=NULL
                     WHERE job_id=:id AND job_status='RUNNING' AND locked_by=:worker
                """),
                {
                    "count": count,
                    "next_retry": next_retry,
                    "reason": reason_code,
                    "id": job_id,
                    "worker": worker_id,
                },
            )
            connection.execute(
                text(
                    "UPDATE app.review_steps SET step_status='RETRY_PENDING',failed_reason_code=:reason WHERE job_id=:id AND step_code='OCR_EXTRACTION'"
                ),
                {"reason": reason_code, "id": job_id},
            )
            return True

    def fail_final(self, job_id: str, *, worker_id: str, now: datetime, reason_code: str) -> None:
        with self._engine.begin() as connection:
            review_id = connection.execute(
                text("""
                    UPDATE app.review_jobs SET job_status='FAILED_FINAL',is_retryable=false,
                     failed_reason_code=:reason,dead_lettered_at=:now,
                     locked_by=NULL,locked_at=NULL
                     WHERE job_id=:id AND job_status='RUNNING' AND locked_by=:worker
                    RETURNING review_id
                """),
                {"reason": reason_code, "now": now, "id": job_id, "worker": worker_id},
            ).scalar_one_or_none()
            if review_id is None:
                raise ValueError("ILLEGAL_JOB_TRANSITION")
            connection.execute(
                text(
                    "UPDATE app.reviews SET review_status='REVIEW_FAILED',failed_reason=:reason,updated_at=:now WHERE review_id=:id"
                ),
                {"reason": reason_code, "now": now, "id": review_id},
            )
            connection.execute(
                text("""
                    UPDATE app.review_steps
                       SET step_status='FAILED',completed_at=:now,failed_reason_code=:reason
                     WHERE job_id=:id AND step_status='RUNNING'
                """),
                {"reason": reason_code, "now": now, "id": job_id},
            )

    def recover_stale(self, *, now: datetime, stale_before: datetime) -> list[QueueMessage]:
        with self._engine.begin() as connection:
            connection.execute(
                text("""
                    UPDATE app.review_jobs SET job_status='STALE',locked_by=NULL,locked_at=NULL,
                     enqueued_at=NULL
                     WHERE job_status='RUNNING' AND heartbeat_at<:stale_before
                """),
                {"stale_before": stale_before},
            )
            rows = connection.execute(
                text("""
                    WITH candidates AS (
                        SELECT job_id
                          FROM app.review_jobs
                         WHERE (
                               job_status='STALE'
                            OR (job_status='PENDING' AND created_at<=:stale_before)
                            OR (job_status='RETRY_PENDING' AND next_retry_at<=:now)
                         )
                           AND (enqueued_at IS NULL OR enqueued_at<=:stale_before)
                         ORDER BY created_at,job_id
                         FOR UPDATE SKIP LOCKED
                    )
                    UPDATE app.review_jobs AS jobs
                       SET enqueued_at=:now
                      FROM candidates
                     WHERE jobs.job_id=candidates.job_id
                    RETURNING jobs.job_id,jobs.review_id,jobs.job_type
                """),
                {"now": now, "stale_before": stale_before},
            ).all()
        return [
            QueueMessage(
                job_id=row._mapping["job_id"],
                review_id=row._mapping["review_id"],
                job_type=row._mapping["job_type"],
                correlation_id=f"recovery-{row._mapping['job_id']}",
                idempotency_key=row._mapping["job_id"],
            )
            for row in rows
        ]

    def close(self) -> None:
        self._engine.dispose()


def _is_scanned_pdf(*, file_name: str, mime_type: str, body: bytes) -> bool:
    """Route image-only PDFs to PaddleOCR before the parser selection is made."""

    if not (file_name.casefold().endswith(".pdf") or mime_type == "application/pdf"):
        return False
    try:
        reader = PdfReader(BytesIO(body))
        return not any((page.extract_text() or "").strip() for page in reader.pages)
    except Exception:
        # The primary PDF adapter owns malformed-PDF errors and their retry policy.
        return False
