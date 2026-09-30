"""Source-program regressions using synthetic observations, never answer keys."""
import copy
import json
import unittest
from pathlib import Path

import run_gemma_exhaustive_dgx as gemma
from revise_review_programs import revise, revise_migration, revise_worklist
from rag.judgment.condition_contracts import compile_canonical_condition_contract
from rag.judgment.manual_review import partition_visual_review_candidates
from rag.judgment.obligation_logic import aggregate_applicability, aggregate_obligations
from rag.judgment.review_program import computed_check, digest, execution_digest
from rag.judgment.unsupported_observations import quarantine_unsupported_observations
from rag.retrieval.evidence_bundle import retrieve_program_nodes
from test_operational_canonical_catalog import load_catalog
from test_operational_rag_contracts import request_row


class ReviewProgramTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = {r['item_id']: r for r in load_catalog().template_rules}

    def contract(self, item):
        return compile_canonical_condition_contract(self.rules[item])

    def verdict(self, item, statuses, facts=None):
        contract = self.contract(item)
        checks = [{'obligation_ref': o['obligation_id'], 'status': statuses.get(o['obligation_id'], 'UNDETERMINED')}
                  for o in contract['obligation_checks']]
        conditions = [{'condition_ref': f['condition_id'], 'status': (facts or {}).get(f['condition_id'], 'SATISFIED')}
                      for f in contract['applicability_conditions']]
        self.assertEqual('APPLICABLE', aggregate_applicability(contract, 'MATCHED', conditions))
        return aggregate_obligations(contract, checks, conditions)

    def test_rate_methods_are_alternatives_not_three_mandatory_methods(self):
        for item in ('MTH-DEPOSIT-DEMAND-R07', 'TPL-MAP-078', 'TPL-MAP-100'):
            for method in ({'O1': 'SATISFIED'}, {'O2': 'SATISFIED', 'O4': 'SATISFIED', 'O8': 'SATISFIED'},
                           {'O3': 'SATISFIED', 'O8': 'SATISFIED'}):
                statuses = {f'O{i}': 'MISSING' for i in range(1, 9)}
                statuses.update(O5='SATISFIED', O6='SATISFIED', O7='SATISFIED', **method)
                with self.subTest(item=item, method=method):
                    self.assertEqual('COMPLIANT', self.verdict(item, statuses))
                    statuses['O7'] = 'VIOLATED'
                    self.assertEqual('VIOLATION', self.verdict(item, statuses))
        self.assertEqual('UNDETERMINED', self.verdict('MTH-DEPOSIT-DEMAND-R07', {'O2': 'SATISFIED'}))

    def test_protection_media_is_decision_branch_not_whole_rule_gate(self):
        item = 'MTH-DEPOSIT-DEMAND-R15'
        self.assertEqual('REQUIRED', self.rules[item]['template_required'])
        for media in ('SATISFIED', 'NOT_SATISFIED', 'UNDETERMINED'):
            self.assertEqual('VIOLATION', self.verdict(item, {'O1': 'MISSING'}, {'B1': media, 'B2': 'UNDETERMINED'}))
        self.assertEqual('COMPLIANT', self.verdict(item, {'O1': 'SATISFIED'}, {'B1': 'SATISFIED', 'B2': 'NOT_SATISFIED'}))
        for media, link in [('NOT_SATISFIED', 'NOT_SATISFIED'), ('SATISFIED', 'SATISFIED'), ('UNDETERMINED', 'NOT_SATISFIED')]:
            self.assertEqual('UNDETERMINED', self.verdict(item, {'O1': 'SATISFIED'}, {'B1': media, 'B2': link}))

    def test_review_only_has_no_artificial_duties_and_stays_visible(self):
        item = 'MTH-LOAN-NAMED-R22'
        contract = self.contract(item)
        self.assertEqual([], contract['obligation_checks'])
        self.assertEqual('REVIEW_ONLY', self.rules[item]['template_required'])
        self.assertTrue(self.rules[item]['template_basis']['manual_review_required'])
        self.assertEqual('UNDETERMINED', self.verdict(item, {}))
        auto, manual = partition_visual_review_candidates([item], self.rules)
        self.assertEqual([], auto)
        self.assertEqual('REVIEW_ONLY', manual[0]['facet'])
        self.assertTrue(manual[0]['reason'])

    def test_isa_approved_revision_has_one_presence_check_without_rate_duty(self):
        for item in ('TPL-MAP-202', 'TPL-MAP-213', 'TPL-MAP-224'):
            contract = self.contract(item)
            self.assertEqual(['PRESENCE'], contract['review_program']['kinds'])
            self.assertEqual(1, len(contract['obligation_checks']))
            self.assertEqual('COMPLIANT', self.verdict(item, {'O1': 'SATISFIED'}))
            self.assertEqual('VIOLATION', self.verdict(item, {'O1': 'MISSING'}))
            self.assertEqual('UNDETERMINED', self.verdict(item, {}))

    def test_review_requested_absence_cannot_become_violation(self):
        self.assertEqual('UNDETERMINED', self.verdict('MTH-DEPOSIT-DEMAND-R04', {'O1': 'MISSING'}))
        self.assertEqual('COMPLIANT', self.verdict('MTH-DEPOSIT-DEMAND-R04', {'O1': 'SATISFIED'}))

    def test_real_contract_reaches_compact_model_and_code_verdict(self):
        item = 'MTH-DEPOSIT-DEMAND-R15'
        row = request_row([item])
        payload = json.loads(row['messages'][1]['content'])
        contract = self.contract(item)
        payload['rules'][0]['condition_contract'] = contract
        payload['canonical_confirmed_facts'] = {item: [
            {'fact_id': 'A1', 'value': True, 'basis': 'template_id'},
            {'fact_id': 'B1', 'value': False, 'basis': 'media_type'}]}
        row['messages'][1]['content'] = json.dumps(payload)
        _, aliases = gemma._compact_model_request(row)
        output = gemma._expand_model_response(row, {'results': [{
            'rule_ref': 'R1', 'scope_check': {'scope_ref': contract['scope_ref'], 'status': 'MATCHED'},
            'condition_checks': [{'condition_ref': f['condition_id'], 'status': 'SATISFIED', 'evidence_refs': ['L1']}
                                 for f in contract['applicability_conditions']],
            'review_condition_checks': [],
            'requirement_checks': [{'obligation_ref': o['obligation_id'], 'requirement': o['text'],
                'status': 'SATISFIED', 'finding_basis': 'OBSERVED', 'evidence_refs': ['L1'], 'reason': '테스트 근거'}
                for o in contract['obligation_checks']],
            'verdict': 'COMPLIANT', 'reason': '테스트 근거', 'confidence': 'HIGH'}]}, aliases)
        result = output['results'][0]
        self.assertEqual('APPLICABLE', result['applicability'])
        self.assertEqual('UNDETERMINED', result['verdict'])
        self.assertEqual('UNDETERMINED', result['requirement_checks'][1]['status'])
        self.assertEqual(contract['review_program']['program_sha256'], result['review_program_trace']['program_sha256'])


class BrokerReviewedMeaningsTests(unittest.TestCase):
    def expand(self, pid, text, statuses):
        rule = next(r for r in load_catalog().template_rules if r['item_id'] == pid)
        contract = compile_canonical_condition_contract(rule)
        row = request_row([pid])
        payload = json.loads(row['messages'][1]['content'])
        payload['rules'][0]['condition_contract'] = contract
        payload.update(parser_coverage='READY', full_ad_text=text,
            evidence_scope={pid: {'evidence_ids': ['E-1'], 'complete_ad_scan': True}},
            canonical_confirmed_facts={pid: [{'fact_id': 'A1', 'value': True, 'basis': 'template_id'}]})
        payload['documents'][0].update(text=text, line_texts={'L-1': text},
            text_selection={'needs_review': False})
        payload['routing']['template_id'] = {'value': rule['product_subtype'], 'status': 'confirmed'}
        row['messages'][1]['content'] = json.dumps(payload, ensure_ascii=False)
        messages, aliases = gemma._compact_model_request(row)
        output = gemma._expand_model_response(row, {'results': [{
            'rule_ref': 'R1', 'scope_check': {'scope_ref': 'SCOPE', 'status': 'MATCHED'},
            'condition_checks': [{'condition_ref': 'A1', 'status': 'SATISFIED', 'evidence_refs': []}],
            'review_condition_checks': [], 'verdict': 'COMPLIANT', 'confidence': 'HIGH',
            'reason': '모델이 주장한 전체 적정',
            'requirement_checks': [{'obligation_ref': a['obligation_id'], 'requirement': a['text'],
                'status': status, 'finding_basis': 'OBSERVED' if status == 'SATISFIED' else 'ABSENCE',
                'evidence_refs': ['L1'] if status == 'SATISFIED' else [],
                'reason': f"'{text}'가 확인됩니다." if status == 'SATISFIED' else '해당 안내가 없습니다.'}
                for a, status in zip(contract['obligation_checks'], statuses)]}]}, aliases)
        self.assertEqual([], gemma.validate(row, output))
        return contract, messages, output['results'][0]

    def test_bank_assessment_cannot_replace_missing_counselor_authority_notice(self):
        _, _, result = self.expand('TPL-MAP-049', '은행이 대출 실행 여부를 직접 심사하고 결정합니다.',
                                  ['MISSING', 'SATISFIED', 'SATISFIED'])
        self.assertEqual('VIOLATION', result['verdict'])
        self.assertEqual('VIOLATION', result['review_program_trace']['verdict'])
        self.assertEqual(['L-1'], result['evidence_line_refs'])

    def test_equivalent_no_fee_meaning_can_support_both_disclosures(self):
        contract, _, result = self.expand('TPL-MAP-048', '상담사에게 별도로 낼 수수료는 없습니다.',
                                         ['SATISFIED', 'SATISFIED'])
        self.assertEqual('COMPLIANT', result['verdict'])
        self.assertEqual([], contract['decision_fact_ids'])
        self.assertFalse(any(a['owners']['human'] or a['owners']['external_input']
                             for a in contract['obligation_checks']))

    def test_customer_information_relation_reaches_wire_with_primary_source(self):
        _, messages, result = self.expand('TPL-MAP-055', '고객이 제공한 정보는 대출 취급은행에서 관리합니다.',
                                         ['SATISFIED'])
        self.assertEqual('COMPLIANT', result['verdict'])
        self.assertIn('관리 주체', messages[1]['content'])
        plan = load_catalog().plans['TPL-MAP-055']
        self.assertEqual('Contents/section0.xml#table4/row17', plan['source']['source_provenance']['locator'])
        self.assertEqual('필수(O)', plan['source']['source_fields']['satisfied'])
        self.assertEqual('', plan['source']['source_fields']['violated'])


class BrokerSourceProgramsTests(unittest.TestCase):
    """Exercise authored broker meanings with supplied synthetic observations.

    These observations test the wire, owners and joins. They do not claim that
    a deterministic validator or a model has inferred the Korean meanings.
    """

    PRIMARY_SHA = '292ddb87daf596a55d47d69b3bb6519c546dee9f5b4bbd9d90d4459220d98f3f'
    BASE_SHA = {
        'TPL-MAP-039': 'c7ed68f676a6cbba10108241743a7546f388abcc3bbb6a6946059aa735fe27fc',
        'TPL-MAP-040': 'fd60b5045a48b8bc52e289e1026f3a4a25185409efd388fb21fc965d3b34f3ba',
        'TPL-MAP-041': '89b5ce5bd44560e06721f8f4487a86dfb197fc1379773b1bffc4a2238419acb3',
        'TPL-MAP-042': 'cf4ab031686f8c832faad7e1a6013c6ee3f8813c216e72a64d8fdc5e0cdbc716',
        'TPL-MAP-043': 'f74ed2d96479b3d17028e86b02533974772109fa4a2ccfd7bf991e473bdd1d14',
        'TPL-MAP-044': 'f635b1ca71fb92b56c4bfdd3bfc26881ebc39873327f385560a45d3e52e0a686',
        'TPL-MAP-045': 'ff253fe5a3de138a11f053159b976eff98498dc6b7d4fe52d887058ca0014f8d',
        'TPL-MAP-046': 'f6768b464cddaa42cd9bb478213b73b5dd98c7e5f7bd4721ad46ea3ca28928c0',
        'TPL-MAP-047': '8d70f4bf1f786a8ceb36417e77d8bd15c300fd919e732e4c34c3e31d802ac5a0',
        'TPL-MAP-050': '652829e335a93822218c6ad14f9981536e05d4e359a24baae06bb838cde54f33',
        'TPL-MAP-051': '10ca44864b3be513e0f56e2efc882f86173811ac2fcc81edae107767f09a038d',
        'TPL-MAP-052': '90829ac5142d7592e7064c6f526f642889391bef4e7a9ab351dc57cfec771e8e',
        'TPL-MAP-053': '164916054fc56f9663f39d1ecf94b67f59e705a678456126c08634ff0c6402eb',
        'TPL-MAP-054': '2a29a8c6cece607798a4af7962efaab0cf311325af9575b98f4af7a5a70b57d7',
        'TPL-MAP-056': 'd9af221db3290b888cbf6d07bdc2b4c30a396686a9d4d66b09139643804234a4',
        'TPL-MAP-057': '9f07970e916002aa13c0983686d883b56fc4d4588e5cf6f1baff06e0b8805562',
    }
    HOLDS = {
        'TPL-MAP-051': 'SOURCE_TERM_SEONIP_INTERPRETATION_UNRESOLVED',
    }
    # Each string belongs to the corresponding semantic O, not to a rendered
    # warning unit. The existing human line-layout O has no model-owned input.
    TEXTS = {
        'TPL-MAP-039': ('대출을 취급하는 금융회사: 농협은행',),
        'TPL-MAP-040': ('은행 신용심사 결과에 따라 대출 이용이 제한될 수 있습니다.',
                        '신청인의 소득과 부채 등 사정에 따라 대출 한도가 달라질 수 있습니다.'),
        'TPL-MAP-041': ('시장 환경과 신용평가 결과에 따라 대출 조건이 변경될 수 있습니다.',),
        'TPL-MAP-042': ('상환할 능력보다 많이 빌리면 개인 신용점수가 낮아질 수 있습니다.',
                        '신용점수 하락으로 금융거래에 불이익이 생길 수 있습니다.'),
        'TPL-MAP-043': ('원금과 이자를 계속 연체하면 만기 전에 모든 원리금을 갚아야 할 수 있습니다.',),
        'TPL-MAP-044': ('이자 납부를 늦추면 연체이율을 적용합니다.',
                        '연체이율은 적용 대출금리에 연 2%p의 가산금리를 더합니다.',
                        '최고 연체이율은 연 12%입니다.'),
        'TPL-MAP-045': ('금융소비자는 금융상품에 대해 충분한 설명을 받을 권리가 있습니다.',),
        'TPL-MAP-046': ('가입 전에 상품설명서를 읽어 보십시오.', '가입 전에 약관을 읽어 보십시오.'),
        'TPL-MAP-047': ('이 광고의 이미지는 생성형 AI를 활용해 편집했습니다.',),
        'TPL-MAP-048': ('대출상담사는 고객에게 별도 수수료를 요구할 수 없습니다.',
                        '대출상담사는 고객에게 별도 수수료를 받을 수 없습니다.'),
        'TPL-MAP-049': ('상담사는 대출 계약을 맺을 권한이 없습니다.',
                        '대출 취급은행이 직접 대출 심사를 합니다.',
                        '대출 실행 여부는 취급은행이 결정합니다.'),
        'TPL-MAP-050': ('대출모집법인: 예시모집 주식회사', '예시모집 주식회사 법인 등록번호: 법인-가123',
                        '이 광고의 상담사는 예시모집 주식회사에 소속되어 있습니다.',
                        '예시모집 주식회사는 농협은행만을 대리·중개하는 대출모집위탁계약을 맺었습니다.',
                        '이 광고의 상담사는 은행연합회에 등록된 대출상담사입니다.'),
        'TPL-MAP-051': ('상담사가 대리·중개 중 고객에게 손해를 주면 취급은행이 배상할 책임을 집니다.',
                        '다만 은행이 상담사 선입과 업무 감독에 적절히 주의하고 손해 방지를 위해 노력한 경우는 예외입니다.'),
        'TPL-MAP-052': ('대출상담사 민원은 취급은행의 상담민원 창구에서 상담합니다.',
                        '대출상담사 민원상담 창구 연락처: 00-1111-2222'),
        'TPL-MAP-053': ('상담사 신원은 은행연합회 등록조회로 확인할 수 있습니다.',
                        '은행연합회 웹주소 registry.example에서 대출상담사 등록조회 메뉴를 이용하십시오.',
                        '상담사 등록번호와 성명을 함께 입력하여 조회하십시오.'),
        'TPL-MAP-054': ('대출모집인에게 지급하는 수수료율을 확인할 수 있습니다.',
                        '취급은행 웹주소 bank.example의 공시 메뉴에서 대출모집인 수수료율을 확인하십시오.'),
        'TPL-MAP-055': ('고객이 제공한 신용정보와 개인정보는 대출 취급은행이 관리합니다.',),
        'TPL-MAP-056': ('대출상담사 성명: 예시상담', '예시상담 대출상담사 전화: 010-0000-0000',
                        '예시상담 대출상담사의 은행연합회 등록번호: 개인-나456'),
        'TPL-MAP-057': ('준법감시인이 심의한 광고입니다.', '준법감시인 심의번호: 심의-다789',
                        '심의-다789의 유효기간: 2026.10.01.부터 2027.03.31.까지'),
    }

    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()
        cls.rules = {r['item_id']: r for r in cls.catalog.template_rules}
        folder = Path(__file__).resolve().parents[1] / 'config'
        cls.policies = {p['plan_id']: p for p in json.loads(
            (folder / 'review-program-policies-v1.json').read_text(encoding='utf-8'))['plans']}

    def contract(self, item):
        return compile_canonical_condition_contract(self.rules[item])

    def observations(self, item):
        return {f'O{i}': text for i, text in enumerate(self.TEXTS[item], 1)}

    def wire(self, item, *, observations=None, statuses=None, facts=None, metadata_facts=None):
        contract = self.contract(item)
        observations = self.observations(item) if observations is None else observations
        # MISSING fixtures contain none of the omitted text. A readable unrelated
        # line keeps complete-scan evidence available for a fully empty notice.
        text = '\n'.join(observations.values()) or '대출 상담 안내'
        lines = {f'L-{ref}': value for ref, value in observations.items()} or {'L-OTHER': text}
        row = request_row([item])
        payload = json.loads(row['messages'][1]['content'])
        payload['rules'][0]['condition_contract'] = contract
        payload.update(parser_coverage='READY', full_ad_text=text,
            reading_quality={'global_scan_incomplete': False},
            evidence_scope={item: {'evidence_ids': ['E-1'], 'complete_ad_scan': True}},
            canonical_confirmed_facts={item: [
                {'fact_id': 'A1', 'value': True, 'basis': 'template_id'}, *(metadata_facts or [])]},
            documents=[{'evidence_id': 'E-1', 'line_refs': list(lines), 'line_texts': lines,
                        'text': text, 'span_status': 'line_level_selected_text',
                        'text_selection': {'needs_review': False}}])
        payload['routing']['template_id'] = {'value': self.rules[item]['product_subtype'], 'status': 'confirmed'}
        row['messages'][1]['content'] = json.dumps(payload, ensure_ascii=False)
        messages, aliases = gemma._compact_model_request(row)
        reverse_lines = {ref: alias for alias, ref in aliases['ref_to_line'].items()}
        checks = []
        for atom in contract['obligation_checks']:
            ref = atom['obligation_id']
            status = (statuses or {}).get(ref, 'SATISFIED')
            quote = observations.get(ref)
            refs = [reverse_lines[f'L-{ref}']] if quote and status in {'SATISFIED', 'VIOLATED'} else []
            checks.append({'obligation_ref': ref, 'requirement': atom['text'], 'status': status,
                'finding_basis': ('OBSERVED' if status in {'SATISFIED', 'VIOLATED'} else
                                  'ABSENCE' if status == 'MISSING' else 'UNKNOWN'),
                'evidence_refs': refs,
                'reason': (f"'{quote}'를 관찰했습니다." if refs else
                           '완전한 광고에서 해당 안내가 없습니다.' if status == 'MISSING' else
                           '이 의미나 담당 입력은 확인할 수 없습니다.')})
        output = gemma._expand_model_response(row, {'results': [{
            'rule_ref': 'R1', 'scope_check': {'scope_ref': 'SCOPE', 'status': 'MATCHED'},
            'condition_checks': [{'condition_ref': f['condition_id'],
                'status': (facts or {}).get(f['condition_id'],
                    'SATISFIED' if f['condition_id'] == 'A1' else 'UNDETERMINED'),
                'evidence_refs': []} for f in contract['applicability_conditions']],
            'review_condition_checks': [], 'requirement_checks': checks,
            'verdict': 'COMPLIANT', 'reason': f"'{next(iter(lines.values()))}'를 관찰했습니다.",
            'confidence': 'HIGH'}]}, aliases)
        self.assertEqual([], gemma.validate(row, output))
        result = output['results'][0]
        self.assertEqual(result['verdict'], result['review_program_trace']['verdict'])
        self.assertEqual(contract['obligation_logic'], result['review_program_trace']['decision'])
        return json.loads(messages[1]['content']), result

    def test_all_nineteen_primary_rows_preserve_source_mandatory_marks_and_bindings(self):
        for index, item in enumerate(self.TEXTS, 1):
            with self.subTest(item=item):
                plan = self.catalog.plans[item]
                source = plan['source']
                self.assertEqual(self.PRIMARY_SHA, source['source_provenance']['sha256'])
                self.assertEqual(f'Contents/section0.xml#table4/row{index}',
                                 source['source_provenance']['locator'])
                self.assertEqual(digest(source), plan['source_sha256'])
                self.assertEqual('필수(△)' if item == 'TPL-MAP-047' else '필수(O)',
                                 source['source_fields']['satisfied'])
                self.assertEqual('CONDITIONAL' if item == 'TPL-MAP-047' else 'REQUIRED',
                                 self.rules[item]['template_required'])
                compact, _ = self.wire(item)
                self.assertEqual(self.contract(item), compact['rules'][0]['condition_contract'])
                if item in self.BASE_SHA:
                    policy = self.policies[item]
                    # The original policy binding is historical; execution
                    # references identify the current revised source instead.
                    self.assertEqual(self.BASE_SHA[item], policy['base_source_sha256'])
                    for key, value in policy['source_revision'].items():
                        self.assertEqual(value, source[key])
                    self.assertEqual(plan['source_sha256'], plan['review_program']['source_sha256'])
                    self.assertIn({'plan_id': item, 'source_sha256': plan['source_sha256']},
                                  plan['review_program']['source_refs'])
        # The HWPX word is preserved rather than the older mapping example.
        example = self.catalog.plans['TPL-MAP-050']['source']['source_fields']['example']
        self.assertIn('대출모집위탁계약', example)
        self.assertNotIn('대출업무위탁계약', example)

    def test_equivalent_source_meanings_reach_all_atoms_without_exact_example_matching(self):
        for item, texts in self.TEXTS.items():
            with self.subTest(item=item):
                contract = self.contract(item)
                semantic = [a for a in contract['obligation_checks'] if a['owners']['llm']]
                self.assertEqual(len(texts), len(semantic))
                for atom in semantic:
                    self.assertEqual({'rule': False, 'llm': True, 'external_input': False, 'human': False},
                                     atom['owners'])
                    self.assertNotIn('deterministic_adapter', atom)
                    self.assertTrue(atom['evidence']['advertisement_direct_quote_required'])
                    for hint in atom['interpretation_hints']:
                        self.assertFalse(hint['exact_match_required'])
                        self.assertFalse(hint['may_be_cited_as_advertisement_evidence'])
                compact, result = self.wire(item)
                expected = ('UNDETERMINED' if item in self.HOLDS or item == 'TPL-MAP-047'
                            or any(a['owners']['human'] for a in contract['obligation_checks']) else 'COMPLIANT')
                self.assertEqual(expected, result['verdict'])
                if item != 'TPL-MAP-047':
                    self.assertEqual('APPLICABLE', result['applicability'])
                    self.assertEqual([a['obligation_id'] for a in contract['obligation_checks']],
                                     [c['obligation_ref'] for c in result['requirement_checks']])
                self.assertEqual(contract['review_program']['program_sha256'],
                                 compact['rules'][0]['condition_contract']['review_program']['program_sha256'])

    def test_known_partial_omission_fails_each_mandatory_conjunct_even_with_human_or_source_hold(self):
        for item in self.TEXTS:
            if item == 'TPL-MAP-047':
                continue  # Its actual-use applicability input is separately unresolved.
            for ref in self.observations(item):
                with self.subTest(item=item, omitted=ref):
                    text = self.observations(item)
                    text.pop(ref)
                    _, result = self.wire(item, observations=text, statuses={ref: 'MISSING'})
                    self.assertEqual('VIOLATION', result['verdict'])
                    observed = next(c for c in result['requirement_checks'] if c['obligation_ref'] == ref)
                    self.assertEqual('MISSING', observed['status'])
                    self.assertEqual('ABSENCE', observed['finding_basis'])
                    self.assertEqual([], observed['evidence_line_refs'])

    def test_ambiguous_partial_meaning_stays_unknown_after_complete_readable_scan(self):
        for item in self.TEXTS:
            for ref in self.observations(item):
                with self.subTest(item=item, ambiguous=ref):
                    _, result = self.wire(item, statuses={ref: 'UNDETERMINED'})
                    self.assertEqual('UNDETERMINED', result['verdict'])
                    if item != 'TPL-MAP-047':
                        check = next(c for c in result['requirement_checks'] if c['obligation_ref'] == ref)
                        self.assertEqual('UNDETERMINED', check['status'])
                        self.assertEqual('UNKNOWN', check['finding_basis'])

    def test_source_warning_line_atom_remains_human_and_cannot_be_model_confirmed_or_failed(self):
        for number in range(40, 47):
            item = f'TPL-MAP-{number:03}'
            contract = self.contract(item)
            human = [a for a in contract['obligation_checks'] if a['owners']['human']]
            self.assertEqual(1, len(human))
            ref = human[0]['obligation_id']
            self.assertFalse(human[0]['owners']['llm'])
            self.assertIn('실제 줄 경계', human[0]['text'])
            self.assertIn('서로 다른 유의사항', human[0]['text'])
            self.assertIn('문장 수나 bbox', human[0]['text'])
            auto, manual = partition_visual_review_candidates([item], self.rules)
            self.assertEqual([item], auto)
            self.assertEqual([], manual)  # Semantic checks remain reachable.
            for claim in ('SATISFIED', 'MISSING', 'VIOLATED'):
                with self.subTest(item=item, model_claim=claim):
                    _, result = self.wire(item, statuses={ref: claim})
                    check = next(c for c in result['requirement_checks'] if c['obligation_ref'] == ref)
                    self.assertEqual(('UNDETERMINED', 'UNKNOWN', []),
                                     (check['status'], check['finding_basis'], check['evidence_line_refs']))
                    self.assertEqual('UNDETERMINED', result['verdict'])

    def test_interpretation_holds_stay_in_the_source_formula_without_invented_human_atoms(self):
        for item, hold in self.HOLDS.items():
            with self.subTest(item=item):
                contract = self.contract(item)
                self.assertIn({'unknown': hold}, contract['obligation_logic']['all'])
                self.assertFalse(any(a['owners']['human'] or a['owners']['external_input']
                                     for a in contract['obligation_checks']))
                compact, result = self.wire(item)
                self.assertIn({'unknown': hold}, compact['rules'][0]['condition_contract']['obligation_logic']['all'])
                self.assertTrue(all(c['status'] == 'SATISFIED' for c in result['requirement_checks']))
                self.assertEqual('UNDETERMINED', result['verdict'])
                self.assertTrue(result['needs_researcher_review'])
        self.assertIn('선입', self.catalog.plans['TPL-MAP-051']['source']['source_fields']['example'])

    def test_counselor_identity_and_masked_contact_reach_semantic_only_and_join(self):
        item = 'TPL-MAP-056'
        contract = self.contract(item)
        self.assertIn('0000 형태로 심의요청',
                      self.catalog.plans[item]['source']['source_fields']['violated'])
        self.assertEqual(['SEMANTIC'], contract['review_program']['kinds'])
        self.assertEqual({'all': [{'ref': 'O1'}, {'ref': 'O2'}, {'ref': 'O3'}]},
                         contract['obligation_logic'])
        self.assertNotIn('source_scope_issue', contract['review_program'])
        # Masked contact is sufficient; it is not a new requirement that every
        # displayed contact use one specific masking pattern or a real number.
        for phone in ('010-0000-0000', '00-0000-0000', '010-1234-5678'):
            with self.subTest(phone=phone):
                observations = self.observations(item)
                observations['O2'] = f'예시상담 대출상담사 전화: {phone}'
                compact, result = self.wire(item, observations=observations)
                projected = compact['rules'][0]['condition_contract']
                self.assertEqual(contract, projected)
                atoms = {a['obligation_id']: a for a in projected['obligation_checks']}
                self.assertIn('성명', atoms['O1']['text'])
                self.assertIn('마스킹 번호도 연락처 표기로 인정', atoms['O2']['text'])
                self.assertIn('상담사에 연결', atoms['O2']['text'])
                self.assertIn('실제 전화번호·전화 연결', atoms['O2']['text'])
                self.assertIn('완전일치를 요구하지 않는다', atoms['O2']['text'])
                self.assertIn('은행연합회 등록번호', atoms['O3']['text'])
                self.assertIn('상담사에 연결', atoms['O3']['text'])
                self.assertEqual('APPLICABLE', result['applicability'])
                self.assertEqual('COMPLIANT', result['verdict'])
                self.assertEqual(['O1', 'O2', 'O3'],
                                 [c['obligation_ref'] for c in result['requirement_checks']])
                self.assertTrue(all(c['status'] == 'SATISFIED' and c['finding_basis'] == 'OBSERVED'
                                    and c['evidence_line_refs'] for c in result['requirement_checks']))
                self.assertIn(observations['O2'], result['requirement_checks'][1]['reason'])

    def test_ai_actual_use_is_external_and_not_inferred_from_missing_disclosure(self):
        item = 'TPL-MAP-047'
        contract = self.contract(item)
        fact = next(f for f in contract['applicability_conditions'] if f['condition_id'] == 'A2')
        self.assertEqual(('EXTERNAL', 'CONFIRMED_EXTERNAL_FACT', 'UNDETERMINED'),
                         (fact['owner'], fact['input_type'], fact['unknown_policy']))
        self.assertNotIn('absence_policy', fact)
        self.assertEqual({'all': [{'fact': 'A1'}, {'fact': 'A2'}]}, contract['applicability_logic'])
        for ad_text in ({}, self.observations(item)):
            for claim in ('SATISFIED', 'NOT_SATISFIED', 'UNDETERMINED'):
                with self.subTest(disclosure=bool(ad_text), model_claim=claim):
                    compact, result = self.wire(item, observations=ad_text,
                        statuses={'O1': 'SATISFIED' if ad_text else 'MISSING'}, facts={'A2': claim})
                    self.assertEqual('UNDETERMINED', result['condition_checks'][1]['status'])
                    self.assertEqual(('UNDETERMINED', 'UNDETERMINED'),
                                     (result['applicability'], result['verdict']))
                    self.assertNotIn('A2', {f['fact_id'] for f in compact['canonical_confirmed_facts']['R1']})
                    self.assertNotIn('applicability_absence_closures', result)
        # An arbitrary fact-map entry is not a verified production-history route.
        for value in (False, True):
            _, result = self.wire(item, metadata_facts=[
                {'fact_id': 'A2', 'value': value, 'basis': 'template_id'}])
            self.assertEqual('UNDETERMINED', result['condition_checks'][1]['status'])

    def test_ai_confirmed_false_true_and_unknown_conditions_have_distinct_code_branches(self):
        # This verifies the authored formula only. The advertisement wire above
        # cannot supply the still-pending verified external input route.
        contract = self.contract('TPL-MAP-047')
        for status, expected in [('NOT_SATISFIED', 'NOT_APPLICABLE'),
                                 ('SATISFIED', 'APPLICABLE'), ('UNDETERMINED', 'UNDETERMINED')]:
            conditions = [{'condition_ref': 'A1', 'status': 'SATISFIED'},
                          {'condition_ref': 'A2', 'status': status}]
            with self.subTest(verified_external_status=status):
                self.assertEqual(expected, aggregate_applicability(contract, 'MATCHED', conditions))
        conditions = [{'condition_ref': 'A1', 'status': 'SATISFIED'},
                      {'condition_ref': 'A2', 'status': 'SATISFIED'}]
        for status, expected in [('SATISFIED', 'COMPLIANT'), ('MISSING', 'VIOLATION'),
                                 ('UNDETERMINED', 'UNDETERMINED')]:
            with self.subTest(disclosure_status=status):
                self.assertEqual(expected, aggregate_obligations(contract,
                    [{'obligation_ref': 'O1', 'status': status}], conditions))

    def test_corporate_registration_counselor_registration_and_exclusivity_are_not_interchangeable(self):
        item = 'TPL-MAP-050'
        predicates = {a['obligation_id']: a['text'] for a in self.contract(item)['obligation_checks']}
        self.assertIn('법인', predicates['O2'])
        self.assertIn('상담사', predicates['O5'])
        self.assertIn('NH농협은행만', predicates['O4'])
        cases = [
            ('O4', '예시모집 주식회사는 농협은행과 다른 은행을 함께 대리·중개합니다.', 'VIOLATED', 'VIOLATION'),
            ('O4', '예시모집 주식회사는 농협은행과 거래하고 있습니다.', 'UNDETERMINED', 'UNDETERMINED'),
            ('O2', '은행연합회 등록번호 개인-나456은 예시상담 상담사의 번호입니다.', 'MISSING', 'VIOLATION'),
            ('O5', '예시모집 주식회사 법인 등록번호는 법인-가123입니다.', 'MISSING', 'VIOLATION'),
            ('O3', '예시상담 상담사의 소속은 농협은행입니다.', 'VIOLATED', 'VIOLATION'),
        ]
        for ref, replacement, status, expected in cases:
            with self.subTest(atom=ref, text=replacement):
                observations = self.observations(item)
                observations[ref] = replacement
                _, result = self.wire(item, observations=observations, statuses={ref: status})
                self.assertEqual(expected, result['verdict'])

    def test_partial_contact_lookup_path_and_review_period_meanings_do_not_complete_the_notice(self):
        cases = [
            ('TPL-MAP-052', 'O2', '개인 대출상담사 전화: 010-0000-0000', 'UNDETERMINED'),
            ('TPL-MAP-053', 'O3', '상담사 등록번호만 입력하여 조회하십시오.', 'MISSING'),
            ('TPL-MAP-054', 'O2', '취급은행 홈페이지 주소는 bank.example입니다.', 'UNDETERMINED'),
            ('TPL-MAP-057', 'O3', '상담사 등록기간: 2026.10.01.부터 2027.03.31.까지', 'UNDETERMINED'),
        ]
        for item, ref, text, status in cases:
            with self.subTest(item=item, atom=ref):
                observations = self.observations(item)
                observations[ref] = text
                _, result = self.wire(item, observations=observations, statuses={ref: status})
                self.assertEqual('VIOLATION' if status == 'MISSING' else 'UNDETERMINED', result['verdict'])


class ReviewedPolicyRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = Path(__file__).resolve().parents[1] / 'config'
        cls.document = json.loads((folder / 'canonical-execution-plans-v2.json').read_text(encoding='utf-8'))
        cls.policies = json.loads((folder / 'review-program-policies-v1.json').read_text(encoding='utf-8'))

    def test_reapplying_current_policies_preserves_source_and_execution(self):
        document, policies = revise(self.document, self.policies)
        self.assertEqual(self.document, document)
        self.assertEqual(self.policies, policies)

    def test_source_correction_rebinds_the_program_without_changing_identity(self):
        updated = copy.deepcopy(self.policies)
        policy = next(p for p in updated['plans'] if p['plan_id'] == 'TPL-MAP-049')
        original = next(p for p in self.document['plans'] if p['plan_id'] == policy['plan_id'])
        fields = copy.deepcopy(original['source']['source_fields'])
        fields['example'] = '합성 원문: 상담사에게 계약 체결 권한이 없습니다.'
        policy['source_revision'] = {'source_fields': fields, 'source_provenance': {
            'filename': 'synthetic-source.hwpx', 'sha256': 'b' * 64, 'locator': 'synthetic table row'}}
        document, policies = revise(self.document, self.policies, updated)
        changed = next(p for p in document['plans'] if p['plan_id'] == original['plan_id'])
        self.assertEqual(original['source']['product_template'], changed['source']['product_template'])
        self.assertEqual(fields, changed['source']['source_fields'])
        self.assertNotEqual(original['source_sha256'], changed['source_sha256'])
        self.assertEqual(digest(changed['source']), changed['source_sha256'])
        self.assertEqual(execution_digest(changed), changed['review_program']['execution_sha256'])
        self.assertEqual(digest({'policy': policy, 'source': changed['source_sha256']}), changed['review_program']['program_sha256'])
        self.assertEqual(digest(policies), document['review_program_source_binding']['policies_sha256'])
        self.assertEqual([p for p in self.document['plans'] if p['plan_id'] != original['plan_id']],
                         [p for p in document['plans'] if p['plan_id'] != original['plan_id']])

    def test_stale_current_execution_cannot_be_repaired_by_a_replacement_policy(self):
        document = copy.deepcopy(self.document)
        document['plans'][0]['obligations'][0]['text'] += ' unreviewed change'
        with self.assertRaisesRegex(ValueError, 'current source/program hash'):
            revise(document, self.policies, copy.deepcopy(self.policies))

    def test_unbound_missing_duplicate_and_extra_policy_rows_are_rejected(self):
        for change in ('missing', 'duplicate', 'extra'):
            updated = copy.deepcopy(self.policies)
            if change == 'missing':
                updated['plans'].pop()
            else:
                row = copy.deepcopy(updated['plans'][0])
                if change == 'extra':
                    row['plan_id'] = 'SYNTHETIC-UNSUPPORTED'
                updated['plans'].append(row)
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'preserve the canonical template set'):
                revise(self.document, self.policies, updated)

    def test_source_revision_cannot_change_product_scope_or_original_binding(self):
        for change in ('scope', 'binding'):
            updated = copy.deepcopy(self.policies)
            policy = updated['plans'][0]
            if change == 'scope':
                policy['source_revision'] = {'product_template': 'synthetic different product'}
            else:
                policy['base_source_sha256'] = 'c' * 64
            with self.subTest(change=change), self.assertRaises(ValueError):
                revise(self.document, self.policies, updated)

    def test_migration_rebinds_only_the_corrected_source_and_preserves_aliases(self):
        folder = Path(__file__).resolve().parents[1] / 'config'
        migration = json.loads((folder / 'operational-catalog-migration-v1.json').read_text(encoding='utf-8'))
        revised = copy.deepcopy(self.document)
        next(p for p in revised['plans'] if p['plan_id'] == 'TPL-MAP-049')['source_sha256'] = 'b' * 64
        result = revise_migration(self.document, migration, revised)
        expected = copy.deepcopy(migration)
        next(row for row in expected['rows'] if row['plan_id'] == 'TPL-MAP-049')['source_sha256'] = 'b' * 64
        self.assertEqual(expected, result)
        self.assertNotEqual(result, migration)

    def test_stale_or_duplicate_migration_cannot_be_silently_repaired(self):
        folder = Path(__file__).resolve().parents[1] / 'config'
        migration = json.loads((folder / 'operational-catalog-migration-v1.json').read_text(encoding='utf-8'))
        for change in ('stale', 'duplicate'):
            candidate = copy.deepcopy(migration)
            if change == 'stale':
                candidate['rows'][0]['source_sha256'] = 'c' * 64
            else:
                candidate['rows'].append(copy.deepcopy(candidate['rows'][0]))
            with self.subTest(change=change), self.assertRaises(ValueError):
                revise_migration(self.document, candidate, self.document)

    def test_source_revision_updates_the_worklist_without_promoting_candidates(self):
        folder = Path(__file__).resolve().parents[1] / 'config'
        worklist = json.loads((folder / 'review-worklist-v1.json').read_text(encoding='utf-8'))
        revised = copy.deepcopy(self.document)
        revised['source_binding_sha256'] = 'b' * 64
        plan = next(p for p in revised['plans'] if p['plan_id'] == 'TPL-MAP-049')
        plan['source']['source_fields']['example'] = '합성 정정 원문'
        plan['source_sha256'] = digest(plan['source'])
        result = revise_worklist(self.document, worklist, revised)
        self.assertEqual(revised['source_binding_sha256'], result['canonical_source_binding_sha256'])
        row = next(row for row in result['rows'] if row['id'] == plan['plan_id'])
        self.assertEqual(plan['source'], row['source'])
        self.assertEqual(worklist['counts'], result['counts'])
        self.assertEqual(worklist['source_audit_sha256'], result['source_audit_sha256'])
        self.assertFalse(result['operationally_connected'])
        self.assertEqual([row for row in worklist['rows'] if row['kind'] != 'TEMPLATE'],
                         [row for row in result['rows'] if row['kind'] != 'TEMPLATE'])

    def test_stale_or_incomplete_worklist_is_not_silently_rebound(self):
        folder = Path(__file__).resolve().parents[1] / 'config'
        worklist = json.loads((folder / 'review-worklist-v1.json').read_text(encoding='utf-8'))
        for change in ('stale', 'missing', 'duplicate', 'promoted'):
            candidate = copy.deepcopy(worklist)
            if change == 'stale':
                candidate['canonical_source_binding_sha256'] = 'c' * 64
            elif change == 'missing':
                candidate['rows'].pop(0)
            elif change == 'duplicate':
                candidate['rows'].append(copy.deepcopy(candidate['rows'][0]))
            else:
                candidate['operationally_connected'] = True
            with self.subTest(change=change), self.assertRaises(ValueError):
                revise_worklist(self.document, candidate, self.document)

    def test_primary_source_correction_reaches_the_model_without_becoming_exact_match(self):
        from run_operational_e2e import model_rule_view
        catalog = load_catalog()
        rule = next(r for r in catalog.template_rules if r['item_id'] == 'TPL-MAP-049')
        plan = catalog.plans[rule['item_id']]
        provenance = plan['source']['source_provenance']
        self.assertEqual('Contents/section0.xml#table4/row11', provenance['locator'])
        self.assertEqual('292ddb87daf596a55d47d69b3bb6519c546dee9f5b4bbd9d90d4459220d98f3f', provenance['sha256'])
        contract = compile_canonical_condition_contract(rule)
        projected = model_rule_view({**rule, 'condition_contract': contract})
        row = {'requested_item_ids': [rule['item_id']], 'messages': [
            {'role': 'system', 'content': 'test'},
            {'role': 'user', 'content': json.dumps({'rules': [projected], 'documents': [], 'evidence_scope': {}})}]}
        messages, _ = gemma._compact_model_request(row)
        wire = messages[1]['content']
        self.assertIn('권한이없으며', wire)
        self.assertNotIn('권한이었으며', wire)
        self.assertEqual({'satisfied': '필수(O)'}, contract['source_criteria'])
        for atom in plan['obligations']:
            for hint in atom['interpretation_hints']:
                self.assertFalse(hint['exact_match_required'])
                self.assertFalse(hint['may_be_cited_as_advertisement_evidence'])


class ComputedObservationTests(unittest.TestCase):
    def payload(self, text, reviewed='2026-03-31'):
        return {'review_context': {'review_date': reviewed}, 'parser_coverage': 'READY',
                'evidence_scope': {'SYNTHETIC': {'evidence_ids': ['E1'], 'complete_ad_scan': True}},
                'documents': [{'evidence_id': 'E1', 'line_refs': ['L1'], 'line_texts': {'L1': text}}]}

    def check(self, adapter, payload):
        return computed_check(adapter, {'evidence_line_refs': ['L1']}, payload, 'SYNTHETIC')['status']

    def test_calendar_month_is_not_thirty_days_and_future_date_fails(self):
        month = {'kind': 'BASIS_DATE_WITHIN', 'unit': 'CALENDAR_MONTH', 'amount': 1}
        days = {'kind': 'BASIS_DATE_WITHIN', 'unit': 'DAYS', 'amount': 30}
        payload = self.payload('기준일 2026.02.28')
        self.assertEqual('SATISFIED', self.check(month, payload))
        self.assertEqual('VIOLATED', self.check(days, payload))
        self.assertEqual('VIOLATED', self.check(month, self.payload('기준일 2026.04.01')))
        self.assertEqual('UNDETERMINED', self.check(month, self.payload('기준일 2026.02.30')))
        self.assertEqual('UNDETERMINED', self.check(month, self.payload('기준일 2026.03.20 및 2026.03.21')))
        outside = copy.deepcopy(payload)
        outside['evidence_scope']['SYNTHETIC']['evidence_ids'] = ['OTHER']
        self.assertEqual('UNDETERMINED', self.check(month, outside))

    def test_sum_requires_complete_explicit_components_and_common_units(self):
        adapter = {'kind': 'BONUS_SUM_BOUND'}
        text = '우대조건 총 2개, 최대 우대금리 연 0.3%p, 우대조건 1: 연 0.1%p, 우대조건 2: 연 0.2%p'
        self.assertEqual('SATISFIED', self.check(adapter, self.payload(text)))
        self.assertEqual('VIOLATED', self.check(adapter, self.payload(text.replace('0.3%p', '0.4%p'))))
        for incomplete in (text.replace('총 2개', '총 3개'), text + ' 중복 불가', text.replace('연 0.2', '월 0.2')):
            self.assertEqual('UNDETERMINED', self.check(adapter, self.payload(incomplete)))
        payload = self.payload(text)
        payload['evidence_scope']['SYNTHETIC']['complete_ad_scan'] = False
        self.assertEqual('UNDETERMINED', self.check(adapter, payload))

    def test_rate_dates_keep_original_line_identity_and_require_pairing(self):
        adapter = {'kind': 'BASIS_DATE_WITHIN', 'unit': 'CALENDAR_MONTH', 'amount': 1}
        payload = self.payload('기본금리 연 1%(2026.03.20. 기준)')
        doc = payload['documents'][0]
        doc['line_refs'].append('L2')
        doc['line_texts']['L2'] = '우대금리 연 2%(2026.03.20. 기준)'
        check = {'evidence_line_refs': ['L1', 'L2']}
        original = copy.deepcopy(payload)
        result = computed_check(adapter, check, payload, 'SYNTHETIC')
        self.assertEqual('SATISFIED', result['status'])
        self.assertEqual(['L1', 'L2'], result['evidence_line_refs'])
        self.assertEqual(2, result['reason'].count('기준일 근거:'))
        self.assertEqual(original, payload)
        doc['line_texts']['L2'] = '우대금리 연 2%(2026.01.20. 기준)'
        result = computed_check(adapter, check, payload, 'SYNTHETIC')
        self.assertEqual('VIOLATED', result['status'])
        self.assertIn('기간을 충족합니다.', result['reason'])
        self.assertIn('기간을 벗어납니다.', result['reason'])
        doc['line_texts']['L2'] = '(2026.03.20. 기준)'
        result = computed_check(adapter, check, payload, 'SYNTHETIC')
        self.assertEqual('UNDETERMINED', result['status'])
        self.assertEqual(['L1', 'L2'], result['evidence_line_refs'])
        # Overlapping retrieval chunks with identical source lines are harmless.
        payload['documents'].append(copy.deepcopy(doc))
        self.assertEqual(result, computed_check(adapter, check, payload, 'SYNTHETIC'))

    def test_conflicting_text_for_same_date_line_is_not_silently_selected(self):
        adapter = {'kind': 'BASIS_DATE_WITHIN', 'unit': 'CALENDAR_MONTH', 'amount': 1}
        payload = self.payload('기본금리 연 1%(2026.03.20. 기준)')
        other = copy.deepcopy(payload['documents'][0])
        other['line_texts']['L1'] = '우대금리 연 2%(2026.03.20. 기준)'
        payload['documents'].append(other)
        self.assertEqual('UNDETERMINED', self.check(adapter, payload))

    def test_two_rate_roles_do_not_share_one_unbound_date(self):
        adapter = {'kind': 'BASIS_DATE_WITHIN', 'unit': 'CALENDAR_MONTH', 'amount': 1}
        payload = self.payload('기본금리 연 1%(2026.03.20. 기준), 우대금리 연 2%')
        self.assertEqual('UNDETERMINED', self.check(adapter, payload))


class NodeRetrievalTests(unittest.TestCase):
    def test_authored_query_reaches_lexical_search_without_dense_or_other_product_evidence(self):
        rule = {'condition_contract': {'review_program': {'evidence_policy': {'mode': 'LEXICAL'}},
            'obligation_checks': [{'obligation_id': 'O1', 'text': '대출계약 체결의 권한 부재 안내',
                                   'retrieval_queries': ['상담사 계약 불가']}]}}
        rows = [{'doc_id': 'TRIGGER', 'ad_id': 'SYNTHETIC', 'product_id': 'P', 'text_canonical': 'trigger'},
                {'doc_id': 'BODY', 'ad_id': 'SYNTHETIC', 'product_id': 'P', 'text_canonical': '상담사는 계약을 맺을 수 없습니다.'},
                {'doc_id': 'OTHER', 'ad_id': 'SYNTHETIC', 'product_id': 'OTHER', 'text_canonical': '상담사 계약 불가'}]
        selected, audit = retrieve_program_nodes(['TRIGGER'], rows, rule, {}, {}, char_budget=100)
        self.assertEqual(['TRIGGER', 'BODY'], selected)
        self.assertEqual(['BODY'], audit['nodes'][0]['evidence_ids'])
        self.assertIn('상담사 계약 불가', audit['nodes'][0]['queries'])
        self.assertFalse(audit['semantic_dependencies_complete'])

    def test_each_authored_node_retrieves_its_own_evidence_without_displacing_trigger(self):
        rule = {'condition_contract': {'review_program': {'schema_version': 'review-program-v1'},
            'obligation_checks': [{'obligation_id': 'O1', 'text': 'first'}, {'obligation_id': 'O2', 'text': 'second'}]}}
        rows = [{'doc_id': k, 'ad_id': 'SYNTHETIC', 'product_id': 'P', 'text_canonical': text}
                for k, text in [('D0', 'trigger'), ('D1', 'first'), ('D2', 'second')]]
        query = {'first': [1, 0], 'second': [0, 1]}
        vectors = {'D0': [0, 0], 'D1': [1, 0], 'D2': [0, 1]}
        selected, audit = retrieve_program_nodes(['D0'], rows, rule, query, vectors, char_budget=50)
        self.assertEqual(['D0', 'D1', 'D2'], selected)
        self.assertEqual([['D1'], ['D2']], [n['evidence_ids'] for n in audit['nodes']])
        self.assertFalse(audit['semantic_dependencies_complete'])
        selected, audit = retrieve_program_nodes(['D0'], rows, rule, query, vectors, char_budget=0)
        self.assertEqual(['D0'], selected)
        self.assertTrue(all(n['status'] == 'BUDGET_DEFERRED' for n in audit['nodes']))
        rows[2]['product_id'] = 'OTHER'
        selected, audit = retrieve_program_nodes(['D0'], rows, rule, query, vectors, char_budget=50)
        self.assertNotIn('D2', selected)
        self.assertEqual('NO_CANDIDATES', audit['nodes'][1]['status'])


class GuardedProgramTests(unittest.TestCase):
    def test_grounding_guard_recomputes_alternatives_and_updates_trace(self):
        request = request_row(['SYNTHETIC'])
        payload = json.loads(request['messages'][1]['content'])
        contract = {'review_program': {'program_sha256': 'synthetic-program', 'source_sha256': 'synthetic-source',
                                      'kinds': ['ALTERNATIVE'], 'allowed_outcomes': ['COMPLIANT', 'VIOLATION', 'UNDETERMINED']},
                    'obligation_checks': [{'obligation_id': 'O1'}, {'obligation_id': 'O2'}],
                    'obligation_logic': {'any': [{'ref': 'O1'}, {'ref': 'O2'}]}}
        payload['rules'][0]['condition_contract'] = contract
        request['messages'][1]['content'] = json.dumps(payload)
        for second, expected in [('SATISFIED', 'COMPLIANT'), ('VIOLATED', 'UNDETERMINED')]:
            value = {'item_id': 'SYNTHETIC', 'applicability': 'APPLICABLE', 'verdict': 'COMPLIANT',
                'review_program_trace': {'verdict': 'COMPLIANT'}, 'requirement_checks': [
                    {'obligation_ref': 'O1', 'status': 'SATISFIED', 'finding_basis': 'OBSERVED', 'evidence_ids': [], 'evidence_line_refs': []},
                    {'obligation_ref': 'O2', 'status': second, 'finding_basis': 'OBSERVED', 'evidence_ids': ['E-1'], 'evidence_line_refs': ['L-1'], 'reason': 'synthetic quote'}]}
            response = {'parsed': {'results': [value]}, 'validation_errors': ['SYNTHETIC: OBSERVED에는 직접 광고 근거가 필요']}
            guarded = quarantine_unsupported_observations(request, response, lambda *args: [])['parsed']['results'][0]
            self.assertEqual(expected, guarded['verdict'])
            self.assertEqual(expected, guarded['review_program_trace']['verdict'])
            self.assertEqual('grounding_guard', guarded['review_program_trace']['stage'])
            self.assertEqual('UNDETERMINED', guarded['review_program_trace']['checks'][0]['status'])
            self.assertEqual([{'verdict': 'COMPLIANT'}], guarded['review_program_history'])


class DepositReviewedBranchesTests(unittest.TestCase):
    """Source-derived deposit branches with synthetic facts, never product answers."""

    R10 = 'MTH-DEPOSIT-DEMAND-R10'
    R11 = 'MTH-DEPOSIT-DEMAND-R11'
    SOURCE_HASHES = {
        R10: 'f24294164fa82b7689c9cff36272294d8a037b94fbfc010c4c9b96eddcc7a9af',
        R11: '89fbbdcd1b0e7d4278e4d8264e0ed5f35d58bd7fea75ffa3d954a5d143d205b9',
    }
    SUM_TEXT = ('우대조건 총 2개, 최대 우대금리 연 0.3%p, '
                '우대조건 1: 연 0.1%p, 우대조건 2: 연 0.2%p')
    RATE_TEXT = '기본금리 연 1.0%(2026.09.28. 기준, 세전)'

    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()
        cls.rules = {r['item_id']: r for r in cls.catalog.template_rules}

    def contract(self, item):
        return compile_canonical_condition_contract(self.rules[item])

    def verdict(self, item, statuses, facts):
        contract = self.contract(item)
        checks = [{'obligation_ref': o['obligation_id'],
                   'status': statuses.get(o['obligation_id'], 'UNDETERMINED')}
                  for o in contract['obligation_checks']]
        conditions = [{'condition_ref': f['condition_id'],
                       'status': facts.get(f['condition_id'],
                                           'SATISFIED' if f['condition_id'] == 'A1' else 'UNDETERMINED')}
                      for f in contract['applicability_conditions']]
        self.assertEqual('APPLICABLE', aggregate_applicability(contract, 'MATCHED', conditions))
        return aggregate_obligations(contract, checks, conditions)

    def wire(self, item, text, statuses, facts, *, payload_overrides=None):
        contract = self.contract(item)
        row = request_row([item])
        payload = json.loads(row['messages'][1]['content'])
        payload['rules'][0]['condition_contract'] = contract
        payload.update(
            review_context={'review_date': '2026-09-28'},
            parser_coverage='READY', full_ad_text=text,
            reading_quality={'global_scan_incomplete': False},
            evidence_scope={item: {'evidence_ids': ['E-1'], 'complete_ad_scan': True}},
            canonical_confirmed_facts={item: [
                {'fact_id': 'A1', 'value': True, 'basis': 'template_id'}]},
            documents=[{'evidence_id': 'E-1', 'line_refs': ['L-1'],
                        'line_texts': {'L-1': text}, 'text': text,
                        'span_status': 'line_level_selected_text'}],
        )
        payload.update(payload_overrides or {})
        row['messages'][1]['content'] = json.dumps(payload, ensure_ascii=False)
        messages, aliases = gemma._compact_model_request(row)
        compact = json.loads(messages[1]['content'])
        output = gemma._expand_model_response(row, {'results': [{
            'rule_ref': 'R1', 'scope_check': {'scope_ref': contract['scope_ref'], 'status': 'MATCHED'},
            'condition_checks': [
                {'condition_ref': f['condition_id'],
                 'status': facts.get(f['condition_id'],
                                     'SATISFIED' if f['condition_id'] == 'A1' else 'UNDETERMINED'),
                 'evidence_refs': ['L1'] if facts.get(f['condition_id']) == 'SATISFIED' else []}
                for f in contract['applicability_conditions']],
            'review_condition_checks': [],
            'requirement_checks': [
                {'obligation_ref': o['obligation_id'], 'requirement': o['text'],
                 'status': statuses.get(o['obligation_id'], 'UNDETERMINED'),
                 'finding_basis': ('ABSENCE' if statuses.get(o['obligation_id']) == 'MISSING' else
                                   'OBSERVED' if statuses.get(o['obligation_id']) in {'SATISFIED', 'VIOLATED'} else
                                   'UNKNOWN'),
                 'evidence_refs': ['L1'] if statuses.get(o['obligation_id']) in {'SATISFIED', 'VIOLATED'} else [],
                 'reason': text}
                for o in contract['obligation_checks']],
            'verdict': 'COMPLIANT', 'reason': text, 'confidence': 'HIGH'}]}, aliases)
        return compact, output['results'][0]

    def test_original_criteria_source_refs_and_exact_aliases_are_preserved(self):
        aliases = {self.R10: ['TPL-29fb4e590eff2786d5ef430a'],
                   self.R11: ['TPL-a09ab7edd13f3b3f436918cf']}
        for item, source_hash in self.SOURCE_HASHES.items():
            with self.subTest(item=item):
                plan = self.catalog.plans[item]
                contract = self.contract(item)
                self.assertEqual(source_hash, plan['source_sha256'])
                self.assertEqual(source_hash, digest(plan['source']))
                fields = plan['source']['source_fields']
                expected = {key: str(fields[key]).strip()
                            for key in ('satisfied', 'violated', 'review',
                                        'violation_guidance', 'review_guidance')
                            if str(fields.get(key) or '').strip()}
                self.assertEqual(expected, contract['source_criteria'])
                self.assertEqual([{'plan_id': item, 'source_sha256': source_hash}],
                                 contract['review_program']['source_refs'])
                self.assertEqual(aliases[item], self.rules[item]['legacy_item_ids'])
                compact, _ = self.wire(item, self.RATE_TEXT, {}, {})
                self.assertEqual(expected, compact['rules'][0]['condition_contract']['source_criteria'])
        self.assertIn('n개 이상', self.contract(self.R10)['source_criteria']['satisfied'])
        self.assertIn('c8셀의 방식 2 또는 c9셀의 방식 3',
                      self.contract(self.R11)['source_criteria']['satisfied'])

    def test_bonus_sum_adapter_and_original_evidence_contract_are_preserved(self):
        atom = next(o for o in self.contract(self.R10)['obligation_checks']
                    if o['obligation_id'] == 'O2')
        self.assertEqual({'kind': 'BONUS_SUM_BOUND'}, atom['deterministic_adapter'])
        self.assertEqual({'rule': True, 'llm': True, 'external_input': False, 'human': False},
                         atom['owners'])
        self.assertEqual({'advertisement_direct_quote_required': True,
                          'absence_requires_complete_scan': True,
                          'same_advertisement_product_revision_scope': True,
                          'rule_or_example_text_is_advertisement_evidence': False}, atom['evidence'])

    def test_incomplete_sum_is_unknown_on_wire_and_cannot_create_an_overall_pass(self):
        text = self.SUM_TEXT + ', ' + self.RATE_TEXT
        _, result = self.wire(self.R10, text, {}, {'B1': 'SATISFIED'},
                              payload_overrides={'reading_quality': {'global_scan_incomplete': True}})
        atom = next(check for check in result['requirement_checks'] if check['obligation_ref'] == 'O2')
        self.assertEqual(('UNDETERMINED', 'UNKNOWN'), (atom['status'], atom['finding_basis']))
        self.assertEqual([], atom['evidence_line_refs'])
        self.assertEqual('UNDETERMINED', result['verdict'])

    def test_threshold_alternative_survives_an_incomplete_sum_in_the_actual_source_contract(self):
        text = '우대조건 총 3개 중 2개 이상 충족하면 우대금리 연 0.4%p를 제공합니다.'
        _, result = self.wire(self.R10, text, {'O1': 'SATISFIED'}, {'B1': 'SATISFIED'},
                              payload_overrides={'reading_quality': {'global_scan_incomplete': True}})
        atom = next(check for check in result['requirement_checks'] if check['obligation_ref'] == 'O2')
        self.assertEqual('UNDETERMINED', atom['status'])
        self.assertEqual('COMPLIANT', result['verdict'])
        self.assertEqual('COMPLIANT', result['review_program_trace']['verdict'])

    def test_advertised_bonus_and_external_product_absence_are_distinct_decision_facts(self):
        for item in (self.R10, self.R11):
            with self.subTest(item=item):
                contract = self.contract(item)
                facts = {f['condition_id']: f for f in contract['applicability_conditions']}
                self.assertEqual('LLM', facts['B1']['owner'])
                self.assertEqual('ADVERTISEMENT_OBSERVATION', facts['B1']['input_type'])
                self.assertEqual('NOT_SATISFIED_IF_COMPLETE_AD_SCAN', facts['B1']['absence_policy'])
                self.assertIn('EXTERNAL', facts['B2']['owner'])
                self.assertEqual('AD_AND_EXTERNAL', facts['B2']['input_type'])
                self.assertEqual('UNDETERMINED', facts['B2']['unknown_policy'])
                self.assertNotIn('absence_policy', facts['B2'])
                self.assertIn('B1', contract['decision_fact_ids'])
                self.assertIn('B2', contract['decision_fact_ids'])
                self.assertEqual({'all': [{'fact': 'A1'}]}, contract['applicability_logic'])

    def test_rate_method_facts_resolve_cell_names_and_keep_base_rate_independent(self):
        contract = self.contract(self.R11)
        facts = {f['condition_id']: f for f in contract['applicability_conditions']}
        self.assertIn('최고금리', facts['B4']['text'])
        self.assertNotIn('기본금리', facts['B4']['text'])
        self.assertIn('최저금리', facts['B5']['text'])
        self.assertIn('최고금리', facts['B5']['text'])
        for ref in ('B4', 'B5'):
            self.assertEqual('LLM', facts[ref]['owner'])
            self.assertEqual('ADVERTISEMENT_OBSERVATION', facts[ref]['input_type'])
            self.assertIn(ref, contract['decision_fact_ids'])
        for node in [*contract['applicability_conditions'], *contract['obligation_checks']]:
            for text in [node['text'], *(node.get('retrieval_queries') or [])]:
                self.assertNotRegex(text, r'(?i)C\s*[789]')
        base = next(o for o in contract['obligation_checks'] if o['obligation_id'] == 'O4')
        self.assertIn('기본금리', base['text'])
        self.assertIn('별도', base['text'])
        statuses = {f'O{i}': 'MISSING' for i in range(1, 10)}
        statuses.update(O3='SATISFIED', O6='SATISFIED', O7='SATISFIED',
                        O8='SATISFIED', O9='SATISFIED', O4='UNDETERMINED')
        method2 = {'B1': 'NOT_SATISFIED', 'B2': 'UNDETERMINED', 'B3': 'NOT_SATISFIED',
                   'B4': 'SATISFIED', 'B5': 'NOT_SATISFIED'}
        self.assertEqual('UNDETERMINED', self.verdict(self.R11, statuses, method2))
        compact, _ = self.wire(self.R11, self.RATE_TEXT, {}, {})
        projected = compact['rules'][0]['condition_contract']
        for fact in projected['applicability_conditions']:
            self.assertNotRegex(fact['text'], r'(?i)C\s*[789]')
        self.assertEqual(base, next(o for o in projected['obligation_checks']
                                   if o['obligation_id'] == 'O4'))

    def test_twenty_source_branch_scenarios_use_the_actual_catalog_formula(self):
        sat, missing, unknown = 'SATISFIED', 'MISSING', 'UNDETERMINED'
        false = 'NOT_SATISFIED'
        c7 = {'O3': sat, 'O4': sat, 'O5': sat, 'O6': sat}
        r10 = {'O1': missing, 'O2': missing, **c7}
        method1 = {'B1': false, 'B2': unknown, 'B3': sat}
        common = {'O7': sat, 'O8': sat, 'O9': sat}
        r11 = {f'O{i}': missing for i in range(1, 10)}
        r11.update(common)
        base_facts = {'B1': false, 'B2': unknown, 'B3': false, 'B4': false, 'B5': false}
        cases = [
            ('sum independently satisfies', self.R10, {**r10, 'O2': sat}, method1, 'COMPLIANT'),
            ('n-of-many permitted alternative', self.R10, {**r10, 'O1': sat}, method1, 'COMPLIANT'),
            ('sum fails with bonus observed', self.R10, {**r10, 'O2': 'VIOLATED'},
             {**method1, 'B1': sat}, 'VIOLATION'),
            ('sum fails and product absence unknown', self.R10, {**r10, 'O2': 'VIOLATED'},
             {**method1, 'B1': unknown}, 'UNDETERMINED'),
            ('verified no bonus complete c7', self.R10, r10,
             {**method1, 'B2': sat}, 'COMPLIANT'),
            ('ad silence does not verify product absence', self.R10, r10, method1, 'UNDETERMINED'),
            ('verified no bonus c7 missing tax', self.R10, {**r10, 'O5': missing},
             {**method1, 'B2': sat}, 'VIOLATION'),
            ('conflicting product absence and ad bonus', self.R10, {**r10, 'O2': unknown},
             {**method1, 'B1': sat, 'B2': sat}, 'UNDETERMINED'),
            ('method2 omits repeated bonus line', self.R11,
             {**r11, 'O3': sat, 'O4': sat, 'O6': sat}, {**base_facts, 'B4': sat}, 'COMPLIANT'),
            ('method3 omits separate base and bonus lines', self.R11,
             {**r11, 'O5': sat, 'O6': sat}, {**base_facts, 'B5': sat}, 'COMPLIANT'),
            ('method2 lacks highest-rate amount', self.R11,
             {**r11, 'O3': sat, 'O4': sat}, {**base_facts, 'B4': sat}, 'VIOLATION'),
            ('method2 lacks separate base rate', self.R11,
             {**r11, 'O3': sat, 'O6': sat}, {**base_facts, 'B4': sat}, 'VIOLATION'),
            ('method3 lacks highest-rate amount', self.R11,
             {**r11, 'O5': sat}, {**base_facts, 'B5': sat}, 'VIOLATION'),
            ('method1 verified no bonus omits amount', self.R11,
             {**r11, 'O1': sat}, {**base_facts, 'B2': sat, 'B3': sat}, 'COMPLIANT'),
            ('method1 with bonus and amount', self.R11,
             {**r11, 'O1': sat, 'O2': sat}, {**base_facts, 'B1': sat, 'B3': sat}, 'COMPLIANT'),
            ('method1 with bonus lacks amount', self.R11,
             {**r11, 'O1': sat}, {**base_facts, 'B1': sat, 'B3': sat}, 'VIOLATION'),
            ('method1 ad silence external absence unknown', self.R11,
             {**r11, 'O1': sat}, {**base_facts, 'B3': sat}, 'UNDETERMINED'),
            ('method1 missing mandatory tax', self.R11,
             {**r11, 'O1': sat, 'O2': sat, 'O8': missing},
             {**base_facts, 'B1': sat, 'B3': sat}, 'UNDETERMINED'),
            ('method role unresolved', self.R11, {**r11, 'O1': sat},
             {**base_facts, 'B3': unknown, 'B4': unknown, 'B5': unknown}, 'UNDETERMINED'),
            ('method2 basis date unresolved', self.R11,
             {**r11, 'O3': sat, 'O4': sat, 'O6': sat, 'O9': unknown},
             {**base_facts, 'B4': sat}, 'UNDETERMINED'),
        ]
        self.assertEqual(20, len(cases))
        for label, item, statuses, facts, expected in cases:
            with self.subTest(case=label):
                self.assertEqual(expected, self.verdict(item, statuses, facts))

    def test_unknown_external_absence_never_creates_a_no_bonus_exception(self):
        sat, missing, unknown = 'SATISFIED', 'MISSING', 'UNDETERMINED'
        for ad_bonus in ('SATISFIED', 'NOT_SATISFIED', 'UNDETERMINED'):
            facts = {'B1': ad_bonus, 'B2': unknown, 'B3': sat, 'B4': 'NOT_SATISFIED',
                     'B5': 'NOT_SATISFIED'}
            for item, statuses in (
                (self.R10, {'O1': missing, 'O2': missing, 'O3': sat, 'O4': sat, 'O5': sat, 'O6': sat}),
                (self.R11, {'O1': sat, 'O2': missing, 'O3': missing, 'O4': missing, 'O5': missing,
                            'O6': missing, 'O7': sat, 'O8': sat, 'O9': sat}),
            ):
                with self.subTest(item=item, ad_bonus=ad_bonus):
                    self.assertNotEqual('COMPLIANT', self.verdict(item, statuses, facts))

    def test_compact_expand_preserves_unverified_external_absence(self):
        sat, missing = 'SATISFIED', 'MISSING'
        for item, statuses in (
            (self.R10, {'O1': missing, 'O2': missing, 'O3': sat, 'O4': sat, 'O5': sat, 'O6': sat}),
            (self.R11, {'O1': sat, 'O2': missing, 'O3': missing, 'O4': missing, 'O5': missing,
                        'O6': missing, 'O7': sat, 'O8': sat, 'O9': sat}),
        ):
            for unverified_claim in ('SATISFIED', 'NOT_SATISFIED', 'UNDETERMINED'):
                facts = {'B1': 'NOT_SATISFIED', 'B2': unverified_claim, 'B3': sat,
                         'B4': 'NOT_SATISFIED', 'B5': 'NOT_SATISFIED'}
                with self.subTest(item=item, unverified_claim=unverified_claim):
                    compact, result = self.wire(item, self.RATE_TEXT, statuses, facts)
                    wire_contract = compact['rules'][0]['condition_contract']
                    external = next(f for f in wire_contract['applicability_conditions']
                                    if f['condition_id'] == 'B2')
                    self.assertIn('EXTERNAL', external['owner'])
                    self.assertNotIn('B2', {f['fact_id'] for f in compact['canonical_confirmed_facts']['R1']})
                    returned = {f['condition_ref']: f['status'] for f in result['condition_checks']}
                    self.assertEqual('UNDETERMINED', returned['B2'])
                    self.assertEqual('NOT_SATISFIED', returned['B1'])
                    self.assertEqual('APPLICABLE', result['applicability'])
                    self.assertEqual('UNDETERMINED', result['verdict'])

    def test_computed_sum_overrides_model_guess_and_passes_despite_external_unknown(self):
        facts = {'B1': 'SATISFIED', 'B2': 'SATISFIED', 'B3': 'NOT_SATISFIED'}
        statuses = {'O1': 'MISSING', 'O2': 'SATISFIED'}
        for text, expected_status, expected_verdict in (
            (self.SUM_TEXT, 'SATISFIED', 'COMPLIANT'),
            (self.SUM_TEXT.replace('0.3%p', '0.4%p'), 'VIOLATED', 'VIOLATION'),
            (self.SUM_TEXT.replace('총 2개', '총 3개'), 'UNDETERMINED', 'UNDETERMINED'),
        ):
            with self.subTest(text=text):
                _, result = self.wire(self.R10, text, statuses, facts)
                checks = {o['obligation_ref']: o for o in result['requirement_checks']}
                conditions = {f['condition_ref']: f['status'] for f in result['condition_checks']}
                self.assertEqual(expected_status, checks['O2']['status'])
                self.assertEqual('SATISFIED', conditions['B1'])
                self.assertEqual('UNDETERMINED', conditions['B2'])
                self.assertEqual(expected_verdict, result['verdict'])

    def test_method2_cap_is_required_while_duplicate_bonus_cap_line_is_optional_on_wire(self):
        text = '최고 연 1.5%(기본금리 1.0%, 2026.09.28. 기준, 세전, 100만원까지 적용)'
        facts = {'B1': 'NOT_SATISFIED', 'B2': 'SATISFIED', 'B3': 'NOT_SATISFIED',
                 'B4': 'SATISFIED', 'B5': 'NOT_SATISFIED'}
        statuses = {f'O{i}': 'MISSING' for i in range(1, 10)}
        statuses.update(O3='SATISFIED', O4='SATISFIED', O6='SATISFIED',
                        O7='SATISFIED', O8='SATISFIED', O9='SATISFIED')
        for cap, expected in (('SATISFIED', 'COMPLIANT'), ('MISSING', 'VIOLATION')):
            with self.subTest(cap=cap):
                observed = text if cap == 'SATISFIED' else text.replace(', 100만원까지 적용', '')
                _, result = self.wire(self.R11, observed, {**statuses, 'O6': cap}, facts)
                self.assertEqual(expected, result['verdict'])
                conditions = {f['condition_ref']: f['status'] for f in result['condition_checks']}
                self.assertEqual('UNDETERMINED', conditions['B2'])

    def test_method1_observed_bonus_uses_amount_without_an_external_no_bonus_assumption(self):
        # This branch test supplies an amount condition, not a second rate with
        # an unbound date. The latter has a separate uncertainty boundary test.
        text = self.RATE_TEXT + ', 우대조건 충족 시 100만원까지 적용'
        facts = {'B1': 'SATISFIED', 'B2': 'UNDETERMINED', 'B3': 'SATISFIED',
                 'B4': 'NOT_SATISFIED', 'B5': 'NOT_SATISFIED'}
        statuses = {f'O{i}': 'MISSING' for i in range(1, 10)}
        statuses.update(O1='SATISFIED', O7='SATISFIED', O8='SATISFIED', O9='SATISFIED')
        for cap, expected in (('SATISFIED', 'COMPLIANT'), ('MISSING', 'VIOLATION')):
            with self.subTest(cap=cap):
                observed = text if cap == 'SATISFIED' else text.replace('100만원까지 적용', '우대 적용')
                _, result = self.wire(self.R11, observed, {**statuses, 'O2': cap}, facts)
                self.assertEqual(expected, result['verdict'])
