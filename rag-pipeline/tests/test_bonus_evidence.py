import copy
import unittest

from rag.judgment.bonus_evidence import bonus_operands
from rag.judgment.review_program import computed_check


class BonusEvidenceTests(unittest.TestCase):
    def fixture(self):
        lines = {
            "S": "우대조건 총 2개, 최대 우대금리 연 0.3%p",
            "H1": "우대조건",
            "H2": "우대금리 (연 %p)",
            "C1": "첫 조건 충족",
            "V1": "0.1",
            "C2": "둘째 조건 충족",
            "V2": "0.2",
            "N": "※ 모든 우대조건 중복 적용 가능",
        }
        cells = []
        for ref, row, col, headers in [
            ("H1", 0, 0, []),
            ("H2", 0, 1, []),
            ("C1", 1, 0, ["H1"]),
            ("V1", 1, 1, ["H2"]),
            ("C2", 2, 0, ["H1"]),
            ("V2", 2, 1, ["H2"]),
        ]:
            cells.append(
                {
                    "cell_id": ref,
                    "row": row,
                    "col": col,
                    "status": "observed",
                    "line_refs": [ref],
                    "header_cell_ids": headers,
                }
            )
        cells[-1]["footnote_line_ids"] = ["N"]
        doc = {
            "evidence_id": "E",
            "line_refs": list(lines),
            "line_texts": lines,
            "table": {"cells": cells},
        }
        return {
            "parser_coverage": "READY",
            "evidence_scope": {"TEST": {"complete_ad_scan": True, "evidence_ids": ["E"]}},
            "documents": [doc],
        }

    def result(self, payload):
        return computed_check(
            {"kind": "BONUS_SUM_BOUND"}, {"evidence_line_refs": ["S", "V1"]}, payload, "TEST"
        )

    def test_observed_table_links_expand_header_other_operand_and_footnote(self):
        payload = self.fixture()
        result = self.result(payload)
        self.assertEqual("SATISFIED", result["status"])
        self.assertTrue(
            {"H1", "H2", "C1", "C2", "V1", "V2", "N"} <= set(result["evidence_line_refs"])
        )
        payload["documents"][0]["line_texts"]["S"] = "우대조건 총 2개, 최대 우대금리 연 0.4%p"
        self.assertEqual("VIOLATED", self.result(payload)["status"])

    def test_percent_unit_is_supported_but_mixed_units_are_unknown(self):
        payload = self.fixture()
        lines = payload["documents"][0]["line_texts"]
        lines["S"], lines["H2"] = lines["S"].replace("%p", "%"), lines["H2"].replace("%p", "%")
        self.assertEqual("SATISFIED", self.result(payload)["status"])
        lines["V2"] = "0.2%p"
        self.assertEqual("UNDETERMINED", self.result(payload)["status"])

    def test_unobserved_missing_or_merged_structure_never_becomes_arithmetic(self):
        for edit in [
            "inferred",
            "headers",
            "missing",
            "merged",
            "row",
            "duplicate",
            "count",
            "scope",
        ]:
            payload = self.fixture()
            doc = payload["documents"][0]
            if edit == "inferred":
                doc["table"]["cells"][-1]["status"] = "inferred"
            if edit == "headers":
                doc["table"]["cells"][-1]["header_cell_ids"] = []
            if edit == "missing":
                del doc["line_texts"]["V2"]
            if edit == "merged":
                doc["table"]["cells"][-1]["row_span"] = 2
            if edit == "row":
                del doc["table"]["cells"][-1]["row"]
            if edit == "duplicate":
                doc["table"]["cells"].append(copy.deepcopy(doc["table"]["cells"][-1]))
            if edit == "count":
                doc["line_texts"]["S"] = doc["line_texts"]["S"].replace("2개", "3개")
            if edit == "scope":
                payload["evidence_scope"]["TEST"]["evidence_ids"] = ["OTHER"]
            with self.subTest(edit=edit):
                self.assertEqual("UNDETERMINED", self.result(payload)["status"])

    def test_unknown_footnote_and_uncited_restriction_are_not_ignored(self):
        for text in [
            "중복 적용 불가",
            "급여 조건과 납입 조건은 선택 적용",
            "세부 조건은 별도 약정에 따릅니다.",
        ]:
            payload = self.fixture()
            payload["documents"][0]["line_texts"]["N"] = text
            self.assertEqual("UNDETERMINED", self.result(payload)["status"])
        payload = self.fixture()
        payload["full_ad_text"] = "추가 각주: 중복하여 적용하지 않음"
        self.assertEqual("UNDETERMINED", self.result(payload)["status"])

    def test_duplicate_views_do_not_duplicate_components_or_cap(self):
        payload = self.fixture()
        second = copy.deepcopy(payload["documents"][0])
        second["evidence_id"] = "E2"
        payload["documents"].append(second)
        payload["evidence_scope"]["TEST"]["evidence_ids"].append("E2")
        self.assertEqual("SATISFIED", self.result(payload)["status"])
        second["line_texts"]["V2"] = "0.9"
        self.assertEqual("UNDETERMINED", self.result(payload)["status"])

    def test_plain_text_requires_bonus_named_cap_and_complete_common_unit(self):
        payload = self.fixture()
        doc = payload["documents"][0]
        doc.pop("table")
        doc["line_texts"]["S"] += ", 우대조건 1: 연 0.1%p, 우대조건 2: 연 0.2%p"
        self.assertEqual("SATISFIED", self.result(payload)["status"])
        doc["line_texts"]["S"] = doc["line_texts"]["S"].replace("최대 우대금리", "최대")
        self.assertIsNone(bonus_operands(payload, "TEST", ["S"]))

    def test_duplicate_cell_line_or_position_cannot_double_count_a_rate(self):
        for field in ("line_refs", "row"):
            payload = self.fixture()
            cells = payload["documents"][0]["table"]["cells"]
            cells[-1][field] = cells[-3][field]
            self.assertEqual("UNDETERMINED", self.result(payload)["status"])

    def test_complete_visit_does_not_override_incomplete_or_uncertain_reading(self):
        for change in ("partial", "missing-coverage", "global", "uncited", "damaged"):
            payload = self.fixture()
            if change == "partial":
                payload["parser_coverage"] = "PARTIAL"
            elif change == "missing-coverage":
                payload.pop("parser_coverage")
            elif change == "global":
                payload["reading_quality"] = {"global_scan_incomplete": True}
            else:
                payload["documents"].append({
                    "evidence_id": "E2", "line_refs": ["U"],
                    "line_texts": {"U": "추가 우대조건 판독 확인" if change == "uncited" else "추가 우대조건 \ufffd"},
                    "text_selection": {"needs_review": change == "uncited"},
                })
                payload["evidence_scope"]["TEST"]["evidence_ids"].append("E2")
            with self.subTest(change=change):
                result = self.result(payload)
                self.assertEqual("UNDETERMINED", result["status"])
                self.assertEqual("UNKNOWN", result["finding_basis"])

    def test_other_product_uncertainty_and_aligned_clean_fallback_do_not_block_sum(self):
        payload = self.fixture()
        payload["documents"].append({
            "evidence_id": "OTHER", "line_refs": ["U"],
            "line_texts": {"U": "다른 상품 판독 확인"},
            "text_selection": {"needs_review": True},
        })
        self.assertEqual("SATISFIED", self.result(payload)["status"])
        fallback = copy.deepcopy(payload["documents"][0])
        fallback.update(evidence_id="FALLBACK", span_status="region_level_selected_text",
                        text_selection={"needs_review": True})
        payload["documents"].append(fallback)
        payload["evidence_scope"]["TEST"]["evidence_ids"].append("FALLBACK")
        result = self.result(payload)
        self.assertEqual("SATISFIED", result["status"])
        self.assertNotIn("FALLBACK", result["evidence_ids"])

    def test_conflicting_advertisement_product_or_revision_cannot_supply_operands(self):
        for field in ("ad_id", "product_id", "revision_id"):
            payload = self.fixture()
            payload["documents"][0][field] = "FIRST"
            payload["evidence_scope"]["TEST"][field] = "SECOND"
            with self.subTest(field=field):
                self.assertEqual("UNDETERMINED", self.result(payload)["status"])
        payload = self.fixture()
        payload["documents"][0]["revision_id"] = "FIRST"
        payload["advertisement_revision_id"] = "SECOND"
        self.assertEqual("UNDETERMINED", self.result(payload)["status"])

    def test_scope_and_citations_must_resolve_completely(self):
        for change in ("missing-document", "duplicate-document", "invalid-ref", "missing-line", "extra-line"):
            payload = self.fixture()
            refs = ["S", "V1"]
            if change == "missing-document":
                payload["evidence_scope"]["TEST"]["evidence_ids"].append("MISSING")
            elif change == "duplicate-document":
                payload["documents"].append(copy.deepcopy(payload["documents"][0]))
            elif change == "invalid-ref":
                refs.append("OUTSIDE")
            elif change == "missing-line":
                del payload["documents"][0]["line_texts"]["C2"]
            else:
                payload["documents"][0]["line_texts"]["UNLINKED"] = "중복 적용 불가"
            with self.subTest(change=change):
                result = computed_check({"kind": "BONUS_SUM_BOUND"},
                                        {"evidence_line_refs": refs}, payload, "TEST")
                self.assertEqual("UNDETERMINED", result["status"])

    def wire(self, source):
        import json
        import run_gemma_exhaustive_dgx as gemma
        from test_operational_rag_contracts import request_row

        request = request_row(["TEST"])
        payload = json.loads(request["messages"][1]["content"])
        payload.update(source)
        payload["routing"]["template_id"] = {"value": "synthetic", "status": "confirmed"}
        payload["rules"][0]["condition_contract"] = {
            "scope_ref": "SCOPE",
            "scope_owner": "RULE",
            "scope_metadata_fields": ["template_id"],
            "applicability_conditions": [],
            "review_conditions": [],
            "obligation_checks": [
                {
                    "obligation_id": "O1",
                    "text": "최대 우대금리와 합 비교",
                    "owners": {"rule": True},
                    "deterministic_adapter": {"kind": "BONUS_SUM_BOUND"},
                }
            ],
            "obligation_logic": {"all": [{"ref": "O1"}]},
        }
        payload["documents"][0]["text"] = "\n".join(payload["documents"][0]["line_texts"].values())
        payload["full_ad_text"] = payload["documents"][0]["text"]
        request["messages"][1]["content"] = json.dumps(payload)
        _, aliases = gemma._compact_model_request(request)
        parsed = gemma._expand_model_response(
            request,
            {
                "results": [
                    {
                        "rule_ref": "R1",
                        "scope_check": {"scope_ref": "SCOPE", "status": "MATCHED"},
                        "condition_checks": [],
                        "review_condition_checks": [],
                        "verdict": "COMPLIANT",
                        "reason": "검증 전 모델 관찰",
                        "confidence": "HIGH",
                        "requirement_checks": [
                            {
                                "obligation_ref": "O1",
                                "requirement": "최대 우대금리와 합 비교",
                                "status": "SATISFIED",
                                "finding_basis": "OBSERVED",
                                "evidence_refs": ["L1", "L5"],
                                "reason": "검증 전 모델 관찰",
                            }
                        ],
                    }
                ]
            },
            aliases,
        )
        return request, parsed

    def test_table_computation_runs_inside_operational_response_expansion(self):
        import run_gemma_exhaustive_dgx as gemma

        request, parsed = self.wire(self.fixture())
        self.assertEqual("SATISFIED", parsed["results"][0]["requirement_checks"][0]["status"])
        self.assertIn("N", parsed["results"][0]["requirement_checks"][0]["evidence_line_refs"])
        self.assertEqual([], gemma.validate(request, parsed))

    def test_partial_or_conflicting_scope_overrides_the_model_pass_on_wire(self):
        import run_gemma_exhaustive_dgx as gemma

        for change in ("partial", "product", "global"):
            payload = self.fixture()
            if change == "partial":
                payload["parser_coverage"] = "PARTIAL"
            elif change == "product":
                payload["documents"][0]["product_id"] = "FIRST"
                payload["evidence_scope"]["TEST"]["product_id"] = "SECOND"
            else:
                payload["reading_quality"] = {"global_scan_incomplete": True}
            with self.subTest(change=change):
                request, parsed = self.wire(payload)
                result = parsed["results"][0]
                self.assertEqual("UNDETERMINED", result["verdict"])
                self.assertEqual("UNKNOWN", result["requirement_checks"][0]["finding_basis"])
                self.assertEqual([], result["requirement_checks"][0]["evidence_line_refs"])
                self.assertEqual([], gemma.validate(request, parsed))
