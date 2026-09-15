# -*- coding: utf-8 -*-
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

import hybrid_rule_retrieval as retrieval  # noqa: E402
import run_gemma_exhaustive_dgx as gemma  # noqa: E402
import run_operational_e2e as operational  # noqa: E402
from rag.parsing import prepare_inputs  # noqa: E402
from rag.judgment.applicability import partition_operational_candidates  # noqa: E402
from rag.judgment.evidence_projection import pack_documents, unpack_documents  # noqa: E402


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
            "finding_basis": "OBSERVED",
            "evidence_ids": ["E-1"],
            "evidence_line_refs": ["L-1"],
            "reason": "근거 확인",
        }],
    }


class WireEvidenceTests(unittest.TestCase):
    def test_fine_visibility_uses_parent_and_only_selected_lines(self):
        facts = {"parser_visibility": {"pages": [{"page_no": 1, "canvas_w": 100,
            "regions": [{"evidence_id": "parent", "line_styles": [
                {"line_ref": "L1", "style": {"size_pt": 10}},
                {"line_ref": "L2", "style": {"size_pt": 20}}]},
                {"evidence_id": "other-product", "line_styles": []}]}]}}
        result = operational.model_deterministic_facts(facts, [
            {"evidence_id": "fine", "parent_evidence_id": "parent", "line_refs": ["L1"]}])
        page = result["parser_visibility"]["pages"][0]
        self.assertEqual(page["canvas_w"], 100)
        self.assertEqual(len(page["regions"]), 1)
        self.assertEqual(page["regions"][0]["line_styles"], [{"line_ref": "L1", "style": {"size_pt": 10}}])

    def test_visibility_model_aliases_resolve_to_the_same_source(self):
        row = request_row(["C-1"])
        payload = json.loads(row["messages"][1]["content"])
        payload["documents"][0]["parent_evidence_id"] = "parent"
        payload["deterministic_facts"] = {"parser_visibility": {"pages": [{"regions": [
            {"evidence_id": "parent", "line_styles": [{"line_ref": "L-1", "style": {"size_pt": 10}}]}]}]}}
        row["messages"][1]["content"] = json.dumps(payload)
        messages, aliases = gemma._compact_model_request(row)
        region = json.loads(messages[1]["content"])["deterministic_facts"]["parser_visibility"]["pages"][0]["regions"][0]
        self.assertEqual(region["evidence_refs"], ["E1"])
        self.assertEqual(aliases["ref_to_line"][region["line_styles"][0]["line_ref"]], "L-1")
        self.assertEqual(region["line_styles"][0]["style"], {"size_pt": 10})

    def test_output_check_refs_and_citation_allowlist_are_source_bound(self):
        row = request_row(["C-1", "C-2"])
        payload = json.loads(row["messages"][1]["content"])
        payload["rules"][0]["condition_contract"] = {"applicability_conditions": [], "review_conditions": []}
        payload["rules"][1]["condition_contract"] = {"applicability_conditions": [{"condition_id": "A2"}], "review_conditions": []}
        payload["evidence_scope"] = {"C-1": {"evidence_ids": ["E-1"]}, "C-2": {"evidence_ids": []}}
        row["messages"][1]["content"] = json.dumps(payload)
        messages, _ = gemma._compact_model_request(row)
        wire = json.loads(messages[1]["content"])
        self.assertEqual(wire["rules"][0]["output_check_refs"]["condition_checks"], [])
        self.assertEqual(wire["rules"][1]["output_check_refs"]["condition_checks"], ["A2"])
        self.assertEqual(wire["evidence_scope"]["R1"]["line_refs"], ["L1"])
        self.assertEqual(wire["evidence_scope"]["R2"]["line_refs"], [])

    def test_checkpoint_rejects_changed_evidence_projection(self):
        source = Path(__file__)
        payload = gemma.checkpoint_payload(input_path=source, host=None, model="test", rows_by_id={})
        self.assertEqual(payload["evidence_projection_sha256"], gemma.sha256(ROOT / "rag/judgment/evidence_projection.py"))
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "checkpoint.json"
            checkpoint.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(gemma.load_checkpoint(checkpoint, input_path=source, host=None, model="test"), {})
            payload["evidence_projection_sha256"] = "previous projection"
            checkpoint.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "evidence_projection_sha256"):
                gemma.load_checkpoint(checkpoint, input_path=source, host=None, model="test")

    def test_retry_history_retains_failure_without_sending_history_to_model(self):
        row = request_row(["C-1"])
        failed = {"validation_errors": ["missing result"], "model_parsed": {"results": []}, "usage": {"prompt_tokens": 10}}
        valid = {"validation_errors": [], "usage": {"prompt_tokens": 11}}
        with patch.object(gemma, "contract_attempt_limit", return_value=2), patch.object(gemma, "call_once", side_effect=[failed, valid]) as call:
            result = gemma.call_with_retry(row, None, None, "test", 100)
        self.assertEqual(len(result["call_history"]), 2)
        self.assertEqual(result["call_history"][0]["validation_errors"], ["missing result"])
        self.assertEqual(result["call_history"][0]["usage"]["prompt_tokens"], 10)
        self.assertEqual(result["call_history"][0]["model_parsed"], {"results": []})
        self.assertNotIn("call_history", json.dumps(call.call_args.args[0]))

    def test_split_history_preserves_each_failed_ancestor_once(self):
        row = request_row(["C-1", "C-2", "C-3", "C-4"])
        def mock_retry(request, *args):
            return {"validation_errors": ["split"] if len(request["requested_item_ids"]) > 1 else [],
                    "call_history": [{"request_id": request["request_id"]}]}
        with patch.object(gemma, "call_with_retry", side_effect=mock_retry):
            results = gemma.call_with_retry_and_split(row, None, None, "test", 100)
        history = [event for result in results for event in result["call_history"]]
        self.assertEqual(len(results), 4)
        self.assertEqual(len(history), 7)  # 1 root + 2 internal + 4 leaves
        self.assertEqual(len({event["request_id"] for event in history}), 7)

    def test_wire_evidence_preserves_exact_line_text_without_duplication(self):
        row = request_row(["C-1"])
        payload = json.loads(row["messages"][1]["content"])
        payload["documents"] = [{"evidence_id": "E-1", "line_refs": ["L-1", "L-2"],
                                 "text": "첫째 줄\n둘째 줄", "line_texts": {"L-1": "첫째 줄", "L-2": "둘째 줄"}}]
        row["messages"][1]["content"] = json.dumps(payload, ensure_ascii=False)
        messages, aliases = gemma._compact_model_request(row)
        document = json.loads(messages[1]["content"])["documents"][0]
        self.assertNotIn("text", document)
        self.assertEqual(list(document["lines"].values()), ["첫째 줄", "둘째 줄"])
        self.assertEqual([aliases["ref_to_line"][ref] for ref in document["lines"]], ["L-1", "L-2"])

    def test_wire_packing_round_trip_preserves_scope_text_boxes_and_uncertainty(self):
        selection = {"needs_review": True, "confidence": 0.0, "reason": "읽기 불확실성"}
        documents = [{
            "evidence_ref": ref, "page_no": page, "product_id": product,
            "text": "선택된 문구", "span_status": "region_level_selected_text",
            "line_refs": ["L1", "L2"],
            "lines": [{"line_ref": "L1", "text": "원문\n 줄"}, {"line_ref": "L2", "text": ""}],
            "line_bboxes": [{"line_ref": "L1", "bbox": [0, 1, 2, 3]}],
            "text_selection": selection,
        } for ref, page, product in (("E1", 1, "P1"), ("E2", 2, "P2"))]
        frozen = json.dumps(documents, ensure_ascii=False)
        packed, contexts = pack_documents(documents)
        self.assertEqual(len(contexts), 1)
        self.assertEqual(unpack_documents(packed, contexts), documents)
        self.assertEqual(json.dumps(documents, ensure_ascii=False), frozen)
        self.assertEqual([d["product_id"] for d in packed], ["P1", "P2"])

    def test_wire_packing_does_not_equate_false_missing_and_true_review(self):
        docs = [{"text_selection": value} for value in ({}, {"needs_review": False}, {"needs_review": True})]
        packed, contexts = pack_documents(docs)
        self.assertEqual(len(contexts), 3)
        self.assertEqual(unpack_documents(packed, contexts), docs)
        other_packed, other_contexts = pack_documents([{"text_selection": {"reason": "other request"}}])
        self.assertEqual(other_packed[0]["text_selection_ref"], "Q1")
        self.assertEqual(other_contexts["Q1"], {"reason": "other request"})

    def test_wire_packing_keeps_empty_and_partial_line_information(self):
        docs = [{"line_refs": ["L1", "L2"], "lines": [{"line_ref": "L1", "text": "x"}]},
                {"line_refs": [], "lines": [], "line_bboxes": []}, {"text": "region only"}]
        packed, contexts = pack_documents(docs)
        self.assertEqual(unpack_documents(packed, contexts), docs)
        self.assertNotIn("L2", packed[0]["lines"])

    def test_wire_packing_rejects_lossy_duplicate_keys_and_unknown_fields(self):
        for lines in ([{"line_ref": "L1", "text": "a"}, {"line_ref": "L1", "text": "b"}],
                      [{"line_ref": "L1", "text": "a", "unknown": "must not discard"}]):
            with self.subTest(lines=lines), self.assertRaises(ValueError):
                pack_documents([{"lines": lines}])

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

    def test_semantic_filter_can_cover_all_v2_categories(self):
        query = retrieval.semantic_rule_filter(
            "예금성", set(), ("PRESENCE", "PROHIBIT", "STYLE")
        )
        filters = query["bool"]["filter"]
        self.assertIn(
            {"terms": {"category": ["PRESENCE", "PROHIBIT", "STYLE"]}},
            filters,
        )


class TemplateFirstRoutingTests(unittest.TestCase):
    def test_v2_priority_mapping_uses_only_explicit_source_fields(self):
        template_id = "예금성상품-적립식"
        self.assertTrue(operational.v2_explicitly_mapped_to_template({
            "source_sheet": "실행_점검항목",
            "product_subtype": template_id,
        }, template_id))
        self.assertTrue(operational.v2_explicitly_mapped_to_template({
            "source_sheet": "실행_점검항목",
            "template_sections": f"예금성상품-거치식;{template_id}",
        }, template_id))
        self.assertFalse(operational.v2_explicitly_mapped_to_template({
            "source_sheet": "실행_점검항목",
            "title": "적립식과 의미상 비슷한 제목",
        }, template_id))

    def test_template_code_prefix_does_not_block_explicit_mapping(self):
        """v2 원문은 "[T-108] 예금성상품-적립식"처럼 T 코드를 붙여 적는다."""
        self.assertTrue(operational.v2_explicitly_mapped_to_template({
            "source_sheet": "실행_점검항목",
            "template_sections": (
                "[T-067] 예금성상품-입출식; [T-108] 예금성상품-적립식"
            ),
        }, "예금성상품-적립식"))
        self.assertFalse(operational.v2_explicitly_mapped_to_template({
            "source_sheet": "실행_점검항목",
            "template_sections": "[T-067] 예금성상품-입출식",
        }, "예금성상품-적립식"))

    def test_row_without_template_binding_is_product_scoped_only(self):
        """결합을 적지 않은 행은 상품군 범위가 유일한 원문 한정이다."""
        self.assertFalse(operational.v2_declares_template_binding({
            "source_sheet": "실행_점검항목",
            "template_sections": "",
            "product_subtype": None,
        }))
        self.assertTrue(operational.v2_declares_template_binding({
            "source_sheet": "실행_점검항목",
            "template_sections": "[T-067] 예금성상품-입출식",
        }))
        self.assertTrue(operational.v2_declares_template_binding({
            "source_sheet": "실행_점검항목",
            "product_subtype": "예금성상품-적립식",
        }))

    def test_template_sections_drop_code_prefix_only(self):
        self.assertEqual(
            operational.v2_template_sections({
                "template_sections": "[T-067] 예금성상품-입출식; 예금성상품-적립식",
            }),
            ["예금성상품-입출식", "예금성상품-적립식"],
        )

    def test_independent_template_rule_is_not_treated_as_v2_mapping(self):
        self.assertFalse(operational.v2_explicitly_mapped_to_template({
            "source_sheet": "HWPX_TEMPLATE",
            "product_subtype": "예금성상품-적립식",
        }, "예금성상품-적립식"))

    def test_uncertain_supplemental_rule_is_separate_review_candidate(self):
        supplemental = {
            "item_id": "C-1",
            "discovery_tier": "SUPPLEMENTAL_V2",
            "judgment": {"applicability": "UNDETERMINED", "verdict": "UNDETERMINED"},
        }
        mapped = {
            "item_id": "C-2",
            "discovery_tier": "MAPPED_V2",
            "judgment": {"applicability": "APPLICABLE", "verdict": "UNDETERMINED"},
        }
        formal, review, excluded = partition_operational_candidates(
            [supplemental, mapped]
        )
        self.assertEqual(formal, [mapped])
        self.assertEqual(review, [supplemental])
        self.assertEqual(excluded, [])


class RuleBasisTests(unittest.TestCase):
    def test_supporting_rule_objects_become_identifiers_not_repr(self):
        basis = operational.rule_basis(
            {
                "item_id": "D-163",
                "legal_basis": "금융소비자 보호에 관한 법률 제22조 제2항",
                "representative_rule_id": "R-1745",
                "supporting_rules": [
                    {"id": "R-1745", "대표": True, "요약": "광고 내 수치 산식·합계 검산"},
                    {"id": "R-1746", "대표": False, "요약": "오인 유발 표시 금지"},
                ],
                "basis_details": "은행 광고심의 기준 제17조 제1호",
                "source_sheet": "실행_점검항목",
            },
            regulation_sha256="0" * 64,
            template_sha256=None,
        )
        refs = basis["legal_basis_refs"]
        self.assertNotIn(True, [ref.startswith("{") for ref in refs])
        self.assertIn("R-1745", refs)
        self.assertIn("R-1746", refs)
        self.assertEqual(len(refs), len(set(refs)))

    def test_plain_string_basis_is_preserved(self):
        basis = operational.rule_basis(
            {
                "item_id": "C-001",
                "legal_basis": "금융소비자 보호에 관한 법률 제22조 제2항",
                "supporting_rules": ["R-0001"],
                "source_sheet": "실행_점검항목",
            },
            regulation_sha256="0" * 64,
            template_sha256=None,
        )
        self.assertEqual(
            basis["legal_basis_refs"],
            ["금융소비자 보호에 관한 법률 제22조 제2항", "R-0001"],
        )


class ModelContractTests(unittest.TestCase):
    def test_parser_accepts_one_complete_json_object_with_closing_fence(self):
        self.assertEqual(gemma.parse_content('{"results": []}\n```'), {"results": []})

    def test_external_partial_input_cannot_be_wholly_compliant(self):
        row = request_row(["X-1"])
        payload = json.loads(row["messages"][1]["content"])
        payload["external_input_assessment"] = {"X-1": {"input_mode": "PARTIAL"}}
        row["messages"][1]["content"] = json.dumps(payload)
        errors = gemma.validate(row, {"ad_id": "AD-X", "results": [result("X-1")]})
        self.assertTrue(any("PARTIAL" in error for error in errors))

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

    def test_satisfied_requirement_cannot_use_unknown_basis(self):
        row = request_row(["X-1"])
        invalid = result("X-1")
        invalid["requirement_checks"][0]["finding_basis"] = "UNKNOWN"
        errors = gemma.validate(row, {"ad_id": "AD-X", "results": [invalid]})
        self.assertTrue(any("SATISFIED finding_basis" in error for error in errors))

    def test_complete_prohibition_absence_can_be_compliant(self):
        row = request_row(["D-178"])
        row["category"] = "PROHIBIT"
        payload = json.loads(row["messages"][1]["content"])
        payload["evidence_scope"] = {
            "D-178": {"evidence_ids": ["E-1"], "complete_ad_scan": True}
        }
        row["messages"][1]["content"] = json.dumps(payload, ensure_ascii=False)
        valid = result("D-178")
        valid["requirement_checks"][0].update(
            status="SATISFIED",
            finding_basis="ABSENCE",
            evidence_ids=[],
            evidence_line_refs=[],
            reason="전체 광고에 금지 표현이 없음",
        )
        errors = gemma.validate(row, {"ad_id": "AD-X", "results": [valid]})
        self.assertFalse(errors, errors)

    def test_complete_presence_missing_cannot_hide_behind_undetermined(self):
        row = request_row(["C-018"])
        payload = json.loads(row["messages"][1]["content"])
        payload["evidence_scope"] = {
            "C-018": {"evidence_ids": ["E-1"], "complete_ad_scan": True}
        }
        row["messages"][1]["content"] = json.dumps(payload, ensure_ascii=False)
        invalid = result("C-018")
        invalid["verdict"] = "UNDETERMINED"
        invalid["requirement_checks"] = [
            {
                "requirement": "필수 문구",
                "status": "MISSING",
                "finding_basis": "ABSENCE",
                "evidence_ids": [],
                "evidence_line_refs": [],
                "reason": "광고 전체에 없음",
            },
            {
                "requirement": "추가 조건",
                "status": "UNDETERMINED",
                "finding_basis": "UNKNOWN",
                "evidence_ids": [],
                "evidence_line_refs": [],
                "reason": "외부 확인 필요",
            },
        ]
        errors = gemma.validate(row, {"ad_id": "AD-X", "results": [invalid]})
        self.assertTrue(any("필수요건" in error for error in errors))

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

    def test_split_isolates_documents_to_child_rule_scopes(self):
        row = request_row(["X-1", "X-2"])
        payload = json.loads(row["messages"][1]["content"])
        payload["documents"] = [
            {"evidence_id": "E-1", "line_refs": ["L-1"], "text": "첫 근거"},
            {"evidence_id": "E-2", "line_refs": ["L-2"], "text": "둘째 근거"},
        ]
        payload["evidence_scope"] = {
            "X-1": {"evidence_ids": ["E-1"], "complete_ad_scan": False},
            "X-2": {"evidence_ids": ["E-2"], "complete_ad_scan": False},
        }
        row["messages"][1]["content"] = json.dumps(payload, ensure_ascii=False)

        children = gemma.split_request_row(row)

        first = json.loads(children[0]["messages"][1]["content"])
        second = json.loads(children[1]["messages"][1]["content"])
        self.assertEqual([doc["evidence_id"] for doc in first["documents"]], ["E-1"])
        self.assertEqual([doc["evidence_id"] for doc in second["documents"]], ["E-2"])
        self.assertEqual(list(first["evidence_scope"]), ["X-1"])
        self.assertEqual(list(second["evidence_scope"]), ["X-2"])

    def test_retry_instruction_lists_only_confirmed_metadata_and_scoped_evidence(self):
        row = request_row(["T-1"])
        payload = json.loads(row["messages"][1]["content"])
        payload["evidence_scope"] = {
            "T-1": {"evidence_ids": ["E-1"], "complete_ad_scan": False}
        }
        payload["routing"] = {
            "product_group": {
                "value": "예금성",
                "routing_provisional": False,
            },
            "template_id": {
                "value": "예금성상품-적립식",
                "status": "provided",
            },
            "product_subtype": {
                "value": "적립식",
                "status": "inferred",
            },
        }
        row["messages"][1]["content"] = json.dumps(payload, ensure_ascii=False)

        instruction = gemma.retry_contract_instruction(row, ["계약 오류"])

        self.assertIn("입력의 rule_ref 순서와 E/L 참조", instruction)
        self.assertIn('T-1', instruction)
        self.assertNotIn('allowed_evidence_ids_by_item', instruction)

    def test_large_invalid_batch_splits_before_same_size_retry(self):
        self.assertEqual(gemma.contract_attempt_limit(request_row([str(i) for i in range(7)])), 1)
        self.assertEqual(gemma.contract_attempt_limit(request_row([str(i) for i in range(6)])), 2)
        self.assertEqual(gemma.contract_attempt_limit(request_row(["X-1"])), 3)

    def test_non_applicable_basis_is_canonicalized_with_audit_record(self):
        parsed = {"results": [dict(
            result("X-1"),
            applicability="NOT_APPLICABLE",
            verdict="NOT_APPLICABLE",
            applicability_basis="ADVERTISEMENT_EVIDENCE",
        )]}

        changes = gemma.normalize_contract_sentinels(parsed)

        self.assertEqual(parsed["results"][0]["applicability_basis"], "NOT_APPLICABLE")
        self.assertEqual(changes, [{
            "item_id": "X-1",
            "field": "applicability_basis",
            "from": "ADVERTISEMENT_EVIDENCE",
            "to": "NOT_APPLICABLE",
        }])

    def test_basis_is_not_normalized_when_semantic_statuses_conflict(self):
        parsed = {"results": [dict(
            result("X-1"),
            applicability="NOT_APPLICABLE",
            verdict="COMPLIANT",
            applicability_basis="ADVERTISEMENT_EVIDENCE",
        )]}

        self.assertEqual(gemma.normalize_contract_sentinels(parsed), [])
        self.assertEqual(
            parsed["results"][0]["applicability_basis"], "ADVERTISEMENT_EVIDENCE"
        )

    def test_requirement_line_refs_are_promoted_without_changing_verdict(self):
        parsed = {"results": [dict(
            result("X-1"),
            verdict="VIOLATION",
            evidence_line_refs=[],
            requirement_checks=[{
                "requirement": "observed issue",
                "status": "VIOLATED",
                "finding_basis": "OBSERVED",
                "evidence_ids": ["E-1"],
                "evidence_line_refs": ["L-1"],
                "reason": "observed",
            }],
        )]}

        changes = gemma.normalize_contract_sentinels(parsed)

        self.assertEqual(parsed["results"][0]["verdict"], "VIOLATION")
        self.assertEqual(parsed["results"][0]["evidence_line_refs"], ["L-1"])
        self.assertEqual(changes[0]["field"], "evidence_line_refs")

    def test_completed_split_request_is_resumable_only_in_original_order(self):
        request = request_row(["X-1", "X-2"])
        valid_rows = [
            {"validation_errors": [], "parsed": {"results": [result("X-1")]}},
            {"validation_errors": [], "parsed": {"results": [result("X-2")]}},
        ]
        self.assertTrue(gemma.logical_request_complete(request, valid_rows))
        self.assertFalse(gemma.logical_request_complete(request, list(reversed(valid_rows))))

    def test_narrow_window_cannot_prove_missing(self):
        row = request_row(["C-1"])
        payload = json.loads(row["messages"][1]["content"])
        payload["evidence_scope"] = {
            "C-1": {"evidence_ids": ["E-1"], "complete_ad_scan": False}
        }
        row["messages"][1]["content"] = json.dumps(payload, ensure_ascii=False)
        invalid = result("C-1")
        invalid["verdict"] = "VIOLATION"
        invalid["requirement_checks"][0]["status"] = "MISSING"
        invalid["requirement_checks"][0]["finding_basis"] = "ABSENCE"
        errors = gemma.validate(row, {"ad_id": "AD-X", "results": [invalid]})
        self.assertTrue(any("축소 근거 창" in error for error in errors))

    def test_deterministic_review_number_blocks_missing_claim(self):
        row = request_row(["C-1"])
        payload = json.loads(row["messages"][1]["content"])
        payload["rules"] = [
            {"item_id": "C-1", "title": "심의필번호 표시", "criterion": "번호 확인"}
        ]
        payload["deterministic_facts"] = {"review_number_present": True}
        row["messages"][1]["content"] = json.dumps(payload, ensure_ascii=False)
        invalid = result("C-1")
        invalid["verdict"] = "VIOLATION"
        invalid["requirement_checks"][0]["status"] = "MISSING"
        invalid["requirement_checks"][0]["finding_basis"] = "ABSENCE"
        errors = gemma.validate(row, {"ad_id": "AD-X", "results": [invalid]})
        self.assertTrue(any("관측값" in error for error in errors))

    def test_violated_requires_observed_evidence(self):
        row = request_row(["C-1"])
        invalid = result("C-1")
        invalid["verdict"] = "VIOLATION"
        invalid["requirement_checks"][0].update(
            status="VIOLATED", finding_basis="OBSERVED",
            evidence_ids=[], evidence_line_refs=[],
        )
        errors = gemma.validate(row, {"ad_id": "AD-X", "results": [invalid]})
        self.assertTrue(any("관찰 근거 없는 VIOLATED" in error for error in errors))

    def test_violation_requires_original_line_reference(self):
        row = request_row(["C-1"])
        invalid = result("C-1")
        invalid["verdict"] = "VIOLATION"
        invalid["evidence_line_refs"] = []
        invalid["requirement_checks"][0].update(
            status="VIOLATED", finding_basis="OBSERVED",
            evidence_ids=["E-1"], evidence_line_refs=[],
        )
        errors = gemma.validate(row, {"ad_id": "AD-X", "results": [invalid]})
        self.assertTrue(any("원본 줄 근거" in error for error in errors))

    def test_complete_scan_missing_violation_does_not_invent_line_reference(self):
        row = request_row(["C-1"])
        payload = json.loads(row["messages"][1]["content"])
        payload["evidence_scope"] = {
            "C-1": {"evidence_ids": ["E-1"], "complete_ad_scan": True}
        }
        row["messages"][1]["content"] = json.dumps(payload, ensure_ascii=False)
        valid = result("C-1")
        valid.update(
            verdict="VIOLATION",
            evidence_ids=["E-1"],
            evidence_line_refs=[],
        )
        valid["requirement_checks"][0].update(
            status="MISSING",
            finding_basis="ABSENCE",
            evidence_ids=["E-1"],
            evidence_line_refs=[],
            reason="완전 스캔에서 필수 문구를 찾지 못함",
        )
        self.assertEqual(
            gemma.validate(row, {"ad_id": "AD-X", "results": [valid]}), []
        )

    def test_complete_text_scan_cannot_be_called_incomplete(self):
        row = request_row(["C-1"])
        payload = json.loads(row["messages"][1]["content"])
        payload["rules"][0]["required_medium"] = "텍스트"
        payload["evidence_scope"] = {
            "C-1": {"evidence_ids": ["E-1"], "complete_ad_scan": True}
        }
        row["messages"][1]["content"] = json.dumps(payload, ensure_ascii=False)
        invalid = result("C-1")
        invalid.update(
            verdict="UNDETERMINED",
            reason="The scan or required layout/external input is incomplete.",
        )
        invalid["requirement_checks"][0].update(
            status="UNDETERMINED",
            finding_basis="UNKNOWN",
            evidence_ids=[],
            evidence_line_refs=[],
            reason="The scan is incomplete.",
        )
        errors = gemma.validate(row, {"ad_id": "AD-X", "results": [invalid]})
        self.assertTrue(any("전체 스캔을 미완료" in error for error in errors))

    def test_applicable_unknown_obligation_check_is_restored_from_frozen_rule(self):
        row = request_row(["C-1"])
        payload = json.loads(row["messages"][1]["content"])
        payload["rules"][0]["condition_contract"] = {
            "scope_ref": "SCOPE",
            "applicability_conditions": [],
            "review_conditions": [],
            "obligation": {"obligation_id": "O1", "text": "필수 문구 표시"}
        }
        row["messages"][1]["content"] = json.dumps(payload, ensure_ascii=False)
        parsed = {"results": [dict(
            result("C-1"),
            verdict="UNDETERMINED",
            requirement_checks=[],
            reason="확인 자료 부족",
            scope_check={"scope_ref": "SCOPE", "status": "MATCHED"},
            condition_checks=[],
            review_condition_checks=[],
        )]}

        changes = gemma.normalize_contract_sentinels(parsed, row)

        check = parsed["results"][0]["requirement_checks"][0]
        self.assertEqual(check["requirement"], "필수 문구 표시")
        self.assertEqual(check["status"], "UNDETERMINED")
        self.assertEqual(check["finding_basis"], "UNKNOWN")
        self.assertTrue(any(change["field"] == "requirement_checks" for change in changes))
        self.assertEqual(gemma.validate(row, {"ad_id": "AD-X", "results": parsed["results"]}), [])

    def test_condition_checks_are_losslessly_reordered_from_frozen_contract(self):
        row = request_row(["C-1"])
        payload = json.loads(row["messages"][1]["content"])
        payload["rules"][0]["condition_contract"] = {
            "scope_ref": "SCOPE",
            "applicability_conditions": [
                {"condition_id": "A1", "text": "첫 번째"},
                {"condition_id": "A2", "text": "둘째 번째"},
            ],
            "review_conditions": [],
            "obligation": {"obligation_id": "O1", "text": "필수 문구"},
        }
        row["messages"][1]["content"] = json.dumps(payload, ensure_ascii=False)
        parsed = {"ad_id": "AD-X", "results": [dict(
            result("C-1"),
            scope_check={"scope_ref": "SCOPE", "status": "MATCHED"},
            condition_checks=[
                {"condition_ref": "A2", "status": "SATISFIED"},
                {"condition_ref": "A1", "status": "SATISFIED"},
            ],
            review_condition_checks=[],
        )]}

        changes = gemma.normalize_contract_sentinels(parsed, row)

        self.assertEqual(
            [check["condition_ref"] for check in parsed["results"][0]["condition_checks"]],
            ["A1", "A2"],
        )
        self.assertTrue(any(change["field"] == "condition_checks" for change in changes))
        self.assertEqual(gemma.validate(row, parsed), [])

    def test_review_number_placeholder_blocks_placeholder_only_violation(self):
        row = request_row(["C-1"])
        payload = json.loads(row["messages"][1]["content"])
        payload["rules"] = [{
            "item_id": "C-1", "title": "심의필번호 형식 준수",
            "criterion": "심의 전 자리표시 형식 인정",
        }]
        payload["deterministic_facts"] = {
            "review_number_placeholder_present": True,
        }
        row["messages"][1]["content"] = json.dumps(payload, ensure_ascii=False)
        invalid = result("C-1")
        invalid["verdict"] = "VIOLATION"
        invalid["needs_researcher_review"] = True
        invalid["requirement_checks"][0].update(
            status="VIOLATED", finding_basis="OBSERVED",
            reason="2026-0000은 자리표시자라 형식 위반",
        )
        errors = gemma.validate(row, {"ad_id": "AD-X", "results": [invalid]})
        self.assertTrue(any("심의번호 자리표시자" in error for error in errors))

    def test_validity_placeholder_range_blocks_placeholder_only_violation(self):
        row = request_row(["C-1"])
        payload = json.loads(row["messages"][1]["content"])
        payload["rules"] = [{
            "item_id": "C-1", "title": "광고 유효기간 기간표기",
            "criterion": "시작일~종료일 형식",
        }]
        payload["deterministic_facts"] = {
            "review_validity_placeholder_range_present": True,
        }
        row["messages"][1]["content"] = json.dumps(payload, ensure_ascii=False)
        invalid = result("C-1")
        invalid["verdict"] = "VIOLATION"
        invalid["needs_researcher_review"] = True
        invalid["requirement_checks"][0].update(
            status="VIOLATED", finding_basis="OBSERVED",
            reason="00.00.00.~00.00.00. 자리표시로 실제 날짜가 아닌",
        )
        errors = gemma.validate(row, {"ad_id": "AD-X", "results": [invalid]})
        self.assertTrue(any("유효기간 자리표시자" in error for error in errors))

    def test_confirmed_notice_does_not_become_push_from_body_mentions(self):
        row = request_row(["C-1"])
        payload = json.loads(row["messages"][1]["content"])
        payload["routing"]["media_type"] = {
            "value": "NOTICE", "source": "web_user", "status": "provided",
        }
        payload["rules"] = [{
            "item_id": "C-1", "title": "수신거부 방법 표시",
            "criterion": "전자적 전송매체 광고의 무료 수신거부",
        }]
        row["messages"][1]["content"] = json.dumps(payload, ensure_ascii=False)
        invalid = result("C-1")
        errors = gemma.validate(row, {"ad_id": "AD-X", "results": [invalid]})
        self.assertTrue(any("확정 매체 NOTICE" in error for error in errors))

        valid = result("C-1")
        valid.update(
            applicability="NOT_APPLICABLE",
            applicability_basis="NOT_APPLICABLE",
            applicability_evidence_ids=[],
            applicability_evidence_line_refs=[],
            verdict="NOT_APPLICABLE",
            evidence_ids=[], evidence_line_refs=[],
            requirement_checks=[{
                "requirement": "전송형 매체 적용 여부",
                "status": "NOT_APPLICABLE", "finding_basis": "UNKNOWN",
                "evidence_ids": [], "evidence_line_refs": [],
                "reason": "NOTICE는 전송형 매체가 아님",
            }],
        )
        self.assertEqual(
            gemma.validate(row, {"ad_id": "AD-X", "results": [valid]}), []
        )

    def test_compact_wire_aliases_are_restored_by_the_runner(self):
        row = request_row(["C-1"])
        payload = json.loads(row["messages"][1]["content"])
        payload["evidence_scope"] = {
            "C-1": {"evidence_ids": ["E-1"], "complete_ad_scan": True}
        }
        row["messages"][1]["content"] = json.dumps(payload, ensure_ascii=False)
        messages, aliases = gemma._compact_model_request(row)
        compact_payload = json.loads(messages[1]["content"])
        self.assertEqual(compact_payload["rules"][0]["rule_ref"], "R1")
        self.assertEqual(compact_payload["documents"][0]["evidence_ref"], "E1")
        self.assertNotIn("E-1", messages[1]["content"])

    def test_compact_wire_recovers_legacy_combined_evidence_and_line_alias(self):
        row = request_row(["C-1"])
        messages, aliases = gemma._compact_model_request(row)
        self.assertIn('["E1", "L1"]', messages[0]["content"])
        parsed = gemma._expand_model_response(row, {"results": [{
            "rule_ref": "R1",
            "applicability": "APPLICABLE",
            "applicability_basis": "ADVERTISEMENT_EVIDENCE",
            "applicability_evidence_refs": ["E1|L1"],
            "applicability_metadata_fields": [],
            "verdict": "COMPLIANT",
            "evidence_refs": ["E1|L1"],
            "requirement_checks": [{
                "requirement": "required", "status": "SATISFIED",
                "finding_basis": "OBSERVED", "evidence_refs": ["E1|L1"],
                "reason": "found",
            }],
            "reason": "found", "confidence": "HIGH",
            "needs_researcher_review": False,
        }]}, aliases)
        self.assertEqual(parsed["results"][0]["evidence_ids"], ["E-1"])
        self.assertEqual(parsed["results"][0]["evidence_line_refs"], ["L-1"])

    def test_compact_wire_sends_boxes_only_to_spatial_rules(self):
        row = request_row(["C-1"])
        payload = json.loads(row["messages"][1]["content"])
        payload["documents"][0].update(
            bbox=[0, 0, 100, 100], line_bboxes={"L-1": [1, 2, 3, 4]}
        )
        row["messages"][1]["content"] = json.dumps(payload, ensure_ascii=False)
        messages, aliases = gemma._compact_model_request(row)
        document = json.loads(messages[1]["content"])["documents"][0]
        self.assertNotIn("bbox", document)
        self.assertNotIn("line_bboxes", document)

        payload["rules"][0]["required_medium"] = "레이아웃"
        row["messages"][1]["content"] = json.dumps(payload, ensure_ascii=False)
        messages, _ = gemma._compact_model_request(row)
        document = json.loads(messages[1]["content"])["documents"][0]
        self.assertEqual(document["bbox"], [0, 0, 100, 100])
        self.assertEqual(document["line_bboxes"], {"L1": [1, 2, 3, 4]})
        parsed = gemma._expand_model_response(row, {"results": [{
            "rule_ref": "R1",
            "applicability": "APPLICABLE",
            "applicability_basis": "ADVERTISEMENT_EVIDENCE",
            "applicability_evidence_refs": ["E1", "L1"],
            "applicability_metadata_fields": [],
            "verdict": "COMPLIANT",
            "evidence_refs": ["E1", "L1"],
            "requirement_checks": [{
                "requirement": "필수 항목", "status": "SATISFIED",
                "finding_basis": "OBSERVED", "evidence_refs": ["E1", "L1"],
                "reason": "근거 확인",
            }],
            "reason": "근거 확인", "confidence": "HIGH",
            "needs_researcher_review": False,
        }]}, aliases)
        self.assertEqual(parsed["ad_id"], "AD-X")
        self.assertEqual(parsed["results"][0]["item_id"], "C-1")
        self.assertEqual(parsed["results"][0]["evidence_ids"], ["E-1"])
        self.assertEqual(parsed["results"][0]["evidence_line_refs"], ["L-1"])
        self.assertEqual(gemma.validate(row, parsed), [])

    def test_singleton_recovers_missing_rule_alias_by_position(self):
        row = request_row(["C-1"])
        _, aliases = gemma._compact_model_request(row)
        parsed = gemma._expand_model_response(row, {"results": [{
            "rule_ref": None,
            "applicability": "UNDETERMINED",
            "applicability_basis": "UNDETERMINED",
            "applicability_evidence_refs": [],
            "applicability_metadata_fields": [],
            "verdict": "UNDETERMINED",
            "evidence_refs": [],
            "requirement_checks": [{
                "requirement": "확인", "status": "UNDETERMINED",
                "finding_basis": "UNKNOWN", "evidence_refs": [],
                "reason": "근거 부족",
            }],
            "reason": "근거 부족", "confidence": "LOW",
            "needs_researcher_review": True,
        }]}, aliases)
        self.assertEqual(parsed["results"][0]["item_id"], "C-1")
        self.assertEqual(gemma.validate(row, parsed), [])

    def test_compact_gate_derives_non_applicable_without_obligation_output(self):
        row = request_row(["C-1"])
        _, aliases = gemma._compact_model_request(row)
        parsed = gemma._expand_model_response(row, {"results": [{
            "rule_ref": "R1",
            "scope_check": {
                "scope_ref": "SCOPE", "status": "NOT_MATCHED",
                "evidence_refs": [], "metadata_fields": [],
            },
            "condition_checks": [],
            "review_condition_checks": [],
            "verdict": "COMPLIANT",
            "requirement_checks": [{
                "requirement": "검사하지 않아야 할 의무",
                "status": "SATISFIED", "finding_basis": "ABSENCE",
                "evidence_refs": [], "reason": "잘못 생성된 후속 판정",
            }],
            "reason": "선행 상황이 아님", "confidence": "HIGH",
        }]}, aliases)

        value = parsed["results"][0]
        self.assertEqual(value["applicability"], "NOT_APPLICABLE")
        self.assertEqual(value["verdict"], "NOT_APPLICABLE")
        self.assertEqual(value["requirement_checks"], [])

    def test_compact_gate_derives_applicable_and_audit_evidence(self):
        row = request_row(["C-1"])
        _, aliases = gemma._compact_model_request(row)
        parsed = gemma._expand_model_response(row, {"results": [{
            "rule_ref": "R1",
            "scope_check": {
                "scope_ref": "SCOPE", "status": "MATCHED",
                "evidence_refs": ["E1", "L1"], "metadata_fields": [],
            },
            "condition_checks": [],
            "review_condition_checks": [],
            "verdict": "COMPLIANT",
            "requirement_checks": [{
                "requirement": "필수 항목", "status": "SATISFIED",
                "finding_basis": "OBSERVED", "evidence_refs": ["E1", "L1"],
                "reason": "근거 확인",
            }],
            "reason": "근거 확인", "confidence": "HIGH",
        }]}, aliases)

        value = parsed["results"][0]
        self.assertEqual(value["applicability"], "APPLICABLE")
        self.assertEqual(value["applicability_basis"], "ADVERTISEMENT_EVIDENCE")
        self.assertEqual(value["applicability_evidence_ids"], ["E-1"])
        self.assertEqual(value["evidence_line_refs"], ["L-1"])
        self.assertFalse(value["needs_researcher_review"])

    def test_observed_finding_without_direct_evidence_is_rejected(self):
        row = request_row(["C-1"])
        invalid = result("C-1")
        invalid["requirement_checks"][0].update(
            finding_basis="OBSERVED", evidence_ids=[], evidence_line_refs=[]
        )
        errors = gemma.validate(row, {"ad_id": "AD-X", "results": [invalid]})
        self.assertTrue(any("OBSERVED" in error for error in errors))


class OperationalSelectionTests(unittest.TestCase):
    def test_candidate_product_scope_uses_rule_metadata_not_manual_source(self):
        rules = {
            "D-LOAN": {
                "item_id": "D-LOAN",
                "product_groups": ["대출성"],
                "basis_details": ["여신금융협회 매뉴얼"],
            },
            "D-ALL": {
                "item_id": "D-ALL",
                "product_groups": ["전체"],
                "basis_details": ["여신금융협회 매뉴얼"],
            },
        }

        operational.assert_candidate_product_scope(
            ["D-LOAN", "D-ALL"],
            rules=rules,
            confirmed_product_groups=["대출성"],
        )
        with self.assertRaisesRegex(RuntimeError, "D-LOAN"):
            operational.assert_candidate_product_scope(
                ["D-LOAN"],
                rules=rules,
                confirmed_product_groups=["예금성"],
            )

    def test_model_rule_view_keeps_decision_content_not_relational_bookkeeping(self):
        rule = {
            "item_id": "C-100",
            "source_sheet": "v2",
            "title": "generic title",
            "question": "generic question",
            "criterion": "generic criterion",
            "input_requirement": "TEXT",
            "product_groups": ["deposit"],
            "representative_rule_id": "R-100",
            "supporting_rules": ["C-099"],
        }
        view = operational.model_rule_view(rule)
        self.assertEqual(view["item_id"], "C-100")
        self.assertEqual(view["criterion"], "generic criterion")
        self.assertNotIn("representative_rule_id", view)
        self.assertNotIn("supporting_rules", view)

    def test_confirmed_template_can_narrow_only_subtype_specific_v2_rule(self):
        generic = {"item_id": "C-1", "product_subtype": None}
        matching = {"item_id": "C-2", "product_subtype": "loan-name-shown"}
        other = {"item_id": "C-3", "product_subtype": "loan-name-hidden"}
        self.assertTrue(operational.template_scoped_rule(generic, "loan-name-shown"))
        self.assertTrue(operational.template_scoped_rule(matching, "loan-name-shown"))
        self.assertFalse(operational.template_scoped_rule(other, "loan-name-shown"))
        self.assertTrue(operational.template_scoped_rule(other, None))

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

    def test_parser_confidence_does_not_confirm_intake(self):
        vlm = prepare_inputs.parser_classification_field(
            {"product_group": "GROUP-A", "source": "filename_and_vlm", "confidence": 1.0},
            "product_group",
        )
        filename_only = prepare_inputs.parser_classification_field(
            {"product_group": "GROUP-A", "source": "filename_no_vlm", "confidence": None},
            "product_group",
        )
        self.assertEqual(vlm["status"], "inferred")
        self.assertEqual(vlm["confidence"], 1.0)
        self.assertEqual(filename_only["status"], "inferred")

    def test_parser_template_confirmation_cannot_narrow_intake(self):
        confirmed = prepare_inputs.parser_template_field(
            {"template_id": "TEMPLATE-A", "status": "확정"}
        )
        card_scoped = prepare_inputs.parser_template_field(
            {"template_id": "TEMPLATE-A", "status": "card_scoped"}
        )
        self.assertEqual(confirmed["status"], "inferred")
        self.assertEqual(confirmed["parser_status"], "확정")
        self.assertEqual(card_scoped["status"], "inferred")

    def test_routing_manifest_requires_explicit_trust_status(self):
        scalar = operational.manifest_routing_field("GROUP-A")
        confirmed = operational.manifest_routing_field(
            {"value": "GROUP-A", "source": "catalog", "status": "confirmed"}
        )
        self.assertEqual(scalar["status"], "provided")
        self.assertEqual(confirmed["status"], "confirmed")
        with self.assertRaises(ValueError):
            operational.manifest_routing_field(
                {"value": "GROUP-A", "source": "filename", "status": "inferred"}
            )

    def test_rule_evidence_is_narrowed_and_deterministic(self):
        rows = [
            {"doc_id": "E-1"},
            {"doc_id": "E-2"},
            {"doc_id": "E-3"},
        ]
        selected = operational.top_rule_evidence(
            "C-1",
            rule_vector_by_id={"C-1": np.array([1.0, 0.0])},
            ad_fine_rows=rows,
            fine_vector_by_id={
                "E-1": np.array([0.1, 0.9]),
                "E-2": np.array([0.8, 0.2]),
                "E-3": np.array([0.4, 0.6]),
            },
            trigger_ids=["E-1"],
            k=1,
        )
        self.assertEqual(selected, ["E-1", "E-2"])

    def test_rule_evidence_keeps_semantic_hit_when_lexical_pool_is_full(self):
        rows = [{"doc_id": name, "text_canonical": text} for name, text in
                [("A", "조건문 조건문"), ("B", "조건문"), ("C", "조건문"), ("D", "동의어 설명")]]
        vectors = {name: np.array([score, 0.0]) for name, score in
                   [("A", .1), ("B", .2), ("C", .3), ("D", .99)]}
        kwargs = dict(rule_vector_by_id={"generic": np.array([1.0, 0.0])},
                      ad_fine_rows=rows, fine_vector_by_id=vectors,
                      trigger_ids=[], rule_text="조건문")
        selected = operational.top_rule_evidence("generic", k=3, **kwargs)
        self.assertIn("D", selected)
        self.assertEqual(len(selected), 3)
        self.assertEqual(operational.top_rule_evidence("generic", k=0, **kwargs), [])

    def test_template_example_is_available_to_evidence_search(self):
        text = operational.judgment_rule_text({"title": "항목", "example_text": "예시검색어"})
        self.assertIn("예시검색어", text)

    def test_rule_evidence_prefers_direct_lexical_support_over_nearby_metadata(self):
        rows = [
            {"doc_id": "BRANCH", "text_canonical": "지점명 송도캠퍼스타운지점"},
            {"doc_id": "CONTACT", "text_canonical": "담당자 홍길동 연락처 032-000-0000"},
        ]
        selected = operational.top_rule_evidence(
            "D-162",
            rule_vector_by_id={"D-162": np.array([1.0, 0.0])},
            ad_fine_rows=rows,
            fine_vector_by_id={
                "BRANCH": np.array([0.99, 0.01]),
                "CONTACT": np.array([0.2, 0.8]),
            },
            trigger_ids=[],
            k=1,
            rule_text="모집인 영업담당 직원의 개인정보 성명 연락처 노출 금지",
        )
        self.assertEqual(selected, ["CONTACT"])

    def test_rules_requiring_unavailable_inputs_are_deferred(self):
        self.assertFalse(
            operational.automated_input_ready(
                {"required_medium": "레이아웃", "input_requirement": "광고물"}
            )
        )
        self.assertFalse(
            operational.automated_input_ready(
                {"required_medium": "텍스트", "input_requirement": "광고물+랜딩캡처"}
            )
        )
        self.assertTrue(
            operational.automated_input_ready(
                {"required_medium": "텍스트", "input_requirement": "광고물"}
            )
        )

    def test_parser_structure_satisfies_only_the_input_it_actually_contains(self):
        structured = {
            "quality": {"line_partition_exact": True},
            "pages": [
                {
                    "parse_status": "ok",
                    "regions": [
                        {
                            "bbox": None,
                            "visibility": {"position": None},
                            "lines": [{"bbox": None, "style": {"size_pt": 10}}],
                        }
                    ],
                }
            ],
        }
        self.assertTrue(
            operational.automated_input_ready(
                {"required_medium": "텍스트", "input_requirement": "광고물(원본형식)"},
                structured,
            )
        )
        self.assertFalse(
            operational.automated_input_ready(
                {"required_medium": "레이아웃", "input_requirement": "광고물"},
                structured,
            )
        )
        structured["pages"][0]["regions"][0]["bbox"] = [0, 0, 10, 10]
        self.assertFalse(
            operational.automated_input_ready(
                {"source_sheet": "HWPX_TEMPLATE", "required_medium": "레이아웃",
                 "input_requirement": "광고물+원본형식+레이아웃"},
                structured,
            )
        )
        structured["layout_observations"] = {"verified_line_grouping": True}
        self.assertFalse(
            operational.automated_input_ready(
                {"source_sheet": "HWPX_TEMPLATE", "required_medium": "레이아웃",
                 "input_requirement": "광고물+원본형식+레이아웃"},
                structured,
            )
        )
        self.assertFalse(
            operational.automated_input_ready(
                {"required_medium": "레이아웃", "input_requirement": "광고물"},
                structured,
            )
        )
        self.assertFalse(
            operational.automated_input_ready(
                {"required_medium": "레이아웃", "input_requirement": "광고물", "question": "문구의 색상 대비가 충분한가?"},
                structured,
            )
        )
        self.assertFalse(
            operational.automated_input_ready(
                {"required_medium": "레이아웃", "input_requirement": "광고물", "question": "문구의 글자 크기가 기준 이상인가?"},
                structured,
            )
        )
        structured["pages"][0]["regions"][0]["visibility"] = {"contrast_ratio": 4.7}
        self.assertFalse(
            operational.automated_input_ready(
                {"required_medium": "레이아웃", "input_requirement": "광고물", "question": "문구의 색상 대비가 충분한가?"},
                structured,
            )
        )

    def test_unverified_recovery_hint_does_not_downgrade_complete_text_scan(self):
        ad = {
            "quality": {
                "line_partition_exact": True,
                "empty_region_count": 0,
            },
            "pages": [{"parse_status": "ok", "regions": []}],
            "unverified_recovery_candidates": [
                {"text": "57", "status": "unverified", "source": "page_sweep"}
            ],
            "diagnostics": {"empty_regions": []},
        }
        self.assertEqual(operational.parser_coverage(ad), "READY")

    def test_parser_coverage_remains_partial_for_incomplete_text_scan(self):
        base = {
            "quality": {
                "line_partition_exact": True,
                "empty_region_count": 0,
            },
            "pages": [{"parse_status": "ok", "regions": []}],
            "diagnostics": {"empty_regions": []},
        }
        for mutation in (
            {"quality": {"line_partition_exact": False, "empty_region_count": 0}},
            {"quality": {"line_partition_exact": True, "empty_region_count": 1}},
            {"pages": [{"parse_status": "failed", "regions": []}]},
            {"diagnostics": {"empty_regions": [{"page_no": 1}]}},
        ):
            ad = {**base, **mutation}
            self.assertEqual(operational.parser_coverage(ad), "PARTIAL")


if __name__ == "__main__":
    unittest.main()
