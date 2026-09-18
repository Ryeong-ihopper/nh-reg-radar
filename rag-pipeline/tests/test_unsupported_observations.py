import copy
import unittest
from test_operational_rag_contracts import gemma, request_row, result
from rag.judgment.unsupported_observations import quarantine_unsupported_observations, abstain_unresolved_applicability


class UnsupportedObservationTests(unittest.TestCase):
    def test_unknown_applicability_is_review_without_guessing_exclusion(self):
        request = request_row(['TEST-X'])
        value = result('TEST-X')
        value.update(applicability='NOT_APPLICABLE', applicability_basis='NOT_APPLICABLE',
            verdict='NOT_APPLICABLE', requirement_checks=[], evidence_ids=[], evidence_line_refs=[],
            reason='자료가 부족하여 적용 여부를 확인할 수 없습니다.')
        response = {'parsed': {'ad_id': request['ad_id'], 'results': [value]}}
        response['validation_errors'] = gemma.validate(request, response['parsed'])
        original = copy.deepcopy(response)
        updated = abstain_unresolved_applicability(request, response, gemma.validate)
        self.assertEqual(updated['validation_errors'], [])
        self.assertEqual(updated['parsed']['results'][0]['verdict'], 'UNDETERMINED')
        self.assertEqual(updated['applicability_quality_review']['original_result'], original['parsed'])
        self.assertEqual(response, original)

    def test_applicability_guard_never_hides_other_failures(self):
        request, response = self.fixture()
        response['validation_errors'] = [
            'TEST-X: explanation says applicability cannot be determined; unknown is UNDETERMINED, not NOT_APPLICABLE',
            'TEST-X: unknown source reference']
        self.assertIs(abstain_unresolved_applicability(request, response, gemma.validate), response)

    def test_unconfirmed_situation_is_not_negative_applicability(self):
        from rag.judgment.source_checks import unresolved_applicability
        self.assertTrue(unresolved_applicability({'verdict': 'NOT_APPLICABLE',
            'reason': '해당 자료가 비교 광고인지 확인할 수 없습니다.'}))
        self.assertFalse(unresolved_applicability({'verdict': 'NOT_APPLICABLE',
            'reason': '매체 정보에서 인쇄물임을 확인하여 전송형 광고 범위를 제외합니다.'}))

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
