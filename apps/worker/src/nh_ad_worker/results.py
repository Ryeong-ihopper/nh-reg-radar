"""Deterministic M5 Rule -> RAG -> structured-result pipeline.

The module deliberately has no provider SDK, credential, or network adapter.
Search and structured output are injected boundaries so production failures and
versioned fixtures remain explicit instead of weakening Rule results.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from math import isfinite
from typing import Literal

from nh_ad_parser_contracts import Coordinate, NormalizedDocument, TextBlock


EvidenceStatus = Literal["CONNECTED", "NOT_REQUIRED", "INSUFFICIENT", "SEARCH_UNAVAILABLE"]
StructuredStatus = Literal["NOT_RUN", "VALID", "INVALID_SCHEMA"]


@dataclass(frozen=True)
class EvidenceCandidate:
    evidence_id: str
    standard_version_id: str
    evidence_type: str
    title: str
    matched_text: str
    relevance_score: float
    match_source: str
    evidence_chunk_id: str | None = None
    article_no: str | None = None


@dataclass(frozen=True)
class ReviewEvidence:
    candidate: EvidenceCandidate
    rank_no: int


@dataclass(frozen=True)
class ReviewAnnotation:
    annotation_id: str
    review_id: str
    review_item_id: str
    file_id: str
    file_type: str
    review_type: str
    risk_level: str
    target_text: str
    display_mode: str
    status: str
    location_confidence: float | None
    confidence_policy_version: str
    display_reason: str
    page_no: int | None
    coordinate: Coordinate | None
    text_block_id: str | None = None
    text_path: str | None = None
    raw_start_offset: int | None = None
    raw_end_offset: int | None = None
    normalized_start_offset: int | None = None
    normalized_end_offset: int | None = None
    matched_text: str | None = None


@dataclass(frozen=True)
class ReviewResultItem:
    review_item_id: str
    review_id: str
    review_type: str
    target_text: str
    result_status: str
    risk_level: str
    risk_policy_version: str
    risk_reason_codes: tuple[str, ...]
    score_detail: dict[str, object]
    evidence_status: EvidenceStatus
    evidence_failure_code: str | None
    reason: str
    recommendation: str | None
    source_engine: str
    source_version: str
    confidence_score: float | None
    page_no: int | None
    evidences: tuple[ReviewEvidence, ...] = ()
    annotation: ReviewAnnotation | None = None
    requires_evidence: bool = False


@dataclass(frozen=True)
class ReviewResultBundle:
    review_id: str
    standard_version_ids: tuple[str, ...]
    items: tuple[ReviewResultItem, ...]
    check_required: bool


class EvidenceSearchFailure(RuntimeError):
    def __init__(self, code: Literal["RAG_SEARCH_UNAVAILABLE", "RAG_SEARCH_FAILED"]) -> None:
        self.code = code
        super().__init__(code)


Search = Callable[[str], Sequence[EvidenceCandidate]]
StructuredOutput = Callable[[ReviewResultItem], object]


class ReviewResultEngine:
    """Provider-independent, deterministic M5 execution boundary."""

    def __init__(
        self,
        *,
        search: Search | None = None,
        structured_output: StructuredOutput | None = None,
        rule_version: str = "rule-config-v1",
        risk_policy_version: str = "risk-policy-v1",
    ) -> None:
        self._search = search
        self._structured_output = structured_output
        self.rule_version = rule_version
        self.risk_policy_version = risk_policy_version

    def execute(
        self,
        document: NormalizedDocument,
        *,
        on_stage: Callable[[str], None] | None = None,
    ) -> ReviewResultBundle:
        """Run ordered review stages and expose durable progress boundaries."""
        items = [
            self._rule_item(document, block, index)
            for index, block in enumerate(document.text_blocks, 1)
        ]
        if on_stage is not None:
            on_stage("RAG_REVIEW")
        items = [self._rag(item) for item in items]
        if on_stage is not None:
            on_stage("RESULT_GENERATION")
        items = [self._structured(item) for item in items]
        return ReviewResultBundle(
            review_id=document.review_id,
            standard_version_ids=tuple(
                dict.fromkeys(
                    evidence.candidate.standard_version_id
                    for item in items
                    for evidence in item.evidences
                )
            ),
            items=tuple(items),
            check_required=any(
                item.result_status != "APPROPRIATE"
                or item.evidence_status in {"INSUFFICIENT", "SEARCH_UNAVAILABLE"}
                or item.score_detail["llm"]["status"] == "INVALID_SCHEMA"  # type: ignore[index]
                for item in items
            ),
        )

    def _rule_item(
        self, document: NormalizedDocument, block: TextBlock, index: int
    ) -> ReviewResultItem:
        text = block.normalized_text.strip()
        lowered = text.casefold()
        codes: tuple[str, ...]
        if any(token in lowered for token in ("최고", "무조건", "100%", "절대")):
            review_type, result_status, risk_level = (
                "MISLEADING_EXPRESSION",
                "NEEDS_REVISION",
                "HIGH",
            )
            codes = ("MISLEADING_ABSOLUTE_EXPRESSION", "RULE_EXPLICIT_VIOLATION")
            reason = "객관적 조건이 없는 절대적·최상급 표현이 확인되었습니다."
            recommendation = "객관적 산정 조건과 적용 범위를 함께 표시해 주세요."
            requires_evidence = True
        elif "%" in text and not any(token in text for token in ("세전", "기준", "적용")):
            review_type, result_status, risk_level = "INTEREST_RATE", "NEEDS_CONFIRMATION", "MEDIUM"
            codes = ("INTEREST_RATE_CONDITION_MISSING",)
            reason = "금리 수치의 기준 또는 적용 조건 확인이 필요합니다."
            recommendation = "세전 여부, 적용 기간, 우대 조건을 함께 표시해 주세요."
            requires_evidence = True
        else:
            review_type, result_status, risk_level = "REQUIRED_PHRASE", "APPROPRIATE", "LOW"
            codes = ("RULE_REQUIRED_CONTEXT_PRESENT",)
            reason = "결정적 문구 규칙에서 명시적 위반이 확인되지 않았습니다."
            recommendation = None
            requires_evidence = False
        item_id = f"ITEM-{document.review_id.removeprefix('REV-')}-{index:04d}"
        annotation = self._annotation(document, block, item_id, review_type, risk_level)
        score_detail: dict[str, object] = {
            "rule": {
                "matched": result_status != "APPROPRIATE",
                "ruleIds": list(codes),
                "severity": risk_level,
            },
            "rag": {
                "topRelevanceScore": None,
                "evidenceCount": 0,
                "evidenceSufficient": not requires_evidence,
                "status": "NOT_REQUIRED" if not requires_evidence else "INSUFFICIENT",
                "failureCode": None,
            },
            "llm": {
                "schemaVersion": "review-structured-output-v1",
                "status": "NOT_RUN",
                "decision": None,
                "confidence": None,
            },
            "parser": {"confidenceStatus": block.confidence_status.value},
            "final": {"riskLevel": risk_level, "decisionRule": codes[-1]},
        }
        return ReviewResultItem(
            item_id,
            document.review_id,
            review_type,
            text,
            result_status,
            risk_level,
            self.risk_policy_version,
            codes,
            score_detail,
            "INSUFFICIENT" if requires_evidence else "NOT_REQUIRED",
            None,
            reason,
            recommendation,
            "RULE",
            self.rule_version,
            block.confidence_score,
            block.page_no,
            annotation=annotation,
            requires_evidence=requires_evidence,
        )

    def _rag(self, item: ReviewResultItem) -> ReviewResultItem:
        if not item.requires_evidence:
            return item
        try:
            candidates = () if self._search is None else tuple(self._search(item.target_text))
        except EvidenceSearchFailure as exc:
            rag: dict[str, object] = {
                "topRelevanceScore": None,
                "evidenceCount": 0,
                "evidenceSufficient": False,
                "status": "SEARCH_UNAVAILABLE",
                "failureCode": exc.code,
            }
            return replace(
                item,
                evidence_status="SEARCH_UNAVAILABLE",
                evidence_failure_code=exc.code,
                score_detail={**item.score_detail, "rag": rag},
            )
        selected = tuple(
            ReviewEvidence(candidate, rank) for rank, candidate in enumerate(candidates[:3], 1)
        )
        status: EvidenceStatus = "CONNECTED" if selected else "INSUFFICIENT"
        rag = {
            "topRelevanceScore": selected[0].candidate.relevance_score if selected else None,
            "evidenceCount": len(selected),
            "evidenceSufficient": bool(selected),
            "status": status,
            "failureCode": None,
        }
        return replace(
            item,
            evidence_status=status,
            evidence_failure_code=None,
            evidences=selected,
            score_detail={**item.score_detail, "rag": rag},
        )

    def _structured(self, item: ReviewResultItem) -> ReviewResultItem:
        if self._structured_output is None:
            return item
        try:
            output = self._structured_output(item)
        except Exception:  # provider boundary is advisory and must not erase Rule results
            return self._invalid_structured(item)
        if not isinstance(output, dict) or set(output) != {
            "decision",
            "confidence",
            "reasonCode",
            "explanation",
        }:
            return self._invalid_structured(item)
        confidence = output["confidence"]
        has_valid_strings = all(
            isinstance(output[field], str) for field in ("decision", "reasonCode", "explanation")
        )
        has_valid_confidence = (
            isinstance(confidence, (int, float))
            and not isinstance(confidence, bool)
            and isfinite(confidence)
            and 0 <= confidence <= 1
        )
        if not has_valid_strings or not has_valid_confidence:
            return self._invalid_structured(item)
        llm = {
            "schemaVersion": "review-structured-output-v1",
            "status": "VALID",
            "decision": output["decision"],
            "confidence": float(confidence),
        }
        return replace(item, score_detail={**item.score_detail, "llm": llm})

    @staticmethod
    def _invalid_structured(item: ReviewResultItem) -> ReviewResultItem:
        llm: dict[str, object] = {
            "schemaVersion": "review-structured-output-v1",
            "status": "INVALID_SCHEMA",
            "decision": None,
            "confidence": None,
        }
        return replace(item, score_detail={**item.score_detail, "llm": llm})

    @staticmethod
    def _annotation(
        document: NormalizedDocument,
        block: TextBlock,
        item_id: str,
        review_type: str,
        risk_level: str,
    ) -> ReviewAnnotation:
        coordinate = block.coordinate
        confidence = coordinate.coordinate_confidence if coordinate else block.confidence_score
        location_confidence: float | None = confidence
        # HWP/HWPX structure coordinates describe the document model, whereas
        # the browser preview is an rhwp SVG rendering.  Use the canonical text
        # anchor there so the UI can resolve against the rendered glyphs instead
        # of drawing a plausible-looking but shifted structural rectangle.
        if (
            document.parser_name == "hwp-hybrid"
            and block.normalized_start_offset is not None
            and block.text_path
        ):
            coordinate = None
            display_mode = "TEXT_HIGHLIGHT"
            status = "PARTIALLY_LOCATED" if confidence < 0.80 else "LOCATED"
            display_reason = "RENDERED_SVG_TEXT_MATCH"
        elif coordinate is not None and confidence >= 0.50:
            display_mode = "BOX"
            status = "LOCATED" if confidence >= 0.80 else "LOW_CONFIDENCE"
            display_reason = "NORMALIZED_COORDINATE"
        elif coordinate is not None:
            display_mode = "LIST_ONLY"
            status = "NOT_LOCATED"
            display_reason = "LOW_LOCATION_CONFIDENCE"
            coordinate = None
        elif block.normalized_start_offset is not None and block.text_path:
            display_mode = "TEXT_HIGHLIGHT"
            status = "PARTIALLY_LOCATED" if confidence < 0.80 else "LOCATED"
            display_reason = "NORMALIZED_TEXT_OFFSET"
        else:
            display_mode = "LIST_ONLY"
            status = "NOT_LOCATED"
            display_reason = "NO_DISPLAY_LOCATION"
            location_confidence = None
        return ReviewAnnotation(
            annotation_id=f"ANN-{item_id.removeprefix('ITEM-')}",
            review_id=document.review_id,
            review_item_id=item_id,
            file_id=document.source_file_id,
            file_type=document.source_file_type,
            review_type=review_type,
            risk_level=risk_level,
            target_text=block.normalized_text,
            display_mode=display_mode,
            status=status,
            location_confidence=location_confidence,
            confidence_policy_version="confidence-thresholds-v1",
            display_reason=display_reason,
            page_no=block.page_no,
            coordinate=coordinate,
            text_block_id=block.text_block_id if display_mode == "TEXT_HIGHLIGHT" else None,
            text_path=block.text_path,
            raw_start_offset=block.raw_start_offset,
            raw_end_offset=block.raw_end_offset,
            normalized_start_offset=block.normalized_start_offset,
            normalized_end_offset=block.normalized_end_offset,
            matched_text=block.normalized_text,
        )
