# -*- coding: utf-8 -*-
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

import hybrid_rule_retrieval as retrieval  # noqa: E402
import run_gemma_exhaustive_dgx as gemma  # noqa: E402
import run_operational_e2e as operational  # noqa: E402


def routing_row(value, status):
    return {
        "routing_metadata": {
            "product_group": {"value": value, "status": status, "source": "test"}
        }
    }


def request_row(item_ids):
    rules = [{"item_id": item_id} for item_id in item_ids]
    payload = {
        "request_id": "req",
        "ad_id": "AD-X",
        "documents": [{
            "evidence_id": "E-1",
            "line_refs": ["L-1"],
            "text": "테스트 근거",
        }],
        "rules": rules,
        "routing": {
            "template_id": {"value": None, "source": None, "status": "unknown"},
        },
    }
    return {
        "request_id": "req",
        "ad_id": "AD-X",
        "category": "PRESENCE",
        "requested_item_ids": item_ids,
        "messages": [
            {"role": "system", "content": "test"},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    }


def result(item_id):
    return {
        "item_id": item_id,
        "applicability": "APPLICABLE",
        "applicability_basis": "ADVERTISEMENT_EVIDENCE",
        "applicability_evidence_ids": ["E-1"],
        "applicability_evidence_line_refs": ["L-1"],
        "applicability_metadata_fields": [],
        "verdict": "COMPLIANT",
        "evidence_ids": ["E-1"],
        "evidence_line_refs": ["L-1"],
        "reason": "근거 확인",
        "confidence": "HIGH",
        "needs_researcher_review": False,
        "requirement_checks": [{
            "requirement": "필수 항목",
            "status": "SATISFIED",
            "evidence_ids": ["E-1"],
            "evidence_line_refs": ["L-1"],
            "reason": "근거 확인",
        }],
    }


class FailOpenRoutingTests(unittest.TestCase):
    def test_inferred_never_removes_other_product_family(self):
        route = retrieval.routing_scope([routing_row("예금성", "inferred")])
        self.assertTrue(route["routing_provisional"])
        self.assertEqual(route["candidate_product_groups"], ["예금성", "대출성"])

    def test_conflict_is_union(self):
        route = retrieval.routing_scope([
            routing_row("예금성", "confirmed"),
            routing_row("대출성", "inferred"),
        ])
        self.assertTrue(route["routing_provisional"])
        self.assertEqual(route["candidate_product_groups"], ["예금성", "대출성"])

    def test_single_confirmed_value_can_narrow(self):
        route = retrieval.routing_scope([routing_row("대출성", "confirmed")])
        self.assertFalse(route["routing_provisional"])
        self.assertEqual(route["candidate_product_groups"], ["대출성"])

    def test_applicable_union_keeps_both_product_rules(self):
        deposit = {"적용상품": ["예금성"]}
        loan = {"적용상품": ["대출성"]}
        scope = ["예금성", "대출성"]
        self.assertTrue(retrieval.applicable_to_any(deposit, scope))
        self.assertTrue(retrieval.applicable_to_any(loan, scope))


class SearchTextVariantTests(unittest.TestCase):
    def test_expansion_is_explicit_and_v2_only(self):
        item = {
            "title": "제목",
            "question": "질의",
            "criterion": "판정",
            "규칙요약": ["요약"],
            "근거상세": ["상세"],
        }
        core = retrieval.item_search_text(item, variant="core")
        expanded = retrieval.item_search_text(item, variant="expanded")
        self.assertNotIn("요약", core)
        self.assertNotIn("상세", core)
        self.assertIn("요약", expanded)
        self.assertIn("상세", expanded)


class ModelContractTests(unittest.TestCase):
    def test_exact_order_required(self):
        row = request_row(["X-1", "X-2"])
        parsed = {"ad_id": "AD-X", "results": [result("X-2"), result("X-1")]}
        errors = gemma.validate(row, parsed)
        self.assertTrue(any("순서/값" in error for error in errors))

    def test_applicability_cannot_contain_verdict_enum(self):
        row = request_row(["X-1"])
        invalid = result("X-1")
        invalid["applicability"] = "COMPLIANT"
        errors = gemma.validate(row, {"ad_id": "AD-X", "results": [invalid]})
        self.assertTrue(any("applicability enum" in error for error in errors))

    def test_partial_requirement_cannot_be_compliant(self):
        row = request_row(["X-1"])
        invalid = result("X-1")
        invalid["requirement_checks"][0]["status"] = "MISSING"
        errors = gemma.validate(row, {"ad_id": "AD-X", "results": [invalid]})
        self.assertTrue(any("COMPLIANT" in error for error in errors))

    def test_applicable_requires_ad_evidence_or_confirmed_metadata(self):
        row = request_row(["T-1"])
        payload = json.loads(row["messages"][1]["content"])
        payload["rules"] = [{
            "item_id": "T-1",
            "source_sheet": "신규규칙후보",
            "product_subtype": "적립식",
        }]
        payload["routing"]["template_id"] = {
            "value": "적립식", "source": "parser", "status": "inferred",
        }
        row["messages"][1]["content"] = json.dumps(payload, ensure_ascii=False)
        invalid = result("T-1")
        invalid["applicability_basis"] = "CONFIRMED_METADATA"
        invalid["applicability_evidence_ids"] = []
        invalid["applicability_evidence_line_refs"] = []
        invalid["applicability_metadata_fields"] = ["template_id"]
        errors = gemma.validate(row, {"ad_id": "AD-X", "results": [invalid]})
        self.assertTrue(any("T 규칙 APPLICABLE" in error for error in errors))

    def test_confirmed_metadata_names_are_validated(self):
        row = request_row(["X-1"])
        invalid = result("X-1")
        invalid["applicability_basis"] = "CONFIRMED_METADATA"
        invalid["applicability_metadata_fields"] = ["template_id"]
        invalid["applicability_evidence_ids"] = []
        invalid["applicability_evidence_line_refs"] = []
        errors = gemma.validate(row, {"ad_id": "AD-X", "results": [invalid]})
        self.assertTrue(any("미확정 template_id" in error for error in errors))

    def test_split_preserves_documents_and_rule_order(self):
        row = request_row(["X-1", "X-2", "X-3", "X-4", "X-5"])
        children = gemma.split_request_row(row)
        self.assertEqual([len(child["requested_item_ids"]) for child in children], [2, 3])
        self.assertEqual(
            [item for child in children for item in child["requested_item_ids"]],
            row["requested_item_ids"],
        )
        original_docs = json.loads(row["messages"][1]["content"])["documents"]
        for child in children:
            self.assertEqual(json.loads(child["messages"][1]["content"])["documents"], original_docs)

    def test_large_invalid_batch_splits_before_same_size_retry(self):
        self.assertEqual(gemma.contract_attempt_limit(request_row([str(i) for i in range(7)])), 1)
        self.assertEqual(gemma.contract_attempt_limit(request_row([str(i) for i in range(6)])), 2)

    def test_completed_split_request_is_resumable_only_in_original_order(self):
        request = request_row(["X-1", "X-2"])
        valid_rows = [
            {"validation_errors": [], "parsed": {"results": [result("X-1")]}},
            {"validation_errors": [], "parsed": {"results": [result("X-2")]}},
        ]
        self.assertTrue(gemma.logical_request_complete(request, valid_rows))
        self.assertFalse(gemma.logical_request_complete(request, list(reversed(valid_rows))))


class OperationalSelectionTests(unittest.TestCase):
    def test_ad_id_filter_is_applied_before_input_set_validation(self):
        ads = {"A": {"ad_id": "A"}, "B": {"ad_id": "B"}}
        coarse = [{"ad_id": "A"}, {"ad_id": "B"}]
        fine = [{"ad_id": "A"}, {"ad_id": "B"}]
        selected_ads, selected_coarse, selected_fine = operational.select_ads(
            ads, coarse, fine, ["B"],
        )
        self.assertEqual(list(selected_ads), ["B"])
        self.assertEqual([row["ad_id"] for row in selected_coarse], ["B"])
        self.assertEqual([row["ad_id"] for row in selected_fine], ["B"])

    def test_integrated_routing_keeps_template_inferred(self):
        ad = {"document": {"routing_metadata": {
            "template_id": "적립식",
            "classification_source": "filename_and_vlm",
        }}}
        product_route = {
            "candidate_product_groups": ["예금성", "대출성"],
            "routing_provisional": True,
        }
        context = operational.routing_context(ad, product_route)
        self.assertEqual(context["template_id"]["value"], "적립식")
        self.assertEqual(context["template_id"]["status"], "inferred")


if __name__ == "__main__":
    unittest.main()
