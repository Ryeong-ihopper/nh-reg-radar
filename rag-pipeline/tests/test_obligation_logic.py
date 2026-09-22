from __future__ import annotations

import copy
import itertools
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools"), str(ROOT / "tests")]

from rag.judgment.obligation_logic import (  # noqa: E402
    aggregate_applicability,
    aggregate_obligations,
    validate_expression,
)
from rag.judgment.condition_contracts import (  # noqa: E402
    audit_compiled_rules,
    compile_canonical_condition_contract,
    compile_condition_contract,
)
from rag.templates.catalog import group_explicit_alternatives  # noqa: E402
import run_gemma_exhaustive_dgx as gemma  # noqa: E402
from test_operational_condition_contracts import request_with_contract, judgment, rule  # noqa: E402


def contract(operator="any"):
    return {
        "obligation_checks": [{"obligation_id": "O1"}, {"obligation_id": "O2"}],
        "obligation_logic": {operator: [{"ref": "O1"}, {"ref": "O2"}]},
    }


def checks(*states):
    return [{"obligation_ref": f"O{i}", "status": state} for i, state in enumerate(states, 1)]


def alternative_rule(group="예금성"):
    members = [
        {
            "item_id": f"TPL-SYNTHETIC{i}",
            "source_sheet": "HWPX_TEMPLATE",
            "product_subtype": f"{group}상품-합성유형",
            "product_groups": [group],
            "title": "표시방법",
            "template_required": "O",
            "guide": "",
            "example_text": f"[방식 {i}] 합성 예시 {i}",
            "criterion": f"방식 {i}의 의미요소를 확인. 원문 전체를 보존한다.",
            "template_basis": {"source_ref": f"synthetic-source#{i}", "legal_basis_refs": []},
        }
        for i in (1, 2)
    ]
    return group_explicit_alternatives(members)[0]


class ObligationLogicTests(unittest.TestCase):
    def test_applicability_logic_calculates_all_any_not_and_unknown(self):
        value = {
            "applicability_conditions": [
                {"condition_id": "A1"}, {"condition_id": "A2"}, {"condition_id": "A3"},
            ],
            "applicability_logic": {
                "all": [
                    {"fact": "A1"},
                    {"any": [{"fact": "A2"}, {"not": {"fact": "A3"}}]},
                ]
            },
        }
        def observed(*states):
            return [
                {"condition_ref": f"A{i}", "status": state}
                for i, state in enumerate(states, 1)
            ]
        self.assertEqual(
            aggregate_applicability(
                value, "MATCHED", observed("SATISFIED", "NOT_SATISFIED", "NOT_SATISFIED")
            ),
            "APPLICABLE",
        )
        self.assertEqual(
            aggregate_applicability(
                value, "MATCHED", observed("SATISFIED", "NOT_SATISFIED", "UNDETERMINED")
            ),
            "UNDETERMINED",
        )
        self.assertEqual(aggregate_applicability(value, "NOT_MATCHED", []), "NOT_APPLICABLE")

    def test_canonical_contract_preserves_every_fact_atom_owner_and_join(self):
        projected = {
            "plan_ref": "SYN-CANONICAL",
            "source_hash": "abc",
            "applicability_inputs": [
                {"fact_id": "A1", "name": "confirmed medium", "owner": "RULE",
                 "type": "CONFIRMED_METADATA", "unknown_policy": "UNDETERMINED"},
                {"fact_id": "A2", "name": "observed trigger", "owner": "LLM",
                 "type": "ADVERTISEMENT_OBSERVATION", "unknown_policy": "UNDETERMINED"},
            ],
            "applicability_logic": {"all": [{"fact": "A1"}, {"fact": "A2"}]},
            "obligations": [
                {"obligation_ref": "O1", "text": "first", "owners": {"rule": False,
                 "llm": True, "external_input": False, "human": False},
                 "evidence_contract": {"advertisement_direct_quote_required": True,
                 "absence_requires_complete_scan": True}, "interpretation_hints": []},
                {"obligation_ref": "O2", "text": "second", "owners": {"rule": True,
                 "llm": True, "external_input": True, "human": False},
                 "evidence_contract": {"advertisement_direct_quote_required": True,
                 "absence_requires_complete_scan": True}, "interpretation_hints": []},
            ],
            "obligation_logic": {"any": [{"ref": "O1"}, {"ref": "O2"}]},
        }
        compiled = compile_canonical_condition_contract({
            "item_id": "SYN-CANONICAL", "source_sheet": "HWPX_TEMPLATE",
            "title": "canonical", "question": "canonical?", "product_groups": ["예금성"],
            "product_subtype": "예금성상품-입출식", "canonical_execution_plan": projected,
        })
        self.assertEqual(["A1", "A2"], [x["condition_id"] for x in compiled["applicability_conditions"]])
        self.assertEqual("RULE", compiled["applicability_conditions"][0]["owner"])
        self.assertEqual(["O1", "O2"], [x["obligation_id"] for x in compiled["obligation_checks"]])
        self.assertTrue(compiled["obligation_checks"][1]["owners"]["external_input"])
        self.assertEqual(projected["obligation_logic"], compiled["obligation_logic"])
        self.assertEqual("CANONICAL_ATOMIC", compiled["obligation_structure"])

    def test_truth_tables_include_unknown_and_failed_alternatives(self):
        states = ["SATISFIED", "MISSING", "VIOLATED", "UNDETERMINED"]
        for a, b in itertools.product(states, repeat=2):
            for operator in ("all", "any"):
                if operator == "any":
                    expected = (
                        "COMPLIANT"
                        if "SATISFIED" in (a, b)
                        else "UNDETERMINED"
                        if "UNDETERMINED" in (a, b)
                        else "VIOLATION"
                    )
                else:
                    expected = (
                        "VIOLATION"
                        if {a, b} & {"MISSING", "VIOLATED"}
                        else "UNDETERMINED"
                        if "UNDETERMINED" in (a, b)
                        else "COMPLIANT"
                    )
                with self.subTest(a=a, b=b, operator=operator):
                    self.assertEqual(
                        aggregate_obligations(contract(operator), checks(a, b)), expected
                    )

    def test_nested_branches_cannot_mix_partial_methods(self):
        c = {
            "obligation_checks": [{"obligation_id": f"O{i}"} for i in range(1, 5)],
            "obligation_logic": {
                "any": [
                    {"all": [{"ref": "O1"}, {"ref": "O2"}]},
                    {"all": [{"ref": "O3"}, {"ref": "O4"}]},
                ]
            },
        }
        self.assertEqual(
            aggregate_obligations(c, checks("SATISFIED", "MISSING", "MISSING", "SATISFIED")),
            "VIOLATION",
        )
        self.assertEqual(
            aggregate_obligations(c, checks("SATISFIED", "SATISFIED", "MISSING", "UNDETERMINED")),
            "COMPLIANT",
        )

    def test_undeclared_or_dropped_obligations_rejected(self):
        for expr in (
            {"any": []},
            {"ref": "O1"},
            {"ref": "O9"},
            {"unknown": []},
            {"ref": "O1", "all": []},
        ):
            with self.assertRaises(ValueError):
                validate_expression(expr, ["O1", "O2"])
        for rows in (
            checks("SATISFIED"),
            list(reversed(checks("SATISFIED", "MISSING"))),
            [checks("SATISFIED")[0]] * 2,
        ):
            with self.assertRaises(ValueError):
                aggregate_obligations(contract(), rows)

    def test_obligation_not_applicable_does_not_waive_required_element(self):
        self.assertEqual(
            aggregate_obligations(contract("all"), checks("SATISFIED", "NOT_APPLICABLE")),
            "UNDETERMINED",
        )

    def test_expression_depth_is_bounded(self):
        expr = {"ref": "O1"}
        for _ in range(26):
            expr = {"all": [expr]}
        with self.assertRaises(ValueError):
            validate_expression(expr, ["O1"])

    def test_explicit_source_methods_compile_for_all_three_product_groups(self):
        for group in ("예금성", "대출성", "투자성"):
            value = alternative_rule(group)
            before = copy.deepcopy(value)
            compiled = compile_condition_contract(value)
            self.assertEqual(compiled["obligation_structure"], "SOURCE_EXPLICIT_ALTERNATIVES")
            self.assertEqual(compiled["obligation_logic"], {"any": [{"ref": "O1"}, {"ref": "O2"}]})
            self.assertEqual(compiled["obligation_checks"][1]["source_ref"], "synthetic-source#2")
            self.assertIn("방식 2의 의미요소", compiled["obligation_checks"][1]["text"])
            self.assertEqual(value, before)

    def test_unstructured_or_conditionally_required_methods_are_not_guessed(self):
        for field, value in (("criterion", ""), ("template_required", "△"), ("source_ref", "")):
            source = alternative_rule()
            source["template_basis"]["alternative_members"][1][field] = value
            compiled = compile_condition_contract(source)
            self.assertNotEqual(compiled["obligation_structure"], "SOURCE_EXPLICIT_ALTERNATIVES")
            self.assertIn("all", compiled["obligation_logic"])

    def test_visual_and_separate_guide_obligations_are_preserved(self):
        value = alternative_rule()
        value["template_basis"]["manual_review_required"] = True
        self.assertNotEqual(
            compile_condition_contract(value)["obligation_structure"],
            "SOURCE_EXPLICIT_ALTERNATIVES",
        )
        value = alternative_rule()
        value["decision_guides"] = [{"requirements": ["공통 필수 의무"]}]
        compiled = compile_condition_contract(value)
        self.assertIn("공통 필수 의무", str(compiled["obligation_checks"]))
        self.assertIn("all", compiled["obligation_logic"])

    def test_method_specific_date_requirement_stays_in_its_own_branch(self):
        value = alternative_rule()
        value["template_basis"]["alternative_members"][0]["criterion"] += (
            " 기준일: 검토일 14일 이내"
        )
        compiled = compile_condition_contract(value)
        self.assertEqual(compiled["obligation_structure"], "SOURCE_EXPLICIT_ALTERNATIVES")
        self.assertIn("all", compiled["obligation_logic"]["any"][0])
        self.assertEqual(compiled["obligation_logic"]["any"][1], {"ref": "O3"})
        self.assertEqual(
            aggregate_obligations(compiled, checks("UNDETERMINED", "UNDETERMINED", "SATISFIED")),
            "COMPLIANT",
        )

    def test_compilation_audit_reports_text_only_limits_and_duplicate_ids(self):
        values = [rule(), alternative_rule()]
        for v in values:
            v["condition_contract"] = compile_condition_contract(v)
        report = audit_compiled_rules(values)
        self.assertEqual(report["structure_counts"]["SOURCE_TEXT_ONLY"], 1)
        self.assertEqual(report["structure_counts"]["SOURCE_EXPLICIT_ALTERNATIVES"], 1)
        with self.assertRaises(ValueError):
            audit_compiled_rules([values[0], values[0]])

    def test_wire_carries_expression_and_synthetic_guidance(self):
        c = compile_condition_contract(alternative_rule())
        messages, _ = gemma._compact_model_request(request_with_contract(c))
        wire = json.loads(messages[1]["content"])
        self.assertEqual(
            wire["rules"][0]["condition_contract"]["obligation_logic"], c["obligation_logic"]
        )
        self.assertIn("Synthetic logic examples", messages[0]["content"])
        self.assertEqual(wire["rules"][0]["output_check_refs"]["requirement_checks"], ["O1", "O2"])

    def test_alternative_source_change_invalidates_contract_fingerprint(self):
        value = alternative_rule()
        before = compile_condition_contract(value)
        value["template_basis"]["alternative_members"][1]["criterion"] += " 추가 원문 요건"
        after = compile_condition_contract(value)
        self.assertNotEqual(before["scope_source_sha256"], after["scope_source_sha256"])

    def test_compact_response_round_trip_preserves_any_and_exact_evidence(self):
        request = request_with_contract(compile_condition_contract(alternative_rule()))
        _, aliases = gemma._compact_model_request(request)
        model_result = {
            "rule_ref": "R1",
            "scope_check": {
                "scope_ref": "SCOPE",
                "status": "MATCHED",
                "evidence_refs": ["E1", "L1"],
                "metadata_fields": [],
            },
            "condition_checks": [],
            "review_condition_checks": [],
            "verdict": "COMPLIANT",
            "reason": "하나의 방식 충족",
            "confidence": "HIGH",
            "requirement_checks": [
                {
                    "obligation_ref": "O1",
                    "requirement": "방식 1",
                    "status": "SATISFIED",
                    "finding_basis": "OBSERVED",
                    "evidence_refs": ["E1", "L1"],
                    "reason": "'특정 담당 주체' 확인",
                },
                {
                    "obligation_ref": "O2",
                    "requirement": "방식 2",
                    "status": "UNDETERMINED",
                    "finding_basis": "UNKNOWN",
                    "evidence_refs": [],
                    "reason": "자료 부족",
                },
            ],
        }
        expanded = gemma._expand_model_response(request, {"results": [model_result]}, aliases)
        self.assertEqual(gemma.validate(request, expanded), [])
        self.assertEqual(expanded["results"][0]["evidence_line_refs"], ["L-CANON"])
        self.assertEqual(expanded["results"][0]["requirement_checks"][1]["status"], "UNDETERMINED")

    def test_unknown_review_condition_cannot_be_bypassed_by_compliant_obligations(self):
        compiled = compile_condition_contract(
            rule(
                guides=[
                    {
                        "review_conditions": ["원자료의 의미가 불명확하면 사람 확인"],
                    }
                ]
            )
        )
        value = judgment()
        value["results"][0]["review_condition_checks"] = [
            {"condition_ref": "U1", "status": "UNDETERMINED"},
        ]
        errors = gemma.validate(request_with_contract(compiled), value)
        self.assertTrue(
            any("미확정/불충족 조건에서 APPLICABLE 금지" in error for error in errors), errors
        )

    def result(self, second="UNDETERMINED", verdict="COMPLIANT"):
        value = judgment()
        row = value["results"][0]
        first = row["requirement_checks"][0]
        other = {**copy.deepcopy(first), "obligation_ref": "O2", "status": second}
        if second == "UNDETERMINED":
            other.update(
                finding_basis="UNKNOWN", evidence_ids=[], evidence_line_refs=[], reason="자료 부족"
            )
        if second == "MISSING":
            other.update(
                finding_basis="ABSENCE",
                evidence_ids=[],
                evidence_line_refs=[],
                reason="전체 확인 후 방식 미기재",
            )
        row.update(
            requirement_checks=[first, other],
            verdict=verdict,
            needs_researcher_review=verdict != "COMPLIANT",
        )
        return value

    def test_real_validator_accepts_one_complete_method_and_checks_all_refs(self):
        request = request_with_contract(compile_condition_contract(alternative_rule()))
        for second in ("UNDETERMINED", "MISSING"):
            self.assertEqual(gemma.validate(request, self.result(second)), [])
        invalid = self.result()
        invalid["results"][0]["requirement_checks"].pop()
        self.assertTrue(
            any("obligation_checks 누락" in e for e in gemma.validate(request, invalid))
        )

    def test_validator_rejects_model_summary_ignoring_any(self):
        request = request_with_contract(compile_condition_contract(alternative_rule()))
        errors = gemma.validate(request, self.result("MISSING", "VIOLATION"))
        self.assertTrue(any("전체 verdict 불일치" in e for e in errors), errors)

    def test_incomplete_scan_still_cannot_prove_missing_alternative(self):
        request = request_with_contract(compile_condition_contract(alternative_rule()))
        payload = json.loads(request["messages"][1]["content"])
        payload["evidence_scope"]["D-X"]["complete_ad_scan"] = False
        request["messages"][1]["content"] = json.dumps(payload)
        errors = gemma.validate(request, self.result("MISSING"))
        self.assertTrue(any("ABSENCE" in e or "부재 확정" in e for e in errors), errors)

    def test_legacy_frozen_contract_keeps_old_semantics(self):
        c = compile_condition_contract(alternative_rule())
        del c["obligation_logic"]
        errors = gemma.validate(request_with_contract(c), self.result())
        self.assertTrue(any("구성요소 미충족" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
