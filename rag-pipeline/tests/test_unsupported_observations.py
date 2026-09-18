import copy
import unittest
from test_operational_rag_contracts import gemma, request_row, result
from rag.judgment.unsupported_observations import quarantine_unsupported_observations


class UnsupportedObservationTests(unittest.TestCase):
    def fixture(self):
        request = request_row(["TEST-X"])
        judgment = result("TEST-X")
        judgment["requirement_checks"][0].update(evidence_ids=[], evidence_line_refs=[])
        response = {"parsed": {"ad_id": request["ad_id"], "results": [judgment]},
                    "validation_errors": ["TEST-X: OBSERVED에는 직접 광고 근거가 필요"]}
        return request, response

    def test_unsupported_compliance_becomes_explicit_human_review(self):
        request, response = self.fixture()
        original = copy.deepcopy(response)
        guarded = quarantine_unsupported_observations(request, response, gemma.validate)
        self.assertEqual(guarded["validation_errors"], [])
        judgment = guarded["parsed"]["results"][0]
        self.assertEqual(judgment["verdict"], "UNDETERMINED")
        self.assertTrue(judgment["needs_researcher_review"])
        self.assertEqual(judgment["evidence_line_refs"], [])
        self.assertEqual(response, original)

    def test_unrelated_errors_and_invalid_contract_remain_failures(self):
        request, response = self.fixture()
        for error in ["missing result", "TEST-X: requirement_checks[0] 제공 밖 line_ref", "timeout"]:
            candidate = copy.deepcopy(response)
            candidate["validation_errors"].append(error)
            self.assertIs(quarantine_unsupported_observations(request, candidate, gemma.validate), candidate)
        response["parsed"]["ad_id"] = "wrong-ad"
        self.assertIs(quarantine_unsupported_observations(request, response, gemma.validate), response)

    def test_heading_only_observation_can_be_quarantined_after_retry(self):
        request, response = self.fixture()
        response['validation_errors'] = [
            'TEST-X: requirement_checks[0] template heading alone cannot establish the required body disclosure']
        guarded = quarantine_unsupported_observations(request, response, gemma.validate)
        self.assertEqual(guarded['validation_errors'], [])
        self.assertEqual(guarded['parsed']['results'][0]['verdict'], 'UNDETERMINED')

    def test_independent_observed_violation_survives(self):
        request, response = self.fixture()
        check = copy.deepcopy(result("TEST-X")["requirement_checks"][0])
        check.update(status="VIOLATED", reason="별도 원문에서 확인한 위반")
        response["parsed"]["results"][0]["requirement_checks"].append(check)
        guarded = quarantine_unsupported_observations(request, response, gemma.validate)
        self.assertEqual(guarded["validation_errors"], [])
        self.assertEqual(guarded["parsed"]["results"][0]["verdict"], "VIOLATION")
        self.assertEqual(guarded["parsed"]["results"][0]["evidence_line_refs"], ["L-1"])
