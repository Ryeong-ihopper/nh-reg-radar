import unittest

from rag.judgment.condition_contracts import compile_condition_contract
from rag.judgment.source_checks import (source_claim_errors, has_arithmetic_mismatch_witness,
                                       unresolved_applicability, template_heading_only_citation)
from rag.judgment.manual_review import text_facet_claim_errors


class SourceChecksTests(unittest.TestCase):
    def test_template_body_requirement_cannot_be_proved_by_heading_alone(self):
        rule = {'item_id':'SYN', 'source_sheet':'HWPX_TEMPLATE', 'title':'해약 안내',
                'example_text':'계약을 해지하면 제공하던 서비스 이용이 제한됩니다.'}
        check = {'obligation_ref':'O1','status':'SATISFIED','finding_basis':'OBSERVED',
                 'evidence_line_refs':['L']}
        for text in ('해약 안내', '상품 해약 안내', '■ 해약 안내:'):
            docs = [{'line_refs':['L'], 'line_texts':{'L':text}}]
            self.assertTrue(template_heading_only_citation(rule, check, docs))
            self.assertTrue(source_claim_errors({'rules':[rule],'documents':docs},
                {'item_id':'SYN','requirement_checks':[check]}))
        for text in ('해약 안내\n해약 후에는 서비스를 사용할 수 없습니다.', '해약 시 이용 제한', ''):
            self.assertFalse(template_heading_only_citation(rule, check,
                [{'line_refs':['L'], 'line_texts':{'L':text}}]))
        docs = [{'line_refs':['L'], 'line_texts':{'L':'상품 해약 안내'}}]
        self.assertFalse(template_heading_only_citation({**rule, 'source_sheet':'V2'},check,docs))
        self.assertFalse(template_heading_only_citation(rule,{**check,'finding_basis':'UNKNOWN'},docs))

    def test_unknown_applicability_is_not_a_confirmed_exclusion(self):
        result = {'item_id': 'SYN', 'verdict': 'NOT_APPLICABLE',
                  'reason': '제작 자료가 없어 의무 적용 여부를 판단할 수 없습니다.'}
        self.assertTrue(unresolved_applicability(result))
        self.assertTrue(source_claim_errors({}, result))
        result['reason'] = '해당 매체가 아니므로 적용 대상에서 제외합니다.'
        self.assertFalse(unresolved_applicability(result))
        result['verdict'] = 'UNDETERMINED'
        result['reason'] = '의무 적용 여부를 판단할 수 없습니다.'
        self.assertFalse(unresolved_applicability(result))

    def test_missing_support_does_not_establish_non_applicability(self):
        for reason in ['해당 방식으로 제작했다는 근거가 없으므로 기재 의무가 적용되지 않습니다.',
                       '유통 자료가 부족하므로 대상에서 제외합니다.']:
            self.assertTrue(unresolved_applicability({'verdict': 'NOT_APPLICABLE', 'reason': reason}))
        for reason in ['확인된 매체가 적용 매체와 다릅니다.',
                       '전체 원문에 조건을 유발하는 표현이 없으므로 해당하지 않습니다.']:
            self.assertFalse(unresolved_applicability({'verdict': 'NOT_APPLICABLE', 'reason': reason}))

    def test_negative_condition_needs_a_source_or_confirmed_metadata(self):
        result = {'verdict': 'NOT_APPLICABLE', 'reason': '조건에 해당하지 않습니다.',
                  'condition_checks': [{'condition_ref': 'A1', 'status': 'NOT_SATISFIED'}]}
        self.assertTrue(unresolved_applicability(result))
        for field, values in [('applicability_metadata_fields', ['media_type']),
                              ('applicability_evidence_line_refs', ['L-1'])]:
            self.assertFalse(unresolved_applicability({**result, field: values}))
    def test_parenthetical_positive_and_negative_scope_is_explicit_without_inventing_conditions(self):
        for phrase in ('외부 링크가 없는 광고', '신청 문구가 있는 광고'):
            rule = {'item_id': 'SYN', 'question': f'안내({phrase})의 고지 여부', 'criterion': '고지 확인'}
            contract = compile_condition_contract(rule)
            self.assertEqual(contract['applicability_conditions'][0]['text'], phrase)
        rule['question'] = '예시(기간 6개월)의 고지 여부'
        self.assertEqual(compile_condition_contract(rule)['applicability_conditions'], [])

    def test_explicit_quoted_mandatory_term_has_own_obligation_and_citation(self):
        rule = {'item_id': 'SYN', 'question': '처리 시점', 'criterion': '방법 설명 및 ‘다음날’ 기재 필수'}
        rule['condition_contract'] = compile_condition_contract(rule)
        checks = rule['condition_contract']['obligation_checks']
        self.assertEqual(checks[1]['text'], '‘다음날’ 기재 필수')
        payload = {'rules': [rule], 'documents': [{'evidence_id': 'E', 'line_refs': ['L'],
                    'line_texts': {'L': '처리 시점은 다음날입니다'}, 'text': '처리 시점은 다음날입니다'}]}
        result = {'item_id': 'SYN', 'requirement_checks': [{'obligation_ref': 'O2',
                  'status': 'SATISFIED', 'evidence_line_refs': ['L']}]}
        self.assertEqual(source_claim_errors(payload, result), [])
        payload['documents'][0]['line_texts']['L'] = '처리 방법 안내'
        self.assertTrue(source_claim_errors(payload, result))
        result['requirement_checks'][0]['status'] = 'UNDETERMINED'
        self.assertEqual(source_claim_errors(payload, result), [])

    def test_quoted_term_is_not_detached_from_a_source_exception(self):
        for criterion in ('수수료가 있으면 ‘부담액’ 기재 필수',
                          '조건에 해당하는 경우 ‘부담액’ 기재 필수',
                          '‘부담액’ 기재 필수, 단, 면제 상품 생략 가능'):
            contract = compile_condition_contract({'item_id': 'SYN', 'question': '비용', 'criterion': criterion})
            self.assertEqual(len(contract['obligation_checks']), 1)
            self.assertEqual(contract['obligation_checks'][0]['text'], criterion)

    def test_visual_reason_cannot_bypass_text_requirement_guard(self):
        payload = {'rules': [{'item_id': 'SYN', 'source_sheet': 'HWPX_TEMPLATE',
                    'template_basis': {'text_facet_only': True}}]}
        result = {'item_id': 'SYN', 'requirement_checks': [{'requirement': '내용 고지',
                  'status': 'VIOLATED', 'reason': '한 줄에 여러 문구가 배치되어 위반'}]}
        self.assertTrue(text_facet_claim_errors(payload, result))
        result['requirement_checks'][0]['reason'] = '의무 문구가 원문과 다름'
        self.assertEqual(text_facet_claim_errors(payload, result), [])

    def test_arithmetic_contradiction_is_rejected_without_deciding_the_correct_verdict(self):
        payload = {'rules': [{'item_id': 'SYN', 'criterion': '산식의 정합성 확인'}]}
        result = {'item_id': 'SYN', 'reason': '합산 결과가 표기와 일치합니다.',
                  'requirement_checks': [{'status': 'VIOLATED', 'reason': '계산 확인'}]}
        self.assertTrue(source_claim_errors(payload, result))
        result['reason'] = '합산 결과가 표기와 불일치합니다.'
        self.assertTrue(source_claim_errors(payload, result))  # Unsupported assertion is still not proof.
        result['requirement_checks'][0]['reason'] = '수정: COMPLIANT로 판정해야 합니다'
        self.assertTrue(source_claim_errors(payload, result))

    def test_arithmetic_witness_needs_real_mismatch_and_all_cited_values(self):
        self.assertTrue(has_arithmetic_mismatch_witness('검산: 2.5+1.5-0.5 != 4.0', '2.5 1.5 0.5 4.0'))
        self.assertFalse(has_arithmetic_mismatch_witness('검산: 2.5+1.5-0.5 != 3.5', '2.5 1.5 0.5 3.5'))
        self.assertFalse(has_arithmetic_mismatch_witness('검산: 2.5+1.5-0.5 != 4.0', '2.5 0.5 4.0'))
        self.assertFalse(has_arithmetic_mismatch_witness('값이 불분명하여 산식이 일치하지 않음', '2.5 1.5 0.5 4.0'))
        self.assertFalse(has_arithmetic_mismatch_witness('검산: 2.5*1.5 != 4.0', '2.5 1.5 4.0'))
