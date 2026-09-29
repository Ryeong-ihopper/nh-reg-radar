from __future__ import annotations

import json
import unittest
from copy import deepcopy
from pathlib import Path

from rag.judgment.canonical_execution_plans import (
    SUPPLEMENT_APPLICABILITY, SUPPLEMENT_OBLIGATIONS, compile_current_scope,
)
from rag.judgment.family_prompts import make_batches, project_plan, prompt_for_family
from rag.judgment.execution_plan_runtime import evaluate_execution_plan
from rag.judgment.obligation_logic import validate_expression
from rag.judgment.review_program import apply_programs, load_policies


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "rag-pipeline/config"
SOURCE = CONFIG / "canonical-source"


def load_document():
    routing = json.loads((SOURCE / "complete-rule-routing-v1.json").read_text(encoding="utf-8"))
    methodologies = json.loads((SOURCE / "structured-review-methodology-v1.json").read_text(encoding="utf-8"))
    methodology_review = json.loads((SOURCE / "methodology-execution-review-v1.json").read_text(encoding="utf-8"))
    return compile_current_scope(routing, methodologies, methodology_review)


class CanonicalExecutionPlansTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = load_document()
        cls.plans = {p["plan_id"]: p for p in cls.document["plans"]}

    def test_tracked_sources_reproduce_the_current_canonical_document(self):
        generated = apply_programs(
            deepcopy(self.document),
            load_policies(CONFIG / "review-program-policies-v1.json"),
        )
        current = json.loads(
            (CONFIG / "canonical-execution-plans-v2.json").read_text(encoding="utf-8")
        )
        self.assertEqual(current, generated)

    def test_scope_has_exactly_271_unique_candidates(self):
        self.assertEqual(271, len(self.plans))
        self.assertEqual(239, self.document["counts"]["template_records"])
        self.assertEqual(32, self.document["counts"]["supplemental_records"])

    def test_card_and_superseded_rows_are_absent(self):
        self.assertFalse(any(str(p["source"].get("product_template") or "").startswith("카드")
                             for p in self.plans.values()))
        for number in [1, 28, 58, 72, 255, 263]:
            self.assertNotIn(f"TPL-MAP-{number:03}", self.plans)
        for rule_id in ["MTH-LOAN-NAMED-R04", "MTH-DEPOSIT-DEMAND-R19",
                        "MTH-RETIREMENT-R14", "MTH-RETIREMENT-ETF-R16",
                        "MTH-RETIREMENT-ELB-R12"]:
            self.assertIn(rule_id, self.plans)

    def test_all_supplements_are_authored_without_id_specific_runtime_branches(self):
        supplement_ids = {p["plan_id"] for p in self.plans.values()
                          if p["source"]["source_kind"] != "TEMPLATE"}
        self.assertEqual(set(SUPPLEMENT_OBLIGATIONS), supplement_ids)
        self.assertEqual(set(SUPPLEMENT_APPLICABILITY), supplement_ids)
        for rule_id in supplement_ids:
            self.assertEqual(len(SUPPLEMENT_OBLIGATIONS[rule_id]),
                             len(self.plans[rule_id]["obligations"]))

    def test_all_supplemental_applicability_is_atomic_and_typed(self):
        for rule_id, clauses in SUPPLEMENT_APPLICABILITY.items():
            with self.subTest(rule=rule_id):
                plan = self.plans[rule_id]
                self.assertEqual(len(clauses), len(plan["applicability_inputs"]))
                self.assertTrue(all(row["owner"] in {"RULE", "LLM", "RULE_LLM", "LLM_EXTERNAL"}
                                    for row in plan["applicability_inputs"]))
        self.assertEqual(2, len(self.plans["C-018"]["applicability_inputs"]))
        self.assertEqual("광고성 전자적 전송인가",
                         self.plans["C-018"]["applicability_inputs"][0]["name"])

    def test_positive_ad_triggers_close_only_after_complete_scan(self):
        arithmetic = self.plans["D-163"]["applicability_inputs"]
        endorsement = self.plans["D-206"]["applicability_inputs"]
        self.assertTrue(all(row["owner"] == "RULE" for row in arithmetic))
        self.assertTrue(all(row["type"] == "DETERMINISTIC_ADAPTER" for row in arithmetic))
        self.assertEqual(
            "NOT_SATISFIED_IF_COMPLETE_AD_SCAN", endorsement[0]["absence_policy"]
        )
        self.assertNotIn("absence_policy", endorsement[1])

    def test_every_plan_has_gates_atoms_logic_and_evidence_contract(self):
        for plan in self.plans.values():
            with self.subTest(plan=plan["plan_id"]):
                self.assertTrue(plan["applicability_inputs"])
                self.assertTrue(plan["obligations"])
                validate_expression(
                    plan["obligation_logic"],
                    [a["obligation_id"] for a in plan["obligations"]],
                )
                for atom in plan["obligations"]:
                    self.assertFalse(atom["evidence"]["rule_or_example_text_is_advertisement_evidence"])
                    self.assertTrue(atom["evidence"]["same_advertisement_product_revision_scope"])
                    self.assertTrue(atom["retrieval_queries"])

    def test_rule_only_obligations_have_executable_adapters(self):
        for plan in self.plans.values():
            for atom in plan["obligations"]:
                owners = atom["owners"]
                if owners["rule"] and not owners["llm"] and not owners["external_input"]:
                    self.assertIn("deterministic_adapter", atom, (plan["plan_id"], atom["obligation_id"]))

    def test_gate_predicates_are_plain_text_and_exemptions_are_not_duplicate_triggers(self):
        ai_plan = self.plans["MTH-DEPOSIT-DEMAND-R18"]
        self.assertEqual(
            ["selected_template", "생성형 AI를 활용한 경우"],
            [row["name"] for row in ai_plan["applicability_inputs"]],
        )
        legacy_ai = self.plans["TPL-MAP-037"]
        self.assertTrue(all(not row["name"].startswith("{")
                            for row in legacy_ai["applicability_inputs"]))
        exemption = self.plans["TPL-MAP-075"]
        self.assertEqual(["A1", "E1"],
                         [row["fact_id"] for row in exemption["applicability_inputs"]])

    def test_company_name_needs_no_user_supplied_medium_recognition_field(self):
        plan = self.plans["MTH-DEPOSIT-DEMAND-R04"]
        self.assertEqual(["selected_template"],
                         [row["name"] for row in plan["applicability_inputs"]])
        self.assertEqual("NH농협은행 명칭이 표시되는가", plan["obligations"][0]["text"])
        self.assertEqual(1, len(plan["obligations"]))
        self.assertEqual({"all": [{"ref": "O1"}]}, plan["obligation_logic"])

    def test_revised_methodology_inherits_reviewed_display_basis_only(self):
        company = self.plans["MTH-LOAN-NAMED-R04"]["source"]["legal_basis"]
        self.assertIn("금융소비자 보호에 관한 법률 제22조", company["statute"])
        self.assertIn("은행 광고심의 기준", company["association"])
        self.assertTrue(company["display_only_not_new_obligation"])
        guidance = self.plans["MTH-LOAN-NAMED-R23"]["source"]["legal_basis"]
        self.assertIn("은행연합회 지도사항", guidance["association"])
        added = self.plans["MTH-RETIREMENT-ETF-R16"]["source"]["legal_basis"]
        self.assertEqual({}, added)
        conflicted = self.plans["MTH-DEPOSIT-DEMAND-R16"]["source"]["legal_basis"]
        self.assertNotIn("은행연합회 지도사항", conflicted.get("association", ""))

    def test_example_defined_semantics_are_in_the_atomic_obligation(self):
        for plan_id in ("MTH-DEPOSIT-DEMAND-R14", "MTH-DEPOSIT-DEMAND-R16",
                        "MTH-DEPOSIT-DEMAND-R17"):
            text = self.plans[plan_id]["obligations"][0]["text"]
            self.assertIn("의미 기준:", text)
            self.assertIn("일부 명사만으로 충족하지 않음", text)

    def test_examples_are_non_binding_hints_with_obligation_fallback(self):
        with_examples = 0
        without_examples = 0
        for plan in self.plans.values():
            for atom in plan["obligations"]:
                if atom["interpretation_hints"]:
                    with_examples += 1
                    hint = atom["interpretation_hints"][0]
                    self.assertFalse(hint["exact_match_required"])
                    self.assertFalse(hint["may_be_cited_as_advertisement_evidence"])
                else:
                    without_examples += 1
                    self.assertIn(atom["text"], atom["retrieval_queries"])
        self.assertGreater(with_examples, 0)
        self.assertGreater(without_examples, 0)

    def test_source_scope_conflict_holds_only_the_conflicting_facet(self):
        for plan_id in ["MTH-DEPOSIT-DEMAND-R16", "MTH-DEPOSIT-DEMAND-R17"]:
            plan = self.plans[plan_id]
            self.assertFalse(plan["unresolved"])
            self.assertEqual("SOURCE_SCOPE_TERM_CONFLICT", plan["held_facets"][0]["reason"])
            self.assertTrue(plan["held_facets"][0]["remaining_text_obligation_active"])

    def test_representative_multicomponent_rules_are_split(self):
        expected = {"C-018": 3, "C-020": 2, "C-032": 2, "C-090": 4,
                    "C-132": 3, "D-191": 2, "D-201": 2}
        for rule_id, count in expected.items():
            self.assertEqual(count, len(self.plans[rule_id]["obligations"]))

    def test_prompt_projection_excludes_display_example_field_and_overall_verdict(self):
        projected = project_plan(self.plans["MTH-RETIREMENT-ETF-R11"])
        encoded = json.dumps(projected, ensure_ascii=False)
        self.assertNotIn("display_example", encoded)
        self.assertNotIn('"verdict"', encoded)
        self.assertIn("obligation_logic", projected)
        self.assertIn("NON_BINDING_SOURCE_EXAMPLE", encoded)

    def test_batches_never_mix_families_and_preserve_all_plans(self):
        batches = make_batches(list(self.plans.values()), max_items=4, max_complexity=12)
        refs = []
        for batch in batches:
            self.assertLessEqual(len(batch["plans"]), 4)
            self.assertTrue(batch["prompt"].startswith("Return structured fact observations only."))
            for plan in batch["plans"]:
                self.assertEqual(batch["family"], self.plans[plan["plan_ref"]]["prompt_family"])
                refs.append(plan["plan_ref"])
        self.assertCountEqual(self.plans, refs)

    def test_human_family_forbids_automated_verdict(self):
        prompt = prompt_for_family("HUMAN_VISUAL")
        self.assertIn("Do not produce an automated compliance judgment", prompt)
        self.assertEqual("HUMAN_VISUAL", self.plans["D-240"]["prompt_family"])

    def _result(self, plan_id, *, applicability="TRUE", statuses=None,
                complete_scan=True, external=True):
        plan = self.plans[plan_id]
        context = {"advertisement_id": "AD-1", "product_id": "PRODUCT-1",
                   "revision_id": "REV-1", "scope_id": "PAGE-ALL"}
        evidence = []
        checks = []
        for index, atom in enumerate(plan["obligations"], 1):
            ad_ref = f"AD-E{index}"
            evidence.append({"evidence_id": ad_ref, "context": context,
                             "source_role": "ADVERTISEMENT_TEXT"})
            refs = [ad_ref]
            if atom["owners"]["external_input"]:
                external_ref = f"EXT-E{index}"
                evidence.append({"evidence_id": external_ref, "context": context,
                                 "source_role": "PRODUCT_DOCUMENT"})
                refs.append(external_ref)
            checks.append({"obligation_ref": atom["obligation_id"],
                           "status": (statuses or {}).get(atom["obligation_id"], "SATISFIED"),
                           "evidence_refs": refs, "external_input_verified": external})
        fact_results = []
        for index, row in enumerate(plan["applicability_inputs"], 1):
            refs = []
            if "LLM" in row["owner"]:
                ref = f"APP-E{index}"
                evidence.append({"evidence_id": ref, "context": context,
                                 "source_role": "ADVERTISEMENT_TEXT"})
                refs.append(ref)
            if "EXTERNAL" in row["owner"]:
                ref = f"APP-EXT-E{index}"
                evidence.append({"evidence_id": ref, "context": context,
                                 "source_role": "CONFIRMED_EXTERNAL_FACT"})
                refs.append(ref)
            fact_results.append({"fact_ref": row["fact_id"], "status": applicability,
                                 "basis": "CONFIRMED_METADATA", "evidence_refs": refs})
        return evaluate_execution_plan(plan, {
            "context": context,
            "evidence": evidence,
            "applicability": fact_results,
            "obligations": checks,
            "complete_scan": complete_scan,
        })

    def test_code_owns_applicability_and_overall_aggregation(self):
        self.assertEqual("NOT_APPLICABLE", self._result("C-018", applicability="FALSE")["verdict"])
        self.assertEqual("UNDETERMINED", self._result("C-018", applicability="UNKNOWN")["verdict"])
        self.assertEqual("COMPLIANT", self._result("C-018")["verdict"])
        self.assertEqual("VIOLATION", self._result("C-018", statuses={"O2": "MISSING"})["verdict"])

    def test_missing_without_complete_scan_becomes_unknown(self):
        result = self._result("C-018", statuses={"O1": "MISSING"}, complete_scan=False)
        self.assertEqual("UNDETERMINED", result["verdict"])

    def test_external_comparison_without_verified_input_becomes_unknown(self):
        result = self._result("C-018", external=False)
        self.assertEqual("UNDETERMINED", result["verdict"])

    def test_visual_unknown_is_preserved_in_human_queue(self):
        plan = self.plans["D-240"]
        context = {"advertisement_id": "AD-1", "product_id": "PRODUCT-1",
                   "revision_id": "REV-1", "scope_id": "PAGE-ALL"}
        result = evaluate_execution_plan(plan, {
            "context": context,
            "evidence": [{"evidence_id": "REGION-1", "context": context,
                          "source_role": "ADVERTISEMENT_REGION"}],
            "applicability": [{"fact_ref": row["fact_id"], "status": "TRUE",
                               "basis": "CONFIRMED_METADATA", "evidence_refs": ["REGION-1"]}
                              for row in plan["applicability_inputs"]],
            "obligations": [{"obligation_ref": "O1", "status": "UNDETERMINED",
                             "evidence_refs": ["REGION-1"]}],
            "complete_scan": True,
        })
        self.assertEqual("UNDETERMINED", result["verdict"])
        self.assertEqual("O1", result["human_review_queue"][0]["obligation_ref"])

    def test_runtime_rejects_missing_or_reordered_results(self):
        plan = self.plans["C-018"]
        with self.assertRaises(ValueError):
            evaluate_execution_plan(plan, {"applicability": [], "obligations": []})
        context = {"advertisement_id": "AD-1", "product_id": "PRODUCT-1",
                   "revision_id": "REV-1", "scope_id": "PAGE-ALL"}
        with self.assertRaises(ValueError):
            evaluate_execution_plan(plan, {
                "context": context,
                "evidence": [{"evidence_id": "E1", "context": context,
                              "source_role": "ADVERTISEMENT_TEXT"}],
                "applicability": [{"fact_ref": row["fact_id"], "status": "TRUE",
                                   "basis": "CONFIRMED_METADATA", "evidence_refs": []}
                                  for row in plan["applicability_inputs"]],
                "obligations": list(reversed([
                    {"obligation_ref": atom["obligation_id"], "status": "SATISFIED",
                     "evidence_refs": ["E1"], "external_input_verified": True}
                    for atom in plan["obligations"]])), "complete_scan": True})

    def test_runtime_rejects_cross_revision_or_unknown_evidence(self):
        plan = self.plans["TPL-MAP-029"]
        context = {"advertisement_id": "AD-1", "product_id": "PRODUCT-1",
                   "revision_id": "REV-1", "scope_id": "PAGE-ALL"}
        base = {
            "context": context,
            "evidence": [{"evidence_id": "E1", "context": {**context, "revision_id": "REV-2"},
                          "source_role": "ADVERTISEMENT_TEXT"}],
            "applicability": [{"fact_ref": "A1", "status": "TRUE",
                               "basis": "CONFIRMED_METADATA", "evidence_refs": []}],
            "obligations": [{"obligation_ref": "O1", "status": "SATISFIED",
                             "evidence_refs": ["E1"]}],
            "complete_scan": True,
        }
        with self.assertRaisesRegex(ValueError, "context differs"):
            evaluate_execution_plan(plan, base)
        base["evidence"][0]["context"] = context
        base["obligations"][0]["evidence_refs"] = ["UNKNOWN"]
        with self.assertRaisesRegex(ValueError, "unknown ids"):
            evaluate_execution_plan(plan, base)

    def test_semantic_applicability_needs_evidence_and_negative_needs_complete_scan(self):
        plan = self.plans["C-032"]
        context = {"advertisement_id": "AD-1", "product_id": "PRODUCT-1",
                   "revision_id": "REV-1", "scope_id": "PAGE-ALL"}
        evidence = [{"evidence_id": "AD-E", "context": context,
                     "source_role": "ADVERTISEMENT_TEXT"}]
        obligations = [{"obligation_ref": atom["obligation_id"], "status": "SATISFIED",
                        "evidence_refs": ["AD-E"]} for atom in plan["obligations"]]
        base = {"context": context, "evidence": evidence, "obligations": obligations,
                "complete_scan": True,
                "applicability": [
                    {"fact_ref": "A1", "status": "TRUE", "basis": "CONFIRMED_METADATA",
                     "evidence_refs": []},
                    {"fact_ref": "A2", "status": "TRUE", "evidence_refs": []},
                ]}
        with self.assertRaisesRegex(ValueError, "advertisement evidence"):
            evaluate_execution_plan(plan, base)
        base["applicability"][1] = {"fact_ref": "A2", "status": "FALSE",
                                      "evidence_refs": ["AD-E"]}
        base["complete_scan"] = False
        with self.assertRaisesRegex(ValueError, "complete scan"):
            evaluate_execution_plan(plan, base)


if __name__ == "__main__":
    unittest.main()
