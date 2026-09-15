import unittest

from rag.judgment.runtime_metrics import judgment_call_metrics


class RuntimeCallMetricsTests(unittest.TestCase):
    def test_split_ancestor_is_counted_once_and_failed_attempt_not_lost(self):
        parent = {"request_id": "R", "attempt": 1, "seconds": 10, "validation_errors": ["bad JSON"]}
        child = {"request_id": "R/a", "attempt": 1, "seconds": 3, "validation_errors": []}
        other = dict(child, request_id="R/b", seconds=4)
        result = judgment_call_metrics([{"call_history": [parent, child]}, {"call_history": [parent, other]}])
        self.assertEqual(result["physical_calls"], 3)
        self.assertEqual(result["failed_contract_calls"], 1)
        self.assertEqual(result["model_seconds_sum"], 17)
        self.assertTrue(result["call_audit_complete"])

    def test_legacy_response_does_not_claim_complete_audit(self):
        self.assertFalse(judgment_call_metrics([{"request_id": "old", "seconds": 5}])["call_audit_complete"])

    def test_conflicting_same_call_not_silently_overwritten(self):
        event = {"request_id": "R", "attempt": 1, "seconds": 1}
        with self.assertRaises(ValueError):
            judgment_call_metrics([{"call_history": [event, dict(event, seconds=2)]}])
