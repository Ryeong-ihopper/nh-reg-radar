"""Actual source-bound contracts and numeric projection on synthetic inputs."""
import json
import unittest

import run_gemma_exhaustive_dgx as gemma
from rag.judgment.condition_contracts import compile_canonical_condition_contract
from rag.judgment.obligation_logic import aggregate_applicability, aggregate_obligations
from rag.judgment.operational_selection import confirmed_metadata_facts
from rag.judgment.policy import confirmed_template
from rag.judgment.review_program import computed_check
from rag.judgment.review_program import verified_calculated_values
from test_operational_canonical_catalog import load_catalog
from test_operational_rag_contracts import request_row


class ReviewedMethodologyProgramsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()
        cls.rules = {r['item_id']: r for r in cls.catalog.template_rules}

    def contract(self, pid):
        return compile_canonical_condition_contract(self.rules[pid])

    def wire(self, pid, text, statuses=None, facts=None, *,
             template_status='confirmed', template_value=None):
        contract = self.contract(pid)
        row = request_row([pid])
        payload = json.loads(row['messages'][1]['content'])
        payload['rules'][0]['condition_contract'] = contract
        payload.update(parser_coverage='READY', full_ad_text=text,
            review_context={'review_date': '2026-03-31'},
            reading_quality={'global_scan_incomplete': False},
            evidence_scope={pid: {'evidence_ids': ['E-1'], 'complete_ad_scan': True}},
            canonical_confirmed_facts={pid: [{'fact_id': 'A1', 'value': True, 'basis': 'template_id'}]})
        payload['documents'][0].update(asset_id='SYNTHETIC-ASSET', product_id='SYNTHETIC-PRODUCT',
            text=text, line_texts={'L-1': text}, text_selection={'needs_review': False})
        selected = self.rules[pid]['product_subtype'] if template_value is None else template_value
        payload['routing']['template_id'] = {'value': selected, 'status': template_status}
        if template_status != 'confirmed':
            # Runtime preserves an explicit unknown RULE-owned fact. Dropping
            # its row would erase the selection contract before expansion.
            payload['canonical_confirmed_facts'][pid] = confirmed_metadata_facts(
                self.catalog.plans[pid], product_groups=self.rules[pid].get('product_groups') or [],
                template_id=confirmed_template(payload['routing']), routing=payload['routing'])
        elif selected != self.rules[pid]['product_subtype']:
            payload['canonical_confirmed_facts'][pid] = [
                {'fact_id': 'A1', 'value': False, 'basis': 'template_id'}]
        row['messages'][1]['content'] = json.dumps(payload, ensure_ascii=False)
        messages, aliases = gemma._compact_model_request(row)
        checks = []
        for atom in contract['obligation_checks']:
            status = (statuses or {}).get(atom['obligation_id'], 'SATISFIED')
            checks.append({'obligation_ref': atom['obligation_id'], 'requirement': atom['text'],
                'status': status, 'finding_basis': 'ABSENCE' if status == 'MISSING' else 'OBSERVED',
                'evidence_refs': [] if status == 'MISSING' else ['L1'],
                'reason': '해당 안내가 없습니다.' if status == 'MISSING' else '원문 근거: "' + text[:100] + '".'})
        parsed = gemma._expand_model_response(row, {'results': [{
            'rule_ref': 'R1', 'scope_check': {'scope_ref': 'SCOPE', 'status': 'MATCHED'},
            'condition_checks': [{'condition_ref': f['condition_id'],
                'status': (facts or {}).get(f['condition_id'], 'SATISFIED'),
                'evidence_refs': [] if f['condition_id'] == 'A1' else ['L1']}
                for f in contract['applicability_conditions']],
            'review_condition_checks': [], 'requirement_checks': checks,
            'verdict': 'COMPLIANT', 'confidence': 'HIGH', 'reason': '모델의 전체 적정 주장'}]}, aliases)
        return row, messages, parsed

    def test_endpoint_calculation_overrides_model_with_actual_citation_and_trace(self):
        text = ('최저 연 3.3% ~ 최고 연 3.8%, 기준금리 2.1%, 가산금리 1.9%, '
                '우대금리 0.5%, 이차보전 0.2%, 2026.02.28 기준, 원리금균등상환, 2등급, 대출기간 3년')
        row, _, parsed = self.wire('MTH-LOAN-NAMED-R13', text)
        self.assertEqual([], gemma.validate(row, parsed))
        answer = parsed['results'][0]
        self.assertEqual('COMPLIANT', answer['verdict'])
        self.assertEqual(['L-1'], answer['evidence_line_refs'])
        self.assertEqual('3.8', answer['requirement_checks'][1]['calculation_trace']['calculated_endpoint'])
        row, _, parsed = self.wire('MTH-LOAN-NAMED-R13', text.replace('최고 연 3.8%', '최고 연 3.9%'))
        self.assertEqual([], gemma.validate(row, parsed))
        self.assertEqual('VIOLATION', parsed['results'][0]['verdict'])

    def test_invalid_or_stale_basis_date_is_not_a_presence_only_pass(self):
        text = ('최저 연 3.3% ~ 최고 연 3.8%, 기준금리 2.1%, 가산금리 1.9%, '
                '우대금리 0.5%, 이차보전 0.2%, 2026.02.27 기준, 원리금균등상환, 2등급, 대출기간 3년')
        row, _, parsed = self.wire('MTH-LOAN-NAMED-R13', text)
        self.assertEqual([], gemma.validate(row, parsed))
        self.assertEqual('VIOLATION', parsed['results'][0]['verdict'])

    def test_loan_amount_alternative_obeys_source_boundary_and_not_model_fact(self):
        for amount, expected in [('5천만원', 'COMPLIANT'), ('5,000만원', 'COMPLIANT'),
                                 ('50,000,001원', 'VIOLATION'),
                                 ('임차보증금의 80% 이내', 'VIOLATION')]:
            with self.subTest(amount=amount):
                row, _, parsed = self.wire('MTH-LOAN-NAMED-R17', '대출한도: ' + amount, {'O1': 'MISSING'})
                self.assertEqual([], gemma.validate(row, parsed))
                self.assertEqual(expected, parsed['results'][0]['verdict'])

    def test_explicit_source_term_survives_both_wire_projections(self):
        row, messages, parsed = self.wire('MTH-LOAN-NAMED-R11', '이자는 매달 이용 후 납부합니다.')
        self.assertEqual(['후취'], self.contract('MTH-LOAN-NAMED-R11')['obligation_checks'][1]['required_terms'])
        self.assertIn('required_terms', messages[1]['content'])
        self.assertTrue(any('source explicitly requires' in error for error in gemma.validate(row, parsed)))
        row, _, parsed = self.wire('MTH-LOAN-NAMED-R11', '이자는 매달 후취 납부합니다.')
        self.assertEqual([], gemma.validate(row, parsed))

    def retirement_numeric_cases(self):
        # Fictional values exercise disclosure roles, not current legal accuracy.
        return (
            ('MTH-RETIREMENT-R08', 'O3', '16.5',
             'IRP 계약기간 만료 전 중도해지하거나 계약기간 종료 후 연금 이외의 형태로 수령하는 경우, '
             '세액공제 받은 납입원금 및 수익에 대해 기타소득세 14.2%가 부과될 수 있습니다.', '14.2%'),
            ('MTH-RETIREMENT-R09', 'O2', '1억원',
             '이 DC·IRP 퇴직연금은 예금자보호법에 따라 예금보호 대상 금융상품으로 운용되는 적립금에 '
             '한하여 1인당 8천만원까지, 운용 금융상품 판매회사별 보호상품 합산 기준으로 보호됩니다.', '8천만원'),
        )

    def test_retirement_numeric_roles_allow_compliance_without_fixed_example_values(self):
        for pid, numeric_id, _, _, _ in self.retirement_numeric_cases():
            contract = self.contract(pid)
            facts = [{'condition_ref': f['condition_id'], 'status': 'SATISFIED'}
                     for f in contract['applicability_conditions']]
            checks = [{'obligation_ref': o['obligation_id'], 'status': 'SATISFIED'}
                      for o in contract['obligation_checks']]
            self.assertEqual('APPLICABLE', aggregate_applicability(contract, 'MATCHED', facts))
            self.assertEqual('COMPLIANT', aggregate_obligations(contract, checks, facts))
            numeric = next(o for o in contract['obligation_checks'] if o['obligation_id'] == numeric_id)
            next(c for c in checks if c['obligation_ref'] == numeric_id)['status'] = 'MISSING'
            self.assertEqual('VIOLATION', aggregate_obligations(contract, checks, facts))
            self.assertIn('수치', numeric['text'])

    def test_retirement_nonexample_numbers_survive_source_and_compact_without_literal_equality(self):
        for pid, numeric_id, example, text, _ in self.retirement_numeric_cases():
            with self.subTest(pid=pid):
                plan = self.catalog.plans[pid]
                self.assertIn(example, plan['source']['source_fields']['example'])
                self.assertIs(False, plan['atomization']['example_values_are_exact_requirements'])
                numeric = next(o for o in self.contract(pid)['obligation_checks']
                               if o['obligation_id'] == numeric_id)
                self.assertNotIn(example, numeric['text'])
                self.assertNotIn(example, json.dumps(numeric.get('required_terms') or [], ensure_ascii=False))
                authored = next(o for o in plan['obligations'] if o['obligation_id'] == numeric_id)
                self.assertTrue(authored.get('retrieval_queries'))
                self.assertTrue(all(example not in query for query in authored['retrieval_queries']))
                row, messages, parsed = self.wire(pid, text)
                compact = json.loads(messages[1]['content'])
                self.assertIn(numeric['text'], json.dumps(compact, ensure_ascii=False))
                self.assertEqual([], gemma.validate(row, parsed))
                answer = parsed['results'][0]
                check = next(c for c in answer['requirement_checks'] if c['obligation_ref'] == numeric_id)
                self.assertEqual('SATISFIED', check['status'])
                self.assertEqual('COMPLIANT', answer['verdict'])

    def test_retirement_missing_numeric_role_is_still_missing_and_a_violation(self):
        for pid, numeric_id, _, text, value in self.retirement_numeric_cases():
            with self.subTest(pid=pid):
                row, _, parsed = self.wire(pid, text.replace(value, ''), {numeric_id: 'MISSING'})
                self.assertEqual([], gemma.validate(row, parsed))
                answer = parsed['results'][0]
                check = next(c for c in answer['requirement_checks'] if c['obligation_ref'] == numeric_id)
                self.assertEqual('MISSING', check['status'])
                self.assertEqual('ABSENCE', check['finding_basis'])
                self.assertEqual('VIOLATION', answer['verdict'])

    def test_retirement_other_required_information_and_product_scope_guards_remain(self):
        for pid, numeric_id, _, text, _ in self.retirement_numeric_cases():
            contract = self.contract(pid)
            facts = [{'condition_ref': f['condition_id'], 'status': 'SATISFIED'}
                     for f in contract['applicability_conditions']]
            checks = [{'obligation_ref': o['obligation_id'], 'status': 'SATISFIED'}
                      for o in contract['obligation_checks']]
            nonnumeric = next(c for c in checks if c['obligation_ref'] != numeric_id)
            nonnumeric['status'] = 'MISSING'
            self.assertEqual('VIOLATION', aggregate_obligations(contract, checks, facts))
            self.assertEqual('UNDETERMINED', aggregate_applicability(contract, 'UNKNOWN', facts))
            self.assertEqual('NOT_APPLICABLE', aggregate_applicability(contract, 'NOT_MATCHED', facts))
            if any(f['condition_ref'] == 'A1' for f in facts):
                next(f for f in facts if f['condition_ref'] == 'A1')['status'] = 'UNDETERMINED'
                self.assertEqual('UNDETERMINED', aggregate_applicability(contract, 'MATCHED', facts))
                next(f for f in facts if f['condition_ref'] == 'A1')['status'] = 'NOT_SATISFIED'
                self.assertEqual('NOT_APPLICABLE', aggregate_applicability(contract, 'MATCHED', facts))
            row, _, unknown = self.wire(pid, text, template_status='unknown')
            payload = json.loads(row['messages'][1]['content'])
            selected_fact = next(f for f in payload['canonical_confirmed_facts'][pid]
                                 if f['fact_id'] == 'A1')
            self.assertIsNone(selected_fact['value'])
            self.assertEqual('UNDETERMINED', unknown['results'][0]['verdict'])
            self.assertEqual([], gemma.validate(row, unknown))
            _, _, mismatch = self.wire(pid, text, template_value='SYNTHETIC-OTHER-PRODUCT-TEMPLATE')
            self.assertEqual('NOT_APPLICABLE', mismatch['results'][0]['verdict'])

    def test_deposit_postmaturity_and_termination_date_roles_are_not_interchangeable(self):
        for pid, required, excluded in [('TPL-MAP-083', '신규일', '만기일'),
                                         ('TPL-MAP-105', '신규일', '만기일'),
                                         ('TPL-MAP-084', '만기일', '신규일'),
                                         ('TPL-MAP-106', '만기일', '신규일')]:
            atom = self.contract(pid)['obligation_checks'][0]
            self.assertIn(required, atom['text'])
            self.assertNotIn(excluded, atom['text'])

    def test_verified_calculator_cannot_waive_an_incorrect_displayed_basis_date(self):
        for pid in ('TPL-MAP-082', 'TPL-MAP-104'):
            contract = self.contract(pid)
            facts = [{'condition_ref': f['condition_id'], 'status': 'SATISFIED'}
                     for f in contract['applicability_conditions']]
            checks = [{'obligation_ref': 'O1', 'status': 'SATISFIED'},
                      {'obligation_ref': 'O2', 'status': 'VIOLATED'}]
            self.assertEqual('VIOLATION', aggregate_obligations(contract, checks, facts))
            # A verified calculator may waive the notice date only if it is absent.
            next(f for f in facts if f['condition_ref'] == 'B2')['status'] = 'NOT_SATISFIED'
            checks[1]['status'] = 'MISSING'
            self.assertEqual('COMPLIANT', aggregate_obligations(contract, checks, facts))

    def test_unimplemented_numeric_adapter_cannot_accept_a_model_calculation(self):
        self.assertEqual('UNDETERMINED', computed_check({'kind': 'UNSUPPORTED_SYNTHETIC_COMPARISON'},
            {'status': 'SATISFIED'}, {}, 'SYNTHETIC')['status'])

    def test_derived_rate_value_requires_a_recomputed_source_bound_trace(self):
        text = ('최저 연 3.3% ~ 최고 연 3.9%, 기준금리 2.1%, 가산금리 1.9%, '
                '우대금리 0.5%, 이차보전 0.2%, 2026.02.28 기준, 원리금균등상환, 2등급, 대출기간 3년')
        row, _, parsed = self.wire('MTH-LOAN-NAMED-R13', text)
        answer = parsed['results'][0]
        answer['reason'] = '계산한 최고금리 3.8%가 표시된 최고금리 3.9%와 다릅니다.'
        self.assertEqual([], gemma.validate(row, parsed))
        payload = json.loads(row['messages'][1]['content'])
        checks = answer['requirement_checks']
        checks[1]['calculation_trace']['calculated_endpoint'] = '9.9'
        self.assertNotIn('9.9', verified_calculated_values(self.contract('MTH-LOAN-NAMED-R13'),
                                                         checks, payload, 'MTH-LOAN-NAMED-R13'))
        answer['reason'] = '임의의 최고금리 9.9%가 표시된 최고금리 3.9%와 다릅니다.'
        self.assertTrue(any('없는 수치' in e for e in gemma.validate(row, parsed)))
