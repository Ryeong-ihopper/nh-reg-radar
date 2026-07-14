"""Pure deterministic M7 KPI and canonical snapshot regression tests."""

import json
from pathlib import Path

from nh_ad_backend.validation import METRIC_ORDER, calculate_metrics, canonical_snapshot_hash


FIXTURE = Path(__file__).parents[3] / "tests" / "fixtures" / "m7" / "validation-kpi-v1.json"


def test_frozen_fixture_calculates_exact_kpis_without_provider_calls() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    metrics = calculate_metrics(fixture["cases"])

    actual = [
        {
            "metricCode": item.metric_code,
            "numerator": float(item.numerator),
            "denominator": item.denominator,
            "score": float(item.score) if item.score is not None else None,
            "excludedCount": item.excluded_count,
            "partialCount": item.partial_count,
            "notApplicable": item.not_applicable,
            "targetScore": float(item.target_score),
            "achieved": item.achieved,
        }
        for item in metrics
    ]
    assert tuple(item["metricCode"] for item in actual) == METRIC_ORDER
    assert actual == fixture["expectedMetrics"]


def test_canonical_snapshot_hash_is_stable_and_semantic_changes_are_visible() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    snapshot = fixture["canonicalSnapshotInput"]

    assert canonical_snapshot_hash(snapshot) == fixture["expectedSnapshotSha256"]
    reordered = {key: snapshot[key] for key in reversed(snapshot)}
    assert canonical_snapshot_hash(reordered) == fixture["expectedSnapshotSha256"]

    changed = json.loads(json.dumps(snapshot))
    changed["judgments"][0]["judgmentVersion"] += 1
    assert canonical_snapshot_hash(changed) != fixture["expectedSnapshotSha256"]


def test_ai_errors_remain_zero_and_zero_denominator_is_not_achieved() -> None:
    metrics = calculate_metrics(
        [
            {
                "caseId": "AI-ERROR",
                "metricCode": "MISLEADING_EXPRESSION_ACCURACY",
                "matchScore": 0,
                "excluded": False,
                "aiError": True,
            },
            {
                "caseId": "APPROVED-EXCLUSION",
                "metricCode": "HUMAN_AGREEMENT_RATE",
                "matchScore": 1,
                "excluded": True,
                "exclusionApproved": True,
                "excludeReasonCode": "OCR_UNREADABLE",
            },
        ]
    )
    misleading = metrics[1]
    assert misleading.denominator == 1
    assert misleading.numerator == 0
    assert misleading.excluded_count == 0
    human = metrics[3]
    assert human.denominator == 0
    assert human.score is None
    assert human.not_applicable is True
    assert human.achieved is False
