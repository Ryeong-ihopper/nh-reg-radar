import unittest
import json
import tempfile
import shutil
from pathlib import Path

from rag.judgment.product_context import resolve_product_templates
from rag.judgment.policy import confirmed_templates
from rag.judgment.operational_catalog import audit_canonical_template_coverage
from rag.judgment.operational_catalog import load_operational_catalog
from rag.judgment.source_checks import source_claim_errors
from rag.judgment.operational_selection import confirmed_metadata_facts, visual_exemption_confirmed
from rag.judgment.condition_contracts import compile_canonical_condition_contract
from rag.judgment.obligation_logic import aggregate_obligations
from rag.retrieval.evidence_bundle import program_nodes, retrieve_program_nodes
from test_operational_canonical_catalog import load_catalog, CONFIG
from run_operational_e2e import model_rule_view, top_rule_evidence
from run_gemma_exhaustive_dgx import _compact_model_request, _expand_model_response


BASE = '투자성상품-퇴직연금 일반'
def field(value, status='provided'):
    return {'value': value, 'status': status, 'source': 'synthetic_intake'}


class ProductContextReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()

    def etf_contract(self, item='MTH-RETIREMENT-ETF-R10'):
        rule = next(r for r in self.catalog.template_rules if r['item_id'] == item)
        return rule, compile_canonical_condition_contract(rule)

    def etf_wire(self, item, text, facts, statuses, *, complete=True,
                 parser_coverage='READY', documents=None, scope_ids=None):
        rule, contract = self.etf_contract(item)
        if documents is None:
            documents = [{'evidence_id': 'synthetic-1', 'line_refs': ['synthetic-1/L1'],
                'line_texts': {'synthetic-1/L1': text}, 'text': text,
                'span_status': 'line_level_selected_text', 'text_selection': {'needs_review': False}}]
        if scope_ids is None:
            scope_ids = [doc['evidence_id'] for doc in documents]
        payload = {'rules': [model_rule_view({**rule, 'condition_contract': contract})],
            'documents': documents, 'parser_coverage': parser_coverage, 'full_ad_text': text,
            'reading_quality': {'global_scan_incomplete': False},
            'evidence_scope': {item: {'evidence_ids': scope_ids, 'complete_ad_scan': complete}},
            'canonical_confirmed_facts': {item: [
                {'fact_id': 'A1', 'value': True, 'basis': 'selected_templates'}]}}
        row = {'request_id': 'synthetic-etf', 'ad_id': 'synthetic-etf', 'category': 'PRESENCE',
            'requested_item_ids': [item], 'messages': [{'role': 'system', 'content': 'test'},
                {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]}
        messages, aliases = _compact_model_request(row)
        compact = json.loads(messages[1]['content'])
        parsed = {'results': [{'rule_ref': 'R1',
            'scope_check': {'scope_ref': 'SCOPE', 'status': 'MATCHED', 'evidence_refs': []},
            'condition_checks': [{'condition_ref': f['condition_id'],
                'status': facts.get(f['condition_id'], 'SATISFIED' if f['condition_id'] == 'A1' else 'UNDETERMINED'),
                'evidence_refs': ['L1'] if facts.get(f['condition_id']) == 'SATISFIED' else []}
                for f in contract['applicability_conditions']],
            'review_condition_checks': [],
            'requirement_checks': [{'obligation_ref': o['obligation_id'], 'requirement': o['text'],
                'status': statuses.get(o['obligation_id'], 'UNDETERMINED'),
                'finding_basis': 'OBSERVED' if statuses.get(o['obligation_id']) == 'SATISFIED'
                    else 'ABSENCE' if statuses.get(o['obligation_id']) == 'MISSING' else 'UNKNOWN',
                'evidence_refs': ['L1'] if statuses.get(o['obligation_id']) == 'SATISFIED' else [],
                'reason': text} for o in contract['obligation_checks']],
            'verdict': 'COMPLIANT', 'reason': text, 'confidence': 'HIGH'}]}
        return compact, _expand_model_response(row, parsed, aliases)['results'][0]

    def test_etf_composition_trigger_and_two_warning_meanings_are_source_bound(self):
        rule, contract = self.etf_contract()
        conditions = {f['condition_id']: f for f in contract['applicability_conditions']}
        self.assertEqual({'A1', 'A2'}, set(conditions))
        self.assertEqual('RULE', conditions['A1']['owner'])
        self.assertEqual('CONFIRMED_METADATA', conditions['A1']['input_type'])
        self.assertEqual('LLM', conditions['A2']['owner'])
        self.assertEqual('ADVERTISEMENT_OBSERVATION', conditions['A2']['input_type'])
        self.assertEqual('NOT_SATISFIED_IF_COMPLETE_AD_SCAN', conditions['A2']['absence_policy'])
        self.assertEqual('UNDETERMINED', conditions['A2']['unknown_policy'])
        self.assertEqual({'all': [{'fact': 'A1'}, {'fact': 'A2'}]}, contract['applicability_logic'])
        self.assertEqual([], contract['decision_fact_ids'])
        checks = contract['obligation_checks']
        self.assertEqual(['O1', 'O2'], [o['obligation_id'] for o in checks])
        self.assertIn('종목', checks[0]['text'])
        self.assertIn('비중', checks[1]['text'])
        self.assertNotEqual(checks[0]['text'], checks[1]['text'])
        self.assertEqual({'all': [{'ref': 'O1'}, {'ref': 'O2'}]}, contract['obligation_logic'])
        example = self.catalog.plans[rule['item_id']]['source']['source_fields']['example']
        for check in checks:
            self.assertTrue(check['owners']['llm'])
            self.assertFalse(check['owners']['external_input'])
            self.assertTrue(check['evidence']['absence_requires_complete_scan'])
            self.assertTrue(check['evidence']['same_advertisement_product_revision_scope'])
            hint = check['interpretation_hints'][0]
            self.assertEqual(example, hint['text'])
            self.assertFalse(hint['exact_match_required'])
            self.assertFalse(hint['may_be_cited_as_advertisement_evidence'])

    def test_etf_composition_search_retains_trigger_and_warnings_without_proving_absence(self):
        rule, contract = self.etf_contract()
        rule = {**rule, 'condition_contract': contract}
        self.assertEqual(['A2', 'O1', 'O2'], [node['source_ref'] for node in program_nodes(rule)])
        rows = [{'doc_id': 'composition', 'ad_id': 'synthetic',
                 'text_canonical': '대상 ETF의 구성 종목은 알파와 베타이며 비중은 각각 70%와 30%입니다.'},
                {'doc_id': 'warning', 'ad_id': 'synthetic',
                 'text_canonical': '편입 종목 및 비중은 추후 변동될 수 있습니다.'},
                {'doc_id': 'contact', 'ad_id': 'synthetic', 'text_canonical': '고객센터 연락처'}]
        selected, trace = retrieve_program_nodes([], rows, rule, {}, {}, char_budget=1000)
        self.assertEqual({'composition', 'warning'}, set(selected))
        events = {node['source_ref']: node for node in trace['nodes']}
        self.assertIn('composition', events['A2']['evidence_ids'])
        for ref in ('O1', 'O2'):
            self.assertIn('warning', events[ref]['evidence_ids'])
            self.assertEqual('LEXICAL', events[ref]['mode'])
        self.assertFalse(trace['semantic_dependencies_complete'])
        selected, trace = retrieve_program_nodes([], rows, rule, {}, {}, char_budget=0)
        self.assertEqual([], selected)
        self.assertTrue(all(node['status'] == 'BUDGET_DEFERRED' for node in trace['nodes']))
        self.assertFalse(trace['semantic_dependencies_complete'])
        _, result = self.etf_wire(rule['item_id'], rows[-1]['text_canonical'], {}, {})
        self.assertEqual('UNDETERMINED', result['verdict'])
        self.assertNotIn('applicability_absence_closures', result)

    def test_etf_composition_atoms_and_source_criteria_survive_actual_compact_wire(self):
        item = 'MTH-RETIREMENT-ETF-R10'
        _, contract = self.etf_contract(item)
        compact, _ = self.etf_wire(item, '합성 판독 텍스트', {}, {})
        wire = compact['rules'][0]
        for key in ('applicability_conditions', 'applicability_logic', 'obligation_checks',
                    'obligation_logic', 'source_criteria', 'review_program'):
            self.assertEqual(contract[key], wire['condition_contract'][key])
        self.assertEqual(['A1', 'A2'], wire['output_check_refs']['condition_checks'])
        self.assertEqual(['O1', 'O2'], wire['output_check_refs']['requirement_checks'])
        fields = self.catalog.plans[item]['source']['source_fields']
        self.assertEqual(fields['satisfied'], wire['condition_contract']['source_criteria']['satisfied'])
        self.assertEqual(fields['violated'], wire['condition_contract']['source_criteria']['violated'])
        self.assertNotIn('example', wire['condition_contract']['source_criteria'])

    def test_etf_composition_final_formula_distinguishes_two_missing_warnings_and_unknown_trigger(self):
        item = 'MTH-RETIREMENT-ETF-R10'
        cases = [
            ('both warnings', 'SATISFIED', 'SATISFIED', 'SATISFIED', 'COMPLIANT',
             '대상 ETF의 구성 종목과 비중은 운용 상황에 따라 변경될 수 있습니다.'),
            ('missing holdings warning', 'SATISFIED', 'MISSING', 'SATISFIED', 'VIOLATION',
             '대상 ETF는 알파와 베타에 투자하며 종목별 비중은 변경될 수 있습니다.'),
            ('missing weights warning', 'SATISFIED', 'SATISFIED', 'MISSING', 'VIOLATION',
             '대상 ETF는 알파와 베타에 투자합니다. 투자하는 종목은 앞으로 변경될 수 있습니다.'),
            ('unread warning', 'SATISFIED', 'UNDETERMINED', 'SATISFIED', 'UNDETERMINED',
             '대상 ETF는 알파와 베타로 구성되며 비중은 변경될 수 있습니다. 나머지 안내는 판독 불명.'),
            ('no composition mention', 'NOT_SATISFIED', 'UNDETERMINED', 'UNDETERMINED', 'NOT_APPLICABLE',
             '고객센터 연락처 안내'),
            ('trigger undecided', 'UNDETERMINED', 'MISSING', 'MISSING', 'UNDETERMINED',
             '구성 안내는 판독 불명'),
        ]
        for name, trigger, o1, o2, verdict, text in cases:
            with self.subTest(case=name):
                _, result = self.etf_wire(item, text, {'A2': trigger}, {'O1': o1, 'O2': o2})
                self.assertEqual(verdict, result['verdict'])
                if verdict in {'NOT_APPLICABLE', 'UNDETERMINED'} and trigger != 'SATISFIED':
                    self.assertEqual([], result['requirement_checks'])
                if trigger == 'NOT_SATISFIED':
                    self.assertEqual('A2', result['applicability_absence_closures'][0]['condition_ref'])

    def test_etf_negative_trigger_requires_readable_scope_even_when_scan_is_marked_complete(self):
        item = 'MTH-RETIREMENT-ETF-R10'
        text = '고객센터 연락처 안내'
        unsafe = {'evidence_id': 'uncertain', 'line_refs': ['uncertain/L1'],
            'line_texts': {'uncertain/L1': text}, 'text': text,
            'text_selection': {'needs_review': True}, 'span_status': 'region_level_selected_text'}
        clean = {**unsafe, 'evidence_id': 'clean', 'text_selection': {'needs_review': False},
            'span_status': 'line_level_selected_text'}
        cases = [
            ('unresolved reading', {'documents': [unsafe]}, 'UNDETERMINED'),
            ('incomplete scan', {'complete': False}, 'UNDETERMINED'),
            ('partial parser', {'parser_coverage': 'PARTIAL'}, 'UNDETERMINED'),
            ('same source line independently readable', {'documents': [unsafe, clean]}, 'NOT_APPLICABLE'),
            ('uncertainty outside item scope', {'documents': [unsafe, clean], 'scope_ids': ['clean']}, 'NOT_APPLICABLE'),
        ]
        for name, options, expected in cases:
            with self.subTest(case=name):
                _, result = self.etf_wire(item, text, {'A2': 'NOT_SATISFIED'}, {}, **options)
                self.assertEqual(expected, result['applicability'])
                self.assertEqual(expected, result['verdict'])
                observation = next(c for c in result['condition_checks'] if c['condition_ref'] == 'A2')
                self.assertEqual('UNDETERMINED' if expected == 'UNDETERMINED' else 'NOT_SATISFIED',
                                 observation['status'])
                self.assertEqual([], result['requirement_checks'])
                if expected == 'UNDETERMINED':
                    self.assertNotIn('applicability_absence_closures', result)

    def test_leverage_warnings_keep_distinct_meanings_and_unmentioned_branch_requires_review(self):
        items = ['MTH-RETIREMENT-ETF-R11', 'MTH-RETIREMENT-ETF-R12']
        contracts = [self.etf_contract(item)[1] for item in items]
        self.assertEqual(contracts[0]['source_criteria'], contracts[1]['source_criteria'])
        self.assertIn('손실', contracts[0]['obligation_checks'][0]['text'])
        self.assertIn('기간 수익률', contracts[1]['obligation_checks'][0]['text'])
        self.assertIn('일간 수익률', contracts[1]['obligation_checks'][0]['text'])
        self.assertNotEqual(contracts[0]['obligation_checks'][0]['text'],
                            contracts[1]['obligation_checks'][0]['text'])
        for item, contract in zip(items, contracts):
            with self.subTest(item=item):
                self.assertEqual({'all': [{'fact': 'A1'}]}, contract['applicability_logic'])
                self.assertEqual(['B1'], contract['decision_fact_ids'])
                branch = next(c for c in contract['applicability_conditions'] if c['condition_id'] == 'B1')
                self.assertEqual('ADVERTISEMENT_OBSERVATION', branch['input_type'])
                self.assertEqual('SOURCE_SCOPE_CONFLICT_UNMENTIONED_REQUIRES_REVIEW',
                                 contract['review_program']['semantic_status'])
                for trigger, check, verdict in [
                        ('SATISFIED', 'SATISFIED', 'COMPLIANT'),
                        ('SATISFIED', 'MISSING', 'VIOLATION'),
                        ('NOT_SATISFIED', 'MISSING', 'UNDETERMINED'),
                        ('UNDETERMINED', 'MISSING', 'UNDETERMINED')]:
                    with self.subTest(trigger=trigger, warning=check):
                        text = '대상 ETF는 지수의 일간 변동률 2배를 추종합니다.'
                        if trigger != 'SATISFIED':
                            text = '고객센터 연락처 안내'
                        elif check == 'SATISFIED':
                            text += (' 원금 손실 폭이 크게 늘어날 수 있습니다.' if item.endswith('R11')
                                     else ' 보유 기간의 수익은 기준 지수의 하루 수익률과 다를 수 있습니다.')
                        compact, result = self.etf_wire(item, text, {'B1': trigger}, {'O1': check})
                        self.assertEqual('APPLICABLE', result['applicability'])
                        self.assertEqual(verdict, result['verdict'])
                        self.assertEqual(contract['obligation_logic'],
                                         compact['rules'][0]['condition_contract']['obligation_logic'])

    def test_composition_enumerates_every_selected_template_and_cannot_drop_a_component(self):
        selected, context, complete = resolve_product_templates({'product_classification_code': BASE,
            'underlying_products': ['ETF', 'ELB'], 'underlying_products_status': 'CONFIRMED'})
        self.assertEqual('RETIREMENT', context)
        self.assertTrue(complete)
        routing = {'template_id': field(BASE), 'selected_templates': field(selected)}
        self.assertEqual(selected, confirmed_templates(routing))
        ids = [r['item_id'] for r in self.catalog.template_rules if r['product_subtype'] in selected]
        self.assertEqual(len(ids), audit_canonical_template_coverage(self.catalog, selected, ids, [])['plan_count'])
        with self.assertRaises(ValueError):
            audit_canonical_template_coverage(self.catalog, selected, ids[:-1], [])
        for p in self.catalog.plans.values():
            if p['source'].get('product_template') == '투자성상품-ETF':
                self.assertTrue(confirmed_metadata_facts(p, product_groups=['투자성'], template_id=BASE, routing=routing)[0]['value'])

    def test_unknown_and_confirmed_empty_are_distinct(self):
        for status, complete in [('UNCONFIRMED', False), ('CONFIRMED', True)]:
            self.assertEqual(([BASE], 'RETIREMENT', complete), resolve_product_templates({
                'product_classification_code': BASE, 'underlying_products_status': status}))

    def test_arbitrary_unions_and_standalone_method_reuse_fail_closed(self):
        with self.assertRaises(ValueError):
            confirmed_templates({'template_id': field(BASE), 'selected_templates': field([BASE, '예금성상품-입출식'])})
        with self.assertRaises(ValueError):
            resolve_product_templates({'product_classification_code': '투자성상품-ETF'})
        with self.assertRaises(ValueError):
            resolve_product_templates({'product_classification_code': BASE, 'underlying_products': ['ETF']})
        self.assertEqual([], confirmed_templates({'template_id': field(BASE, 'inferred')}))

    def test_logo_exemption_keeps_nonprotected_text_and_unknown_context_is_not_exemption(self):
        for item in ['MTH-RETIREMENT-ETF-R14', 'MTH-RETIREMENT-ELB-R10']:
            rule = next(r for r in self.catalog.template_rules if r['item_id'] == item)
            contract = compile_canonical_condition_contract(rule)
            checks = [{'obligation_ref': 'O1', 'status': 'SATISFIED'}, {'obligation_ref': 'O2', 'status': 'UNDETERMINED'}]
            self.assertEqual('COMPLIANT', aggregate_obligations(contract, checks, [{'condition_ref': 'B1', 'status': 'SATISFIED'}]))
            self.assertEqual('UNDETERMINED', aggregate_obligations(contract, checks, [{'condition_ref': 'B1', 'status': 'UNDETERMINED'}]))
            checks[0]['status'] = 'MISSING'
            self.assertEqual('VIOLATION', aggregate_obligations(contract, checks, [{'condition_ref': 'B1', 'status': 'SATISFIED'}]))
            self.assertTrue(visual_exemption_confirmed(rule, {'product_context': field('RETIREMENT')}))
            self.assertFalse(visual_exemption_confirmed(rule, {'product_context': field('RETIREMENT', 'inferred')}))

    def test_line_facets_cannot_be_auto_passed_by_text_only(self):
        matched = [r for r in self.catalog.template_rules if r['canonical_execution_plan']['review_program'].get('line_structure_policy')]
        self.assertEqual(33, len(matched))
        for rule in matched:
            contract = compile_canonical_condition_contract(rule)
            checks = [{'obligation_ref': c['obligation_id'], 'status': 'UNDETERMINED' if c['owners']['human'] else 'SATISFIED'} for c in contract['obligation_checks']]
            self.assertEqual('UNDETERMINED', aggregate_obligations(contract, checks, []))

    def test_lexical_policy_does_not_require_or_take_an_unrelated_dense_hit(self):
        rows = [{'doc_id': 'right', 'ad_id': 'A', 'text_canonical': '금리 안내'},
                {'doc_id': 'wrong', 'ad_id': 'A', 'text_canonical': '연락처'}]
        self.assertEqual(['right'], top_rule_evidence('R', rule_vector_by_id={}, ad_fine_rows=rows,
            fine_vector_by_id={}, trigger_ids=[], k=1, rule_text='금리', evidence_mode='LEXICAL'))
        rule = {'condition_contract': {'review_program': {'evidence_policy': {'mode': 'LEXICAL'}},
            'obligation_checks': [{'obligation_id': 'O1', 'text': '금리 안내'}]}}
        selected, trace = retrieve_program_nodes([], rows, rule, {}, {}, char_budget=100)
        self.assertEqual(['right'], selected)
        self.assertEqual('LEXICAL', trace['nodes'][0]['mode'])

    def test_separate_line_check_does_not_veto_the_body_absence_check(self):
        rule = next(r for r in self.catalog.template_rules if r['item_id'] == 'MTH-LOAN-NAMED-R23')
        rule = {**rule, 'condition_contract': compile_canonical_condition_contract(rule)}
        errors = source_claim_errors({'rules': [rule], 'documents': []}, {'item_id': rule['item_id'],
            'requirement_checks': [{'obligation_ref': 'O1', 'status': 'MISSING', 'finding_basis': 'ABSENCE',
                                    'reason': '전체 원문에서 필수 본문을 확인하지 못함', 'evidence_ids': [], 'evidence_line_refs': []}]})
        self.assertFalse(any('same-line notice' in error for error in errors))

    def test_evidence_policy_cannot_change_without_its_reviewed_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            names = ['canonical-execution-plans-v2.json', 'review-program-policies-v1.json',
                     'operational-catalog-migration-v1.json', 'operational-rule-dispositions-v1.json']
            for name in names:
                shutil.copy2(CONFIG / name, folder / name)
            path = folder / names[0]
            document = json.loads(path.read_text(encoding='utf-8'))
            document['plans'][0]['review_program']['evidence_policy']['mode'] = 'HYBRID'
            path.write_text(json.dumps(document), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'evidence/decision policy differs'):
                load_operational_catalog(path, folder / names[2], folder / names[3],
                                         legacy_template_rules=[], v2_rules=[])


if __name__ == '__main__':
    unittest.main()
