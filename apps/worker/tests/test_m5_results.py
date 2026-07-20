import json
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
    WorkerJob,
)
from nh_ad_worker.results import (
    EvidenceCandidate,
    EvidenceSearchFailure,
    ReviewResultEngine,
    ReviewResultItem,
)


FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "m4"
M5_FIXTURES = FIXTURES.parent / "m5"


def document(name: str = "normalized-image-v1.json") -> NormalizedDocument:
    return NormalizedDocument.model_validate_json((FIXTURES / name).read_text())


def evidence(score: float = 0.91) -> EvidenceCandidate:
    return EvidenceCandidate(
        "EVD-SYNTH-M5-001",
        "STDVER-SYNTH-M5-001",
        "GUIDELINE",
        "광고 표현 기준",
        "객관적 기준 없는 절대적 표현은 사용할 수 없습니다.",
        score,
        "HYBRID",
        "ECH-SYNTH-M5-001",
    )


def test_m5a_rule_result_is_deterministic_and_has_box_annotation() -> None:
    first = ReviewResultEngine().execute(document())
    second = ReviewResultEngine().execute(document())

    assert first == second
    item = first.items[0]
    assert (item.source_engine, item.source_version) == ("RULE", "rule-config-v1")
    assert item.risk_level == "HIGH"
    assert item.evidence_status == "INSUFFICIENT"
    assert item.risk_reason_codes == (
        "MISLEADING_ABSOLUTE_EXPRESSION",
        "RULE_EXPLICIT_VIOLATION",
    )
    assert item.annotation is not None
    assert (item.annotation.display_mode, item.annotation.status) == ("BOX", "LOCATED")


def test_m5b_preserves_search_rank_without_applying_a_cross_engine_score_cutoff() -> None:
    bundle = ReviewResultEngine(search=lambda _query: [evidence(0.91), evidence(0.69)]).execute(
        document()
    )
    item = bundle.items[0]

    assert (item.result_status, item.risk_level) == ("NEEDS_REVISION", "HIGH")
    assert item.evidence_status == "CONNECTED"
    assert [value.rank_no for value in item.evidences] == [1, 2]
    assert item.score_detail["rag"] == {
        "topRelevanceScore": 0.91,
        "evidenceCount": 2,
        "evidenceSufficient": True,
        "status": "CONNECTED",
        "failureCode": None,
    }


def test_m5b_search_failure_is_explicit_and_never_erases_rule_result() -> None:
    def unavailable(_query: str) -> list[EvidenceCandidate]:
        raise EvidenceSearchFailure("RAG_SEARCH_UNAVAILABLE")

    item = ReviewResultEngine(search=unavailable).execute(document()).items[0]

    assert (item.result_status, item.risk_level, item.source_engine) == (
        "NEEDS_REVISION",
        "HIGH",
        "RULE",
    )
    assert item.evidence_status == "SEARCH_UNAVAILABLE"
    assert item.evidence_failure_code == "RAG_SEARCH_UNAVAILABLE"
    assert item.evidences == ()


def test_m5c_invalid_provider_independent_schema_preserves_rule_and_rag() -> None:
    fixture = json.loads((M5_FIXTURES / "structured-output-v1.json").read_text())
    assert (fixture["provider"], fixture["model"], fixture["networkAllowed"]) == (
        None,
        None,
        False,
    )
    invalid = next(value for value in fixture["cases"] if value["caseId"] == "INVALID_SCHEMA")
    item = (
        ReviewResultEngine(
            search=lambda _query: [evidence()],
            structured_output=lambda _item: invalid["output"],
        )
        .execute(document())
        .items[0]
    )

    assert (item.result_status, item.risk_level, item.evidence_status) == (
        "NEEDS_REVISION",
        "HIGH",
        "CONNECTED",
    )
    assert item.score_detail["llm"] == {
        "schemaVersion": "review-structured-output-v1",
        "status": "INVALID_SCHEMA",
        "decision": None,
        "confidence": None,
    }


def test_m5c_provider_failure_preserves_rule_and_rag() -> None:
    def unavailable(_item: ReviewResultItem) -> object:
        raise RuntimeError("provider unavailable")

    item = (
        ReviewResultEngine(search=lambda _query: [evidence()], structured_output=unavailable)
        .execute(document())
        .items[0]
    )

    assert (item.result_status, item.risk_level, item.evidence_status) == (
        "NEEDS_REVISION",
        "HIGH",
        "CONNECTED",
    )
    assert item.score_detail["llm"]["status"] == "INVALID_SCHEMA"


@pytest.mark.parametrize(
    "invalid_output",
    [
        {
            "decision": "RISKY",
            "confidence": True,
            "reasonCode": "LLM_MISLEADING_CONTEXT",
            "explanation": "invalid boolean confidence",
        },
        {
            "decision": "RISKY",
            "confidence": float("nan"),
            "reasonCode": "LLM_MISLEADING_CONTEXT",
            "explanation": "invalid non-finite confidence",
        },
        {
            "decision": "RISKY",
            "confidence": float("inf"),
            "reasonCode": "LLM_MISLEADING_CONTEXT",
            "explanation": "invalid non-finite confidence",
        },
        {
            "decision": "RISKY",
            "confidence": -0.01,
            "reasonCode": "LLM_MISLEADING_CONTEXT",
            "explanation": "invalid out-of-range confidence",
        },
        {
            "decision": "RISKY",
            "confidence": 1.01,
            "reasonCode": "LLM_MISLEADING_CONTEXT",
            "explanation": "invalid out-of-range confidence",
        },
        {
            "decision": None,
            "confidence": 0.86,
            "reasonCode": "LLM_MISLEADING_CONTEXT",
            "explanation": "invalid decision type",
        },
        {
            "decision": "RISKY",
            "confidence": 0.86,
            "reasonCode": 1,
            "explanation": "invalid reason code type",
        },
        {
            "decision": "RISKY",
            "confidence": 0.86,
            "reasonCode": "LLM_MISLEADING_CONTEXT",
            "explanation": ["invalid explanation type"],
        },
    ],
)
def test_m5c_rejects_invalid_structured_field_types_without_erasing_prior_results(
    invalid_output: dict[str, object],
) -> None:
    item = (
        ReviewResultEngine(
            search=lambda _query: [evidence()],
            structured_output=lambda _item: invalid_output,
        )
        .execute(document())
        .items[0]
    )

    assert (item.result_status, item.risk_level, item.evidence_status) == (
        "NEEDS_REVISION",
        "HIGH",
        "CONNECTED",
    )
    assert len(item.evidences) == 1
    assert item.score_detail["rag"] == {
        "topRelevanceScore": 0.91,
        "evidenceCount": 1,
        "evidenceSufficient": True,
        "status": "CONNECTED",
        "failureCode": None,
    }
    assert item.score_detail["llm"] == {
        "schemaVersion": "review-structured-output-v1",
        "status": "INVALID_SCHEMA",
        "decision": None,
        "confidence": None,
    }


@pytest.mark.parametrize(
    ("location_confidence", "display_mode", "status"),
    [
        (0.49, "LIST_ONLY", "NOT_LOCATED"),
        (0.50, "BOX", "LOW_CONFIDENCE"),
        (0.79, "BOX", "LOW_CONFIDENCE"),
        (0.80, "BOX", "LOCATED"),
    ],
)
def test_annotation_location_thresholds_follow_adr_0053(
    location_confidence: float,
    display_mode: str,
    status: str,
) -> None:
    fixture = document().model_copy(deep=True)
    coordinate = fixture.text_blocks[0].coordinate
    assert coordinate is not None
    fixture.text_blocks[0].coordinate = coordinate.model_copy(
        update={"coordinate_confidence": location_confidence}
    )

    bundle = ReviewResultEngine().execute(fixture)

    assert len(bundle.items) == 1
    annotation = bundle.items[0].annotation
    assert annotation is not None
    assert (annotation.display_mode, annotation.status) == (display_mode, status)
    assert annotation.location_confidence == location_confidence
    assert (annotation.coordinate is None) is (status == "NOT_LOCATED")


def test_hwpx_uses_text_offset_annotation() -> None:
    item = ReviewResultEngine().execute(document("normalized-hwpx-v1.json")).items[0]

    assert item.annotation is not None
    assert item.annotation.display_mode == "TEXT_HIGHLIGHT"
    assert item.annotation.text_block_id == "OCR-SYNTH-002"
    assert item.annotation.normalized_start_offset == 0


@pytest.mark.parametrize(
    ("text", "status", "risk"),
    [
        ("무조건 최고 혜택", "NEEDS_REVISION", "HIGH"),
        ("연 3.5%", "NEEDS_CONFIRMATION", "MEDIUM"),
        ("중도해지 시 불이익이 발생할 수 있습니다.", "APPROPRIATE", "LOW"),
    ],
)
def test_rule_decision_table_is_stable(text: str, status: str, risk: str) -> None:
    fixture = document().model_copy(deep=True)
    fixture.text_blocks[0].normalized_text = text
    item = ReviewResultEngine().execute(fixture).items[0]

    assert (item.result_status, item.risk_level) == (status, risk)
    assert item.risk_policy_version == "risk-policy-v1"
    assert item.risk_reason_codes
    assert (item.evidence_status == "SEARCH_UNAVAILABLE") is (
        item.evidence_failure_code is not None
    )


def test_parser_job_persists_results_before_completing() -> None:
    fixture = document()

    class Adapter:
        name = "paddleocr"

        def parse(self, _source: DocumentInput) -> NormalizedDocument:
            return fixture

    source = DocumentInput(
        source_file_id=fixture.source_file_id,
        review_id=fixture.review_id,
        file_name="fixture.png",
        mime_type="image/png",
        body=b"synthetic",
    )
    job = WorkerJob("JOB-M5-0001", fixture.review_id, source)
    repository = InMemoryJobRepository([job])
    processor = ParserJobProcessor(
        repository,
        ParserRouter({"paddleocr": Adapter()}),
        ArtifactStore(
            InMemoryArtifactStorage(),
            InMemoryArtifactMetadataRepository(),
            bucket="parser-artifacts",
        ),
        InMemoryDeadLetterSink(),
        worker_id="worker-m5",
        raw_output=lambda _source, _document: b'{"fixture":"m5"}',
        result_engine=ReviewResultEngine(search=lambda _query: [evidence()]),
    )
    payload = {
        "messageVersion": "review-job-v1",
        "jobId": job.job_id,
        "reviewId": job.review_id,
        "jobType": "REVIEW_ANALYSIS",
        "correlationId": "corr-m5",
        "idempotencyKey": job.job_id,
    }

    assert processor.process(payload) == "CHECK_REQUIRED"
    assert job.review_results is not None
    assert job.progress_rate == 100
    assert job.current_step is None
    assert job.progress_history == [
        "FILE_PREPROCESSING",
        "OCR_EXTRACTION",
        "LAYOUT_ANALYSIS",
        "RULE_REVIEW",
        "RAG_REVIEW",
        "RESULT_GENERATION",
    ]
    assert job.review_results.items[0].evidence_status == "CONNECTED"
    assert len(repository.suggestions) == 1
    generated = next(iter(repository.suggestions.values()))
    assert generated.review_item_id == job.review_results.items[0].review_item_id
    assert generated.evidence_ids == ("EVD-SYNTH-M5-001",)
    assert job.status == "COMPLETED"
    assert processor.process(payload) == "DUPLICATE_IGNORED"
    assert len(repository.suggestions) == 1


def test_parser_job_skips_suggestions_when_the_request_disables_them() -> None:
    fixture = document()

    class Adapter:
        name = "paddleocr"

        def parse(self, _source: DocumentInput) -> NormalizedDocument:
            return fixture

    source = DocumentInput(
        source_file_id=fixture.source_file_id,
        review_id=fixture.review_id,
        file_name="fixture.png",
        mime_type="image/png",
        body=b"synthetic",
    )
    job = WorkerJob("JOB-M5-NO-SUGGESTION", fixture.review_id, source, include_suggestion=False)
    repository = InMemoryJobRepository([job])
    processor = ParserJobProcessor(
        repository,
        ParserRouter({"paddleocr": Adapter()}),
        ArtifactStore(
            InMemoryArtifactStorage(),
            InMemoryArtifactMetadataRepository(),
            bucket="parser-artifacts",
        ),
        InMemoryDeadLetterSink(),
        worker_id="worker-m5",
        result_engine=ReviewResultEngine(search=lambda _query: [evidence()]),
    )
    payload = {
        "messageVersion": "review-job-v1",
        "jobId": job.job_id,
        "reviewId": job.review_id,
        "jobType": "REVIEW_ANALYSIS",
        "correlationId": "corr-m5-no-suggestion",
        "idempotencyKey": job.job_id,
    }

    assert processor.process(payload) == "CHECK_REQUIRED"
    assert repository.suggestions == {}
