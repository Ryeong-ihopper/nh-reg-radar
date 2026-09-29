"""Synthetic source-scoped date comparisons; no advertisement/answer fixtures."""

import copy
import unittest

from rag.judgment.basis_date_evidence import KIND, date_equality_check


class BasisDateEvidenceTests(unittest.TestCase):
    def fixture(self, loan=True):
        lines = (
            {"L1": "대출금리 기준일: 2032.02.29.", "L2": "우대금리 기준일: 2032-02-29"}
            if loan
            else {
                "L1": "기본이율 기준일: 2032.02.29.",
                "L2": "예상 수취이자 산출 기준일: 2032년 2월 29일",
            }
        )
        roles = (
            ("loan_rate_basis_date", "bonus_rate_basis_date")
            if loan
            else ("deposit_rate_basis_date", "expected_interest_basis_date")
        )
        adapter = {"kind": KIND, "left_role": roles[0], "right_role": roles[1], "unit": "DATE"}
        doc = {
            "evidence_id": "E1",
            "asset_id": "ASSET",
            "product_id": "PRODUCT",
            "source_role": "ADVERTISEMENT_CONTENT",
            "span_status": "line_level_selected_text",
            "line_refs": list(lines),
            "line_texts": lines,
        }
        payload = {
            "parser_coverage": "READY",
            "full_ad_text": "\n".join(lines.values()),
            "documents": [doc],
            "evidence_scope": {"TEST": {"complete_ad_scan": True, "evidence_ids": ["E1"]}},
        }
        return adapter, {"evidence_line_refs": ["L1", "L2"]}, payload

    def result(self, fixture):
        return date_equality_check(*fixture, "TEST")

    def refresh_full_text(self, fixture):
        fixture[2]["full_ad_text"] = "\n".join(fixture[2]["documents"][0]["line_texts"].values())

    def assertUnknown(self, fixture):
        result = self.result(fixture)
        self.assertEqual("UNDETERMINED", result["status"])
        self.assertEqual("UNKNOWN", result["finding_basis"])
        self.assertEqual([], result["evidence_ids"])
        self.assertEqual([], result["evidence_line_refs"])

    def test_both_source_role_pairs_and_different_calendar_formats(self):
        for loan in (True, False):
            fixture = self.fixture(loan)
            with self.subTest(loan=loan):
                result = self.result(fixture)
                self.assertEqual("SATISFIED", result["status"])
                self.assertEqual("OBSERVED", result["finding_basis"])
                self.assertEqual(["E1"], result["evidence_ids"])
                self.assertEqual(["L1", "L2"], result["evidence_line_refs"])
                for text in fixture[2]["documents"][0]["line_texts"].values():
                    self.assertIn('"' + text + '"', result["reason"])

    def test_explicit_unequal_dates_are_an_observed_violation(self):
        fixture = self.fixture()
        fixture[2]["documents"][0]["line_texts"]["L2"] = "우대금리 기준일: 2032-02-28"
        self.refresh_full_text(fixture)
        result = self.result(fixture)
        self.assertEqual("VIOLATED", result["status"])
        self.assertEqual("OBSERVED", result["finding_basis"])
        self.assertEqual(["L1", "L2"], result["evidence_line_refs"])

    def test_heading_row_can_bind_its_only_explicit_basis_date(self):
        fixture = self.fixture()
        lines = fixture[2]["documents"][0]["line_texts"]
        lines["L1"] = (
            "대출금리 | 최저 연 2%, 최고 연 3% (2032.02.29. 기준, 기준금리 연 1%, 우대금리 연 1%)"
        )
        lines["L2"] = "우대금리 | 최대 연 1%p (2032.02.29. 기준, 조건 1 연 1%p)"
        self.refresh_full_text(fixture)
        self.assertEqual("SATISFIED", self.result(fixture)["status"])

    def test_two_roles_on_one_original_line_keep_one_real_citation(self):
        fixture = self.fixture()
        doc = fixture[2]["documents"][0]
        doc["line_refs"] = ["L1"]
        doc["line_texts"] = {"L1": "대출금리 기준일: 2032-02-29; 우대금리 기준일: 2032/02/29"}
        fixture[1]["evidence_line_refs"] = ["L1"]
        self.refresh_full_text(fixture)
        self.assertEqual(["L1"], self.result(fixture)["evidence_line_refs"])
        self.assertEqual("SATISFIED", self.result(fixture)["status"])

    def test_generic_basis_date_or_benchmark_date_cannot_supply_rate_role(self):
        for text in (
            "기준일: 2032-02-29",
            "기준금리 기준일: 2032-02-29",
            "대출금리 | 출시일 2032-02-29, 기준금리 연 1%",
            "대출금리 2032-02-29",
        ):
            fixture = self.fixture()
            fixture[2]["documents"][0]["line_texts"]["L1"] = text
            with self.subTest(text=text):
                self.assertUnknown(fixture)

    def test_invalid_partial_range_and_multiple_role_dates_are_unknown(self):
        for text in (
            "대출금리 기준일: 2031-02-29",
            "대출금리 기준일: 2032-02-?",
            "대출금리 기준일: 2032-02-01~2032-02-29",
            "대출금리 기준일: 2032-02-29 또는 2032-03-01",
            "대출금리 기준일: 2032-02-29, 2032-03-01",
            "대출금리 기준일: 2032-02-29; 대출금리 기준일: 2032-02-29",
        ):
            fixture = self.fixture()
            fixture[2]["documents"][0]["line_texts"]["L1"] = text
            with self.subTest(text=text):
                self.assertUnknown(fixture)

    def test_uncited_second_candidate_cannot_be_ignored(self):
        for date_text in ("2032-02-29", "2032-03-01"):
            fixture = self.fixture()
            doc = fixture[2]["documents"][0]
            doc["line_refs"].append("L3")
            doc["line_texts"]["L3"] = "우대금리 기준일: " + date_text
            with self.subTest(date=date_text):
                self.assertUnknown(fixture)

    def test_missing_or_forged_operand_citation_is_unknown(self):
        for refs in ([], ["L1"], ["L1", "FAKE"], [["L1"], "L2"]):
            fixture = self.fixture()
            fixture[1]["evidence_line_refs"] = refs
            with self.subTest(refs=refs):
                self.assertUnknown(fixture)

    def test_source_text_and_model_supplied_dates_are_not_operands(self):
        fixture = self.fixture()
        fixture[1].update(
            status="SATISFIED",
            basis_date="2032-02-29",
            left_date="2032-02-29",
            right_date="2032-02-29",
        )
        fixture[2]["basis_date_observations"] = [{"basis_date": "2032-02-29"}]
        fixture[2]["documents"][0]["line_texts"]["L2"] = "우대조건 설명만 있음"
        self.assertUnknown(fixture)
        for role in ("RULE_SOURCE", "EXTERNAL_INPUT", "LANDING_CONTENT"):
            fixture = self.fixture()
            fixture[2]["documents"][0]["source_role"] = role
            with self.subTest(role=role):
                self.assertUnknown(fixture)

    def test_asset_product_revision_and_document_scope_must_match(self):
        for edit in (
            "different_asset",
            "different_product",
            "missing_asset",
            "missing_product",
            "different_revision",
            "partial_revision",
            "missing_document",
            "wrong_item_scope",
        ):
            fixture = self.fixture()
            payload = fixture[2]
            doc = payload["documents"][0]
            second = copy.deepcopy(doc)
            second["evidence_id"] = "E2"
            payload["documents"].append(second)
            payload["evidence_scope"]["TEST"]["evidence_ids"].append("E2")
            if edit == "different_asset":
                second["asset_id"] = "OTHER"
            if edit == "different_product":
                second["product_id"] = "OTHER"
            if edit == "missing_asset":
                del second["asset_id"]
            if edit == "missing_product":
                del second["product_id"]
            if edit in ("different_revision", "partial_revision"):
                doc["revision_id"] = "R1"
                if edit == "different_revision":
                    second["revision_id"] = "R2"
            if edit == "missing_document":
                payload["documents"].pop()
            if edit == "wrong_item_scope":
                payload["evidence_scope"] = {
                    "OTHER": {"complete_ad_scan": True, "evidence_ids": ["E1", "E2"]}
                }
            with self.subTest(edit=edit):
                self.assertUnknown(fixture)

    def test_incomplete_or_unreadable_scope_is_unknown(self):
        for edit in (
            "scan",
            "parser",
            "global",
            "selection",
            "malformed_selection",
            "replacement",
            "nul",
        ):
            fixture = self.fixture()
            payload = fixture[2]
            doc = payload["documents"][0]
            if edit == "scan":
                payload["evidence_scope"]["TEST"]["complete_ad_scan"] = False
            if edit == "parser":
                payload["parser_coverage"] = "PARTIAL"
            if edit == "global":
                payload["reading_quality"] = {"global_scan_incomplete": True}
            if edit == "selection":
                doc["text_selection"] = {"needs_review": True}
            if edit == "malformed_selection":
                doc["text_selection"] = "unknown"
            if edit == "replacement":
                doc["line_texts"]["L1"] += "\ufffd"
            if edit == "nul":
                doc["line_texts"]["L1"] += "\x00"
            with self.subTest(edit=edit):
                self.assertUnknown(fixture)

    def test_missing_actual_line_or_conflicting_duplicate_view_is_unknown(self):
        for edit in ("missing_ref", "missing_text", "conflict"):
            fixture = self.fixture()
            doc = fixture[2]["documents"][0]
            if edit == "missing_ref":
                doc["line_refs"].remove("L2")
            if edit == "missing_text":
                del doc["line_texts"]["L2"]
            if edit == "conflict":
                second = copy.deepcopy(doc)
                second["evidence_id"] = "E2"
                second["line_texts"]["L2"] = "우대금리 기준일: 2032-03-01"
                fixture[2]["documents"].append(second)
                fixture[2]["evidence_scope"]["TEST"]["evidence_ids"].append("E2")
            with self.subTest(edit=edit):
                self.assertUnknown(fixture)

    def test_identical_views_do_not_duplicate_date_operands(self):
        fixture = self.fixture()
        second = copy.deepcopy(fixture[2]["documents"][0])
        second["evidence_id"] = "E2"
        fixture[2]["documents"].append(second)
        fixture[2]["evidence_scope"]["TEST"]["evidence_ids"].append("E2")
        self.assertEqual("SATISFIED", self.result(fixture)["status"])
        self.assertEqual(["E1"], self.result(fixture)["evidence_ids"])

    def test_unallowed_documents_never_supply_an_operand(self):
        fixture = self.fixture()
        extra = copy.deepcopy(fixture[2]["documents"][0])
        extra["evidence_id"] = "OUTSIDE"
        extra["line_texts"]["L2"] = "우대금리 기준일: 2032-03-01"
        fixture[2]["documents"].append(extra)
        self.assertEqual("SATISFIED", self.result(fixture)["status"])
        fixture[2]["documents"][0]["line_texts"]["L2"] = "우대조건 안내"
        self.assertUnknown(fixture)

    def table_fixture(self):
        fixture = self.fixture()
        doc = fixture[2]["documents"][0]
        lines = {
            "H1": "대출금리 기준일",
            "V1": "2032.02.29.",
            "H2": "우대금리 기준일",
            "V2": "2032-02-29",
        }
        doc["line_refs"], doc["line_texts"] = list(lines), lines
        self.refresh_full_text(fixture)
        doc["table"] = {
            "cells": [
                {
                    "cell_id": ref,
                    "row": row,
                    "col": col,
                    "status": "observed",
                    "line_refs": [ref],
                    "header_cell_ids": headers,
                }
                for ref, row, col, headers in [
                    ("H1", 0, 0, []),
                    ("V1", 1, 0, ["H1"]),
                    ("H2", 0, 1, []),
                    ("V2", 1, 1, ["H2"]),
                ]
            ]
        }
        fixture[1]["evidence_line_refs"] = ["V1", "V2"]
        return fixture

    def test_observed_table_role_links_expand_only_real_header_citations(self):
        fixture = self.table_fixture()
        result = self.result(fixture)
        self.assertEqual("SATISFIED", result["status"])
        self.assertEqual({"H1", "H2", "V1", "V2"}, set(result["evidence_line_refs"]))
        self.assertEqual(["E1"], result["evidence_ids"])
        fixture[2]["documents"][0]["line_texts"]["V2"] = "2032-03-01"
        self.refresh_full_text(fixture)
        self.assertEqual("VIOLATED", self.result(fixture)["status"])

    def test_inferred_merged_missing_or_ambiguous_table_binding_is_unknown(self):
        for edit in (
            "inferred",
            "merged",
            "missing_header",
            "missing_ref",
            "missing_position",
            "duplicate_position",
            "both_roles",
            "footnote",
            "multiple_dates",
        ):
            fixture = self.table_fixture()
            doc = fixture[2]["documents"][0]
            cell = doc["table"]["cells"][-1]
            if edit == "inferred":
                cell["status"] = "inferred"
            if edit == "merged":
                cell["row_span"] = 2
            if edit == "missing_header":
                cell["header_cell_ids"] = ["MISSING"]
            if edit == "missing_ref":
                doc["table"]["cells"][-2]["line_refs"] = ["MISSING"]
            if edit == "missing_position":
                del cell["row"]
            if edit == "duplicate_position":
                cell["row"] = 0
            if edit == "both_roles":
                cell["header_cell_ids"] = ["H1", "H2"]
            if edit == "footnote":
                cell["footnote_line_ids"] = ["UNKNOWN"]
            if edit == "multiple_dates":
                doc["line_texts"]["V2"] += " 또는 2032-03-01"
            with self.subTest(edit=edit):
                self.assertUnknown(fixture)

    def test_conflicting_table_views_cannot_rebind_the_same_date_line(self):
        fixture = self.table_fixture()
        second = copy.deepcopy(fixture[2]["documents"][0])
        second["evidence_id"] = "E2"
        second["table"]["cells"][1]["header_cell_ids"] = ["H2"]
        fixture[2]["documents"].append(second)
        fixture[2]["evidence_scope"]["TEST"]["evidence_ids"].append("E2")
        self.assertUnknown(fixture)

    def test_explicit_adapter_unit_role_pair_and_kind_are_required(self):
        for key, value in (
            ("unit", "DAYS"),
            ("left_role", "event_start_date"),
            ("right_role", "expected_interest_basis_date"),
            ("left_role", ["loan_rate_basis_date"]),
        ):
            fixture = self.fixture()
            fixture[0][key] = value
            with self.subTest(key=key, value=value):
                self.assertUnknown(fixture)
        fixture = self.fixture()
        fixture[0]["kind"] = "OTHER"
        self.assertIsNone(self.result(fixture))

    def test_full_advertisement_cannot_hide_or_change_a_role_date(self):
        for edit in ("missing", "hidden_role", "changed_date", "unreadable"):
            fixture = self.fixture()
            payload = fixture[2]
            if edit == "missing":
                del payload["full_ad_text"]
            if edit == "hidden_role":
                payload["full_ad_text"] += "\n우대금리 기준일: 2032-03-01"
            if edit == "changed_date":
                payload["full_ad_text"] = payload["full_ad_text"].replace(
                    "우대금리 기준일: 2032-02-29", "우대금리 기준일: 2032-03-01"
                )
            if edit == "unreadable":
                payload["full_ad_text"] += "\ufffd"
            with self.subTest(edit=edit):
                self.assertUnknown(fixture)

    def test_request_and_item_scope_metadata_must_match_the_original_product(self):
        for edit in ("product", "asset", "revision", "ad_id"):
            fixture = self.fixture()
            payload = fixture[2]
            doc = payload["documents"][0]
            if edit == "product":
                payload["evidence_scope"]["TEST"]["product_id"] = "OTHER"
            if edit == "asset":
                payload["evidence_scope"]["TEST"]["asset_id"] = "OTHER"
            if edit == "revision":
                payload["revision_id"], doc["revision_id"] = "ONE", "OTHER"
            if edit == "ad_id":
                payload["ad_id"], doc["ad_id"] = "ONE", "OTHER"
            with self.subTest(edit=edit):
                self.assertUnknown(fixture)

    def test_product_body_and_other_advertisement_roles_remain_positive(self):
        for role in (
            "PRODUCT_BODY",
            "ADVERTISEMENT_CONTENT",
            "ADVERTISEMENT_TEXT",
            "ADVERTISEMENT_REGION",
            "ADVERTISEMENT_SCAN",
        ):
            fixture = self.fixture()
            fixture[2]["documents"][0]["source_role"] = role
            with self.subTest(role=role):
                self.assertEqual("SATISFIED", self.result(fixture)["status"])

    def test_region_only_date_does_not_invent_aligned_citations(self):
        fixture = self.fixture()
        fixture[2]["documents"][0]["span_status"] = "region_level_selected_text"
        self.assertUnknown(fixture)
        clean = copy.deepcopy(fixture[2]["documents"][0])
        clean["evidence_id"], clean["span_status"] = "CLEAN", "line_level_selected_text"
        fixture[2]["documents"][0]["text_selection"] = {"needs_review": True}
        fixture[2]["documents"].append(clean)
        fixture[2]["evidence_scope"]["TEST"]["evidence_ids"].append("CLEAN")
        result = self.result(fixture)
        self.assertEqual("SATISFIED", result["status"])
        self.assertEqual(["CLEAN"], result["evidence_ids"])


if __name__ == "__main__":
    unittest.main()
