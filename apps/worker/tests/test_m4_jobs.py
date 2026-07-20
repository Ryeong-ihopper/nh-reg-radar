from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

import pytest

from nh_ad_parser_contracts import (
    ArtifactStore,
    DocumentInput,
    InMemoryArtifactMetadataRepository,
    InMemoryArtifactStorage,
    HwpHybridDocument,
    NormalizedDocument,
    ParserRouter,
)
from nh_ad_worker.jobs import (
    InMemoryDeadLetterSink,
    InMemoryJobRepository,
    ParserJobProcessor,
    QueueMessage,
    TransientParserError,
    WorkerJob,
    redacted_log,
)
from nh_ad_worker.results import ReviewResultEngine


FIXTURE = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "m4" / "normalized-image-v1.json"
)


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 7, 14, 10, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value


class FixtureAdapter:
    name = "paddleocr"

    def __init__(self, document: NormalizedDocument) -> None:
        self.document = document

    def parse(self, _input: DocumentInput) -> NormalizedDocument:
        return self.document


class CountingAdapter(FixtureAdapter):
    def __init__(self, document: NormalizedDocument) -> None:
        super().__init__(document)
        self.calls = 0

    def parse(self, document: DocumentInput) -> NormalizedDocument:
        self.calls += 1
        return super().parse(document)


class TransientAdapter:
    name = "paddleocr"

    def parse(self, _input: DocumentInput) -> NormalizedDocument:
        raise TransientParserError("provider timeout")


class UnexpectedAdapter:
    name = "paddleocr"

    def parse(self, _input: DocumentInput) -> NormalizedDocument:
        raise RuntimeError("unexpected provider response")


class CrashBeforeCompleteRepository(InMemoryJobRepository):
    def __init__(self, jobs: list[WorkerJob]) -> None:
        super().__init__(jobs)
        self.crash_once = True

    def complete(
        self,
        job_id: str,
        *,
        worker_id: str,
        now: datetime,
        check_required: bool,
    ) -> None:
        if self.crash_once:
            self.crash_once = False
            raise SystemExit("simulated worker termination")
        super().complete(
            job_id,
            worker_id=worker_id,
            now=now,
            check_required=check_required,
        )


class CrashAfterClaimRepository(InMemoryJobRepository):
    def claim(
        self,
        message: QueueMessage,
        *,
        worker_id: str,
        now: datetime,
    ) -> WorkerJob | None:
        super().claim(message, worker_id=worker_id, now=now)
        raise RuntimeError("source loading failed after claim")


class HeartbeatRepository(InMemoryJobRepository):
    def __init__(self, jobs: list[WorkerJob], heartbeat_seen: Event) -> None:
        super().__init__(jobs)
        self.heartbeat_seen = heartbeat_seen
        self.heartbeat_calls = 0

    def heartbeat(self, job_id: str, *, worker_id: str, now: datetime) -> None:
        super().heartbeat(job_id, worker_id=worker_id, now=now)
        self.heartbeat_calls += 1
        self.heartbeat_seen.set()


class HeartbeatBlockingAdapter(FixtureAdapter):
    def __init__(self, document: NormalizedDocument, heartbeat_seen: Event) -> None:
        super().__init__(document)
        self.heartbeat_seen = heartbeat_seen

    def parse(self, document: DocumentInput) -> NormalizedDocument:
        assert self.heartbeat_seen.wait(1), "processor did not refresh its active-job heartbeat"
        return super().parse(document)


def setup(
    adapter: object,
) -> tuple[ParserJobProcessor, WorkerJob, InMemoryJobRepository, Clock, InMemoryDeadLetterSink]:
    fixture = NormalizedDocument.model_validate_json(FIXTURE.read_text())
    source = DocumentInput(
        source_file_id=fixture.source_file_id,
        review_id=fixture.review_id,
        file_name="fixture.png",
        mime_type="image/png",
        body=b"synthetic",
    )
    job = WorkerJob("JOB-M4-1", fixture.review_id, source)
    repository = InMemoryJobRepository([job])
    clock = Clock()
    dead_letters = InMemoryDeadLetterSink()
    processor = ParserJobProcessor(
        repository,
        ParserRouter({"paddleocr": adapter}),  # type: ignore[arg-type]
        ArtifactStore(
            InMemoryArtifactStorage(),
            InMemoryArtifactMetadataRepository(),
            bucket="parser-artifacts",
        ),
        dead_letters,
        worker_id="worker-m4",
        now=clock,
        raw_output=lambda _input, _output: b'{"synthetic":"provider-v1"}',
    )
    return processor, job, repository, clock, dead_letters


def message(job: WorkerJob) -> dict[str, object]:
    return {
        "messageVersion": "review-job-v1",
        "jobId": job.job_id,
        "reviewId": job.review_id,
        "jobType": "REVIEW_ANALYSIS",
        "correlationId": "corr-m4",
        "idempotencyKey": job.job_id,
    }


def test_selected_output_is_persisted_and_duplicate_delivery_is_idempotent() -> None:
    fixture = NormalizedDocument.model_validate_json(FIXTURE.read_text())
    processor, job, _repository, _clock, _dead_letters = setup(FixtureAdapter(fixture))

    assert processor.process(message(job)) == "COMPLETED"
    assert job.status == "COMPLETED"
    assert job.review_status == "REVIEW_COMPLETED"
    assert job.selected_artifact is not None and job.selected_artifact.is_selected_output
    assert job.normalized_document == fixture
    assert processor.process(message(job)) == "DUPLICATE_IGNORED"


def test_technical_retry_uses_one_three_ten_then_dead_letters_after_three_retries() -> None:
    fixture = NormalizedDocument.model_validate_json(FIXTURE.read_text())
    processor, job, _repository, clock, dead_letters = setup(TransientAdapter())

    assert processor.process(message(job)) == "RETRY_PENDING"
    assert job.next_retry_at == clock.value + timedelta(minutes=1)
    clock.value = job.next_retry_at
    assert processor.process(message(job)) == "RETRY_PENDING"
    assert job.next_retry_at == clock.value + timedelta(minutes=3)
    clock.value = job.next_retry_at
    assert processor.process(message(job)) == "RETRY_PENDING"
    assert job.next_retry_at == clock.value + timedelta(minutes=10)
    clock.value = job.next_retry_at
    assert processor.process(message(job)) == "FAILED_FINAL"
    assert job.retry_count == 3 and job.dead_lettered_at == clock.value
    assert dead_letters.messages == [
        {
            "messageVersion": "review-job-v1",
            "jobId": job.job_id,
            "reviewId": fixture.review_id,
            "reasonCode": "TRANSIENTPARSERERROR",
        }
    ]


def test_stale_recovery_and_queue_payload_redaction() -> None:
    fixture = NormalizedDocument.model_validate_json(FIXTURE.read_text())
    processor, job, repository, clock, _dead_letters = setup(FixtureAdapter(fixture))
    parsed = QueueMessage.parse(message(job))
    assert repository.claim(parsed, worker_id="crashed-worker", now=clock.value) is job
    clock.value += timedelta(minutes=3)
    recovered = repository.recover_stale(
        now=clock.value, stale_before=clock.value - timedelta(minutes=2)
    )
    assert job.status == "STALE"
    assert recovered[0].job_id == job.job_id
    assert "raw" not in redacted_log(message(job)).casefold()
    assert "object" not in redacted_log(message(job)).casefold()
    assert processor.process(message(job)) == "COMPLETED"


def test_active_processing_refreshes_heartbeat_until_completion() -> None:
    fixture = NormalizedDocument.model_validate_json(FIXTURE.read_text())
    source = DocumentInput(
        source_file_id=fixture.source_file_id,
        review_id=fixture.review_id,
        file_name="fixture.png",
        mime_type="image/png",
        body=b"synthetic",
    )
    job = WorkerJob("JOB-M4-HEARTBEAT", fixture.review_id, source)
    heartbeat_seen = Event()
    repository = HeartbeatRepository([job], heartbeat_seen)
    clock = Clock()
    processor = ParserJobProcessor(
        repository,
        ParserRouter({"paddleocr": HeartbeatBlockingAdapter(fixture, heartbeat_seen)}),
        ArtifactStore(
            InMemoryArtifactStorage(),
            InMemoryArtifactMetadataRepository(),
            bucket="parser-artifacts",
        ),
        InMemoryDeadLetterSink(),
        worker_id="worker-heartbeat",
        now=clock,
        heartbeat_interval_seconds=0.01,
    )

    assert processor.process(message(job)) == "COMPLETED"
    assert repository.heartbeat_calls >= 1
    assert job.heartbeat_at == clock.value


def test_unconfigured_parser_fails_claimed_job_without_leaving_it_running() -> None:
    fixture = NormalizedDocument.model_validate_json(FIXTURE.read_text())
    source = DocumentInput(
        source_file_id=fixture.source_file_id,
        review_id=fixture.review_id,
        file_name="fixture.png",
        mime_type="image/png",
        body=b"synthetic",
    )
    job = WorkerJob("JOB-M4-NO-ADAPTER", fixture.review_id, source)
    repository = InMemoryJobRepository([job])
    dead_letters = InMemoryDeadLetterSink()
    processor = ParserJobProcessor(
        repository,
        ParserRouter(),
        ArtifactStore(
            InMemoryArtifactStorage(),
            InMemoryArtifactMetadataRepository(),
            bucket="parser-artifacts",
        ),
        dead_letters,
        worker_id="worker-no-adapter",
        now=Clock(),
    )

    assert processor.process(message(job)) == "FAILED_FINAL"
    assert job.status == "FAILED_FINAL"
    assert job.review_status == "REVIEW_FAILED"
    assert job.failed_reason_code == "PARSER_ADAPTER_NOT_CONFIGURED"
    assert job.locked_by is None
    assert dead_letters.messages == [
        {
            "messageVersion": "review-job-v1",
            "jobId": job.job_id,
            "reviewId": job.review_id,
            "reasonCode": "PARSER_ADAPTER_NOT_CONFIGURED",
        }
    ]


def test_unexpected_processing_error_fails_final_and_dead_letters() -> None:
    fixture = NormalizedDocument.model_validate_json(FIXTURE.read_text())
    processor, job, _repository, _clock, dead_letters = setup(UnexpectedAdapter())

    assert processor.process(message(job)) == "FAILED_FINAL"
    assert job.status == "FAILED_FINAL"
    assert job.review_status == "REVIEW_FAILED"
    assert job.failed_reason_code == "UNEXPECTED_PROCESSING_ERROR"
    assert job.locked_by is None
    assert dead_letters.messages == [
        {
            "messageVersion": "review-job-v1",
            "jobId": job.job_id,
            "reviewId": fixture.review_id,
            "reasonCode": "UNEXPECTED_PROCESSING_ERROR",
        }
    ]


def test_unexpected_claim_error_fails_final_and_dead_letters() -> None:
    fixture = NormalizedDocument.model_validate_json(FIXTURE.read_text())
    source = DocumentInput(
        source_file_id=fixture.source_file_id,
        review_id=fixture.review_id,
        file_name="fixture.png",
        mime_type="image/png",
        body=b"synthetic",
    )
    job = WorkerJob("JOB-M4-CLAIM-ERROR", fixture.review_id, source)
    repository = CrashAfterClaimRepository([job])
    dead_letters = InMemoryDeadLetterSink()
    processor = ParserJobProcessor(
        repository,
        ParserRouter({"paddleocr": FixtureAdapter(fixture)}),
        ArtifactStore(
            InMemoryArtifactStorage(),
            InMemoryArtifactMetadataRepository(),
            bucket="parser-artifacts",
        ),
        dead_letters,
        worker_id="worker-claim-error",
        now=Clock(),
    )

    assert processor.process(message(job)) == "FAILED_FINAL"
    assert job.status == "FAILED_FINAL"
    assert job.failed_reason_code == "UNEXPECTED_PROCESSING_ERROR"
    assert dead_letters.messages[0]["reasonCode"] == "UNEXPECTED_PROCESSING_ERROR"


def test_post_claim_mutations_reject_a_worker_that_lost_its_lease() -> None:
    fixture = NormalizedDocument.model_validate_json(FIXTURE.read_text())
    source = DocumentInput(
        source_file_id=fixture.source_file_id,
        review_id=fixture.review_id,
        file_name="fixture.png",
        mime_type="image/png",
        body=b"synthetic",
    )
    job = WorkerJob("JOB-M4-LEASE", fixture.review_id, source)
    repository = InMemoryJobRepository([job])
    now = Clock()()
    assert repository.claim(QueueMessage.parse(message(job)), worker_id="worker-a", now=now) is job
    job.locked_by = "worker-b"

    with pytest.raises(ValueError, match="ILLEGAL_JOB_TRANSITION"):
        repository.retry_or_dead_letter(
            job.job_id,
            worker_id="worker-a",
            now=now,
            reason_code="TRANSIENT",
        )
    with pytest.raises(ValueError, match="ILLEGAL_JOB_TRANSITION"):
        repository.fail_final(
            job.job_id,
            worker_id="worker-a",
            now=now,
            reason_code="PERMANENT",
        )
    with pytest.raises(ValueError, match="ILLEGAL_JOB_TRANSITION"):
        repository.persist_selected(
            job.job_id,
            fixture,
            ArtifactStore(
                InMemoryArtifactStorage(),
                InMemoryArtifactMetadataRepository(),
                bucket="parser-artifacts",
            ).put(
                b"{}",
                raw_artifact_id="ART-LEASE",
                review_id=job.review_id,
                file_id=fixture.source_file_id,
                review_step_id=job.review_step_id,
                artifact_type="PROVIDER_RAW",
                content_type="application/json",
                parser_name=fixture.parser_name,
                parser_version=fixture.parser_version,
                parser_rule_version=fixture.parser_rule_version,
                ir_version=fixture.ir_version,
                attempt_no=1,
                is_primary_attempt=True,
                is_selected_output=True,
                rerun_reason_code=None,
                confidence_score=fixture.confidence.score,
                confidence_status=fixture.confidence.status.value,
                created_at=now,
                retention_until=now + timedelta(days=14),
            ),
            worker_id="worker-a",
        )
    with pytest.raises(ValueError, match="ILLEGAL_JOB_TRANSITION"):
        repository.complete(
            job.job_id,
            worker_id="worker-a",
            now=now,
            check_required=False,
        )


def test_stale_replay_after_selected_output_and_results_completes_idempotently() -> None:
    fixture = NormalizedDocument.model_validate_json(FIXTURE.read_text())
    source = DocumentInput(
        source_file_id=fixture.source_file_id,
        review_id=fixture.review_id,
        file_name="fixture.png",
        mime_type="image/png",
        body=b"synthetic",
    )
    job = WorkerJob("JOB-M4-REPLAY", fixture.review_id, source)
    repository = CrashBeforeCompleteRepository([job])
    metadata = InMemoryArtifactMetadataRepository()
    storage = InMemoryArtifactStorage()
    clock = Clock()
    processor = ParserJobProcessor(
        repository,
        ParserRouter({"paddleocr": FixtureAdapter(fixture)}),
        ArtifactStore(
            storage,
            metadata,
            bucket="parser-artifacts",
        ),
        InMemoryDeadLetterSink(),
        worker_id="worker-replay",
        now=clock,
        result_engine=ReviewResultEngine(),
    )

    with pytest.raises(SystemExit, match="simulated worker termination"):
        processor.process(message(job))
    assert job.status == "RUNNING"
    assert job.selected_artifact is not None
    assert job.review_results is not None

    clock.value += timedelta(minutes=3)
    repository.recover_stale(
        now=clock.value,
        stale_before=clock.value - timedelta(minutes=2),
    )

    assert processor.process(message(job)) == "CHECK_REQUIRED"
    assert job.status == "COMPLETED"
    assert len(metadata.items) == 1
    assert len(storage.objects) == 1


def test_queue_contract_rejects_raw_or_object_storage_fields() -> None:
    fixture = NormalizedDocument.model_validate_json(FIXTURE.read_text())
    _processor, job, _repository, _clock, _dead_letters = setup(FixtureAdapter(fixture))
    payload = message(job)
    payload["rawText"] = "forbidden"
    with pytest.raises(ValueError, match="INVALID_REVIEW_QUEUE_MESSAGE"):
        QueueMessage.parse(payload)


def test_claim_rejects_cross_job_idempotency_key_before_execution() -> None:
    fixture = NormalizedDocument.model_validate_json(FIXTURE.read_text())
    processor, job, _repository, _clock, _dead_letters = setup(FixtureAdapter(fixture))
    payload = message(job)
    payload["idempotencyKey"] = "JOB-M4-OTHER"

    with pytest.raises(ValueError, match="IDEMPOTENCY_KEY_MISMATCH"):
        processor.process(payload)

    assert job.status == "PENDING"
    assert job.selected_artifact is None


def candidate(parser_name: str, score: float) -> NormalizedDocument:
    data = NormalizedDocument.model_validate_json(FIXTURE.read_text()).model_dump(
        by_alias=True, mode="json"
    )
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


def test_hwp_hybrid_persists_both_components_before_the_selected_document() -> None:
    rhwp = candidate("rhwp", 0.95)
    document_processor = candidate("document-processor", 0.90)
    final = candidate("hwp-hybrid", 0.90)
    hybrid = HwpHybridDocument.model_validate(
        {
            **final.model_dump(mode="python"),
            "component_documents": (rhwp, document_processor),
        }
    )
    source = DocumentInput(
        source_file_id=hybrid.source_file_id,
        review_id=hybrid.review_id,
        file_name="advertisement.hwp",
        mime_type="application/x-hwp",
        body=b"hwp",
    )
    job = WorkerJob("JOB-M4-HYBRID", hybrid.review_id, source)
    repository = InMemoryJobRepository([job])
    metadata = InMemoryArtifactMetadataRepository()
    processor = ParserJobProcessor(
        repository,
        ParserRouter({"hwp-hybrid": FixtureAdapter(hybrid)}),
        ArtifactStore(InMemoryArtifactStorage(), metadata, bucket="parser-artifacts"),
        InMemoryDeadLetterSink(),
        worker_id="worker-m4",
        now=Clock(),
    )

    assert processor.process(message(job)) == "COMPLETED"
    artifacts = list(metadata.items.values())
    assert {item.parser_name for item in artifacts} == {
        "rhwp",
        "document-processor",
        "hwp-hybrid",
    }
    assert [item.parser_name for item in artifacts if item.is_selected_output] == ["hwp-hybrid"]
    assert {item.parser_name for item in artifacts if item.artifact_type == "PARSER_RAW"} == {
        "rhwp",
        "document-processor",
    }


def test_quality_rerun_executes_secondary_and_persists_exactly_one_selected_output() -> None:
    primary = candidate("opendataloader-pdf", 0.49)
    secondary = candidate("mineru", 0.91)
    primary_adapter = CountingAdapter(primary)
    secondary_adapter = CountingAdapter(secondary)
    source = DocumentInput(
        source_file_id=primary.source_file_id,
        review_id=primary.review_id,
        file_name="complex.pdf",
        mime_type="application/pdf",
        body=b"synthetic",
        complex_layout=True,
    )
    job = WorkerJob("JOB-M4-RERUN", primary.review_id, source)
    repository = InMemoryJobRepository([job])
    metadata = InMemoryArtifactMetadataRepository()
    processor = ParserJobProcessor(
        repository,
        ParserRouter(
            {
                "opendataloader-pdf": primary_adapter,
                "mineru": secondary_adapter,
            }
        ),
        ArtifactStore(InMemoryArtifactStorage(), metadata, bucket="parser-artifacts"),
        InMemoryDeadLetterSink(),
        worker_id="worker-m4",
        now=Clock(),
    )

    assert processor.process(message(job)) == "COMPLETED"
    assert (primary_adapter.calls, secondary_adapter.calls) == (1, 1)
    attempts = sorted(metadata.items.values(), key=lambda item: item.attempt_no)
    assert [item.parser_name for item in attempts] == ["opendataloader-pdf", "mineru"]
    assert [item.rerun_reason_code for item in attempts] == [
        "TABLE_EXTRACTION_MISSING",
        "TABLE_EXTRACTION_MISSING",
    ]
    assert [item.is_selected_output for item in attempts] == [False, True]
    assert sum(item.is_selected_output for item in attempts) == 1
    assert job.normalized_document == secondary
    assert job.selected_artifact == attempts[1]


def test_quality_rerun_deterministically_keeps_better_primary_candidate() -> None:
    primary = candidate("opendataloader-pdf", 0.79)
    secondary = candidate("mineru", 0.49)
    primary_adapter = CountingAdapter(primary)
    secondary_adapter = CountingAdapter(secondary)
    router = ParserRouter(
        {
            "opendataloader-pdf": primary_adapter,
            "mineru": secondary_adapter,
        }
    )
    source = DocumentInput(
        source_file_id=primary.source_file_id,
        review_id=primary.review_id,
        file_name="complex.pdf",
        mime_type="application/pdf",
        body=b"synthetic",
        complex_layout=True,
    )

    selection = router.parse_with_attempts(source)

    assert (primary_adapter.calls, secondary_adapter.calls) == (1, 1)
    assert selection.selected_document == primary
    assert [attempt.is_selected_output for attempt in selection.attempts] == [True, False]
    assert router.parse(source) == primary


def test_transient_primary_failure_retries_without_running_quality_secondary() -> None:
    secondary = candidate("mineru", 0.91)
    secondary_adapter = CountingAdapter(secondary)
    source = DocumentInput(
        source_file_id=secondary.source_file_id,
        review_id=secondary.review_id,
        file_name="complex.pdf",
        mime_type="application/pdf",
        body=b"synthetic",
        complex_layout=True,
    )
    job = WorkerJob("JOB-M4-TECHNICAL", secondary.review_id, source)
    repository = InMemoryJobRepository([job])
    processor = ParserJobProcessor(
        repository,
        ParserRouter(
            {
                "opendataloader-pdf": TransientAdapter(),
                "mineru": secondary_adapter,
            }
        ),
        ArtifactStore(
            InMemoryArtifactStorage(),
            InMemoryArtifactMetadataRepository(),
            bucket="parser-artifacts",
        ),
        InMemoryDeadLetterSink(),
        worker_id="worker-m4",
        now=Clock(),
    )

    assert processor.process(message(job)) == "RETRY_PENDING"
    assert job.retry_count == 1
    assert secondary_adapter.calls == 0
    assert job.selected_artifact is None
