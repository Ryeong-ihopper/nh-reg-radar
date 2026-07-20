from pathlib import Path

from nh_ad_parser_contracts import NormalizedDocument

from nh_ad_worker.results import EvidenceCandidate, ReviewResultEngine
from nh_ad_worker.suggestions import rule_suggestions


FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "m4"


def document() -> NormalizedDocument:
    return NormalizedDocument.model_validate_json(
        (FIXTURES / "normalized-image-v1.json").read_text()
    )


def evidence() -> EvidenceCandidate:
    return EvidenceCandidate(
        "EVD-SUG-001",
        "STDVER-SUG-001",
        "GUIDELINE",
        "광고 표현 기준",
        "객관적 기준 없는 절대적 표현은 사용할 수 없습니다.",
        0.91,
        "HYBRID",
    )


def test_rule_suggestions_are_repeatable_and_keep_review_evidence() -> None:
    results = ReviewResultEngine(search=lambda _query: [evidence()]).execute(document())

    first = rule_suggestions(results)
    second = rule_suggestions(results)

    assert first == second
    assert len(first) == 1
    suggestion = first[0]
    assert suggestion.suggestion_type == "SOFTENING"
    assert suggestion.evidence_ids == ("EVD-SUG-001",)
    assert "적용 조건" in suggestion.suggested_text


def test_rule_suggestions_skip_appropriate_items() -> None:
    fixture = document().model_copy(deep=True)
    fixture.text_blocks[0].normalized_text = "중도해지 시 불이익이 발생할 수 있습니다."

    assert rule_suggestions(ReviewResultEngine().execute(fixture)) == ()


def test_rule_suggestions_do_not_detach_a_phrase_from_its_evidence() -> None:
    assert rule_suggestions(ReviewResultEngine().execute(document())) == ()


def test_invalid_or_failed_refinement_keeps_the_rule_suggestion() -> None:
    results = ReviewResultEngine(search=lambda _query: [evidence()]).execute(document())

    suggestion = rule_suggestions(results, refine=lambda _item, _proposal: None)[0]

    assert "적용 조건" in suggestion.suggested_text
    assert "AI가 문장을 보강" not in suggestion.suggestion_reason
