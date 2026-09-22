from __future__ import annotations

import unittest

from rag.evaluation.prompt_ablation import build_protocol, compare_predictions


class PromptAblationTests(unittest.TestCase):
    def protocol(self):
        plans = {"source_binding_sha256": "sha", "plans": [{
            "plan_id": "P1", "prompt_family": "F", "obligations": [{"obligation_id": "O1"}],
            "unresolved": [],
        }]}
        batches = {"source_binding_sha256": "sha", "batches": [{"prompt": "p", "family": "F"}]}
        return build_protocol(plans, batches)

    def test_protocol_never_claims_unmeasured_accuracy(self):
        protocol = self.protocol()
        self.assertFalse(protocol["reporting_policy"]["may_claim_dev_improvement"])
        self.assertFalse(protocol["reporting_policy"]["may_claim_generalization"])
        self.assertEqual(0, protocol["splits"]["holdout"]["labeled_pairs"])

    def test_holdout_comparison_is_refused_when_holdout_absent(self):
        with self.assertRaises(ValueError):
            compare_predictions(self.protocol(), {}, [], split="holdout")

    def test_dev_requires_exact_keys_and_compares_all_arms(self):
        protocol = self.protocol()
        gold = [{"ad_id": "A", "item_id": "I", "verdict": "COMPLIANT"}]
        result = compare_predictions(protocol, {
            "A0": [{"ad_id": "A", "item_id": "I", "verdict": "VIOLATION",
                    "citation_supported": False}],
            "A1": [{"ad_id": "A", "item_id": "I", "verdict": "COMPLIANT",
                    "citation_supported": True}],
        }, gold, split="dev_regression")
        self.assertEqual(0, result["arms"]["A0"]["exact_verdict"])
        self.assertEqual(1, result["arms"]["A1"]["exact_verdict"])
        self.assertIsNone(result["arms"]["A1"]["violation_recall"])
        self.assertEqual(1.0, result["arms"]["A0"]["unsupported_citation_rate"])
        with self.assertRaises(ValueError):
            compare_predictions(protocol, {"A1": []}, gold, split="dev_regression")

    def test_complete_ablation_can_require_all_four_arms(self):
        protocol = self.protocol()
        gold = [{"ad_id": "A", "item_id": "I", "verdict": "VIOLATION",
                 "rule_family": "SEMANTIC"}]
        row = [{"ad_id": "A", "item_id": "I", "verdict": "VIOLATION",
                "citation_supported": True}]
        result = compare_predictions(protocol, {arm: row for arm in ["A0", "A1", "A2", "A3"]},
                                     gold, split="dev_regression", require_all_arms=True)
        self.assertEqual(1.0, result["arms"]["A3"]["violation_recall"])
        self.assertEqual(1, result["arms"]["A3"]["rule_family_breakdown"]["SEMANTIC"]["exact"])
        with self.assertRaisesRegex(ValueError, "A0-A3"):
            compare_predictions(protocol, {"A0": row}, gold, split="dev_regression",
                                require_all_arms=True)


if __name__ == "__main__":
    unittest.main()
