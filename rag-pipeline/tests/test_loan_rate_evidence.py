"""Synthetic endpoint arithmetic and abstention cases; no advertisement fixtures."""
import copy
import unittest

from rag.judgment.loan_rate_evidence import KIND, endpoint_check


ITEM = "synthetic-endpoint-check"
BASE_LINES = [
    "대출금리 최저 연 4.7% ~ 최고 연 5.3%",
    "기준금리 3.4%, 가산금리 2.1%, 우대금리 0.6%, 이차보전 0.2%",
]


def payload_for(lines=None):
    lines = BASE_LINES if lines is None else lines
    refs = [f"synthetic-source/L{index + 1}" for index in range(len(lines))]
    document = {
        "evidence_id": "synthetic-source", "asset_id": "synthetic-asset",
        "product_id": "synthetic-product", "ad_id": "synthetic-ad",
        "text": "\n".join(lines), "line_refs": refs,
        "line_texts": dict(zip(refs, lines)), "span_status": "line_level_selected_text",
        "text_selection": {"needs_review": False},
        "page_no": 2, "bbox": [12, 25, 312, 87],
        "table_geometry": {"row": 3, "column": 2, "bbox": [13, 26, 310, 86]},
    }
    return {
        "ad_id": "synthetic-ad", "full_ad_text": document["text"],
        "parser_coverage": "READY", "reading_quality": {"global_scan_incomplete": False},
        "documents": [document],
        "evidence_scope": {ITEM: {"complete_ad_scan": True,
                                   "evidence_ids": [document["evidence_id"]]}},
    }


def append_document(payload, document, *, in_scope=True):
    payload["documents"].append(document)
    if in_scope:
        payload["evidence_scope"][ITEM]["evidence_ids"].append(document["evidence_id"])


class LoanRateEvidenceTests(unittest.TestCase):
    def evaluate(self, payload=None, endpoint="MAX", refs=None, **check_fields):
        payload = payload_for() if payload is None else payload
        if refs is None:
            refs = payload["documents"][0].get("line_refs", [])
        check = {"evidence_line_refs": refs, **check_fields}
        return endpoint_check({"kind": KIND, "endpoint": endpoint}, check, payload, ITEM)

    def assert_unknown(self, payload, endpoint="MAX", refs=None):
        result = self.evaluate(payload, endpoint, refs)
        self.assertEqual("UNDETERMINED", result["status"])
        self.assertEqual("UNKNOWN", result["finding_basis"])
        self.assertEqual([], result["evidence_ids"])
        self.assertEqual([], result["evidence_line_refs"])
        return result

    def test_max_min_use_different_source_formulas_with_exact_original_citations(self):
        for endpoint, expected in (("MAX", "5.3"), ("MIN", "4.7")):
            with self.subTest(endpoint=endpoint):
                result = self.evaluate(endpoint=endpoint)
                self.assertEqual("SATISFIED", result["status"])
                self.assertEqual("OBSERVED", result["finding_basis"])
                self.assertEqual(expected, result["calculation_trace"]["calculated_endpoint"])
                self.assertEqual("EXACT_NO_ROUNDING", result["calculation_trace"]["decimal_comparison"])
                self.assertEqual(["synthetic-source"], result["evidence_ids"])
                self.assertEqual(payload_for()["documents"][0]["line_refs"], result["evidence_line_refs"])
                for line in BASE_LINES:
                    self.assertIn('"' + line + '"', result["reason"])

    def test_unequal_endpoint_is_violation_even_when_model_claims_satisfied(self):
        for endpoint, line, other in (
            ("MAX", "대출금리 최저 연 4.7% ~ 최고 연 5.4%", "MIN"),
            ("MIN", "대출금리 최저 연 4.8% ~ 최고 연 5.3%", "MAX"),
        ):
            with self.subTest(endpoint=endpoint):
                payload = payload_for([line, BASE_LINES[1]])
                result = self.evaluate(payload, endpoint, status="SATISFIED", reason="synthetic model assertion")
                self.assertEqual("VIOLATED", result["status"])
                self.assertEqual("SATISFIED", self.evaluate(payload, other)["status"])
                self.assertIn(" != ", result["reason"])

    def test_decimal_arithmetic_does_not_use_float_tolerance(self):
        lines = ["대출금리 최저 연 0.3% ~ 최고 연 0.3%", "기준금리 0.1%, 가산금리 0.2%"]
        for endpoint in ("MAX", "MIN"):
            self.assertEqual("SATISFIED", self.evaluate(payload_for(lines), endpoint)["status"])
        lines[0] = "대출금리 최저 연 0.30000000000000000001% ~ 최고 연 0.30000000000000000001%"
        for endpoint in ("MAX", "MIN"):
            self.assertEqual("VIOLATED", self.evaluate(payload_for(lines), endpoint)["status"])

    def test_decimal_precision_is_preserved_without_rounding(self):
        lines = ["대출금리 최고 연 0.30000000000000000000000000000000000003%",
                 "기준금리 0.10000000000000000000000000000000000001%, 가산금리 0.20000000000000000000000000000000000002%"]
        result = self.evaluate(payload_for(lines))
        self.assertEqual("SATISFIED", result["status"])
        self.assertEqual("0.30000000000000000000000000000000000003", result["calculation_trace"]["calculated_endpoint"])

    def test_authorized_optional_absence_defaults_only_bonus_and_subsidy(self):
        cases = [
            (["대출금리 최저 연 5.3% ~ 최고 연 5.3%", "기준금리 3.4%, 가산금리 2.1%, 이차보전 0.2%"], ["bonus_rate"]),
            (["대출금리 최저 연 4.9% ~ 최고 연 5.5%", "기준금리 3.4%, 가산금리 2.1%, 우대금리 0.6%"], ["subsidy_rate"]),
            (["대출금리 최저 연 5.5% ~ 최고 연 5.5%", "기준금리 3.4%, 가산금리 2.1%"], ["bonus_rate", "subsidy_rate"]),
        ]
        for lines, defaults in cases:
            for endpoint in ("MAX", "MIN"):
                with self.subTest(endpoint=endpoint, defaults=defaults):
                    result = self.evaluate(payload_for(lines), endpoint)
                    self.assertEqual("SATISFIED", result["status"])
                    trace = result["calculation_trace"]
                    self.assertEqual(defaults, trace["absence_defaults"]["roles"])
                    self.assertFalse(trace["absence_defaults"]["product_nonexistence_inferred"])
                    for role in defaults:
                        self.assertTrue(trace["operands"][role]["defaulted"])
                        self.assertIsNone(trace["operands"][role]["line_ref"])
                        self.assertIsNone(trace["operands"][role]["span"])
                    for role in ("base_rate", "spread_rate"):
                        self.assertFalse(trace["operands"][role]["defaulted"])

    def test_single_annual_rate_is_usable_only_with_bonus_unmentioned(self):
        payload = payload_for(["대출금리: 연 6.2%", "기준금리 4.0%, 가산금리 2.2%"])
        for endpoint in ("MAX", "MIN"):
            result = self.evaluate(payload, endpoint)
            self.assertEqual("SATISFIED", result["status"])
            self.assertEqual("SINGLE_RATE_WHEN_BONUS_UNMENTIONED", result["calculation_trace"]["advertised_endpoint"]["role"])
        for extra in ("우대금리 0.0%", "우대 조건은 별도 확인", "금리 감면: 연 0.0%"):
            with self.subTest(extra=extra):
                self.assert_unknown(payload_for(["대출금리: 연 6.2%", "기준금리 4.0%, 가산금리 2.2%, " + extra]))

    def test_nonstandard_optional_role_mentions_are_not_absence(self):
        for unsupported in ("우대: 연 0.5%", "금리 감면: 연 0.5%", "이자 할인: 연 0.5%",
                            "할인: 연 0.5%", "감면: 연 0.5%", "지원: 연 0.5%", "연 0.5% 지원",
                            "이자 보전: 연 0.5%", "지자체 보전 연 0.5%", "보전 있음",
                            "이차 지원: 연 0.5%", "금리 보조: 연 0.5%"):
            with self.subTest(unsupported=unsupported):
                payload = payload_for(["대출금리 최저 연 5.5% ~ 최고 연 5.5%",
                                       "기준금리 3.4%, 가산금리 2.1%", unsupported])
                self.assert_unknown(payload, "MIN")

    def test_an_existing_optional_value_does_not_bind_additional_discount_or_subsidy_rates(self):
        for extra in ("추가 할인 연 0.5%", "지자체 보전 연 0.5%", "우대조건 급여이체 연 0.3%",
                      "이자 지원 연 0.4%", "연 0.3% 추가 감면"):
            for endpoint in ("MAX", "MIN"):
                with self.subTest(extra=extra, endpoint=endpoint):
                    self.assert_unknown(payload_for(BASE_LINES + [extra]), endpoint)

    def test_base_spread_or_endpoint_absence_never_defaults(self):
        for lines in ([BASE_LINES[0], "가산금리 2.1%, 우대금리 0.6%, 이차보전 0.2%"],
                      [BASE_LINES[0], "기준금리 3.4%, 우대금리 0.6%, 이차보전 0.2%"],
                      [BASE_LINES[1]],
                      ["대출금리 안내", BASE_LINES[1]]):
            with self.subTest(lines=lines):
                self.assert_unknown(payload_for(lines))

    def test_mentioned_optional_role_without_value_is_not_zero(self):
        for tail in ("우대금리", "이차보전", "우대금리 산정 불명", "이차보전 금액 확인 필요"):
            with self.subTest(tail=tail):
                self.assert_unknown(payload_for(["대출금리 최고 연 5.5%", "기준금리 3.4%, 가산금리 2.1%, " + tail]))

    def test_full_text_operand_omitted_from_line_scope_is_not_zero(self):
        for tail in ("우대금리 0.5%", "이차보전 0.5%", "우대: 연 0.5%"):
            payload = payload_for(["대출금리 최고 연 5.5%", "기준금리 3.4%, 가산금리 2.1%"])
            payload["full_ad_text"] += "\n" + tail
            self.assert_unknown(payload)

    def test_incomplete_scan_or_unreadable_input_never_establishes_optional_zero(self):
        clean = payload_for(["대출금리 최고 연 5.5%", "기준금리 3.4%, 가산금리 2.1%"])
        mutations = (
            lambda p: p.update(parser_coverage="PARTIAL"),
            lambda p: p["evidence_scope"][ITEM].update(complete_ad_scan=False),
            lambda p: p["evidence_scope"][ITEM].pop("complete_ad_scan"),
            lambda p: p["reading_quality"].update(global_scan_incomplete=True),
            lambda p: p["reading_quality"].update(global_scan_incomplete="false"),
            lambda p: p.update(full_ad_text=""),
            lambda p: p.update(full_ad_text=p["full_ad_text"] + "\ufffd"),
            lambda p: p["documents"][0]["text_selection"].update(needs_review=True),
            lambda p: p["documents"][0]["text_selection"].update(needs_review="false"),
            lambda p: p["documents"][0]["line_texts"].update({"synthetic-source/L2": "기준금리 3.4%, 가산금리 \ufffd%"}),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                payload = copy.deepcopy(clean)
                mutate(payload)
                self.assert_unknown(payload)

    def test_exact_annual_endpoint_unit_is_required_without_unit_conversion(self):
        cases = [
            ["대출금리 최고 5.3%", BASE_LINES[1]],
            ["대출금리 최고 월 5.3%", BASE_LINES[1]],
            [BASE_LINES[0], "기준금리 3.4%, 가산금리 2.1%p, 우대금리 0.6%, 이차보전 0.2%"],
            [BASE_LINES[0], "기준금리 월 3.4%, 가산금리 연 2.1%, 우대금리 0.6%, 이차보전 0.2%"],
            [BASE_LINES[0], "기준금리 3.4bp, 가산금리 2.1%, 우대금리 0.6%, 이차보전 0.2%"],
            ["대출금리 최고 연 5.3%p", BASE_LINES[1]],
        ]
        for lines in cases:
            with self.subTest(lines=lines):
                self.assert_unknown(payload_for(lines))

    def test_full_width_percent_is_same_literal_unit(self):
        payload = payload_for([line.replace("%", "％") for line in BASE_LINES])
        for endpoint in ("MAX", "MIN"):
            self.assertEqual("SATISFIED", self.evaluate(payload, endpoint)["status"])

    def test_multiple_products_assets_conditions_or_variants_are_undetermined(self):
        for key in ("asset_id", "product_id", "rate_variant_id", "revision_id", "ad_id"):
            with self.subTest(key=key):
                payload = payload_for()
                payload["documents"][0][key] = "synthetic-first"
                second = copy.deepcopy(payload["documents"][0])
                second.update(evidence_id="synthetic-second", **{key: "synthetic-second"})
                append_document(payload, second)
                self.assert_unknown(payload)
        payload = payload_for(BASE_LINES + ["기준금리 3.4%, 가산금리 2.1%"])
        self.assert_unknown(payload)

    def test_rounding_selection_and_conditional_rate_text_are_undetermined(self):
        for condition in ("소수 둘째 자리에서 반올림", "소수점 이하 절사", "우대금리는 중복 적용 불가",
                          "금리는 상환방식별로 상이", "조건부 이자 지원", "연 5.3% 또는 연 5.7%",
                          "고정금리와 변동금리 중 선택", "대출기간에 따라 금리가 달라집니다",
                          "대출 기간은 12개월 또는 24개월", "상환 방식은 원금균등 또는 원리금균등",
                          "신용등급 1등급과 2등급 각각 적용"):
            with self.subTest(condition=condition):
                self.assert_unknown(payload_for(BASE_LINES + [condition]))
        payload = payload_for()
        payload["full_ad_text"] += "\n소수 셋째 자리 버림"
        self.assert_unknown(payload)

    def test_unrelated_contact_alternative_does_not_become_a_rate_condition(self):
        payload = payload_for(BASE_LINES + ["상담은 홈페이지 또는 영업점에서 가능합니다."])
        self.assertEqual("SATISFIED", self.evaluate(payload)["status"])

    def test_legacy_frozen_scope_does_not_require_a_fabricated_revision_id(self):
        result = self.evaluate()
        self.assertEqual("SATISFIED", result["status"])
        scope = result["calculation_trace"]["scope"]
        self.assertIsNone(scope["revision_id"])
        self.assertEqual("FROZEN_REQUEST_EVIDENCE_SCOPE", scope["revision_binding"])

    def test_existing_explicit_revision_ids_must_agree_across_request_scope_and_source(self):
        payload = payload_for()
        payload["revision_id"] = "synthetic-revision"
        payload["evidence_scope"][ITEM]["advertisement_revision_id"] = "synthetic-revision"
        payload["documents"][0]["revision_id"] = "synthetic-revision"
        result = self.evaluate(payload)
        self.assertEqual("SATISFIED", result["status"])
        self.assertEqual("EXPLICIT_ID", result["calculation_trace"]["scope"]["revision_binding"])
        payload["documents"][0]["revision_id"] = "synthetic-other-revision"
        self.assert_unknown(payload)

    def test_asset_and_product_identity_are_required(self):
        for key in ("asset_id", "product_id"):
            payload = payload_for()
            payload["documents"][0].pop(key)
            self.assert_unknown(payload)
        payload = payload_for()
        payload["evidence_scope"][ITEM]["product_id"] = "synthetic-other-product"
        self.assert_unknown(payload)

    def test_identical_views_of_the_same_original_lines_are_deduplicated(self):
        payload = payload_for()
        duplicate = copy.deepcopy(payload["documents"][0])
        duplicate["evidence_id"] = "synthetic-second-view"
        append_document(payload, duplicate)
        result = self.evaluate(payload)
        self.assertEqual("SATISFIED", result["status"])
        self.assertEqual(["synthetic-source"], result["evidence_ids"])
        self.assertEqual(2, len(result["evidence_line_refs"]))
        duplicate["line_texts"]["synthetic-source/L2"] = "기준금리 4.4%, 가산금리 1.1%"
        self.assert_unknown(payload)

    def test_uncertain_region_can_only_be_superseded_by_all_its_aligned_clean_lines(self):
        payload = payload_for()
        region = copy.deepcopy(payload["documents"][0])
        region.update(evidence_id="synthetic-region", span_status="region_level_selected_text",
                      text_selection={"needs_review": True})
        append_document(payload, region)
        result = self.evaluate(payload)
        self.assertEqual("SATISFIED", result["status"])
        self.assertEqual(["synthetic-source"], result["evidence_ids"])
        region["line_refs"].append("synthetic-source/L3")
        region["line_texts"]["synthetic-source/L3"] = "판독이 불명확한 추가 조건"
        self.assert_unknown(payload)

    def test_region_only_text_never_invents_fine_line_provenance(self):
        payload = payload_for()
        payload["documents"][0]["span_status"] = "region_level_selected_text"
        self.assert_unknown(payload)

    def test_out_of_scope_uncertain_document_does_not_contaminate_closed_item_scope(self):
        payload = payload_for()
        outside = copy.deepcopy(payload["documents"][0])
        outside.update(evidence_id="synthetic-outside", asset_id="synthetic-outside-asset",
                       product_id="synthetic-outside-product", text_selection={"needs_review": True})
        append_document(payload, outside, in_scope=False)
        self.assertEqual("SATISFIED", self.evaluate(payload)["status"])

    def test_missing_duplicate_or_incomplete_source_provenance_abstains(self):
        mutations = (
            lambda p: p["evidence_scope"][ITEM]["evidence_ids"].append("synthetic-missing"),
            lambda p: p["documents"].append(copy.deepcopy(p["documents"][0])),
            lambda p: p["documents"][0]["line_refs"].append("synthetic-source/L1"),
            lambda p: p["documents"][0]["line_texts"].pop("synthetic-source/L1"),
            lambda p: p["documents"][0]["line_texts"].update({"synthetic-extra/L1": "unused extra text"}),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                payload = payload_for()
                mutate(payload)
                self.assert_unknown(payload)

    def test_model_citation_must_touch_the_original_rate_bundle(self):
        payload = payload_for(BASE_LINES + ["고객센터 안내"])
        for refs in ([], ["synthetic-unknown/L1"], ["synthetic-source/L3"]):
            with self.subTest(refs=refs):
                self.assert_unknown(payload, refs=refs)
        result = self.evaluate(payload, refs=["synthetic-source/L1"])
        self.assertEqual("SATISFIED", result["status"])
        self.assertEqual(["synthetic-source/L1", "synthetic-source/L2"], result["evidence_line_refs"])

    def test_table_headers_and_values_on_separate_lines_are_not_guessed(self):
        self.assert_unknown(payload_for(["대출금리 최고 연 5.3%", "기준금리 | 가산금리 | 우대금리 | 이차보전", "3.4% | 2.1% | 0.6% | 0.2%"] ))

    def test_malformed_optional_metadata_abstains_without_crashing(self):
        mutations = (
            lambda p: p["documents"][0].update(asset_id=[]),
            lambda p: p["documents"][0].update(product_id={}),
            lambda p: p["documents"][0].update(ad_id=[]),
            lambda p: p.update(ad_id=[]),
            lambda p: p["documents"][0].update(revision_id={}),
            lambda p: p["documents"][0].update(rate_variant_id=[]),
            lambda p: p["documents"][0].update(line_refs=[{}]),
            lambda p: p["documents"][0].update(line_texts=[]),
            lambda p: p.update(evidence_scope="malformed"),
            lambda p: p.update(reading_quality="malformed"),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                payload = payload_for()
                mutate(payload)
                self.assert_unknown(payload)

    def test_other_adapter_kind_is_not_intercepted_and_unknown_endpoint_abstains(self):
        payload = payload_for()
        check = {"evidence_line_refs": payload["documents"][0]["line_refs"]}
        self.assertIsNone(endpoint_check({"kind": "OTHER_CHECK"}, check, payload, ITEM))
        self.assertEqual("UNDETERMINED", endpoint_check({"kind": KIND, "endpoint": "MID"}, check, payload, ITEM)["status"])

    def test_source_names_do_not_select_arithmetic_and_geometry_is_never_mutated(self):
        payload = payload_for()
        payload["documents"][0].update(source_file="synthetic-document-a.xlsx", source_version="synthetic-version-a")
        check = {"evidence_line_refs": payload["documents"][0]["line_refs"], "reason": "synthetic model reason"}
        before_payload, before_check = copy.deepcopy(payload), copy.deepcopy(check)
        first = endpoint_check({"kind": KIND, "endpoint": "MAX"}, check, payload, ITEM)
        self.assertEqual(before_payload, payload)
        self.assertEqual(before_check, check)
        payload["documents"][0].update(source_file="synthetic-document-b.pdf", source_version="synthetic-version-b")
        second = endpoint_check({"kind": KIND, "endpoint": "MAX"}, check, payload, ITEM)
        self.assertEqual(first, second)
        self.assertEqual([12, 25, 312, 87], payload["documents"][0]["bbox"])
        self.assertEqual({"row": 3, "column": 2, "bbox": [13, 26, 310, 86]}, payload["documents"][0]["table_geometry"])


if __name__ == "__main__":
    unittest.main()
