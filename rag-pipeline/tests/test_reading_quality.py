"""Synthetic positive/negative/boundary cases; no ad-specific answers."""
import copy
import json
import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from test_operational_rag_contracts import request_row, result
import run_gemma_exhaustive_dgx as gemma
import run_operational_e2e as operational
from rag.judgment.reading_quality import apply_reading_guard, needs_reading_review
from rag.judgment.policy import deterministic_facts
from rag.judgment.grounding import cited_window_text


class ReadingQualityTests(unittest.TestCase):
    def test_explicit_partial_reading_survives_parser_adapter_and_combine(self):
        from test_parser_contract_adapter import external_pair
        from rag.parsing.prepare_inputs import combine
        p1, p3 = external_pair()
        p1['coverage'] = {'complete_document_read': False}
        p1['pages'][0]['unread_regions'] = [{'reason': 'cropped text'}]
        relation = {'type': 'header_for', 'status': 'observed',
            'from_line_ids': ['p1/R-1/L000'], 'to_line_ids': ['p1/R-1/L000']}
        p1['pages'][0]['relations'] = [relation]
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / 'p1.json', Path(directory) / 'p3.json'
            a.write_text(json.dumps(p1), encoding='utf-8')
            b.write_text(json.dumps(p3), encoding='utf-8')
            ad = combine(a, b)
        self.assertFalse(ad['quality']['complete_document_read'])
        self.assertEqual(ad['pages'][0]['unread_regions'], [{'reason': 'cropped text'}])
        self.assertEqual(operational.parser_coverage(ad), 'PARTIAL')
        from rag.parsing.prepare_inputs import search_docs
        coarse, fine = search_docs(ad)
        self.assertEqual(coarse[0]['source_relations'], [relation])
        self.assertEqual(fine[0]['source_relations'], [relation])

    def test_compliant_numeric_claim_must_match_the_cited_line(self):
        row, payload, parsed = self.setup_case(uncertain=False)
        doc = payload['documents'][0]
        doc.update(text='기본 1.0% 우대 5.0%', line_refs=['L-1', 'L-extra'],
            line_texts={'L-1': '기본 1.0%', 'L-extra': '우대 5.0%'})
        parsed['results'][0]['requirement_checks'][0]['reason'] = '금리 5.0% 표기가 있음'
        self.assertEqual(cited_window_text(['L-1'], [doc]), '기본 1.0%')
        self.assertTrue(any('5.0' in error for error in self.validate_case(row, payload, parsed)))
        parsed['results'][0]['requirement_checks'][0]['reason'] = '금리 1.0% 표기가 있음'
        self.assertEqual(self.validate_case(row, payload, parsed), [])

    def test_applicability_cannot_borrow_another_rule_evidence(self):
        row, payload, parsed = self.setup_case(uncertain=False)
        payload['evidence_scope']['X-1']['evidence_ids'] = ['E-1']
        parsed['results'][0].update(applicability_basis='ADVERTISEMENT_EVIDENCE',
            applicability_evidence_ids=['E-2'], applicability_evidence_line_refs=['L-2'])
        self.assertTrue(any('적용성 evidence_scope' in error for error in self.validate_case(row, payload, parsed)))

    def test_invalid_ids_are_not_hidden_by_reading_guard_in_call_once(self):
        row, payload, parsed = self.setup_case()
        parsed['results'][0]['requirement_checks'][0]['evidence_ids'].append('GHOST')
        row['messages'][1]['content'] = json.dumps(payload)
        response = {'choices': [{'message': {'content': '{}'}, 'finish_reason': 'stop'}]}
        with patch('dgx_openai_client.post_json', return_value=response), \
             patch.object(gemma, '_expand_model_response', return_value=parsed):
            batch = gemma.call_once(row, None, None, 'mock', 1000)
        self.assertTrue(batch['validation_errors'])
        self.assertEqual(batch['reading_quality_guards'], [])

    def setup_case(self, *, uncertain=True, complete=True):
        row = request_row(['X-1'])
        payload = json.loads(row['messages'][1]['content'])
        payload['documents'][0]['text_selection'] = {'needs_review': uncertain}
        payload['documents'].append({'evidence_id': 'E-2', 'line_refs': ['L-2'],
            'text': '독립적으로 판독된 근거', 'text_selection': {'needs_review': False}})
        payload['routing']['media_type'] = {'value': 'NOTICE', 'status': 'confirmed'}
        payload['evidence_scope'] = {'X-1': {'evidence_ids': ['E-1', 'E-2'], 'complete_ad_scan': complete}}
        answer = result('X-1')
        answer.update(applicability_basis='CONFIRMED_METADATA', applicability_evidence_ids=[],
            applicability_evidence_line_refs=[], applicability_metadata_fields=['media_type'])
        return row, payload, {'ad_id': row['ad_id'], 'results': [answer]}

    def validate_case(self, row, payload, parsed):
        row['messages'][1]['content'] = json.dumps(payload)
        return gemma.validate(row, parsed)

    def test_uncertain_compliance_is_review_with_original_preserved(self):
        row, payload, parsed = self.setup_case()
        original = copy.deepcopy(parsed['results'][0])
        self.assertTrue(self.validate_case(row, payload, parsed))
        audit = apply_reading_guard(payload, parsed)
        self.assertEqual(audit[0]['original_result'], original)
        self.assertEqual(parsed['results'][0]['verdict'], 'UNDETERMINED')
        self.assertTrue(parsed['results'][0]['needs_researcher_review'])
        self.assertEqual(self.validate_case(row, payload, parsed), [])
        self.assertEqual(apply_reading_guard(payload, parsed), [])

    def test_independent_clean_evidence_is_not_blocked(self):
        row, payload, parsed = self.setup_case()
        answer = parsed['results'][0]
        answer['evidence_ids'], answer['evidence_line_refs'] = ['E-2'], ['L-2']
        answer['requirement_checks'][0].update(evidence_ids=['E-2'], evidence_line_refs=['L-2'])
        self.assertEqual(apply_reading_guard(payload, parsed), [])
        self.assertEqual(self.validate_case(row, payload, parsed), [])

    def test_uncertain_absence_including_prohibition_compliance(self):
        for category, verdict, status in [('PRESENCE', 'VIOLATION', 'MISSING'),
                                          ('PROHIBIT', 'COMPLIANT', 'SATISFIED')]:
            with self.subTest(category=category):
                row, payload, parsed = self.setup_case(complete=False)
                row['category'] = category
                answer = parsed['results'][0]
                answer.update(verdict=verdict, evidence_ids=[], evidence_line_refs=[])
                answer['requirement_checks'][0].update(status=status, finding_basis='ABSENCE',
                    evidence_ids=[], evidence_line_refs=[])
                row['messages'][1]['content'] = json.dumps(payload)
                self.assertEqual(gemma.validate(row, parsed, check_reading=False), [])
                self.assertTrue(apply_reading_guard(payload, parsed))
                self.assertEqual(self.validate_case(row, payload, parsed), [])

    def test_clear_complete_absence_is_still_a_violation(self):
        row, payload, parsed = self.setup_case(uncertain=False)
        answer = parsed['results'][0]
        answer.update(verdict='VIOLATION', evidence_ids=[], evidence_line_refs=[])
        answer['requirement_checks'][0].update(status='MISSING', finding_basis='ABSENCE',
            evidence_ids=[], evidence_line_refs=[])
        self.assertEqual(apply_reading_guard(payload, parsed), [])
        self.assertEqual(self.validate_case(row, payload, parsed), [])

    def test_uncertainty_elsewhere_prevents_absence_but_not_observation(self):
        row, payload, parsed = self.setup_case(uncertain=False)
        payload['reading_quality'] = {'requires_review': True}
        self.assertEqual(apply_reading_guard(payload, parsed), [])
        check = parsed['results'][0]['requirement_checks'][0]
        check.update(status='MISSING', finding_basis='ABSENCE')
        parsed['results'][0]['verdict'] = 'VIOLATION'
        self.assertTrue(apply_reading_guard(payload, parsed))

    def test_partial_scan_allows_clean_presence_but_not_absence(self):
        row, payload, parsed = self.setup_case(uncertain=False, complete=False)
        payload['parser_coverage'] = 'PARTIAL'
        payload['reading_quality'] = {'requires_review': True}
        self.assertEqual(apply_reading_guard(payload, parsed), [])
        self.assertEqual(self.validate_case(row, payload, parsed), [])
        self.assertEqual(parsed['results'][0]['verdict'], 'COMPLIANT')
        check = parsed['results'][0]['requirement_checks'][0]
        check.update(status='MISSING', finding_basis='ABSENCE', evidence_ids=[], evidence_line_refs=[])
        parsed['results'][0].update(verdict='VIOLATION', evidence_ids=[], evidence_line_refs=[])
        self.assertTrue(apply_reading_guard(payload, parsed))
        self.assertEqual(parsed['results'][0]['verdict'], 'UNDETERMINED')

    def test_model_contract_distinguishes_presence_from_whole_ad_absence(self):
        prompt = gemma.COMPACT_OUTPUT_SYSTEM
        self.assertIn('not a directly observed required phrase', prompt)
        self.assertIn('If that obligation depends on unread text', prompt)
        self.assertIn('Never return an empty result object', prompt)
        self.assertNotIn('When the scan or required layout/external\ninput is incomplete', prompt)

    def test_uncertain_gate_cannot_hide_as_not_applicable(self):
        row, payload, parsed = self.setup_case()
        answer = parsed['results'][0]
        answer.update(applicability='NOT_APPLICABLE', applicability_basis='NOT_APPLICABLE',
            verdict='NOT_APPLICABLE', requirement_checks=[])
        answer['scope_check'] = {'status': 'NOT_MATCHED', 'evidence_ids': ['E-1'], 'evidence_line_refs': ['L-1']}
        self.assertTrue(apply_reading_guard(payload, parsed))
        self.assertEqual(answer['applicability'], 'UNDETERMINED')
        self.assertEqual(self.validate_case(row, payload, parsed), [])

    def test_valid_violation_survives_another_uncertain_component(self):
        row, payload, parsed = self.setup_case()
        answer = parsed['results'][0]
        answer['verdict'] = 'VIOLATION'
        answer['evidence_line_refs'].append('L-2')
        answer['requirement_checks'].append({'requirement': '별도 요건', 'status': 'VIOLATED',
            'finding_basis': 'OBSERVED', 'evidence_ids': ['E-2'], 'evidence_line_refs': ['L-2'], 'reason': '관찰 위반'})
        self.assertTrue(apply_reading_guard(payload, parsed))
        self.assertEqual(answer['verdict'], 'VIOLATION')
        self.assertEqual(self.validate_case(row, payload, parsed), [])

    def test_partial_quality_is_applied_for_regions_and_unassigned_lines(self):
        for slot in ('regions', 'unassigned_lines'):
            ad = {'quality': {'line_partition_exact': True}, 'pages': [{'parse_status': 'ok',
                slot: [{'text_selection': {'needs_review': True}}]}]}
            self.assertEqual(operational.parser_coverage(ad), 'PARTIAL')
        for extra in ({'unread_regions': [{'reason': 'unread'}]},):
            ad = {'quality': {'line_partition_exact': True}, 'pages': [{'parse_status': 'ok', **extra}]}
            self.assertEqual(operational.parser_coverage(ad), 'PARTIAL')

    def test_malformed_flag_and_unresolved_status_never_promote_trust(self):
        for selection in ({'needs_review': 'false'}, {'needs_review': None},
                          {'needs_review': False, 'selection_status': 'judge_unresolved_parser_fallback'}, [], None):
            self.assertTrue(needs_reading_review({'text_selection': selection}))
        self.assertFalse(needs_reading_review({}))

    def test_uncertain_text_cannot_create_deterministic_fact(self):
        uncertain = {'text_canonical': '심의필 2026-1234', 'text_selection': {'needs_review': True}}
        self.assertFalse(deterministic_facts([uncertain])['review_number_present'])
        clean = {**uncertain, 'text_selection': {'needs_review': False}}
        self.assertTrue(deterministic_facts([uncertain, clean])['review_number_present'])

    def test_call_once_routes_to_review_without_contract_retry(self):
        row, payload, parsed = self.setup_case(complete=False)
        answer = parsed['results'][0]
        answer.update(verdict='VIOLATION', evidence_ids=[], evidence_line_refs=[])
        answer['requirement_checks'][0].update(status='MISSING', finding_basis='ABSENCE', evidence_ids=[], evidence_line_refs=[])
        row['messages'][1]['content'] = json.dumps(payload)
        response = {'choices': [{'message': {'content': '{}'}, 'finish_reason': 'stop'}]}
        with patch('dgx_openai_client.post_json', return_value=response) as post, \
             patch.object(gemma, '_expand_model_response', return_value=parsed):
            batch = gemma.call_with_retry(row, None, None, 'mock', 1000)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(batch['validation_errors'], [])
        self.assertEqual(batch['parsed']['results'][0]['verdict'], 'UNDETERMINED')
        self.assertEqual(len(batch['reading_quality_guards']), 1)


if __name__ == '__main__':
    unittest.main()
