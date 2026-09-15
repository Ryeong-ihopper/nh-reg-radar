from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rag.evaluation.blind import (  # noqa: E402
    BlindEvaluationError,
    content_sha256,
    create_review_packet,
    evaluate_frozen_prediction,
    freeze_prediction,
    seal_human_labels,
)


def prediction() -> dict:
    identity = {
        "ad_id": "ADV-NEW",
        "scope_id": "ADV-NEW::P1",
        "product_id": "P1",
    }
    return {
        "schema_version": "operational-e2e-result-v1",
        "audit": {"model": {"requested": "gemma"}},
        "counts": {"requested_pairs": 2, "predicted_pairs": 2, "output_failures": 0},
        "output_failure_pairs": [],
        "ads": [
            {
                **identity,
                "candidates": [
                    {
                        "item_id": "C-001",
                        "rule_basis": {"source_type": "REGULATION_V2"},
                        "condition_contract": {
                            "scope_text": "deposit ads",
                            "obligation": {"text": "show rate"},
                        },
                        "judgment": {
                            "verdict": "COMPLIANT",
                            "reason": "model-only reason",
                            "confidence": "HIGH",
                            "evidence_ids": ["E1"],
                            "evidence_line_refs": ["L1"],
                        },
                        "decision_trace": {"decision_source": "LLM"},
                    }
                ],
                "excluded_candidates": [
                    {
                        "item_id": "D-001",
                        "rule_basis": {"source_type": "REGULATION_V2"},
                        "condition_contract": {
                            "scope_text": "loan only",
                            "obligation": {"text": "show warning"},
                        },
                        "judgment": {
                            "verdict": "NOT_APPLICABLE",
                            "reason": "model-only reason",
                            "confidence": "HIGH",
                            "evidence_ids": [],
                            "evidence_line_refs": [],
                        },
                    }
                ],
            }
        ],
    }


def frozen(value: dict | None = None, *, split: str = "DEV_REGRESSION") -> dict:
    value = value or prediction()
    return freeze_prediction(
        value,
        prediction_sha256=content_sha256(value),
        dataset_id="DATASET-1",
        split=split,
        unseen_confirmed_by="review-lead" if split == "BLIND_HOLDOUT" else None,
        unseen_confirmed_at="2026-09-14T10:00:00+09:00" if split == "BLIND_HOLDOUT" else None,
    )


def completed_packet() -> tuple[dict, dict]:
    value = prediction()
    freeze = frozen(value)
    packet = create_review_packet(value, freeze)
    for row in packet["rows"]:
        verdict = "VIOLATION" if row["item_id"] == "C-001" else "COMPLIANT"
        row["reviewer_decisions"] = [
            {
                "reviewer_id": "reviewer-a",
                "verdict": verdict,
                "reason": "광고 원문과 규칙 적용조건을 확인함",
                "evidence_refs": ["L1"],
                "reviewed_at": "2026-09-14T10:10:00+09:00",
            },
            {
                "reviewer_id": "reviewer-b",
                "verdict": verdict,
                "reason": "독립 검수 결과가 동일함",
                "evidence_refs": ["L1"],
                "reviewed_at": "2026-09-14T10:20:00+09:00",
            },
        ]
        row["final_decision"] = {
            "verdict": verdict,
            "reason": "두 검수자 판정 일치",
            "decided_by": "review-lead",
            "decided_at": "2026-09-14T10:30:00+09:00",
            "resolution": "CONSENSUS",
        }
    return freeze, packet


class BlindEvaluationTests(unittest.TestCase):
    def test_holdout_requires_unseen_declaration(self):
        value = prediction()
        with self.assertRaisesRegex(BlindEvaluationError, "unseen-data declaration"):
            freeze_prediction(
                value,
                prediction_sha256=content_sha256(value),
                dataset_id="DATASET-1",
                split="BLIND_HOLDOUT",
            )

    def test_review_packet_contains_rules_but_no_model_output(self):
        value = prediction()
        packet = create_review_packet(value, frozen(value))
        text = str(packet["rows"])
        self.assertIn("condition_contract", text)
        self.assertNotIn("model-only reason", text)
        self.assertNotIn("predicted_verdict", text)
        self.assertNotIn("decision_trace", text)

    def test_packet_rejects_prediction_changed_after_freeze(self):
        value = prediction()
        freeze = frozen(value)
        value["ads"][0]["candidates"][0]["judgment"]["verdict"] = "VIOLATION"
        with self.assertRaisesRegex(BlindEvaluationError, "does not match the freeze"):
            create_review_packet(value, freeze)

    def test_one_reviewer_can_be_accumulated_but_is_not_gold_ready(self):
        freeze, packet = completed_packet()
        del freeze
        for row in packet["rows"]:
            row["reviewer_decisions"] = row["reviewer_decisions"][:1]
        sealed = seal_human_labels(packet, minimum_reviewers=2)
        self.assertEqual(sealed["status"], "HUMAN_REVIEW_IN_PROGRESS")
        self.assertEqual(sealed["counts"]["below_minimum_reviewers"], 2)

    def test_invalid_consensus_is_rejected(self):
        _freeze, packet = completed_packet()
        packet["rows"][0]["reviewer_decisions"][1]["verdict"] = "COMPLIANT"
        with self.assertRaisesRegex(BlindEvaluationError, "not a valid consensus"):
            seal_human_labels(packet)

    def test_gold_ready_snapshot_and_error_taxonomy(self):
        freeze, packet = completed_packet()
        labels = seal_human_labels(packet, minimum_reviewers=2)
        self.assertEqual(labels["status"], "GOLD_READY")
        result = evaluate_frozen_prediction(freeze, labels)
        self.assertEqual(result["counts"], {"pairs": 2, "exact_agreement": 0, "errors": 2})
        self.assertEqual(result["error_types"]["VERDICT_ERROR"], 1)
        self.assertEqual(result["error_types"]["MISSED_APPLICABLE_RULE"], 1)

    def test_evaluation_rejects_incomplete_human_review(self):
        freeze, packet = completed_packet()
        packet["rows"][0]["final_decision"] = None
        labels = seal_human_labels(packet)
        with self.assertRaisesRegex(BlindEvaluationError, "not GOLD_READY"):
            evaluate_frozen_prediction(freeze, labels)

    def test_labels_cannot_be_joined_to_another_prediction(self):
        freeze, packet = completed_packet()
        labels = seal_human_labels(packet)
        other = copy.deepcopy(freeze)
        other["prediction_sha256"] = "0" * 64
        with self.assertRaisesRegex(BlindEvaluationError, "different prediction"):
            evaluate_frozen_prediction(other, labels)


if __name__ == "__main__":
    unittest.main()
