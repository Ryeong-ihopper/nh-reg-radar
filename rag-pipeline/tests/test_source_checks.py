import unittest

from rag.judgment.condition_contracts import compile_condition_contract
from rag.judgment.source_checks import (source_claim_errors, has_arithmetic_mismatch_witness,
                                       evidence_rows_for_rule, observed_grounding_errors,
                                       page_chrome_only_citation,
                                       unresolved_applicability,
                                       template_heading_only_citation)
from rag.judgment.manual_review import text_facet_claim_errors


class SourceChecksTests(unittest.TestCase):
    def test_presence_observation_must_quote_the_exact_cited_line(self):
        payload = {'rules': [{'item_id': 'SYN', 'category': 'PRESENCE',
                    'question': '표시되어 있는가?', 'criterion': '표시 확인'}],
                   'documents': [{'line_refs': ['L'], 'line_texts': {
                       'L': '신탁보수 연 0.2%'}}]}
        result = {'item_id': 'SYN', 'requirement_checks': [{
            'status': 'SATISFIED', 'finding_basis': 'OBSERVED',
            'evidence_line_refs': ['L'],
            'reason': '심의필 번호와 유효기간이 표시되어 있습니다.',
        }]}
        self.assertTrue(observed_grounding_errors(payload, result))
        result['requirement_checks'][0]['reason'] = "'신탁보수 연 0.2%'가 표시되어 있습니다."
        self.assertEqual(observed_grounding_errors(payload, result), [])

    def test_prohibition_observation_must_quote_the_exact_cited_line(self):
        payload = {'rules': [{'item_id': 'SYN', 'category': 'PROHIBIT',
                    'question': '금지 표현을 사용하지 않았는가?', 'criterion': '금지 표현 확인'}],
                   'documents': [{'line_refs': ['L'], 'line_texts': {
                       'L': '주민등록번호 공개여부: 비공개'}}]}
        result = {'item_id': 'SYN', 'requirement_checks': [{
            'status': 'VIOLATED', 'finding_basis': 'OBSERVED',
            'evidence_line_refs': ['L'],
            'reason': "광고의 '횟수제한없이' 문구가 금지 표현입니다.",
        }]}
        self.assertTrue(observed_grounding_errors(payload, result))
        result['requirement_checks'][0]['reason'] = "'주민등록번호 공개여부: 비공개' 문구를 확인했습니다."
        self.assertEqual(observed_grounding_errors(payload, result), [])

    def test_external_comparison_note_prevents_ad_text_only_violation(self):
        for note in ('실제 제약조건은 상품설명서 대조가 필요해 보조 판정',
                     '기간 대표성 판단에 원자료 확인이 필요해 보조 판정'):
            with self.subTest(note=note):
                payload = {'rules': [{'item_id': 'SYN', 'category': 'PROHIBIT',
                            'v2_note': note, 'criterion': '표현 확인'}],
                           'documents': [{'line_refs': ['L'], 'line_texts': {'L': '제한없이 이용'}}]}
                result = {'item_id': 'SYN', 'requirement_checks': [{
                    'status': 'VIOLATED', 'finding_basis': 'OBSERVED',
                    'evidence_line_refs': ['L'], 'reason': "'제한없이 이용'은 위반입니다.",
                }]}
                self.assertTrue(any('외부 자료 대조 없이' in error
                                    for error in observed_grounding_errors(payload, result)))

    def test_factual_cap_and_non_guarantee_are_not_assertive_markers(self):
        rule = {'item_id': 'SYN', 'category': 'PROHIBIT',
                'question': '불확실한 사항에 대해 단정적 판단을 제공하지 않았는가?',
                'criterion': "불확실한 사항을 확정적으로 단언하면 위반. '반드시'·'보장' 금지"}
        check = {'status': 'VIOLATED', 'finding_basis': 'OBSERVED',
                 'evidence_line_refs': ['L'], 'reason': ''}
        result = {'item_id': 'SYN', 'requirement_checks': [check]}
        for text in ('원금비보장상품', '최대 400만원 비과세'):
            with self.subTest(text=text):
                payload = {'rules': [rule], 'documents': [
                    {'line_refs': ['L'], 'line_texts': {'L': text}}]}
                check['reason'] = f"'{text}'가 단정 표현입니다."
                self.assertTrue(any('단정적 판단 위반을 확정할 수 없음' in error
                                    for error in observed_grounding_errors(payload, result)))
        payload['documents'][0]['line_texts']['L'] = '수익을 반드시 보장합니다'
        check['reason'] = "'수익을 반드시 보장합니다'라고 표시했습니다."
        self.assertEqual(observed_grounding_errors(payload, result), [])

    def test_shared_page_chrome_cannot_prove_unrelated_disclosure(self):
        check = {'status': 'SATISFIED', 'finding_basis': 'OBSERVED',
                 'evidence_ids': ['E'], 'evidence_line_refs': ['L']}
        for question, text in [
            ('광고 관련 절차 준수 사항을 표시하였는가?', '계열사/관련사이트'),
            ('금융상품의 명칭과 내용을 표시하였는가?', 'NHBank금융상품몰'),
            ('수수료 및 부대비용을 표시하였는가?', '전화상담'),
        ]:
            with self.subTest(question=question):
                docs = [{'evidence_id': 'E', 'line_refs': ['L'],
                         'line_texts': {'L': text}}]
                self.assertTrue(page_chrome_only_citation(
                    {'question': question}, check, docs))

    def test_structural_page_chrome_is_rejected_without_keyword_matching(self):
        check = {'status': 'SATISFIED', 'finding_basis': 'OBSERVED',
                 'evidence_ids': ['E'], 'evidence_line_refs': ['L']}
        docs = [{'evidence_id': 'E', 'source_role': 'PAGE_CHROME',
                 'line_refs': ['L'], 'line_texts': {'L': '빠른 업무 바로가기'}}]
        self.assertTrue(page_chrome_only_citation(
            {'question': '상품의 주요 거래조건을 표시하였는가?'}, check, docs))
        self.assertFalse(page_chrome_only_citation(
            {'question': '웹사이트 링크를 표시하였는가?'}, check, docs))

    def test_structural_page_chrome_is_filtered_before_body_rule_retrieval(self):
        rows = [
            {'doc_id': 'body', 'source_role': 'ADVERTISEMENT_CONTENT'},
            {'doc_id': 'chrome', 'source_role': 'PAGE_CHROME'},
        ]
        body_rule = {'question': '상품의 주요 거래조건을 표시하였는가?'}
        identity_rule = {'question': '금융회사의 명칭을 표시하였는가?'}
        self.assertEqual(
            [row['doc_id'] for row in evidence_rows_for_rule(body_rule, rows)],
            ['body'],
        )
        self.assertEqual(
            [row['doc_id'] for row in evidence_rows_for_rule(identity_rule, rows)],
            ['body', 'chrome'],
        )

    def test_page_chrome_may_prove_the_identity_fact_it_states(self):
        check = {'status': 'SATISFIED', 'finding_basis': 'OBSERVED',
                 'evidence_ids': ['E'], 'evidence_line_refs': ['L']}
        docs = [{'evidence_id': 'E', 'line_refs': ['L'],
                 'line_texts': {'L': 'NHBank금융상품몰'}}]
        rule = {'question': '금융상품을 판매하는 금융회사의 명칭을 표시하였는가?'}
        self.assertFalse(page_chrome_only_citation(rule, check, docs))

    def test_body_disclosure_is_not_classified_as_page_chrome(self):
        check = {'status': 'SATISFIED', 'finding_basis': 'OBSERVED',
                 'evidence_ids': ['E'], 'evidence_line_refs': ['L']}
        docs = [{'evidence_id': 'E', 'line_refs': ['L'], 'line_texts': {
            'L': '준법감시인심의번호 2026-4847(2026.09.01 ~2027.08.31.)'}}]
        rule = {'question': '심의주체와 심의필 번호 및 유효기간을 표시하였는가?'}
        self.assertFalse(page_chrome_only_citation(rule, check, docs))

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

    def test_example_defined_meaning_rejects_a_short_noun_fragment(self):
        rule = {'item_id': 'SYN', 'source_sheet': 'HWPX_TEMPLATE', 'title': '유의사항',
                'criterion': '예시문구와 유사한 문구 기재 시 적정',
                'example_text': '가입 전에 상품설명서 및 약관을 반드시 읽어보시기 바랍니다.'}
        check = {'obligation_ref': 'O1', 'status': 'SATISFIED',
                 'finding_basis': 'OBSERVED', 'evidence_line_refs': ['L']}
        short = [{'line_refs': ['L'], 'line_texts': {'L': '상품설명서'}}]
        substantive = [{'line_refs': ['L'], 'line_texts': {
            'L': '가입 전에 상품설명서 및 약관을 읽어보시기 바랍니다.'}}]
        self.assertTrue(template_heading_only_citation(rule, check, short))
        self.assertFalse(template_heading_only_citation(rule, check, substantive))

    def test_example_defined_meaning_rejects_a_long_but_unrelated_sentence(self):
        rule = {'item_id': 'SYN', 'source_sheet': 'HWPX_TEMPLATE', 'title': '지급제한',
                'criterion': '예시문구와 유사한 의미 기재시 적정',
                'example_text': '예금잔액증명서 발급 당일에는 입금·출금·이체 등 잔액 변동이 불가합니다.'}
        check = {'obligation_ref': 'O1', 'status': 'SATISFIED',
                 'finding_basis': 'OBSERVED', 'evidence_line_refs': ['L']}
        unrelated = [{'line_refs': ['L'], 'line_texts': {
            'L': '매년 넷째 토요일에 결산하여 다음 영업일에 이자를 지급합니다.'}}]
        related = [{'line_refs': ['L'], 'line_texts': {
            'L': '잔액증명서 발급 당일에는 계좌 잔액을 변경할 수 없습니다.'}}]
        self.assertTrue(template_heading_only_citation(rule, check, unrelated))
        self.assertFalse(template_heading_only_citation(rule, check, related))

    def test_example_defined_meaning_reads_canonical_interpretation_hint(self):
        rule = {'item_id': 'SYN', 'source_sheet': 'HWPX_TEMPLATE', 'title': '이자지급제한',
                'criterion': '예시문구와 유사한 의미 기재시 적정',
                'template_basis': {'canonical_plan': {'obligations': [{
                    'interpretation_hints': [{
                        'role': 'NON_BINDING_SOURCE_EXAMPLE',
                        'text': '예금잔액증명서 발급 당일에는 입금·출금·이체 등 잔액 변동이 불가합니다.',
                    }],
                }]}}}
        check = {'obligation_ref': 'O1', 'status': 'SATISFIED',
                 'finding_basis': 'OBSERVED', 'evidence_line_refs': ['L']}
        unrelated = [{'line_refs': ['L'], 'line_texts': {
            'L': '매년 지정된 날짜에 결산하여 다음 영업일에 이자를 지급합니다.'}}]
        self.assertTrue(template_heading_only_citation(rule, check, unrelated))

    def test_disclosure_absence_cannot_be_reported_as_observed(self):
        payload = {'rules': [{'item_id': 'SYN', 'criterion': '심의주체 명칭 표시'}],
                   'documents': [{'line_refs': ['L'], 'line_texts': {'L': '2026-1234'}}]}
        result = {'item_id': 'SYN', 'reason': '심의주체 명칭이 누락되었습니다.',
                  'requirement_checks': [{'obligation_ref': 'O1', 'status': 'VIOLATED',
                    'finding_basis': 'OBSERVED', 'evidence_line_refs': ['L'],
                    'reason': '심의주체 명칭이 확인되지 않습니다.'}]}
        self.assertTrue(source_claim_errors(payload, result))
        result['requirement_checks'][0]['finding_basis'] = 'ABSENCE'
        result['requirement_checks'][0]['evidence_line_refs'] = []
        self.assertEqual(source_claim_errors(payload, result), [])

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

    def test_same_line_notice_violation_requires_two_notices_on_one_cited_line(self):
        rule = {'item_id': 'SYN', 'guide': '한 줄에 2개 이상의 유의사항 문구 기재 불가능'}
        result = {'item_id': 'SYN', 'requirement_checks': [{
            'status': 'VIOLATED', 'finding_basis': 'OBSERVED',
            'evidence_line_refs': ['L1'], 'reason': '한 줄에 복수 문구가 있습니다.',
        }]}
        payload = {'rules': [rule], 'documents': [{
            'line_refs': ['L1', 'L2'], 'line_texts': {
                'L1': '※ 금융소비자는 설명을 받을 권리가 있습니다.',
                'L2': '※ 계약 전 상품설명서를 읽어보시기 바랍니다.',
            },
        }]}
        self.assertTrue(source_claim_errors(payload, result))
        result['requirement_checks'][0]['evidence_line_refs'] = ['L1', 'L2']
        self.assertTrue(source_claim_errors(payload, result))
        result['requirement_checks'][0]['evidence_line_refs'] = ['L3']
        payload['documents'][0]['line_refs'].append('L3')
        payload['documents'][0]['line_texts']['L3'] = (
            '※ 설명을 받을 권리가 있습니다. ※ 계약 전 약관을 읽어야 합니다.'
        )
        result['requirement_checks'][0]['reason'] = (
            "'설명을 받을 권리가 있습니다'와 '계약 전 약관을 읽어야 합니다'가 같은 줄에 있습니다."
        )
        self.assertEqual(source_claim_errors(payload, result), [])

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

    def test_disclosure_or_combined_duration_does_not_require_numeric_mismatch(self):
        for criterion in (
            '비용 면제 대상과 기간을 표시한다. 계약 유지기간 합산 한도 초과 부과는 금지한다.',
            '수수료 산식과 적용 요율을 명시한다.',
            '합산 대상과 계산 방법을 정확히 표시한다.',
        ):
            payload = {'rules': [{'item_id': 'SYN', 'criterion': criterion}]}
            for status in ('VIOLATED', 'MISSING'):
                result = {'item_id': 'SYN', 'requirement_checks': [
                    {'status': status, 'reason': '면제 요건에 대한 설명이 누락되었습니다.'}]}
                self.assertEqual(source_claim_errors(payload, result), [])

    def test_actual_numeric_consistency_still_requires_cited_witness(self):
        for criterion in ('산식의 정합성 확인', '우대금리 합계가 표시 수치와 일치해야 한다.',
                          '계산 예시의 정확성을 확인한다.'):
            payload = {'rules': [{'item_id': 'SYN', 'criterion': criterion}],
                       'documents': [{'line_refs': ['L'], 'line_texts': {'L': '2.5 1.5 0.5 4.0'}}]}
            result = {'item_id': 'SYN', 'requirement_checks': [{'status': 'VIOLATED',
                      'reason': '수치가 어긋납니다.', 'evidence_line_refs': ['L']}]}
            self.assertTrue(source_claim_errors(payload, result))
            result['requirement_checks'][0]['reason'] = '검산: 2.5+1.5-0.5 != 4.0'
            self.assertEqual(source_claim_errors(payload, result), [])

    def test_numeric_guard_uses_the_selected_obligation(self):
        payload = {'rules': [{'item_id': 'SYN', 'criterion': '합계의 정확성과 면제 고지',
            'condition_contract': {'obligation_checks': [
                {'obligation_id': 'O1', 'text': '합계의 정확성 확인'},
                {'obligation_id': 'O2', 'text': '합산 대상과 면제 요건을 고지한다.'}]}}]}
        result = {'item_id': 'SYN', 'requirement_checks': [
            {'obligation_ref': 'O2', 'status': 'MISSING', 'reason': '면제 요건 누락'}]}
        self.assertEqual(source_claim_errors(payload, result), [])
        result['requirement_checks'][0]['obligation_ref'] = 'O1'
        self.assertTrue(source_claim_errors(payload, result))
