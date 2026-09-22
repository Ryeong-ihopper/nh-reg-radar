import unittest

from rag.evaluation.source_coverage import evaluation_source_coverage


class EvaluationSourceCoverageTest(unittest.TestCase):
    def test_unscored_v2_blocks_overall_accuracy_claim(self):
        report = evaluation_source_coverage([
            {"review_id": "r", "item_id": "tpl", "source_type": "INTERNAL_TEMPLATE",
             "discovery_tier": "TEMPLATE_PRIMARY"},
            {"review_id": "r", "item_id": "v2", "source_type": "REGULATION_V2",
             "discovery_tier": "MAPPED_V2"},
        ], {("r", "tpl")})
        self.assertEqual(report["scored_rows"], 1)
        self.assertEqual(report["unscored_rows"], 1)
        self.assertEqual(report["by_source"]["REGULATION_V2"]["score_coverage"], 0)
        self.assertFalse(report["overall_accuracy_claim_allowed"])

    def test_complete_formal_scope_allows_accuracy_claim(self):
        rows = [{"review_id": "r", "item_id": "tpl", "source_type": "INTERNAL_TEMPLATE",
                 "discovery_tier": "TEMPLATE_PRIMARY"}]
        report = evaluation_source_coverage(rows, {("r", "tpl")})
        self.assertTrue(report["overall_accuracy_claim_allowed"])

    def test_duplicate_formal_prediction_is_rejected(self):
        row = {"review_id": "r", "item_id": "tpl", "source_type": "INTERNAL_TEMPLATE",
               "discovery_tier": "TEMPLATE_PRIMARY"}
        with self.assertRaisesRegex(ValueError, "duplicate formal prediction"):
            evaluation_source_coverage([row, row], set())


if __name__ == "__main__":
    unittest.main()
