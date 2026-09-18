# -*- coding: utf-8 -*-
import json
import sys
import unittest
import copy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

import run_gemma_exhaustive_dgx as gemma  # noqa: E402
from rag.judgment.condition_contracts import (  # noqa: E402
    VERSION,
    audit_v2_source_items,
    compile_condition_contract,
)


def rule(*, guides=None, template_required=None, guide=None):
    return {
        "item_id": "D-X",
        "title": "대상 한정 규칙",
        "question": "특정 담당 주체의 정보를 표시하지 않았는가?",
        "criterion": "해당 주체일 때만 표시 금지를 검사한다.",
        "product_groups": ["전체"],
        "product_subtype": None,
        "decision_guides": guides or [],
        "template_required": template_required,
        "guide": guide,
    }


def request_with_contract(contract):
    payload = {
        "routing": {
            "product_group": {
                "candidate_product_groups": ["대출성"],
                "routing_provisional": False,
                "hard_route": True,
            }
        },
        "documents": [{
            "evidence_id": "E-CANON",
            "line_refs": ["L-CANON"],
            "text": "특정 담당 주체",
        }],
        "evidence_scope": {
            "D-X": {"evidence_ids": ["E-CANON"], "complete_ad_scan": True}
        },
        "rules": [{"item_id": "D-X", "condition_contract": contract}],
    }
    return {
        "request_id": "REQ",
        "ad_id": "AD",
        "category": "PROHIBIT",
        "requested_item_ids": ["D-X"],
        "messages": [
            {"role": "system", "content": "test"},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    }


def judgment(*, scope_status="MATCHED", applicability="APPLICABLE", condition_checks=None):
    return {
        "ad_id": "AD",
        "results": [{
            "item_id": "D-X",
            "scope_check": {
                "scope_ref": "SCOPE",
                "status": scope_status,
            },
            "condition_checks": condition_checks or [],
            "review_condition_checks": [],
            "applicability": applicability,
            "applicability_basis": (
                "ADVERTISEMENT_EVIDENCE" if applicability == "APPLICABLE"
                else applicability
            ),
            "applicability_evidence_ids": ["E-CANON"],
            "applicability_evidence_line_refs": ["L-CANON"],
            "applicability_metadata_fields": [],
            "verdict": "COMPLIANT" if applicability == "APPLICABLE" else applicability,
            "evidence_ids": ["E-CANON"],
            "evidence_line_refs": ["L-CANON"],
            "requirement_checks": [{
                "obligation_ref": "O1",
                "requirement": "의무",
                "status": "SATISFIED" if applicability == "APPLICABLE" else applicability,
                "finding_basis": "OBSERVED" if applicability == "APPLICABLE" else "UNKNOWN",
                "evidence_ids": ["E-CANON"],
                "evidence_line_refs": ["L-CANON"],
                "reason": "확인",
            }],
            "reason": "확인",
            "confidence": "HIGH",
            "needs_researcher_review": False,
        }],
    }


class ConditionContractCompilationTests(unittest.TestCase):
    def test_published_v2_schema_declares_compiler_fields(self):
        schema = json.loads((ROOT / 'schemas/rule-applicability-contract-v2.schema.json').read_text(encoding='utf-8'))
        contract = compile_condition_contract(rule(guides=[{'requirements': ['필수 요소']}]))
        self.assertEqual(schema['properties']['schema_version']['const'], contract['schema_version'])
        self.assertFalse(set(schema['required']) - set(contract))
        self.assertFalse(set(contract) - set(schema['properties']))
        self.assertIn('obligation_checks', schema['required'])

    def test_source_note_is_part_of_scope_and_hash(self):
        base = rule()
        before = compile_condition_contract(base)
        base['v2_note'] = '개별 항목 검사는 제외하고 원문에 명시된 범위만 검사한다.'
        after = compile_condition_contract(base)
        self.assertIn(base['v2_note'], after['scope_text'])
        self.assertNotEqual(before['scope_source_sha256'], after['scope_source_sha256'])
        payload, _ = gemma._compact_model_request(request_with_contract(after))
        wire = json.loads(payload[1]['content'])['rules'][0]
        self.assertIn(base['v2_note'], wire['condition_contract']['scope_text'])
        self.assertEqual(wire['output_check_refs']['requirement_checks'], ['O1'])
        self.assertNotIn('obligation', wire['condition_contract'])
        self.assertIn('obligation', after)  # Frozen source was not mutated.

    def test_explicit_requirements_not_examples_become_checks(self):
        base = rule(guides=[{'guide_id': 'G-SYNTHETIC', 'requirements': ['기간 표시', '금액 표시'],
            'compliant_examples': ['예시 금액 123원'], 'applicability_conditions': [], 'review_conditions': []}])
        contract = compile_condition_contract(base)
        self.assertEqual([r['obligation_id'] for r in contract['obligation_checks']], ['O1', 'O2', 'O3'])
        self.assertNotIn('예시 금액 123원', str(contract['obligation_checks']))
        changed = copy.deepcopy(base)
        changed['decision_guides'][0]['requirements'].append('대상 표시')
        self.assertNotEqual(contract['scope_source_sha256'], compile_condition_contract(changed)['scope_source_sha256'])

    def test_compound_or_alternative_source_is_not_split_by_conjunction(self):
        base = rule()
        base['criterion'] = '금액 또는 비율 중 하나를 표시하되, 조건이 있는 경우에만 기간을 확인한다.'
        contract = compile_condition_contract(base)
        self.assertEqual(len(contract['obligation_checks']), 1)
        self.assertEqual(contract['obligation_checks'][0]['text'], base['criterion'])

    def test_source_scoped_rule_keeps_full_source_scope_without_conditions(self):
        contract = compile_condition_contract(rule())
        self.assertEqual(contract["schema_version"], VERSION)
        self.assertEqual(contract["applicability_mode"], "SOURCE_SCOPED")
        self.assertEqual(contract["applicability_conditions"], [])
        self.assertIn("특정 담당 주체", contract["scope_text"])
        self.assertIn("해당 주체일 때만", contract["scope_text"])

    def test_required_template_is_unconditional_inside_confirmed_template(self):
        value = rule(template_required="O")
        value["source_sheet"] = "HWPX_TEMPLATE"
        contract = compile_condition_contract(value)
        self.assertEqual(contract["applicability_mode"], "UNCONDITIONAL")

    def test_source_audit_rejects_duplicate_ids(self):
        item = {
            "id": "D-X",
            "title": "제목",
            "question": "질문",
            "criterion": "기준",
            "적용상품": ["전체"],
        }
        with self.assertRaisesRegex(ValueError, "duplicate"):
            audit_v2_source_items([item, dict(item)])

    def test_bound_guide_conditions_are_individually_enumerated(self):
        contract = compile_condition_contract(rule(guides=[{
            "applicability_conditions": ["조건 하나", "조건 둘"],
            "review_conditions": [],
        }]))
        self.assertEqual(contract["applicability_mode"], "CONDITIONAL")
        self.assertEqual(
            [row["condition_id"] for row in contract["applicability_conditions"]],
            ["A1", "A2"],
        )

    def test_conditional_template_uses_its_own_guidance(self):
        contract = compile_condition_contract(
            rule(template_required="△", guide="금리를 표시한 경우에만 기재")
        )
        self.assertEqual(contract["applicability_mode"], "CONDITIONAL")
        self.assertEqual(contract["applicability_conditions"][0]["text"], "금리를 표시한 경우에만 기재")

    def test_template_exemption_is_distinguished_from_trigger(self):
        exemption = rule(template_required="△", guide="앱/웹 계산기 기능이 있는 경우 생략 가능")
        exemption["source_sheet"] = "HWPX_TEMPLATE"
        trigger = rule(template_required="△", guide="생성형 AI 활용 시 필수")
        trigger["source_sheet"] = "HWPX_TEMPLATE"

        self.assertEqual(
            compile_condition_contract(exemption)["applicability_conditions"][0]["condition_role"],
            "EXEMPTION",
        )
        self.assertEqual(
            compile_condition_contract(trigger)["applicability_conditions"][0]["condition_role"],
            "TRIGGER",
        )


class ConditionContractValidationTests(unittest.TestCase):
    def multiple_contract(self):
        return compile_condition_contract(rule(guides=[{
            'guide_id': 'G-SYNTHETIC', 'requirements': ['기간 표시', '금액 표시'],
            'applicability_conditions': [], 'review_conditions': []}]))

    def complete_judgment(self):
        value = judgment()
        first = value['results'][0]['requirement_checks'][0]
        value['results'][0]['requirement_checks'] = [
            {**copy.deepcopy(first), 'obligation_ref': f'O{i}', 'requirement': text}
            for i, text in enumerate(['전체 기준', '기간', '금액'], 1)]
        return value

    def test_summary_check_cannot_replace_all_required_elements(self):
        errors = gemma.validate(request_with_contract(self.multiple_contract()), judgment())
        self.assertTrue(any('obligation_checks 누락' in error for error in errors))

    def test_each_explicit_element_passes_and_duplicates_or_unknown_fail(self):
        request = request_with_contract(self.multiple_contract())
        self.assertEqual(gemma.validate(request, self.complete_judgment()), [])
        for ref in ('O1', 'O999', None):
            value = self.complete_judgment()
            value['results'][0]['requirement_checks'][2]['obligation_ref'] = ref
            self.assertTrue(any('obligation_checks 누락' in error for error in gemma.validate(request, value)))

    def test_one_unknown_element_prevents_total_compliance(self):
        value = self.complete_judgment()
        value['results'][0]['requirement_checks'][1].update(status='UNDETERMINED', finding_basis='UNKNOWN')
        errors = gemma.validate(request_with_contract(self.multiple_contract()), value)
        self.assertTrue(any('구성요소 미충족' in error for error in errors))

    def test_independent_violation_cannot_be_hidden_by_unknown_other_obligation(self):
        for category in ('PRESENCE', 'PROHIBIT', 'STYLE'):
            with self.subTest(category=category):
                request = request_with_contract(self.multiple_contract())
                request['category'] = category
                value = self.complete_judgment()
                result = value['results'][0]
                result.update(verdict='UNDETERMINED', needs_researcher_review=True)
                result['requirement_checks'][0].update(status='VIOLATED', finding_basis='OBSERVED')
                result['requirement_checks'][1].update(status='UNDETERMINED', finding_basis='UNKNOWN')
                self.assertTrue(any('전체 verdict 불일치' in error for error in gemma.validate(request, value)))
                result['verdict'] = 'VIOLATION'
                self.assertEqual(gemma.validate(request, value), [])

    def test_unknown_without_confirmed_violation_stays_unknown(self):
        value = self.complete_judgment()
        value['results'][0].update(verdict='UNDETERMINED', needs_researcher_review=True)
        value['results'][0]['requirement_checks'][1].update(status='UNDETERMINED', finding_basis='UNKNOWN')
        self.assertEqual(gemma.validate(request_with_contract(self.multiple_contract()), value), [])

    def test_unknown_placeholder_preserves_all_source_obligations(self):
        value = judgment()
        value['results'][0].update(verdict='UNDETERMINED', requirement_checks=[])
        request = request_with_contract(self.multiple_contract())
        self.assertTrue(gemma.normalize_contract_sentinels(value, request))
        checks = value['results'][0]['requirement_checks']
        self.assertEqual([c['obligation_ref'] for c in checks], ['O1', 'O2', 'O3'])
        self.assertTrue(all(c['status'] == 'UNDETERMINED' for c in checks))
        self.assertEqual(gemma.validate(request, value), [])

    def test_success_is_never_filled_with_unchecked_source_obligations(self):
        value = judgment()
        value['results'][0]['requirement_checks'] = []
        gemma.normalize_contract_sentinels(value, request_with_contract(self.multiple_contract()))
        self.assertEqual(value['results'][0]['requirement_checks'], [])

    def test_obligation_order_is_repaired_without_inventing_checks(self):
        value = self.complete_judgment()
        original = copy.deepcopy(value['results'][0]['requirement_checks'])
        value['results'][0]['requirement_checks'].reverse()
        request = request_with_contract(self.multiple_contract())
        self.assertTrue(gemma.normalize_contract_sentinels(value, request))
        self.assertEqual(value['results'][0]['requirement_checks'], original)
        self.assertEqual(gemma.validate(request, value), [])

    def test_scope_check_is_required_before_obligation_verdict(self):
        contract = compile_condition_contract(rule())
        value = judgment()
        del value["results"][0]["scope_check"]
        errors = gemma.validate(request_with_contract(contract), value)
        self.assertIn("D-X: source scope 확인 누락", errors)

    def test_scope_mismatch_cannot_be_applicable(self):
        contract = compile_condition_contract(rule())
        errors = gemma.validate(
            request_with_contract(contract), judgment(scope_status="NOT_MATCHED")
        )
        self.assertTrue(any("APPLICABLE 금지" in error for error in errors))

    def test_not_applicable_scope_needs_no_obligation_check(self):
        contract = compile_condition_contract(rule())
        value = judgment(scope_status="NOT_MATCHED", applicability="NOT_APPLICABLE")
        result = value["results"][0]
        result["applicability_basis"] = "NOT_APPLICABLE"
        result["verdict"] = "NOT_APPLICABLE"
        result["requirement_checks"] = []
        self.assertEqual(gemma.validate(request_with_contract(contract), value), [])

    def test_every_explicit_condition_must_be_returned_and_satisfied(self):
        contract = compile_condition_contract(rule(guides=[{
            "applicability_conditions": ["특정 상황일 때"],
            "review_conditions": [],
        }]))
        missing = gemma.validate(request_with_contract(contract), judgment())
        self.assertTrue(any("condition_checks 누락" in error for error in missing))
        failed = gemma.validate(
            request_with_contract(contract),
            judgment(condition_checks=[{
                "condition_ref": "A1",
                "status": "NOT_SATISFIED",
            }]),
        )
        self.assertTrue(any("APPLICABLE 금지" in error for error in failed))

    def test_matching_scope_and_conditions_pass_condition_guard(self):
        contract = compile_condition_contract(rule(guides=[{
            "applicability_conditions": ["특정 상황일 때"],
            "review_conditions": [],
        }]))
        errors = gemma.validate(
            request_with_contract(contract),
            judgment(condition_checks=[{
                "condition_ref": "A1",
                "status": "SATISFIED",
            }]),
        )
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
