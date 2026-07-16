"""Opt-in actual PostgreSQL + Redis + MinIO M4 evidence.

Apply migrations through 0004 and provision the two private buckets, then set
M4_LIVE_DATABASE_URL, M4_LIVE_REDIS_URL, M4_LIVE_S3_ENDPOINT,
M4_LIVE_S3_ACCESS_KEY, and M4_LIVE_S3_SECRET_KEY.  Synthetic fixtures only;
no provider execution or customer data is used.
"""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from nh_ad_parser_contracts import (
    ArtifactAccessDenied,
    ArtifactStore,
    DocumentInput,
    NormalizedDocument,
    ParserRoute,
    ParserRouter,
)
from redis import Redis
from sqlalchemy import create_engine, text

from nh_ad_backend.reviews import (
    PostgresReviewRepository,
    RedisReviewQueue,
    Review,
    ReviewBundle,
    ReviewJob,
    ReviewQueueMessage,
    ReviewStep,
    STEP_DEFINITIONS,
)
from nh_ad_worker.jobs import ParserJobProcessor
from nh_ad_worker.object_storage import S3ArtifactStorage
from nh_ad_worker.postgres import (
    PostgresArtifactAudit,
    PostgresArtifactMetadataRepository,
    PostgresJobRepository,
)
from nh_ad_worker.queue import RedisDeadLetterSink, RedisJobQueue


FIXTURE = Path(__file__).parents[1] / "fixtures" / "m4" / "normalized-image-v1.json"


class FixtureAdapter:
    def __init__(self, name: str, document: NormalizedDocument) -> None:
        self.name = name
        self.document = document

    def parse(self, _input: object) -> NormalizedDocument:
        return self.document


class QualityRerunRouter(ParserRouter):
    """Marks the synthetic complex PDF as an ADR-0073 rerun candidate."""

    def route(self, _document: DocumentInput) -> ParserRoute:
        return ParserRoute(
            "opendataloader-pdf",
            ("mineru",),
            "TABLE_EXTRACTION_MISSING",
        )


def normalized_candidate(
    fixture_data: dict[str, object], parser_name: str, score: float
) -> NormalizedDocument:
    data = json.loads(json.dumps(fixture_data))
    status = "READABLE" if score >= 0.8 else "LOW_CONFIDENCE" if score >= 0.5 else "UNREADABLE"
    data["sourceFileType"] = "pdf"
    data["parserName"] = parser_name
    data["parserVersion"] = f"{parser_name}-fixture-1"
    data["confidence"] = {
        "score": score,
        "status": status,
        "policyVersion": "confidence-thresholds-v1",
    }
    for block in data["textBlocks"]:
        block["parserName"] = parser_name
        block["parserVersion"] = f"{parser_name}-fixture-1"
        block["confidenceScore"] = score
        block["confidenceStatus"] = status
    return NormalizedDocument.model_validate(data)


def test_actual_postgres_redis_minio_review_worker_vertical() -> None:
    database_url = os.getenv("M4_LIVE_DATABASE_URL")
    redis_url = os.getenv("M4_LIVE_REDIS_URL")
    endpoint = os.getenv("M4_LIVE_S3_ENDPOINT")
    access_key = os.getenv("M4_LIVE_S3_ACCESS_KEY")
    secret_key = os.getenv("M4_LIVE_S3_SECRET_KEY")
    if not all((database_url, redis_url, endpoint, access_key, secret_key)):
        pytest.skip("set M4_LIVE_DATABASE_URL/REDIS_URL/S3_* for live tri-store")
    assert database_url and redis_url and endpoint and access_key and secret_key

    suffix = uuid4().hex[:10]
    department_id, user_id = f"DPT-M4-{suffix}", f"USR-M4-{suffix}"
    advertisement_id, file_id = f"ADV-M4-{suffix}", f"FILE-M4-{suffix}"
    review_id, job_id = f"REV-M4-{suffix}", f"JOB-M4-{suffix}"
    queue_name, dead_name = f"m4-live-{suffix}", f"m4-live-{suffix}-dead"
    originals_bucket = os.getenv("M4_LIVE_AD_BUCKET", "nh-ad-originals")
    artifacts_bucket = os.getenv("M4_LIVE_ARTIFACT_BUCKET", "parser-artifacts")
    original_key = f"advertisements/{suffix}.png"
    now = datetime.now(UTC)
    engine = create_engine(database_url, pool_pre_ping=True)
    redis = Redis.from_url(redis_url, decode_responses=True)
    storage = S3ArtifactStorage(endpoint, access_key, secret_key)
    storage.put(originals_bucket, original_key, b"synthetic-image", "image/png")

    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO app.departments(department_id,department_name) VALUES (:id,'M4 Synthetic')"
            ),
            {"id": department_id},
        )
        connection.execute(
            text("""
                INSERT INTO app.users
                (user_id,auth_provider,user_name,email,department_id,user_status)
                VALUES (:id,'LOCAL','M4 Synthetic',:email,:department,'ACTIVE')
            """),
            {"id": user_id, "email": f"{suffix}@example.invalid", "department": department_id},
        )
        connection.execute(
            text("""
                INSERT INTO app.advertisements
                (advertisement_id,advertisement_name,product_group,advertisement_type,
                 department_id,owner_user_id,review_status,created_by)
                VALUES (:id,'M4 synthetic','SAVINGS','MOBILE_BANNER',:department,:user,'UPLOADED',:user)
            """),
            {"id": advertisement_id, "department": department_id, "user": user_id},
        )
        connection.execute(
            text("""
                INSERT INTO app.advertisement_files
                (file_id,advertisement_id,file_type,original_file_name,storage_provider,bucket,
                 object_key,mime_type,file_size,checksum_sha256,created_by)
                VALUES (:file,:advertisement,'ADVERTISEMENT','synthetic.png','minio',:bucket,
                 :key,'image/png',15,:checksum,:user)
            """),
            {
                "file": file_id,
                "advertisement": advertisement_id,
                "bucket": originals_bucket,
                "key": original_key,
                "checksum": "0" * 64,
                "user": user_id,
            },
        )

    repository = PostgresReviewRepository(engine, queue_name)
    steps = [
        ReviewStep(uuid4(), code, name, "PENDING", index, now + timedelta(seconds=seconds))
        for index, (code, name, seconds) in enumerate(STEP_DEFINITIONS, 1)
    ]
    repository.add(
        ReviewBundle(
            Review(
                review_id,
                advertisement_id,
                None,
                1,
                "ANALYSIS_REQUESTED",
                now.date(),
                (),
                ("OCR_QUALITY",),
                False,
                False,
                "live synthetic evidence",
                now,
                user_id,
            ),
            ReviewJob(
                job_id,
                review_id,
                "REVIEW_ANALYSIS",
                "PENDING",
                0,
                0,
                3,
                now + timedelta(minutes=30),
            ),
            steps,
        )
    )
    message = ReviewQueueMessage(job_id, review_id, "REVIEW_ANALYSIS", f"corr-{suffix}", job_id)
    RedisReviewQueue(redis_url, queue_name).publish(message)
    raw_envelope = json.loads(redis.lindex(queue_name, 0))
    assert set(raw_envelope) == {
        "messageVersion",
        "jobId",
        "reviewId",
        "jobType",
        "correlationId",
        "idempotencyKey",
    }

    fixture_data = json.loads(FIXTURE.read_text())
    fixture_data["reviewId"], fixture_data["sourceFileId"] = review_id, file_id
    fixture_data["documentId"] = f"DOC-M4-{suffix}"
    fixture_data["rawArtifactRef"] = f"ART-M4-{suffix}"
    for block in fixture_data["textBlocks"]:
        block["fileId"] = file_id
        block["textBlockId"] = f"{block['textBlockId']}-{suffix}"
    for block in fixture_data["layoutBlocks"]:
        block["fileId"] = file_id
        block["layoutBlockId"] = f"{block['layoutBlockId']}-{suffix}"
        block["relatedTextBlockIds"] = []
    primary = normalized_candidate(fixture_data, "opendataloader-pdf", 0.49)
    secondary = normalized_candidate(fixture_data, "mineru", 0.91)

    metadata = PostgresArtifactMetadataRepository(engine)
    artifacts = ArtifactStore(
        storage,
        metadata,
        bucket=artifacts_bucket,
        audit=PostgresArtifactAudit(engine),
    )
    job_repository = PostgresJobRepository(engine, storage.get)
    queue = RedisJobQueue(redis_url, queue_name=queue_name, dead_letter_name=dead_name)
    processor = ParserJobProcessor(
        job_repository,
        QualityRerunRouter(
            {
                "opendataloader-pdf": FixtureAdapter("opendataloader-pdf", primary),
                "mineru": FixtureAdapter("mineru", secondary),
            }
        ),
        artifacts,
        RedisDeadLetterSink(queue),
        worker_id=f"worker-{suffix}",
        now=lambda: now,
        raw_output=lambda _source, result: json.dumps(
            {"provider": result.parser_name}, separators=(",", ":")
        ).encode(),
    )
    payload = queue.pop(timeout=1)
    assert payload is not None and processor.process(payload) == "COMPLETED"
    assert processor.process(payload) == "DUPLICATE_IGNORED"

    with engine.connect() as connection:
        row = (
            connection.execute(
                text("""
                SELECT j.job_status,r.review_status,
                       (SELECT COUNT(*) FROM app.ocr_text_blocks b WHERE b.review_id=r.review_id) blocks,
                       (SELECT COUNT(*) FROM app.review_steps s WHERE s.job_id=j.job_id
                         AND s.step_status <> 'COMPLETED') incomplete_steps,
                       (SELECT COUNT(*) FROM app.parser_artifacts a WHERE a.review_id=r.review_id
                        AND a.is_selected_output) selected,
                       (SELECT COUNT(*) FROM app.parser_artifacts a
                         WHERE a.review_id=r.review_id) attempts
                  FROM app.review_jobs j JOIN app.reviews r USING(review_id)
                 WHERE j.job_id=:job
            """),
                {"job": job_id},
            )
            .one()
            ._mapping
        )
        assert (row["job_status"], row["review_status"]) == ("COMPLETED", "REVIEW_COMPLETED")
        assert row["incomplete_steps"] == 0
        assert row["blocks"] > 0 and row["selected"] == 1 and row["attempts"] == 2
        attempts = connection.execute(
            text("""
                SELECT raw_artifact_id,parser_name,attempt_no,is_primary_attempt,
                       is_selected_output,rerun_reason_code,confidence_score,object_key
                  FROM app.parser_artifacts WHERE review_id=:review ORDER BY attempt_no
            """),
            {"review": review_id},
        ).all()
        attempt_rows = [attempt._mapping for attempt in attempts]
        assert [attempt["parser_name"] for attempt in attempt_rows] == [
            "opendataloader-pdf",
            "mineru",
        ]
        assert [attempt["attempt_no"] for attempt in attempt_rows] == [1, 2]
        assert [attempt["is_primary_attempt"] for attempt in attempt_rows] == [True, False]
        assert [attempt["is_selected_output"] for attempt in attempt_rows] == [False, True]
        assert {attempt["rerun_reason_code"] for attempt in attempt_rows} == {
            "TABLE_EXTRACTION_MISSING"
        }
        assert [float(attempt["confidence_score"]) for attempt in attempt_rows] == [0.49, 0.91]
        assert len({attempt["raw_artifact_id"] for attempt in attempt_rows}) == 2
        assert len({attempt["object_key"] for attempt in attempt_rows}) == 2
        selected_artifact_id = next(
            attempt["raw_artifact_id"] for attempt in attempt_rows if attempt["is_selected_output"]
        )
        persisted_artifact_ids = (
            connection.execute(
                text("""
                SELECT raw_artifact_id FROM app.ocr_text_blocks WHERE review_id=:review
                UNION
                SELECT raw_artifact_id FROM app.layout_blocks WHERE review_id=:review
            """),
                {"review": review_id},
            )
            .scalars()
            .all()
        )
        assert set(persisted_artifact_ids) == {selected_artifact_id}

    with pytest.raises(ArtifactAccessDenied):
        artifacts.read_privileged(
            selected_artifact_id,
            role="PRODUCT_DEPARTMENT_USER",
            actor_id=user_id,
            purpose="debug",
        )
    assert (
        artifacts.read_privileged(
            selected_artifact_id,
            role="SYSTEM_ADMIN",
            actor_id=user_id,
            purpose="approved synthetic replay",
        )
        == b'{"provider":"mineru"}'
    )
    metadata.set_retention_hold(selected_artifact_id, True)
    assert not artifacts.delete_expired(
        selected_artifact_id, now=now + timedelta(days=30), approved=True, actor_id=user_id
    )
    metadata.set_retention_hold(selected_artifact_id, False)
    for attempt in attempt_rows:
        assert artifacts.delete_expired(
            attempt["raw_artifact_id"],
            now=now + timedelta(days=30),
            approved=True,
            actor_id=user_id,
        )
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE app.review_jobs SET job_status='RUNNING',heartbeat_at=:old WHERE job_id=:job"
            ),
            {"old": now - timedelta(minutes=5), "job": job_id},
        )
    recovered = job_repository.recover_stale(now=now, stale_before=now - timedelta(minutes=2))
    assert recovered and recovered[0].job_id == job_id
    with engine.connect() as connection:
        audits = connection.execute(
            text("SELECT result,metadata_json FROM audit.audit_logs WHERE target_id=:artifact"),
            {"artifact": selected_artifact_id},
        ).all()
        assert {row._mapping["result"] for row in audits} >= {"DENIED", "SUCCESS"}
        assert all("object" not in str(row._mapping["metadata_json"]).casefold() for row in audits)

    with engine.begin() as connection:
        connection.execute(
            text("UPDATE app.advertisements SET latest_review_id=NULL WHERE advertisement_id=:id"),
            {"id": advertisement_id},
        )
        connection.execute(
            text("DELETE FROM app.layout_blocks WHERE review_id=:id"), {"id": review_id}
        )
        connection.execute(
            text("DELETE FROM app.ocr_text_blocks WHERE review_id=:id"), {"id": review_id}
        )
        connection.execute(
            text("DELETE FROM app.parser_artifacts WHERE review_id=:id"), {"id": review_id}
        )
        connection.execute(text("DELETE FROM app.reviews WHERE review_id=:id"), {"id": review_id})
        connection.execute(
            text("DELETE FROM app.advertisements WHERE advertisement_id=:id"),
            {"id": advertisement_id},
        )
        connection.execute(text("DELETE FROM app.users WHERE user_id=:id"), {"id": user_id})
        connection.execute(
            text("DELETE FROM app.departments WHERE department_id=:id"), {"id": department_id}
        )
    storage.delete(originals_bucket, original_key)
    redis.delete(queue_name, dead_name)
