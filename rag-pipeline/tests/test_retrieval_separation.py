import json
import tempfile
import unittest
from pathlib import Path

from rag.evaluation.retrieval_separation import evaluate_search, freeze_search


class RetrievalSeparationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.discovery = {"ads": [{"ad_id": "ad", "candidate_budget": {
            "selected_ids": ["rule"], "deferred_ids": ["deferred"]}}]}
        self.body = {"ad_id": "ad", "rules": [{"item_id": "rule"}],
                     "evidence_scope": {"rule": {"evidence_ids": ["own"]}},
                     "documents": [{"evidence_id": "own", "line_texts": {"line": "verified text"},
                                    "text_selection": {"needs_review": False}},
                                   {"evidence_id": "other", "line_texts": {"foreign": "other rule text"}}]}

    def run_case(self, ref="line", text="verified text", item="rule"):
        (self.root / "01_discovery.json").write_text(json.dumps(self.discovery))
        (self.root / "02_judgment_requests.jsonl").write_text(json.dumps({
            "messages": [{}, {"content": json.dumps(self.body)}]}))
        freeze_search(self.root)
        path = self.root / "reference.json"
        path.write_text(json.dumps({"purpose": "DEV_REGRESSION", "targets": [{
            "ad_id": "ad", "item_id": item, "evidence_groups": [{"name": "proof",
            "lines": [{"line_ref": ref, "text": text}]}]}]}))
        return evaluate_search(self.root, path)["targets"][0]

    def test_exact_source_and_text(self):
        row = self.run_case()
        self.assertEqual(row["discovery_method"], "SUPPLEMENTAL_SEARCH")
        self.assertTrue(row["evidence_groups"][0]["verified_complete"])

    def test_batched_other_rule_evidence_is_not_recalled(self):
        row = self.run_case("foreign", "other rule text")
        self.assertFalse(row["evidence_groups"][0]["exact_complete"])

    def test_same_id_wrong_ocr_is_not_recalled(self):
        self.body["documents"][0]["line_texts"]["line"] = "broken OCR"
        self.assertFalse(self.run_case()["evidence_groups"][0]["exact_complete"])

    def test_uncertain_exact_text_is_separate(self):
        self.body["documents"][0]["text_selection"]["needs_review"] = True
        row = self.run_case()["evidence_groups"][0]
        self.assertTrue(row["exact_complete"])
        self.assertFalse(row["verified_complete"])

    def test_budget_deferral_is_discovery_not_request(self):
        row = self.run_case(item="deferred")
        self.assertEqual(row["discovery_method"], "SUPPLEMENTAL_SEARCH")
        self.assertEqual(row["request_state"], "BUDGET_DEFERRED")

    def test_audit_only_discovery_is_not_reported_as_budget_deferral(self):
        self.discovery["ads"][0]["candidate_budget"]["method"] = "discovery_audit_only_v1"
        row = self.run_case(item="deferred")
        self.assertEqual(row["discovery_method"], "SUPPLEMENTAL_SEARCH")
        self.assertEqual(row["request_state"], "AUDIT_ONLY")

    def test_modified_predictions_rejected(self):
        self.run_case()
        (self.root / "01_discovery.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "changed"):
            evaluate_search(self.root, self.root / "reference.json")

    def test_freeze_cannot_be_overwritten(self):
        self.run_case()
        with self.assertRaises(FileExistsError):
            freeze_search(self.root)

    def test_reference_not_read_before_freeze(self):
        with self.assertRaises(FileNotFoundError) as caught:
            evaluate_search(self.root, self.root / "must-not-read.json")
        self.assertIn("RETRIEVAL_FREEZE", str(caught.exception))

    def test_same_text_with_different_source_is_text_only(self):
        self.body["documents"][0]["text"] = "verified text"
        row = self.run_case(ref="different-source")["evidence_groups"][0]
        self.assertTrue(row["text_complete"])
        self.assertFalse(row["exact_complete"])

    def test_unobserved_reading_quality_is_not_verified(self):
        del self.body["documents"][0]["text_selection"]
        self.assertFalse(self.run_case()["evidence_groups"][0]["verified_complete"])
