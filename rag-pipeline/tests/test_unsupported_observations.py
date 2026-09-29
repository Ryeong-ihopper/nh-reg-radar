import copy
import json
import unittest
from test_operational_rag_contracts import gemma, request_row, result
from rag.judgment.unsupported_observations import quarantine_unsupported_observations, abstain_unresolved_applicability
from rag.judgment.obligation_logic import aggregate_obligations
from rag.judgment.review_program import program_trace


class CanonicalMetadataObservationTests(unittest.TestCase):
    """Exercise the real validator and recovery with synthetic disclosure facts."""

    disclosures = (
        ('상담사의 별도 수수료 요구 금지 안내',
         '상담사는 고객에게 별도 수수료를 청구할 수 없습니다.'),
        ('상담사의 별도 수수료 수취 금지 안내',
         '상담사는 고객에게 별도 수수료를 받을 수 없습니다.'),
        ('상담사의 대출계약 체결 권한 부재 안내',
         '상담사에게 대출계약을 맺을 권한은 없습니다.'),
        ('은행의 직접 대출 심사 안내',
         '은행이 대출 실행 여부를 직접 심사합니다.'),
        ('은행의 대출 실행 여부 결정 안내',
         '대출 실행 여부는 은행에서 결정합니다.'),
        ('고객 제공 정보의 은행 관리 안내',
         '고객이 제공한 신용정보와 개인정보는 취급 은행이 관리합니다.'),
    )

    def fixture(self):
        request = request_row(['SYNTHETIC-DISCLOSURE'])
        payload = json.loads(request['messages'][1]['content'])
        line_texts = {f'L-{index}': quote
                      for index, (_, quote) in enumerate(self.disclosures, 1)}
        payload['documents'] = [{
            'evidence_id': 'E-1', 'line_refs': list(line_texts),
            'line_texts': line_texts, 'text': '\n'.join(line_texts.values()),
        }]
        payload.update(
            parser_coverage='READY', full_ad_text='\n'.join(line_texts.values()),
            reading_quality={'global_scan_incomplete': False},
            evidence_scope={'SYNTHETIC-DISCLOSURE': {
                'evidence_ids': ['E-1'], 'complete_ad_scan': True}},
            routing={'template_id': {
                'value': 'SYNTHETIC-TEMPLATE', 'status': 'confirmed', 'source': 'test'}},
        )
        obligations = [{
            'obligation_id': f'O{index}', 'text': meaning,
            'owners': {'rule': False, 'llm': True, 'external_input': False, 'human': False},
            'evidence': {'advertisement_direct_quote_required': True,
                         'absence_requires_complete_scan': True},
        } for index, (meaning, _) in enumerate(self.disclosures, 1)]
        contract = {
            'scope_ref': 'SCOPE', 'scope_owner': 'RULE',
            'applicability_conditions': [{
                'condition_id': 'A1', 'text': 'selected_template',
                'owner': 'RULE', 'condition_role': 'FACT'}],
            'applicability_logic': {'all': [{'fact': 'A1'}]},
            'review_conditions': [], 'obligation_checks': obligations,
            'obligation_logic': {'all': [{'ref': o['obligation_id']} for o in obligations]},
            'review_program': {
                'program_sha256': 'synthetic-program', 'source_sha256': 'synthetic-source',
                'kinds': ['SEMANTIC'],
                'allowed_outcomes': ['COMPLIANT', 'VIOLATION', 'UNDETERMINED']},
        }
        payload['rules'][0].update(
            title='합성 모집인 안내', question='합성 모집인 안내',
            criterion='선택한 합성 템플릿의 안내 의미를 확인한다.',
            source_sheet='HWPX_TEMPLATE', required_medium='TEXT', condition_contract=contract,
        )
        request['messages'][1]['content'] = json.dumps(payload, ensure_ascii=False)
        value = result('SYNTHETIC-DISCLOSURE')
        value.update(
            scope_check={'scope_ref': 'SCOPE', 'status': 'MATCHED'},
            condition_checks=[{'condition_ref': 'A1', 'status': 'SATISFIED',
                               'metadata_fields': ['template_id']}],
            review_condition_checks=[], applicability_basis='CONFIRMED_METADATA',
            applicability_evidence_ids=[], applicability_evidence_line_refs=[],
            applicability_metadata_fields=['template_id'],
            evidence_line_refs=list(line_texts),
            requirement_checks=[{
                'obligation_ref': f'O{index}', 'requirement': meaning,
                'status': 'SATISFIED', 'finding_basis': 'OBSERVED',
                'evidence_ids': ['E-1'], 'evidence_line_refs': [f'L-{index}'],
                'reason': f'"{quote}"에서 해당 안내 의미를 확인합니다.',
            } for index, (meaning, quote) in enumerate(self.disclosures, 1)],
        )
        self.refresh_trace(contract, value)
        return request, contract, {'ad_id': request['ad_id'], 'results': [value]}

    def refresh_trace(self, contract, value):
        value['verdict'] = aggregate_obligations(
            contract, value['requirement_checks'], value['condition_checks'])
        value['needs_researcher_review'] = value['verdict'] != 'COMPLIANT'
        value['review_program_trace'] = program_trace(
            contract, value['requirement_checks'], value['condition_checks'], value['verdict'])

    def guard(self, request, parsed):
        response = {'parsed': parsed, 'validation_errors': gemma.validate(request, parsed)}
        original = copy.deepcopy(response)
        guarded = quarantine_unsupported_observations(request, response, gemma.validate)
        self.assertEqual(response, original)
        return original, guarded

    def test_confirmed_scope_and_six_direct_observations_are_valid(self):
        request, contract, parsed = self.fixture()
        self.assertEqual(gemma.validate(request, parsed), [])
        self.assertEqual(parsed['results'][0]['verdict'], 'COMPLIANT')
        self.assertEqual(len(contract['applicability_conditions']), 1)
        self.assertTrue(all(not o['owners']['human'] for o in contract['obligation_checks']))
        self.assertTrue(all(o['owners']['llm'] for o in contract['obligation_checks']))

    def test_metadata_cannot_certify_any_advertisement_disclosure(self):
        for index, (meaning, _) in enumerate(self.disclosures):
            for retain_quote in (False, True):
                with self.subTest(meaning=meaning, retain_quote=retain_quote):
                    request, contract, parsed = self.fixture()
                    value = parsed['results'][0]
                    check = value['requirement_checks'][index]
                    check.update(finding_basis='CONFIRMED_METADATA',
                                 reason='접수 템플릿 선택값이 확정됐습니다.')
                    if not retain_quote:
                        check.update(evidence_ids=[], evidence_line_refs=[])
                    original, guarded = self.guard(request, parsed)
                    self.assertEqual(original['validation_errors'], [
                        f'SYNTHETIC-DISCLOSURE: requirement_checks[{index}] '
                        'metadata cannot establish an advertisement-only obligation'])
                    self.assertEqual(guarded['validation_errors'], [])
                    final = guarded['parsed']['results'][0]
                    self.assertEqual(final['requirement_checks'][index]['status'], 'UNDETERMINED')
                    self.assertEqual(final['requirement_checks'][index]['finding_basis'], 'UNKNOWN')
                    self.assertEqual(final['requirement_checks'][index]['evidence_line_refs'], [])
                    self.assertEqual(final['verdict'], 'UNDETERMINED')
                    self.assertTrue(final['needs_researcher_review'])
                    self.assertEqual(final['condition_checks'], value['condition_checks'])
                    self.assertEqual(final['review_program_trace']['verdict'], 'UNDETERMINED')
                    self.assertEqual(final['review_program_trace']['stage'], 'grounding_guard')
                    self.assertEqual(final['review_program_trace']['checks'][index]['status'], 'UNDETERMINED')
                    self.assertEqual(final['review_program_history'][0]['verdict'], 'COMPLIANT')
                    for other_index, other in enumerate(final['requirement_checks']):
                        if other_index != index:
                            self.assertEqual(other, value['requirement_checks'][other_index])

    def test_metadata_cannot_invent_disclosure_absence(self):
        request, contract, parsed = self.fixture()
        value = parsed['results'][0]
        value['requirement_checks'][0].update(
            status='MISSING', finding_basis='CONFIRMED_METADATA',
            evidence_ids=[], evidence_line_refs=[],
            reason='접수 템플릿 선택값에서 해당 안내를 확인하지 못했습니다.',
        )
        value['reason'] = '접수값만으로 안내의 부재를 주장한 합성 응답입니다.'
        self.refresh_trace(contract, value)
        self.assertEqual(value['verdict'], 'VIOLATION')
        original, guarded = self.guard(request, parsed)
        self.assertEqual(original['validation_errors'], [
            'SYNTHETIC-DISCLOSURE: requirement_checks[0] '
            'metadata cannot establish an advertisement-only obligation'])
        self.assertEqual(guarded['validation_errors'], [])
        final = guarded['parsed']['results'][0]
        self.assertEqual(final['verdict'], 'UNDETERMINED')
        self.assertEqual(final['requirement_checks'][0]['status'], 'UNDETERMINED')
        self.assertEqual(final['review_program_history'][0]['verdict'], 'VIOLATION')
        self.assertEqual(final['review_program_trace']['verdict'], 'UNDETERMINED')

    def test_uncertain_meaning_stays_unknown_after_complete_scan(self):
        request, contract, parsed = self.fixture()
        value = parsed['results'][0]
        value['requirement_checks'][3].update(
            status='UNDETERMINED', finding_basis='UNKNOWN',
            evidence_ids=[], evidence_line_refs=[],
            reason='은행의 직접 심사를 뜻하는지 원문 의미를 확인할 수 없습니다.',
        )
        self.refresh_trace(contract, value)
        self.assertEqual(gemma.validate(request, parsed), [])
        original, guarded = self.guard(request, parsed)
        self.assertEqual(guarded, original)
        self.assertEqual(value['verdict'], 'UNDETERMINED')
        self.assertEqual(len(value['requirement_checks']), len(self.disclosures))
        self.assertEqual(value['requirement_checks'][3]['finding_basis'], 'UNKNOWN')


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

    def test_missing_direct_quote_can_be_quarantined_after_retry(self):
        request, response = self.fixture()
        response['validation_errors'] = [
            'TEST-X: requirement_checks[0] 관찰 판정 사유에 인용한 원문 줄의 직접 인용이 없음; '
            '실제 지지 문구를 따옴표로 제시하고 그 문구가 있는 줄만 인용해야 함']
        guarded = quarantine_unsupported_observations(request, response, gemma.validate)
        self.assertEqual(guarded['validation_errors'], [])
        self.assertEqual(guarded['parsed']['results'][0]['verdict'], 'UNDETERMINED')

    def test_missing_external_comparison_can_be_quarantined_after_retry(self):
        request, response = self.fixture()
        response['validation_errors'] = [
            'TEST-X: requirement_checks[0] 규칙이 요구하는 외부 자료 대조 없이 '
            '광고 원문만으로 위반을 확정할 수 없음']
        guarded = quarantine_unsupported_observations(request, response, gemma.validate)
        self.assertEqual(guarded['validation_errors'], [])
        self.assertEqual(guarded['parsed']['results'][0]['verdict'], 'UNDETERMINED')

    def test_independent_observed_violation_survives(self):
        request, response = self.fixture()
        check = copy.deepcopy(result("TEST-X")["requirement_checks"][0])
        check.update(status="VIOLATED", reason="'테스트 근거'에서 확인한 위반")
        response["parsed"]["results"][0]["requirement_checks"].append(check)
        guarded = quarantine_unsupported_observations(request, response, gemma.validate)
        self.assertEqual(guarded["validation_errors"], [])
        self.assertEqual(guarded["parsed"]["results"][0]["verdict"], "VIOLATION")
        self.assertEqual(guarded["parsed"]["results"][0]["evidence_line_refs"], ["L-1"])
