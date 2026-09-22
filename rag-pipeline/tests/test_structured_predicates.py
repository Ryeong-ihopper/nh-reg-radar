"""Synthetic branch tests; no customer advertisements or case answers."""
from __future__ import annotations

import copy
import unittest

from rag.judgment.structured_predicates import evaluate_plan, validate_plan
from rag.templates.deposit_methodology_plan import compile_deposit_plans


def plans():
    rows = [{"rule_id": f"MTH-DEPOSIT-DEMAND-R{n:02}",
             "source": {"excel_row": n, "original_sha256":
                        "f79f7d5a7ca19e9508b13e5e11c82684a8d9d65cef6d260b4f50aa570d93f31b"},
             "outcomes": {}, "display_example": "synthetic source reference"}
            for n in range(4, 20)]
    return {p["plan_id"].removeprefix("DEPOSIT-DEMAND-"): p for p in compile_deposit_plans(rows)}


def payload(plan, **values):
    context = {"advertisement": "synthetic-ad", "product": "synthetic-product",
               "revision": "1", "scope": "same-rate-offer"}
    result = {"context": context, "facts": {}, "evidence": {}, "scans": {}}
    values = {"selected_scope": True, **values}
    for key, value in values.items():
        spec = plan["facts"][key]
        result["facts"][key] = {"value": value, "verified": True, "owner": spec["owner"],
                                 "mode": "OBSERVED", "evidence_refs": [key],
                                 "unit": spec.get("unit"), "complete": True}
        result["evidence"][key] = {"verified": True, "context": context.copy(),
                                    "source_type": spec["sources"][0], "locator": "synthetic:1"}
        if spec["type"] == "decimal_list":
            component_refs = [f"{key}:{n}" for n in range(len(value))]
            result["facts"][key]["component_refs"] = component_refs
            result["facts"][key]["evidence_refs"].extend(component_refs)
            for ref in component_refs:
                result["evidence"][ref] = {**result["evidence"][key], "locator": ref}
        if value is False and spec.get("false_requires_scan"):
            result["facts"][key].update(mode="ABSENT", scan_ref=key)
            result["scans"][key] = {"verified": True, "complete": True,
                                     "context": context.copy(), "evidence_refs": [key]}
    return result


class StructuredPredicatesTests(unittest.TestCase):
    def setUp(self):
        self.plans = plans()

    def result(self, name, **values):
        plan = self.plans[name]
        return evaluate_plan(plan, payload(plan, **values))["verdict"]

    def test_all_sixteen_source_rows_preserved_in_fourteen_plans(self):
        self.assertEqual(14, len(self.plans))
        self.assertEqual(set(range(4, 20)), {
            r["excel_row"] for p in self.plans.values() for r in p["source_refs"]})

    def test_unknown_scope_never_passes_or_excludes(self):
        p = self.plans["PRODUCT"]
        data = payload(p, product_name=True)
        del data["facts"]["selected_scope"]
        self.assertEqual("UNDETERMINED", evaluate_plan(p, data)["verdict"])

    def test_scope_false_excludes(self):
        self.assertEqual("NOT_APPLICABLE", self.result("PRODUCT", selected_scope=False))

    def test_missing_product_and_unread_product_differ(self):
        self.assertEqual("VIOLATION", self.result("PRODUCT", product_name=False))
        self.assertEqual("UNDETERMINED", self.result("PRODUCT"))

    def test_absence_requires_matching_complete_scan(self):
        p = self.plans["PRODUCT"]
        data = payload(p, product_name=False)
        item = data["facts"]["product_name"]
        item.update(mode="ABSENT", scan_ref="scan")
        self.assertEqual("UNDETERMINED", evaluate_plan(p, data)["verdict"])

        data["scans"]["scan"] = {"verified": True, "complete": True,
                                    "context": data["context"], "evidence_refs": ["product_name"]}
        self.assertEqual("VIOLATION", evaluate_plan(p, data)["verdict"])
        data["scans"]["scan"]["complete"] = False
        self.assertEqual("UNDETERMINED", evaluate_plan(p, data)["verdict"])

    def test_observed_label_cannot_bypass_absence_scan(self):
        p = self.plans["PRODUCT"]
        data = payload(p, product_name=False)
        data["facts"]["product_name"]["mode"] = "OBSERVED"
        self.assertEqual("UNDETERMINED", evaluate_plan(p, data)["verdict"])

    def test_company_and_ai_absence_are_review_only(self):
        self.assertEqual("REVIEW_REQUIRED", self.result("COMPANY", company_name=False))
        self.assertEqual("REVIEW_REQUIRED", self.result("AI", ai_notice=False))

    def test_company_and_ai_present_pass(self):
        self.assertEqual("COMPLIANT", self.result("COMPANY", company_name=True))
        self.assertEqual("COMPLIANT", self.result("AI", ai_notice=True))

    def test_bonus_sum_boundary_uses_decimal(self):
        for maximum, expected in [("0.3", "COMPLIANT"), ("0.3001", "VIOLATION"),
                                  ("0.2999", "COMPLIANT")]:
            with self.subTest(maximum=maximum):
                self.assertEqual(expected, self.result("BONUS", has_bonus=True,
                    threshold_scheme=False, bonus_maximum=maximum, bonus_components=["0.1", "0.2"]))

    def test_bonus_threshold_alternative_does_not_need_individual_sum(self):
        self.assertEqual("COMPLIANT", self.result("BONUS", has_bonus=True, threshold_scheme=True))

    def test_unresolved_alternative_does_not_turn_failed_sum_into_violation(self):
        self.assertEqual("UNDETERMINED", self.result("BONUS", has_bonus=True,
            bonus_maximum="0.8", bonus_components=["0.1", "0.2"]))

    def test_no_bonus_requires_product_fact_and_method_one(self):
        self.assertEqual("COMPLIANT", self.result("BONUS", has_bonus=False, method_one=True))
        self.assertEqual("UNDETERMINED", self.result("BONUS", method_one=True))
        self.assertEqual("VIOLATION", self.result("BONUS", has_bonus=False, method_one=False))

    def test_bonus_components_cannot_be_incomplete(self):
        p = self.plans["BONUS"]
        data = payload(p, has_bonus=True, threshold_scheme=False,
                       bonus_maximum="0.3", bonus_components=["0.1", "0.2"])
        data["facts"]["bonus_components"]["complete"] = False
        self.assertEqual("UNDETERMINED", evaluate_plan(p, data)["verdict"])

    def test_bad_numeric_inputs_are_not_silently_normalized(self):
        for value in [float("nan"), "NaN", "Infinity", "-1", True, "1%", 0.3]:
            with self.subTest(value=value):
                self.assertEqual("UNDETERMINED", self.result("BONUS", has_bonus=True,
                    threshold_scheme=False, bonus_maximum=value, bonus_components=["1"]))

    def test_sum_cannot_duplicate_or_omit_component_evidence(self):
        p = self.plans["BONUS"]
        for refs in [["bonus_components:0", "bonus_components:0"], ["bonus_components:0"]]:
            data = payload(p, has_bonus=True, threshold_scheme=False,
                           bonus_maximum="0.3", bonus_components=["0.1", "0.2"])
            data["facts"]["bonus_components"]["component_refs"] = refs
            self.assertEqual("UNDETERMINED", evaluate_plan(p, data)["verdict"])

    def test_bad_unit_or_wrong_product_revision_scope_is_rejected(self):
        p = self.plans["BONUS"]
        original = payload(p, has_bonus=True, threshold_scheme=False,
                           bonus_maximum="0.2", bonus_components=["0.3"])
        for key in ("advertisement", "product", "revision", "scope"):
            data = copy.deepcopy(original)
            data["evidence"]["bonus_components"]["context"][key] = "other"
            self.assertEqual("UNDETERMINED", evaluate_plan(p, data)["verdict"])
        data = copy.deepcopy(original)
        data["facts"]["bonus_components"]["unit"] = "monthly_percent"
        self.assertEqual("UNDETERMINED", evaluate_plan(p, data)["verdict"])

    def test_method_one_cap_with_bonus_is_required(self):
        for cap, expected in [(True, "COMPLIANT"), (False, "VIOLATION")]:
            self.assertEqual(expected, self.result("BONUS-CAP", method_one=True,
                method_two=False, method_three=False, has_bonus=True, bonus_cap=cap))

    def test_method_two_repeat_cap_waiver_does_not_waive_rate_cap(self):
        self.assertEqual("COMPLIANT", self.result("BONUS-CAP", method_two=True))
        self.assertEqual("VIOLATION", self.result("RATE", method_one=False,
            method_two=True, method_three=False, base_rate=True, maximum_cap=False,
            annual=True, before_tax=True, basis_date=True))

    def test_method_three_does_not_require_separate_base_rate(self):
        p = self.plans["RATE"]
        data = payload(p, method_one=False, method_two=False, method_three=True,
                       maximum_cap=True, annual=True, before_tax=True, basis_date=True)
        result = evaluate_plan(p, data)
        self.assertEqual("UNDETERMINED", result["verdict"])  # date interpretation only
        methods = [x for x in result["trace"] if x["operator"] == "any"]
        self.assertTrue(methods[0]["result"])

    def test_rate_date_conflict_cannot_hide_missing_annual_or_tax(self):
        for key in ["annual", "before_tax", "basis_date"]:
            values = dict(method_one=True, annual=True, before_tax=True, basis_date=True)
            values[key] = False
            self.assertEqual("VIOLATION", self.result("RATE", **values))

    def test_lms_without_link_waives_only_logo(self):
        self.assertEqual("COMPLIANT", self.result("PROTECTION", lms=True,
                         has_link=False, protection_text=True))
        self.assertEqual("VIOLATION", self.result("PROTECTION", lms=True,
                         has_link=False, protection_text=False))

    def test_lms_link_conflict_and_unknown_link_remain_unknown(self):
        self.assertEqual("UNDETERMINED", self.result("PROTECTION", lms=True,
                         has_link=True, protection_text=True))
        self.assertEqual("UNDETERMINED", self.result("PROTECTION", lms=True, protection_text=True))

    def test_non_lms_logo_requires_human_observation(self):
        p = self.plans["PROTECTION"]
        data = payload(p, lms=False, protection_text=True, protection_logo=True)
        self.assertEqual("COMPLIANT", evaluate_plan(p, data)["verdict"])
        data["facts"]["protection_logo"]["owner"] = "LLM"
        result = evaluate_plan(p, data)
        self.assertEqual("UNDETERMINED", result["verdict"])
        self.assertEqual("protection_logo", result["human_review"][0]["fact"])

    def test_line_conflict_does_not_discard_text_violation(self):
        self.assertEqual("VIOLATION", self.result("RIGHTS", explanation_right=False))
        self.assertEqual("UNDETERMINED", self.result("RIGHTS", explanation_right=True))

    def test_eligibility_version_conflict_and_positive_evidence(self):
        self.assertEqual("COMPLIANT", self.result("ELIGIBILITY", eligibility=True))
        self.assertEqual("UNDETERMINED", self.result("ELIGIBILITY", eligibility=False))

    def test_separate_restriction_obligations(self):
        self.assertEqual("COMPLIANT", self.result("SEIZURE", seizure_restriction=True))
        self.assertEqual("UNDETERMINED", self.result("CERTIFICATE"))

    def test_approval_checks_every_component(self):
        self.assertEqual("COMPLIANT", self.result("APPROVAL", approval_issuer=True,
                         approval_number=True, approval_dates=True))
        self.assertEqual("VIOLATION", self.result("APPROVAL", approval_issuer=False,
                         approval_number=True, approval_dates=True))

    def test_template_example_and_unverified_evidence_cannot_be_ad_evidence(self):
        p = self.plans["PRODUCT"]
        for source in ["TEMPLATE_EXAMPLE", "CASE_ANSWER", "RULE_SOURCE"]:
            data = payload(p, product_name=True)
            data["evidence"]["product_name"]["source_type"] = source
            self.assertEqual("UNDETERMINED", evaluate_plan(p, data)["verdict"])
        data = payload(p, product_name=True)
        data["facts"]["product_name"]["verified"] = False
        self.assertEqual("UNDETERMINED", evaluate_plan(p, data)["verdict"])

    def test_undefined_and_unused_facts_or_empty_expressions_rejected(self):
        p = copy.deepcopy(self.plans["PRODUCT"])
        p["expression"] = {"fact": "invented"}
        with self.assertRaises(ValueError):
            validate_plan(p)
        p["expression"] = {"all": []}
        with self.assertRaises(ValueError):
            validate_plan(p)
        p["expression"] = {"fact": "selected_scope"}
        with self.assertRaises(ValueError):
            validate_plan(p)


if __name__ == "__main__":
    unittest.main()
