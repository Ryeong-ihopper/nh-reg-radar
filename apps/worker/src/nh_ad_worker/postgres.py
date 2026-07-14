"""PostgreSQL job and parser-artifact persistence for M4 workers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from typing import Any
from uuid import UUID
from uuid import uuid4

from nh_ad_parser_contracts import ArtifactMetadata, DocumentInput, NormalizedDocument
from sqlalchemy import Engine, text

from nh_ad_worker.jobs import QueueMessage, RETRY_DELAYS, WorkerJob


class PostgresArtifactMetadataRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, item: ArtifactMetadata) -> None:
        with self._engine.begin() as connection:
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

    def get(self, raw_artifact_id: str) -> ArtifactMetadata | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                text("SELECT * FROM app.parser_artifacts WHERE raw_artifact_id=:id"),
                {"id": raw_artifact_id},
            ).first()
        if row is None:
            return None
        value = dict(row._mapping)
        value["review_step_id"] = str(value["review_step_id"])
        value.pop("rerun_reason_message", None)
        return ArtifactMetadata(**value)

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
    ) -> None:
        self._engine = engine
        self._source_loader = source_loader

    def claim(self, message: QueueMessage, *, worker_id: str, now: datetime) -> WorkerJob | None:
        if message.idempotency_key != message.job_id:
            raise ValueError("IDEMPOTENCY_KEY_MISMATCH")
        with self._engine.begin() as connection:
            job = connection.execute(
                text("""
                    UPDATE app.review_jobs
                       SET job_status='RUNNING',locked_by=:worker,locked_at=:now,
                           heartbeat_at=:now,started_at=COALESCE(started_at,:now),
                           current_step='OCR_EXTRACTION'
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
                     WHERE job_id=:job_id AND step_code='OCR_EXTRACTION'
                    RETURNING review_step_id
                """),
                {"now": now, "job_id": message.job_id},
            ).scalar_one()
            source = (
                connection.execute(
                    text("""
                    SELECT f.file_id,f.original_file_name,f.mime_type,f.bucket,f.object_key
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
                external_ai_allowed=False,
            ),
            review_step_id=str(step),
            status="RUNNING",
            retry_count=job._mapping["retry_count"],
            max_retries=job._mapping["max_retries"],
            heartbeat_at=now,
            locked_by=worker_id,
            review_status="ANALYZING",
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
                    "coordinate_x",
                    "coordinate_y",
                    "coordinate_width",
                    "coordinate_height",
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
            "coordinate_x": coordinate.x,
            "coordinate_y": coordinate.y,
            "coordinate_width": coordinate.width,
            "coordinate_height": coordinate.height,
            "normalized_x": coordinate.normalized_x,
            "normalized_y": coordinate.normalized_y,
            "normalized_width": coordinate.normalized_width,
            "normalized_height": coordinate.normalized_height,
            "rotation": coordinate.rotation,
            "coordinate_confidence": coordinate.coordinate_confidence,
        }

    def persist_selected(
        self, job_id: str, document: NormalizedDocument, artifact: ArtifactMetadata
    ) -> None:
        if not artifact.is_selected_output:
            raise ValueError("UNSELECTED_OUTPUT_PERSISTENCE_FORBIDDEN")
        with self._engine.begin() as connection:
            selected = connection.execute(
                text("""
                    SELECT raw_artifact_id FROM app.parser_artifacts
                     WHERE review_step_id=:step AND is_selected_output
                """),
                {"step": UUID(artifact.review_step_id)},
            ).scalar_one_or_none()
            if selected != artifact.raw_artifact_id:
                raise ValueError("SELECTED_ARTIFACT_MISMATCH")
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
                         source_width,source_height,source_unit,coordinate_x,coordinate_y,
                         coordinate_width,coordinate_height,normalized_x,normalized_y,
                         normalized_width,normalized_height,rotation,coordinate_confidence,
                         raw_artifact_id,created_at)
                        VALUES (:id,:review_id,:file_id,:page_no,:raw,:normalized,:path,:type,
                         :raw_start,:raw_end,:normalized_start,:normalized_end,:parser,:version,
                         :rules,:ir,:confidence,:confidence_status,:policy,:source_width,
                         :source_height,:source_unit,:coordinate_x,:coordinate_y,:coordinate_width,
                         :coordinate_height,:normalized_x,:normalized_y,:normalized_width,
                         :normalized_height,:rotation,:coordinate_confidence,:artifact,:created)
                    """),
                    values,
                )
            for layout_block in document.layout_blocks:
                connection.execute(
                    text("""
                        INSERT INTO app.layout_blocks
                        (layout_block_id,review_id,file_id,page_no,layout_type,source_width,
                         source_height,source_unit,coordinate_x,coordinate_y,coordinate_width,
                         coordinate_height,normalized_x,normalized_y,normalized_width,
                         normalized_height,rotation,coordinate_confidence,related_ocr_block_ids,
                         confidence_score,raw_artifact_id,created_at)
                        VALUES (:id,:review_id,:file_id,:page_no,:type,:source_width,:source_height,
                         :source_unit,:coordinate_x,:coordinate_y,:coordinate_width,
                         :coordinate_height,:normalized_x,:normalized_y,:normalized_width,
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

    def complete(self, job_id: str, *, now: datetime, check_required: bool) -> None:
        review_status = "CHECK_REQUIRED" if check_required else "REVIEW_COMPLETED"
        with self._engine.begin() as connection:
            review_id = connection.execute(
                text("""
                    UPDATE app.review_jobs
                       SET job_status='COMPLETED',progress_rate=100,current_step=NULL,
                           completed_at=:now,heartbeat_at=:now,locked_by=NULL,locked_at=NULL,
                           is_retryable=false
                     WHERE job_id=:job_id AND job_status='RUNNING'
                    RETURNING review_id
                """),
                {"now": now, "job_id": job_id},
            ).scalar_one_or_none()
            if review_id is None:
                raise ValueError("ILLEGAL_JOB_TRANSITION")
            connection.execute(
                text("""
                    UPDATE app.review_steps SET step_status='COMPLETED',completed_at=:now
                     WHERE job_id=:job_id AND step_code='OCR_EXTRACTION'
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

    def retry_or_dead_letter(self, job_id: str, *, now: datetime, reason_code: str) -> bool:
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT review_id,retry_count,max_retries FROM app.review_jobs WHERE job_id=:id FOR UPDATE"
                    ),
                    {"id": job_id},
                )
                .one()
                ._mapping
            )
            if row["retry_count"] >= row["max_retries"]:
                connection.execute(
                    text("""
                        UPDATE app.review_jobs SET job_status='FAILED_FINAL',is_retryable=false,
                         failed_reason_code=:reason,dead_lettered_at=:now,locked_by=NULL
                         WHERE job_id=:id
                    """),
                    {"reason": reason_code, "now": now, "id": job_id},
                )
                connection.execute(
                    text(
                        "UPDATE app.reviews SET review_status='REVIEW_FAILED',failed_reason=:reason,updated_at=:now WHERE review_id=:id"
                    ),
                    {"reason": reason_code, "now": now, "id": row["review_id"]},
                )
                return False
            count = row["retry_count"] + 1
            next_retry = now + RETRY_DELAYS[count - 1]
            connection.execute(
                text("""
                    UPDATE app.review_jobs SET job_status='RETRY_PENDING',retry_count=:count,
                     next_retry_at=:next_retry,failed_reason_code=:reason,locked_by=NULL,locked_at=NULL
                     WHERE job_id=:id
                """),
                {
                    "count": count,
                    "next_retry": next_retry,
                    "reason": reason_code,
                    "id": job_id,
                },
            )
            connection.execute(
                text(
                    "UPDATE app.review_steps SET step_status='RETRY_PENDING',failed_reason_code=:reason WHERE job_id=:id AND step_code='OCR_EXTRACTION'"
                ),
                {"reason": reason_code, "id": job_id},
            )
            return True

    def fail_final(self, job_id: str, *, now: datetime, reason_code: str) -> None:
        with self._engine.begin() as connection:
            review_id = connection.execute(
                text("""
                    UPDATE app.review_jobs SET job_status='FAILED_FINAL',is_retryable=false,
                     failed_reason_code=:reason,dead_lettered_at=:now,locked_by=NULL
                     WHERE job_id=:id AND job_status='RUNNING' RETURNING review_id
                """),
                {"reason": reason_code, "now": now, "id": job_id},
            ).scalar_one_or_none()
            if review_id is None:
                raise ValueError("ILLEGAL_JOB_TRANSITION")
            connection.execute(
                text(
                    "UPDATE app.reviews SET review_status='REVIEW_FAILED',failed_reason=:reason,updated_at=:now WHERE review_id=:id"
                ),
                {"reason": reason_code, "now": now, "id": review_id},
            )

    def recover_stale(self, *, now: datetime, stale_before: datetime) -> list[QueueMessage]:
        with self._engine.begin() as connection:
            rows = connection.execute(
                text("""
                    UPDATE app.review_jobs SET job_status='STALE',locked_by=NULL,locked_at=NULL
                     WHERE job_status='RUNNING' AND heartbeat_at<:stale_before
                    RETURNING job_id,review_id,job_type
                """),
                {"stale_before": stale_before},
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
