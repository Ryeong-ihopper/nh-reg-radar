"""Synthetic wire checks: structural decoding must not choose a legal verdict."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_operational_rag_contracts import gemma, request_row, result
from rag.judgment.grounding import grounded_source_excerpt_present, grounding_errors
from rag.judgment.output_contract import response_format


class OutputContractTests(unittest.TestCase):
    def focused_fixture(self):
        row = request_row(['TEST-A', 'TEST-B'])
        payload = json.loads(row['messages'][1]['content'])
        payload['documents'][0]['line_texts'] = {'L-1': '테스트 근거'}
        payload['documents'][0]['labels'] = ['보조 검색 라벨']
        payload['full_ad_text'] = '허용 근거 밖 전문'
        payload['documents'].append({'evidence_id': 'OTHER', 'line_refs': [], 'text': '다른 항목 근거'})
        payload['evidence_scope'] = {'TEST-A': {'evidence_ids': ['E-1']},
                                     'TEST-B': {'evidence_ids': ['E-1', 'OTHER']}}
        payload['rules'][0]['condition_contract'] = {'applicability_mode': 'UNCONDITIONAL'}
        row['messages'][1]['content'] = json.dumps(payload)
        unknown = result('TEST-A')
        unknown.update(verdict='UNDETERMINED', evidence_ids=[], evidence_line_refs=[],
                       needs_researcher_review=True)
        unknown['requirement_checks'][0].update(status='UNKNOWN', finding_basis='UNKNOWN',
                                               evidence_ids=[], evidence_line_refs=[])
        batch = {'parsed': {'ad_id': row['ad_id'], 'results': [unknown, result('TEST-B')]},
                 'model_parsed': {'original': True}, 'validation_errors': [], 'call_history': []}
        return row, payload, batch

    def test_focus_uses_only_existing_scope_preserves_neighbor_and_audit(self):
        row, _, batch = self.focused_fixture()
        frozen_row, frozen_batch = copy.deepcopy(row), copy.deepcopy(batch)
        retry = {'parsed': {'ad_id': row['ad_id'], 'results': [result('TEST-A')]},
                 'validation_errors': [], 'usage': {'total_tokens': 7}}
        retry['parsed']['results'][0].update(scope_check={'scope_ref': None, 'status': 'MATCHED'},
                                             condition_checks=[], review_condition_checks=[])
        with patch.object(gemma, 'call_with_retry', return_value=retry) as call:
            updated = gemma.focus_unresolved_source_checks(row, batch, None, None, 'test', 100)
        isolated = call.call_args.args[0]
        self.assertEqual(isolated['requested_item_ids'], ['TEST-A'])
        self.assertEqual(len(isolated['messages']), 3)
        focused_payload = json.loads(isolated['messages'][1]['content'])
        self.assertNotIn('full_ad_text', focused_payload)
        self.assertNotIn('labels', focused_payload['documents'][0])
        self.assertEqual([d['evidence_id'] for d in json.loads(isolated['messages'][1]['content'])['documents']], ['E-1'])
        self.assertEqual(updated['parsed']['results'][0]['verdict'], 'COMPLIANT')
        self.assertEqual(updated['parsed']['results'][1], batch['parsed']['results'][1])
        self.assertEqual(updated['model_parsed'], batch['model_parsed'])
        self.assertEqual(updated['source_focus_attempts'][0]['response'], retry)
        self.assertEqual(updated['source_focus_attempts'][0]['request'], isolated)
        self.assertEqual(updated['call_history'][0]['usage']['total_tokens'], 7)
        self.assertEqual(updated['source_focus_applied'], ['TEST-A'])
        self.assertEqual(row, frozen_row)
        self.assertEqual(batch, frozen_batch)

    def test_focus_does_not_replace_unknown_invalid_or_inapplicable(self):
        for mode in ('unknown', 'invalid', 'not_applicable', 'exception'):
            with self.subTest(mode=mode):
                row, _, batch = self.focused_fixture()
                retry = {'parsed': {'ad_id': row['ad_id'], 'results': [copy.deepcopy(batch['parsed']['results'][0])]},
                         'validation_errors': []}
                if mode == 'invalid':
                    retry['validation_errors'] = ['invalid reference']
                if mode == 'not_applicable':
                    retry['parsed']['results'][0]['verdict'] = 'NOT_APPLICABLE'
                with patch.object(gemma, 'call_with_retry', return_value=retry,
                                  side_effect=RuntimeError('timeout') if mode == 'exception' else None) as call:
                    updated = gemma.focus_unresolved_source_checks(row, batch, None, None, 'test', 100)
                self.assertEqual(call.call_count, 1)
                self.assertEqual(updated['parsed'], batch['parsed'])
                self.assertEqual(updated['source_focus_applied'], [])

    def test_focus_records_existing_contract_correction_calls(self):
        row, _, batch = self.focused_fixture()
        valid = {'parsed': {'ad_id': row['ad_id'], 'results': [result('TEST-A')]},
                 'validation_errors': [], 'usage': {'total_tokens': 7}}
        valid['parsed']['results'][0].update(scope_check={'scope_ref': None, 'status': 'MATCHED'},
                                             condition_checks=[], review_condition_checks=[])
        invalid = {'validation_errors': ['quoted text not on cited line'], 'usage': {'total_tokens': 3}}
        with patch.object(gemma, 'call_once', side_effect=[invalid, valid]) as call:
            updated = gemma.focus_unresolved_source_checks(row, batch, None, None, 'test', 100)
        self.assertEqual(call.call_count, 2)
        self.assertEqual(updated['source_focus_applied'], ['TEST-A'])
        self.assertEqual(sum(event['usage']['total_tokens'] for event in updated['call_history']), 10)
        self.assertTrue(all(event['purpose'] == 'isolated_source_judgment' for event in updated['call_history']))

    def test_focus_skips_guarded_conditional_external_and_other_requests(self):
        for mode in ('guarded', 'conditional', 'external', 'unsafe', 'other_category'):
            with self.subTest(mode=mode):
                row, payload, batch = self.focused_fixture()
                if mode == 'guarded':
                    batch['parsed']['results'][0]['reading_quality_review'] = {'status': 'REVIEW'}
                if mode == 'conditional':
                    payload['rules'][0]['condition_contract']['applicability_conditions'] = ['A1']
                if mode == 'external':
                    payload['external_input_assessment'] = {'TEST-A': {'input_mode': 'EXTERNAL'}}
                if mode == 'unsafe':
                    payload['documents'][0]['text_selection'] = {'needs_review': True}
                if mode == 'other_category':
                    row['category'] = 'CONSISTENCY'
                row['messages'][1]['content'] = json.dumps(payload)
                with patch.object(gemma, 'call_with_retry') as call:
                    updated = gemma.focus_unresolved_source_checks(row, batch, None, None, 'test', 100)
                call.assert_not_called()
                self.assertIs(updated, batch)

    def test_focus_includes_source_scoped_presence_and_source_arithmetic(self):
        for category in ('PRESENCE', 'PROHIBIT'):
            row, payload, batch = self.focused_fixture()
            row['category'] = category
            payload['rules'][0]['condition_contract']['applicability_mode'] = 'SOURCE_SCOPED'
            if category == 'PROHIBIT':
                payload['rules'][0]['condition_contract']['obligation_checks'] = [{'text': '표기된 합산 결과 검산'}]
            batch['parsed']['results'][0]['evidence_line_refs'] = ['L-1']
            row['messages'][1]['content'] = json.dumps(payload)
            with patch.object(gemma, 'call_with_retry', return_value={'parsed': {}, 'validation_errors': []}) as call:
                updated = gemma.focus_unresolved_source_checks(row, batch, None, None, 'test', 100)
            self.assertEqual(call.call_count, 1)
            self.assertEqual(updated['parsed'], batch['parsed'])

    def test_canonical_focus_observes_unknown_leaf_without_reopening_scope(self):
        row, payload, batch = self.focused_fixture()
        contract = payload['rules'][0]['condition_contract']
        contract.update(review_program={'mode': 'AUTOMATIC', 'kinds': ['PRESENCE']},
            applicability_conditions=[{'condition_id': 'A1'}],
            obligation_checks=[{'obligation_id': 'O1', 'owners': {'llm': True}}])
        batch['parsed']['results'][0]['requirement_checks'][0].update(
            obligation_ref='O1', status='UNDETERMINED')
        payload['external_input_assessment'] = {'TEST-A': {'input_mode': 'EXTERNAL'}}
        row['messages'][1]['content'] = json.dumps(payload)
        original = copy.deepcopy(batch)
        retry = {'parsed': {}, 'validation_errors': []}
        with patch.object(gemma, 'call_with_retry', return_value=retry) as call:
            updated = gemma.focus_unresolved_source_checks(row, batch, None, None, 'test', 100)
        call.assert_called_once()
        focused = json.loads(call.call_args.args[0]['messages'][1]['content'])
        self.assertEqual('허용 근거 밖 전문', focused['full_ad_text'])
        self.assertEqual(contract, focused['rules'][0]['condition_contract'])
        self.assertNotIn('labels', focused['documents'][0])
        self.assertEqual(original['parsed'], updated['parsed'])
        self.assertEqual([], updated['source_focus_applied'])
        self.assertEqual(batch, original)

    def test_canonical_focus_skips_human_external_calculation_and_guarded_unknowns(self):
        for kind in ('human', 'external_input', 'computed', 'reading', 'inapplicable', 'invalid', 'branch', 'semantic'):
            with self.subTest(kind=kind):
                row, payload, batch = self.focused_fixture()
                atom = {'obligation_id': 'O1', 'owners': {'llm': True}}
                payload['rules'][0]['condition_contract'].update(
                    review_program={'mode': 'AUTOMATIC', 'kinds': ['PRESENCE']},
                    applicability_conditions=[{'condition_id': 'A1'}], obligation_checks=[atom])
                judgment = batch['parsed']['results'][0]
                judgment['requirement_checks'][0].update(obligation_ref='O1', status='UNDETERMINED')
                if kind in {'human', 'external_input'}:
                    atom['owners'][kind] = True
                elif kind == 'computed':
                    atom['deterministic_adapter'] = {'kind': 'BASIS_DATE_WITHIN'}
                elif kind == 'reading':
                    judgment['reading_quality_review'] = {'status': 'REVIEW'}
                elif kind == 'inapplicable':
                    judgment['applicability'] = 'UNDETERMINED'
                elif kind == 'branch':
                    payload['rules'][0]['condition_contract']['decision_fact_ids'] = ['B1']
                elif kind == 'semantic':
                    payload['rules'][0]['condition_contract']['review_program']['kinds'] = ['SEMANTIC']
                else:
                    batch['validation_errors'] = ['invalid evidence reference']
                row['messages'][1]['content'] = json.dumps(payload)
                with patch.object(gemma, 'call_with_retry') as call:
                    updated = gemma.focus_unresolved_source_checks(row, batch, None, None, 'test', 100)
                call.assert_not_called()
                self.assertIs(updated, batch)

    def test_source_marked_presence_violation_gets_isolated_source_recheck(self):
        row, payload, batch = self.focused_fixture()
        original = batch['parsed']['results'][0]
        original.update(verdict='VIOLATION', needs_researcher_review=True)
        original['requirement_checks'][0].update(
            status='MISSING', finding_basis='ABSENCE', evidence_ids=[], evidence_line_refs=[])
        payload['rules'][0]['template_basis'] = {
            'methodology': {'decision_mode': 'PRESENCE_ONLY'}
        }
        row['messages'][1]['content'] = json.dumps(payload)
        retry_result = result('TEST-A')
        retry_result.update(scope_check={'scope_ref': None, 'status': 'MATCHED'},
                            condition_checks=[], review_condition_checks=[])
        retry = {'parsed': {'ad_id': row['ad_id'], 'results': [retry_result]},
                 'validation_errors': []}
        with patch.object(gemma, 'call_with_retry', return_value=retry) as call:
            updated = gemma.focus_unresolved_source_checks(
                row, batch, None, None, 'test', 100)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(updated['parsed']['results'][0]['verdict'], 'COMPLIANT')
        self.assertIn('[판정방식: 존재확인]', call.call_args.args[0]['messages'][-1]['content'])

    def test_unmarked_presence_violation_is_not_retried(self):
        row, payload, batch = self.focused_fixture()
        batch['parsed']['results'][0].update(verdict='VIOLATION', needs_researcher_review=True)
        batch['parsed']['results'][0]['requirement_checks'][0].update(
            status='MISSING', finding_basis='ABSENCE', evidence_ids=[], evidence_line_refs=[])
        row['messages'][1]['content'] = json.dumps(payload)
        with patch.object(gemma, 'call_with_retry') as call:
            updated = gemma.focus_unresolved_source_checks(
                row, batch, None, None, 'test', 100)
        call.assert_not_called()
        self.assertIs(updated, batch)

    def test_presence_absence_claim_cannot_use_violated_observed(self):
        row = request_row(['TEST-A'])
        payload = json.loads(row['messages'][1]['content'])
        payload['documents'][0].update(
            line_texts={'L-1': '고객투자유의사항'},
            span_status='parser_line_exact',
            text_selection={'needs_review': False},
        )
        payload['evidence_scope'] = {
            'TEST-A': {'evidence_ids': ['E-1'], 'complete_ad_scan': True}
        }
        row['messages'][1]['content'] = json.dumps(payload, ensure_ascii=False)
        judgment = result('TEST-A')
        judgment.update(
            verdict='VIOLATION', reason='설명받을 권리 안내 문구가 누락되었습니다.',
            needs_researcher_review=True,
        )
        judgment['requirement_checks'][0].update(
            status='VIOLATED', finding_basis='OBSERVED',
            reason='설명받을 권리에 대한 안내 문구가 확인되지 않습니다.',
        )
        parsed = {'ad_id': row['ad_id'], 'results': [judgment]}
        errors = gemma.validate(row, parsed)
        self.assertTrue(any('표시의무 누락을 VIOLATED+OBSERVED로 우회함' in error
                            for error in errors))
        instruction = gemma.retry_contract_instruction(row, errors)
        self.assertIn('동일 취지 문구가 있으면 SATISFIED+OBSERVED', instruction)

    def test_presence_observed_violation_without_absence_claim_remains_valid(self):
        row = request_row(['TEST-A'])
        payload = json.loads(row['messages'][1]['content'])
        payload['documents'][0].update(
            line_texts={'L-1': '광고에 허용되지 않은 확정 표현'},
            span_status='parser_line_exact',
            text_selection={'needs_review': False},
        )
        payload['evidence_scope'] = {
            'TEST-A': {'evidence_ids': ['E-1'], 'complete_ad_scan': True}
        }
        row['messages'][1]['content'] = json.dumps(payload, ensure_ascii=False)
        judgment = result('TEST-A')
        judgment.update(
            verdict='VIOLATION', reason='허용되지 않은 확정 표현이 관찰되었습니다.',
            needs_researcher_review=True,
        )
        judgment['requirement_checks'][0].update(
            status='VIOLATED', finding_basis='OBSERVED',
            reason='허용되지 않은 확정 표현이 관찰되었습니다.',
        )
        parsed = {'ad_id': row['ad_id'], 'results': [judgment]}
        self.assertFalse(any('표시의무 누락을 VIOLATED+OBSERVED로 우회함' in error
                             for error in gemma.validate(row, parsed)))

    def test_focus_single_request_does_not_mutate_original_messages(self):
        row, payload, batch = self.focused_fixture()
        row['requested_item_ids'] = ['TEST-A']
        payload['rules'] = payload['rules'][:1]
        row['messages'][1]['content'] = json.dumps(payload)
        batch['parsed']['results'] = batch['parsed']['results'][:1]
        frozen = copy.deepcopy(row)
        with patch.object(gemma, 'call_with_retry', return_value={'parsed': {}, 'validation_errors': []}) as call:
            gemma.focus_unresolved_source_checks(row, batch, None, None, 'test', 100)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(row, frozen)

    def test_uncertain_candidates_are_preserved_but_not_citable(self):
        row = request_row(['TEST-A'])
        payload = json.loads(row['messages'][1]['content'])
        readable = payload['documents'][0]
        readable['line_texts'] = {'L-1': '독립적으로 읽힌 회사명 문장'}
        unsafe = {**copy.deepcopy(readable), 'evidence_id': 'E-uncertain', 'line_refs': ['L-unsafe'],
                  'line_texts': {'L-unsafe': '불확실한 로고'}, 'text': '불확실한 로고',
                  'text_selection': {'needs_review': True}}
        payload['documents'].insert(0, unsafe)
        payload['evidence_scope'] = {'TEST-A': {'evidence_ids': ['E-uncertain', 'E-1'], 'complete_ad_scan': True}}
        row['messages'][1]['content'] = json.dumps(payload)
        frozen = copy.deepcopy(row)
        messages, aliases = gemma._compact_model_request(row)
        wire = json.loads(messages[1]['content'])
        self.assertEqual(aliases['ref_to_evidence'], {'E1': 'E-1'})
        self.assertEqual(aliases['ref_to_line'], {'L1': 'L-1'})
        # A local uncertain selection stays non-citable without falsely
        # downgrading the completed scan of the rest of the advertisement.
        self.assertTrue(wire['evidence_scope']['R1']['complete_ad_scan'])
        self.assertEqual(wire['evidence_scope']['R1']['line_refs'], ['L1'])
        self.assertEqual(wire['evidence_scope']['R1']['evidence_refs'], ['L1'])
        schema = response_format(wire)['json_schema']['schema']
        self.assertEqual(schema['properties']['results']['items']['properties']['scope_check']
                         ['properties']['evidence_refs']['items']['enum'], ['L1'])
        self.assertEqual(wire['uncertain_context'][0]['text'], '불확실한 로고')
        self.assertFalse(wire['uncertain_context'][0]['citable'])
        self.assertEqual(row, frozen)
        readable['text_selection'] = {'needs_review': True}
        row['messages'][1]['content'] = json.dumps(payload)
        messages, aliases = gemma._compact_model_request(row)
        self.assertEqual(aliases['ref_to_line'], {})
        self.assertEqual(json.loads(messages[1]['content'])['documents'], [])

    def test_observed_compliance_requires_exact_line_when_supplied(self):
        row = request_row(['TEST-A'])
        payload = json.loads(row['messages'][1]['content'])
        payload['documents'][0]['line_texts'] = {'L-1': '테스트 근거'}
        row['messages'][1]['content'] = json.dumps(payload)
        judgment = result('TEST-A')
        judgment['requirement_checks'][0]['evidence_line_refs'] = []
        parsed = {'ad_id': row['ad_id'], 'results': [judgment]}
        self.assertTrue(any('원본 줄을 직접' in error for error in gemma.validate(row, parsed)))
        judgment['requirement_checks'][0]['evidence_line_refs'] = ['L-1']
        self.assertEqual(gemma.validate(row, parsed), [])
        payload['documents'][0]['span_status'] = 'region_level_selected_text'
        row['messages'][1]['content'] = json.dumps(payload)
        judgment['requirement_checks'][0]['evidence_line_refs'] = []
        self.assertEqual(gemma.validate(row, parsed), [])
        # Legacy region-only text does not acquire a fabricated exact line.
        payload['documents'][0].pop('line_texts')
        row['messages'][1]['content'] = json.dumps(payload)
        judgment['requirement_checks'][0]['evidence_line_refs'] = []
        self.assertEqual(gemma.validate(row, parsed), [])

    def setUp(self):
        self.env = patch.dict(os.environ, {"NH_JUDGE_RESPONSE_FORMAT": "json_schema"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.row = request_row(["TEST-A"])
        p = json.loads(self.row["messages"][1]["content"])
        p["rules"][0]["condition_contract"] = {"applicability_conditions": [],
            "review_conditions": [], "obligation_checks": [{"obligation_id": "O1"}]}
        p["evidence_scope"] = {"TEST-A": {"evidence_ids": ["E-1"], "complete_ad_scan": False}}
        self.row["messages"][1]["content"] = json.dumps(p)
        messages, _ = gemma._compact_model_request(self.row)
        self.compact = json.loads(messages[1]["content"])
        self.schema = response_format(self.compact)["json_schema"]["schema"]
        self.result_schema = self.schema["properties"]["results"]["items"]

    def sample(self):
        return {"results": [{"rule_ref": "R1", "scope_check": {"scope_ref": "SCOPE",
            "status": "UNDETERMINED", "evidence_refs": [], "metadata_fields": []},
            "condition_checks": [], "review_condition_checks": [],
            "verdict": "UNDETERMINED", "requirement_checks": [],
            "reason": "추가 입력 필요", "confidence": "LOW"}]}

    def test_review_date_survives_compact_wire_projection(self):
        payload = json.loads(self.row['messages'][1]['content'])
        payload['review_context'] = {'review_date': '2026-04-12', 'date_basis': 'review_request_date'}
        self.row['messages'][1]['content'] = json.dumps(payload)
        messages, _ = gemma._compact_model_request(self.row)
        self.assertEqual(json.loads(messages[1]['content'])['review_context'], payload['review_context'])

    def test_wire_uses_bound_obligations_without_competing_auxiliary_visual_guidance(self):
        payload = json.loads(self.row['messages'][1]['content'])
        rule = payload['rules'][0]
        rule.update(standard_guidance='다른 범위의 표준 안내', guide='한 줄 배치',
                    template_basis={'text_facet_only': True, 'source_ref': 'source/row1',
                                    'fields': {'guidance': '한 줄 배치'}, 'manual_guidance': '한 줄 배치'})
        self.row['messages'][1]['content'] = json.dumps(payload)
        frozen = copy.deepcopy(self.row)
        messages, _ = gemma._compact_model_request(self.row)
        wire = json.loads(messages[1]['content'])['rules'][0]
        self.assertNotIn('standard_guidance', wire)
        self.assertNotIn('guide', wire)
        self.assertNotIn('fields', wire['template_basis'])
        self.assertTrue(wire['template_basis']['text_facet_only'])
        self.assertEqual(wire['template_basis']['source_ref'], 'source/row1')
        self.assertEqual(self.row, frozen)

    def test_empty_or_missing_result_rejected(self):
        self.assertEqual(self.schema["required"], ["results"])
        array = self.schema["properties"]["results"]
        self.assertEqual((array["minItems"], array["maxItems"]), (1, 1))
        self.assertEqual(set(self.result_schema["required"]), set(self.sample()["results"][0]))
        self.assertFalse(self.result_schema["additionalProperties"])

    def test_unknown_gate_can_abstain_without_obligations(self):
        props = self.result_schema["properties"]
        self.assertIn("UNDETERMINED", props["scope_check"]["properties"]["status"]["enum"])
        self.assertEqual(props["requirement_checks"].get("minItems", 0), 0)

    def test_all_verdicts_remain_possible(self):
        for verdict, status, basis in (("COMPLIANT", "SATISFIED", "OBSERVED"),
                ("VIOLATION", "MISSING", "ABSENCE"), ("UNDETERMINED", "UNDETERMINED", "UNKNOWN")):
            props = self.result_schema["properties"]
            checks = props["requirement_checks"]["items"]["properties"]
            self.assertIn(verdict, props["verdict"]["enum"])
            self.assertIn(status, checks["status"]["enum"])
            self.assertIn(basis, checks["finding_basis"]["enum"])
            self.assertEqual(checks["obligation_ref"]["enum"], ["O1"])

    def test_compact_and_repair_prompts_match_existing_source_quote_minimum(self):
        source = "표시 조건은 세전 기준입니다."
        short = "'세전'이 표시되어 있습니다."
        contextual = "'세전 기준'이 표시되어 있습니다."
        self.assertFalse(grounded_source_excerpt_present(short, source))
        self.assertTrue(grounded_source_excerpt_present(contextual, source))
        errors = grounding_errors(item_id="TEST-A", location="O1", reason=short,
            line_refs=["L-1"], documents=[{"line_refs": ["L-1"], "line_texts": {"L-1": source}}],
            require_source_excerpt=True)
        self.assertTrue(any("직접 인용이 없음" in error for error in errors))
        messages, _ = gemma._compact_model_request(self.row)
        system = " ".join(messages[0]["content"].split())
        self.assertIn("at least 4 non-whitespace source characters", system)
        self.assertIn("original surrounding context of a short word, value or date", system)
        for failure in (errors, ["계약 오류"]):
            instruction = gemma.retry_contract_instruction(self.row, failure)
            self.assertIn("공백을 제외한 원문 최소 4자 이상", instruction)
            self.assertIn("주변 원문 맥락", instruction)

    def test_date_comparison_prompt_keeps_advertisement_proof_separate_from_metadata(self):
        payload = json.loads(self.row["messages"][1]["content"])
        source = "기준일 2026.04.01."
        payload["review_context"] = {"review_date": "2026-04-15"}
        payload["documents"][0].update(text=source, line_texts={"L-1": source})
        payload["rules"][0]["condition_contract"]["obligation_checks"][0]["evidence"] = {
            "advertisement_direct_quote_required": True}
        self.row["messages"][1]["content"] = json.dumps(payload)
        judgment = result("TEST-A")
        judgment.update(scope_check={"scope_ref": None, "status": "MATCHED",
                                     "evidence_ids": ["E-1"], "evidence_line_refs": ["L-1"]},
                        condition_checks=[], review_condition_checks=[])
        judgment["reason"] = "'기준일 2026.04.01.'을 심의일과 비교했습니다."
        check = judgment["requirement_checks"][0]
        check.update(obligation_ref="O1", finding_basis="CONFIRMED_METADATA",
                     evidence_ids=[], evidence_line_refs=[], reason=judgment["reason"])
        parsed = {"ad_id": self.row["ad_id"], "results": [judgment]}
        errors = gemma.validate(self.row, parsed)
        self.assertTrue(any("metadata cannot establish an advertisement-only obligation" in error for error in errors))
        messages, _ = gemma._compact_model_request(self.row)
        system = " ".join(messages[0]["content"].split())
        self.assertIn("date is OBSERVED", system)
        self.assertIn("review_context.review_date can be a comparison input", system)
        self.assertIn("does not prove that a value, date or disclosure is printed", system)
        instruction = gemma.retry_contract_instruction(self.row, errors)
        self.assertIn("산술·날짜 계산도 OBSERVED", instruction)
        self.assertIn("trusted review_date는 비교 입력일 뿐", instruction)
        self.assertIn("광고 관찰을 CONFIRMED_METADATA로 바꾸지 말라", instruction)
        check.update(finding_basis="OBSERVED", evidence_ids=["E-1"], evidence_line_refs=["L-1"])
        self.assertEqual(gemma.validate(self.row, parsed), [])

    def test_complete_scan_repair_preserves_canonical_branches_and_reading_uncertainty(self):
        instruction = gemma.retry_contract_instruction(self.row, ["완료된 텍스트 전체 스캔을 미완료로 판단함"])
        self.assertIn("범위 방문 완료 정보이며 판독 불확실이 해소됐다는 뜻은 아니다", instruction)
        self.assertIn("정본 review_program", instruction)
        self.assertIn("해당 fact의 NOT_SATISFIED", instruction)
        self.assertIn("전체 applicability_logic가 NOT_APPLICABLE로 계산될 때만 제외", instruction)
        self.assertIn("decision_fact_ids는 전체 적용성 게이트가 아니므로", instruction)
        self.assertIn("독립 의무는 계속 관찰", instruction)
        self.assertIn("review_program이 없는 legacy 계약에서만", instruction)
        self.assertIn("판독이 불확실하면 UNDETERMINED+UNKNOWN", instruction)
        self.assertNotIn("선행 상황이 없으면 SCOPE=NOT_MATCHED", instruction)

    def test_unknown_alias_and_invented_condition_rejected(self):
        props = self.result_schema["properties"]
        self.assertEqual(props["scope_check"]["properties"]["evidence_refs"]["items"]["enum"], ["E1", "L1"])
        self.assertEqual(props["condition_checks"]["maxItems"], 0)
        self.assertEqual(props["review_condition_checks"]["maxItems"], 0)

    def test_format_switch_invalidates_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "input.jsonl"
            p.write_text(json.dumps(self.row), encoding="utf-8")
            checkpoint = Path(directory) / "checkpoint.json"
            checkpoint.write_text(json.dumps(gemma.checkpoint_payload(input_path=p,
                host=None, model="test", rows_by_id={})), encoding="utf-8")
            with patch.dict(os.environ, {"NH_JUDGE_RESPONSE_FORMAT": "json_object"}):
                self.assertEqual(response_format(self.compact), {"type": "json_object"})
                with self.assertRaisesRegex(RuntimeError, "response_format"):
                    gemma.load_checkpoint(checkpoint, input_path=p, host=None, model="test")

    def test_previous_attempt_checkpoint_is_reused_only_when_compatible(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "input.jsonl"
            p.write_text(json.dumps(self.row), encoding="utf-8")
            current = Path(directory) / "current.json"
            previous = Path(directory) / "previous.json"
            previous.write_text(json.dumps(gemma.checkpoint_payload(
                input_path=p, host=None, model="test", rows_by_id={"request": []}
            )), encoding="utf-8")
            loaded = gemma.load_checkpoint_for_run(
                current, previous, input_path=p, host=None, model="test"
            )
            self.assertEqual(loaded, {"request": []})
            p.write_text(json.dumps({**self.row, "request_id": "changed"}), encoding="utf-8")
            self.assertEqual(
                gemma.load_checkpoint_for_run(
                    current, previous, input_path=p, host=None, model="test"
                ),
                {},
            )

    def test_unknown_mode_rejected_not_silently_downgraded(self):
        with patch.dict(os.environ, {"NH_JUDGE_RESPONSE_FORMAT": "typo"}):
            with self.assertRaises(ValueError):
                response_format(self.compact)

    def test_nonempty_gate_contract_and_legacy_shape(self):
        p = copy.deepcopy(self.compact)
        p["rules"][0]["output_check_refs"]["condition_checks"] = ["A1"]
        p["rules"][0]["output_check_refs"].pop("requirement_checks")
        props = response_format(p)["json_schema"]["schema"]["properties"]["results"]["items"]["properties"]
        self.assertEqual(props["condition_checks"]["items"]["properties"]["condition_ref"]["enum"], ["A1"])
        self.assertNotIn("obligation_ref", props["requirement_checks"]["items"]["required"])

    def test_required_gate_entries_cannot_be_omitted_but_can_abstain(self):
        compact = copy.deepcopy(self.compact)
        compact["rules"][0]["output_check_refs"]["condition_checks"] = ["A1"]
        schema = response_format(compact)["json_schema"]["schema"]
        props = schema["properties"]["results"]["items"]["properties"]
        checks = props["condition_checks"]
        self.assertEqual((checks.get("minItems", 0), checks.get("maxItems")), (1, 1))
        self.assertIn("UNDETERMINED", checks["items"]["properties"]["status"]["enum"])
        self.assertIn("NOT_MATCHED", props["scope_check"]["properties"]["status"]["enum"])
        self.assertEqual(props["requirement_checks"].get("minItems", 0), 0)

    def test_mixed_rule_gate_lengths_keep_each_source_contract_possible(self):
        compact = copy.deepcopy(self.compact)
        second = copy.deepcopy(compact["rules"][0])
        second["rule_ref"] = "R2"
        second["output_check_refs"]["review_condition_checks"] = ["C1", "C2"]
        compact["rules"].append(second)
        schema = response_format(compact)["json_schema"]["schema"]
        checks = schema["properties"]["results"]["items"]["properties"]["review_condition_checks"]
        self.assertEqual((checks.get("minItems", 0), checks.get("maxItems")), (0, 2))
        compact["rules"][0]["output_check_refs"]["review_condition_checks"] = ["C1", "C2"]
        schema = response_format(compact)["json_schema"]["schema"]
        checks = schema["properties"]["results"]["items"]["properties"]["review_condition_checks"]
        self.assertEqual((checks["minItems"], checks["maxItems"]), (2, 2))

    def canonical_compact(self, count=8, confirmed=True, decision_branch=False):
        payload = json.loads(self.row["messages"][1]["content"])
        conditions = [{"condition_id": "A1", "owner": "RULE"}]
        if decision_branch:
            conditions.append({"condition_id": "A2", "owner": "LLM"})
        obligations = [{"obligation_id": f"O{i + 1}", "text": "Synthetic source atom"}
                       for i in range(count)]
        payload["rules"][0]["condition_contract"] = {
            "canonical_plan_ref": "synthetic-plan", "scope_owner": "RULE",
            "review_program": {"mode": "AUTOMATIC", "allowed_outcomes": [
                "COMPLIANT", "VIOLATION", "UNDETERMINED"]},
            "applicability_conditions": conditions, "applicability_logic": {"fact": "A1"},
            "decision_fact_ids": ["A2"] if decision_branch else [],
            "review_conditions": [], "obligation_checks": obligations,
            "obligation_logic": {"all": [{"ref": value["obligation_id"]} for value in obligations]},
        }
        if decision_branch:
            payload["rules"][0]["condition_contract"]["obligation_logic"] = {"if": [
                {"fact": "A2"}, {"ref": obligations[0]["obligation_id"]},
                {"all": [{"ref": value["obligation_id"]} for value in obligations[1:]]},
            ]}
        payload["canonical_confirmed_facts"] = {"TEST-A": [
            {"fact_id": "A1", "value": confirmed, "basis": "template_id"}]}
        row = copy.deepcopy(self.row)
        row["messages"][1]["content"] = json.dumps(payload)
        messages, _ = gemma._compact_model_request(row)
        return json.loads(messages[1]["content"])

    def canonical_properties(self, compact):
        return response_format(compact)["json_schema"]["schema"]["properties"]["results"]["items"]["properties"]

    def test_single_confirmed_canonical_requires_all_atoms_without_deciding_status(self):
        for count in (1, 8, 9):
            with self.subTest(count=count):
                compact = self.canonical_compact(count=count)
                frozen = copy.deepcopy(compact)
                props = self.canonical_properties(compact)
                checks = props["requirement_checks"]
                self.assertEqual((checks["minItems"], checks["maxItems"]), (count, count))
                self.assertEqual(checks["items"]["properties"]["obligation_ref"]["enum"],
                                 [f"O{i + 1}" for i in range(count)])
                self.assertEqual(checks["items"]["properties"]["status"]["enum"],
                                 ["SATISFIED", "MISSING", "VIOLATED", "UNDETERMINED"])
                self.assertIn("UNKNOWN", checks["items"]["properties"]["finding_basis"]["enum"])
                self.assertEqual(props["verdict"]["enum"], ["COMPLIANT", "VIOLATION", "UNDETERMINED"])
                self.assertEqual(compact, frozen)

    def test_unknown_decision_branch_does_not_open_confirmed_applicability_gate(self):
        compact = self.canonical_compact(decision_branch=True)
        props = self.canonical_properties(compact)
        self.assertEqual((props["requirement_checks"]["minItems"], props["requirement_checks"]["maxItems"]), (8, 8))
        self.assertEqual(props["condition_checks"]["minItems"], 2)
        self.assertIn("UNDETERMINED", props["condition_checks"]["items"]["properties"]["status"]["enum"])

    def test_unknown_or_inapplicable_canonical_gate_keeps_empty_requirements_legal(self):
        for value in (None, False, "true", "false"):
            with self.subTest(value=value):
                compact = self.canonical_compact(confirmed=value)
                checks = self.canonical_properties(compact)["requirement_checks"]
                self.assertEqual(checks.get("minItems", 0), 0)
                self.assertNotIn("maxItems", checks)
        compact = self.canonical_compact()
        compact["canonical_confirmed_facts"] = {}
        checks = self.canonical_properties(compact)["requirement_checks"]
        self.assertEqual(checks.get("minItems", 0), 0)
        self.assertNotIn("maxItems", checks)

    def test_any_gate_uses_aggregate_applicability_with_unknown_neighbor(self):
        compact = self.canonical_compact()
        contract = compact["rules"][0]["condition_contract"]
        contract["applicability_conditions"].append({"condition_id": "A2", "owner": "LLM"})
        contract["applicability_logic"] = {"any": [{"fact": "A1"}, {"fact": "A2"}]}
        checks = self.canonical_properties(compact)["requirement_checks"]
        self.assertEqual((checks["minItems"], checks["maxItems"]), (8, 8))
        contract["applicability_logic"] = {"all": [{"fact": "A1"}, {"fact": "A2"}]}
        checks = self.canonical_properties(compact)["requirement_checks"]
        self.assertEqual(checks.get("minItems", 0), 0)
        self.assertNotIn("maxItems", checks)

    def test_multi_rule_confirmed_canonical_does_not_restrict_shared_requirements(self):
        compact = self.canonical_compact()
        second = copy.deepcopy(compact["rules"][0])
        second["rule_ref"] = "R2"
        compact["rules"].append(second)
        compact["evidence_scope"]["R2"] = copy.deepcopy(compact["evidence_scope"]["R1"])
        compact["canonical_confirmed_facts"]["R2"] = copy.deepcopy(compact["canonical_confirmed_facts"]["R1"])
        checks = self.canonical_properties(compact)["requirement_checks"]
        self.assertEqual(checks.get("minItems", 0), 0)
        self.assertNotIn("maxItems", checks)

    def test_review_condition_or_noncanonical_scope_keeps_empty_requirements_legal(self):
        for mode in ("review_condition", "model_scope", "no_program", "legacy", "malformed_logic"):
            with self.subTest(mode=mode):
                compact = self.canonical_compact()
                contract = compact["rules"][0]["condition_contract"]
                if mode == "review_condition":
                    contract["review_conditions"] = [{"condition_id": "C1"}]
                elif mode == "model_scope":
                    contract["scope_owner"] = "LLM"
                elif mode == "no_program":
                    contract["review_program"] = {}
                elif mode == "legacy":
                    contract.pop("canonical_plan_ref")
                else:
                    contract["applicability_logic"] = {"fact": "unknown-fact"}
                checks = self.canonical_properties(compact)["requirement_checks"]
                self.assertEqual(checks.get("minItems", 0), 0)
                self.assertNotIn("maxItems", checks)
