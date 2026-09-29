"""Synthetic amount alternatives; no advertisement examples or gold inputs."""

import copy
import unittest

from rag.judgment.loan_amount_evidence import amount_check


class LoanAmountEvidenceTests(unittest.TestCase):
    def fixture(self, text="대출한도: 6천만원"):
        return {
            "parser_coverage": "READY",
            "full_ad_text": text,
            "evidence_scope": {"RULE": {"evidence_ids": ["E"], "complete_ad_scan": True}},
            "documents": [
                {
                    "evidence_id": "E",
                    "asset_id": "A",
                    "product_id": "P",
                    "source_role": "ADVERTISEMENT_CONTENT",
                    "span_status": "exact_line",
                    "line_refs": ["L"],
                    "line_texts": {"L": text},
                }
            ],
        }

    def result(self, payload, refs=None):
        return amount_check(
            {"kind": "LOAN_AMOUNT_CAP_WITHIN", "maximum_won": 70000000},
            {"evidence_line_refs": ["L"] if refs is None else refs},
            payload,
            "RULE",
        )

    def check(self, text, **changes):
        payload = self.fixture(text)
        payload.update(changes)
        return self.result(payload)

    def test_inclusive_source_parameter_and_currency_units(self):
        for text, expected in [
            ("대출한도: 최대 7천만원", "SATISFIED"),
            ("대출한도: 7,000만원 이하", "SATISFIED"),
            ("대출한도: 70,000,001원", "VIOLATED"),
            ("대출한도: 0.8억원", "VIOLATED"),
        ]:
            with self.subTest(text=text):
                result = self.check(text)
                self.assertEqual(expected, result["status"])
                self.assertEqual(["L"], result["evidence_line_refs"])
                self.assertIn('"' + text + '"', result["reason"])

    def test_percentage_is_a_failed_amount_alternative_not_an_unknown_amount(self):
        self.assertEqual("VIOLATED", self.check("대출한도: 임차보증금의 80% 이내")["status"])

    def test_current_advertisement_body_roles_keep_valid_positive_evidence(self):
        for role in (
            "PRODUCT_BODY",
            "ADVERTISEMENT_CONTENT",
            "ADVERTISEMENT_TEXT",
            "ADVERTISEMENT_REGION",
            "ADVERTISEMENT_SCAN",
        ):
            payload = self.fixture()
            payload["documents"][0]["source_role"] = role
            with self.subTest(role=role):
                self.assertEqual("SATISFIED", self.result(payload)["status"])

    def test_unknown_format_missing_complete_scope_and_other_product_abstain(self):
        for text in (
            "대출한도: 상담 후 결정",
            "대출한도: 6천만원 또는 9천만원",
            "대출한도: 최대 6천만원, 별도 가산 가능",
            "대출한도: [판독 불명]",
        ):
            self.assertEqual("UNDETERMINED", self.check(text)["status"])
        self.assertEqual(
            "UNDETERMINED",
            self.check(
                "대출한도: 6천만원",
                evidence_scope={"RULE": {"evidence_ids": ["E"], "complete_ad_scan": False}},
            )["status"],
        )
        docs = [
            {
                "evidence_id": "E",
                "asset_id": "A",
                "product_id": "P",
                "line_refs": ["L"],
                "line_texts": {"L": "대출한도: 6천만원"},
            },
            {
                "evidence_id": "F",
                "asset_id": "A",
                "product_id": "OTHER",
                "line_refs": ["OTHER-L"],
                "line_texts": {"OTHER-L": "대출한도: 6천만원"},
            },
        ]
        self.assertEqual(
            "UNDETERMINED",
            self.check(
                "",
                documents=copy.deepcopy(docs),
                evidence_scope={"RULE": {"evidence_ids": ["E", "F"], "complete_ad_scan": True}},
            )["status"],
        )
        docs[1]["product_id"] = "P"
        docs[0]["revision_id"], docs[1]["revision_id"] = "R1", "R2"
        self.assertEqual(
            "UNDETERMINED",
            self.check(
                "",
                documents=docs,
                evidence_scope={"RULE": {"evidence_ids": ["E", "F"], "complete_ad_scan": True}},
            )["status"],
        )

    def test_parser_full_text_and_line_provenance_cannot_hide_a_second_cap(self):
        for edit in (
            "partial",
            "missing_full",
            "full_other_cap",
            "full_conflicting_value",
            "unlisted_line",
            "missing_line_text",
            "unreadable_full",
            "unreadable_line",
        ):
            payload = self.fixture()
            doc = payload["documents"][0]
            if edit == "partial":
                payload["parser_coverage"] = "PARTIAL"
            if edit == "missing_full":
                del payload["full_ad_text"]
            if edit == "full_other_cap":
                payload["full_ad_text"] += "\n대출한도: 9천만원"
            if edit == "full_conflicting_value":
                payload["full_ad_text"] = "대출한도: 9천만원"
            if edit == "unlisted_line":
                doc["line_texts"]["HIDDEN"] = "대출한도: 9천만원"
            if edit == "missing_line_text":
                doc["line_refs"].append("HIDDEN")
            if edit == "unreadable_full":
                payload["full_ad_text"] += "\ufffd"
            if edit == "unreadable_line":
                doc["text_selection"] = {"needs_review": True}
            with self.subTest(edit=edit):
                result = self.result(payload)
                self.assertEqual("UNDETERMINED", result["status"])
                self.assertEqual([], result["evidence_line_refs"])

    def test_explicit_frozen_ad_product_revision_and_variant_conflicts_abstain(self):
        for edit in (
            "scope_product",
            "scope_asset",
            "ad_id",
            "revision",
            "advertisement_revision",
            "amount_variant",
            "product_variant",
            "loan_variant",
            "non_advertisement",
        ):
            payload = self.fixture()
            doc = payload["documents"][0]
            scope = payload["evidence_scope"]["RULE"]
            if edit == "scope_product":
                scope["product_id"] = "OTHER"
            if edit == "scope_asset":
                scope["asset_id"] = "OTHER"
            if edit == "ad_id":
                payload["ad_id"], doc["ad_id"] = "ONE", "OTHER"
            if edit == "revision":
                payload["revision_id"], doc["revision_id"] = "ONE", "OTHER"
            if edit == "advertisement_revision":
                scope["advertisement_revision_id"], doc["revision_id"] = "ONE", "OTHER"
            if edit in ("amount_variant", "product_variant", "loan_variant"):
                key = edit + "_id"
                scope[key], doc[key] = "ONE", "OTHER"
            if edit == "non_advertisement":
                doc["source_role"] = "RULE_SOURCE"
            with self.subTest(edit=edit):
                self.assertEqual("UNDETERMINED", self.result(payload)["status"])

    def test_other_product_or_example_prefix_cannot_become_a_cap_role(self):
        for text in (
            "다른상품 대출한도: 6천만원",
            "예시 대출한도: 6천만원",
            "조건에 따라 대출한도: 6천만원",
            "담보 종류별 대출한도: 6천만원",
        ):
            with self.subTest(text=text):
                self.assertEqual("UNDETERMINED", self.check(text)["status"])

    def test_uncited_cap_condition_or_additional_amount_stays_unknown(self):
        for note in (
            "한도는 담보 조건에 따라 변경됩니다.",
            "별도 한도 증액이 가능합니다.",
            "추가 담보 제공 시 최대 9천만원까지 가능합니다.",
        ):
            payload = self.fixture()
            payload["full_ad_text"] += "\n" + note
            with self.subTest(note=note):
                self.assertEqual("UNDETERMINED", self.result(payload)["status"])

    def test_decimal_comparison_does_not_round_an_above_boundary_cap_down(self):
        self.assertEqual(
            "VIOLATED", self.check("대출한도: 70000000.0000000000000000000000000001원")["status"]
        )
        self.assertEqual(
            "VIOLATED", self.check("대출한도: 0.700000000000000000000000000000000001억원")["status"]
        )

    def test_grounding_reason_uses_plain_currency_numbers_without_exponents(self):
        for text in ("대출한도: 5,000만원", "대출한도: 0.5억원"):
            with self.subTest(text=text):
                result = self.check(text)
                self.assertEqual("SATISFIED", result["status"])
                self.assertIn("50000000원 <= 70000000원", result["reason"])
                self.assertNotRegex(result["reason"], r"[eE][+-][0-9]")

    def test_malformed_number_currency_and_forged_citations_stay_unknown(self):
        for text in (
            "대출한도: 6,,000만원",
            "대출한도: 6,00만원",
            "대출한도: 6천달러",
            "대출한도: 6천만원 또는 9천만원",
        ):
            with self.subTest(text=text):
                self.assertEqual("UNDETERMINED", self.check(text)["status"])
        for refs in ([], ["FORGED"], ["L", "FORGED"]):
            with self.subTest(refs=refs):
                self.assertEqual("UNDETERMINED", self.result(self.fixture(), refs)["status"])

    def test_uncertain_region_cannot_quote_unaligned_lines(self):
        payload = self.fixture()
        payload["documents"][0]["span_status"] = "region_level_selected_text"
        self.assertEqual("UNDETERMINED", self.result(payload)["status"])

    def test_independently_aligned_line_can_replace_an_uncertain_region_view(self):
        payload = self.fixture()
        fallback = copy.deepcopy(payload["documents"][0])
        fallback["evidence_id"] = "REGION"
        fallback["span_status"] = "region_level_selected_text"
        fallback["text_selection"] = {"needs_review": True}
        payload["documents"].append(fallback)
        payload["evidence_scope"]["RULE"]["evidence_ids"].append("REGION")
        result = self.result(payload)
        self.assertEqual("SATISFIED", result["status"])
        self.assertEqual(["E"], result["evidence_ids"])
        self.assertEqual(["L"], result["evidence_line_refs"])
