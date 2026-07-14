from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from nh_ad_parser_contracts import (
    ArtifactStore,
    DocumentInput,
    InMemoryArtifactMetadataRepository,
    InMemoryArtifactStorage,
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
