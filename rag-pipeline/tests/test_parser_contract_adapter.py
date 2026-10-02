# -*- coding: utf-8 -*-
import json
import copy
import tempfile
import unittest
from pathlib import Path

from rag.parsing.parser_contract_adapter import adapt_p1_p3
from rag.parsing.prepare_inputs import combine, search_docs


def external_pair():
    p1 = {
        "contract": {"version": "nh-ad-parse-evidence-v1"},
        "doc_id": "DOC-1",
        "source_file": "advertisement.pdf",
        "file_type": "pdf",
        "classification": {"product_group": "예금성", "source": "vlm", "confidence": 0.9},
        "template": {"template_id": "deposit-demand", "status": "확정"},
        "pages": [
            {
                "page_no": 1,
                "canvas_w": 1000,
                "canvas_h": 1400,
                "dpi": 200,
                "parse_route": "ocr",
                "parse_status": "ok",
                "regions": [
                    {
                        "region_id": "R-1",
                        "bbox": [10, 20, 210, 80],
                        "label": "text",
                        "layout_score": 0.95,
                        "lines": [
                            {
                                "line_ref": "p1/R-1/L000",
                                "text": "표시 문구",
                                "bbox": [10, 20, 210, 50],
                                "confidence": 0.99,
                                "source": "ocr",
                                "style": None,
                            }
                        ],
                        "text_evidence": {"parser_primary_text": "표시 문구"},
                    }
                ],
                "unassigned_lines": [],
                "recovery_candidates": [],
            }
        ],
    }
    p3 = {
        "contract": {"version": "nh-ad-region-review-input-v1"},
        "document": {"doc_id": "DOC-1", "source_file": "advertisement.pdf", "file_type": "pdf"},
        "pages": [
            {
                "page_no": 1,
                "regions": [
                    {
                        "region_id": "R-1",
                        "selected_text": "표시 문구",
                        "selected_source": "ocr_parser",
                        "line_refs": ["p1/R-1/L000"],
                        "labels": [
                            {
                                "label_id": "T-1",
                                "label": "필수 표기",
                                "spans": [{"line_refs": ["p1/R-1/L000"], "sources": ["parser"]}],
                            }
                        ],
                    }
                ],
                "unassigned_text": [],
            }
        ],
        "unverified_recovery_candidates": [],
        "diagnostics": {},
        "summary": {},
    }
    return p1, p3


def parser_fin_pair():
    p1 = {
        "contract": {"version": "nh-ad-parse-evidence-v3"},
        "doc_id": "DOC-FIN",
        "source_file": "fin.png",
        "file_type": "png",
        "product_group": "예금성",
        "category_source": "vlm",
        "classification": {"product_group": "예금성"},
        "template": {"template_id": "deposit-demand"},
        "pages": [
            {
                "page_no": 1,
                "canvas": [1200, 1800],
                "parse_route": "ocr",
                "parse_status": "ok",
                "regions": [
                    {
                        "region_id": "p1_r001",
                        "bbox": [20, 40, 600, 120],
                        "label": "text",
                        "layout_score": 0.98,
                        "role": "본문",
                        "lines": [
                            {
                                "line_ref": "p1/r1/L1",
                                "text": "원금과 이자 보호",
                                "bbox": [25, 45, 580, 90],
                                "source": "ocr",
                                "confidence": 0.99,
                            }
                        ],
                    }
                ],
                "unassigned_lines": [
                    {
                        "line_ref": "p1/u/L1",
                        "text": "하단 고지",
                        "bbox": [20, 1700, 300, 1750],
                        "source": "ocr",
                    }
                ],
                "recovery_candidates": [
                    {
                        "candidate_id": "p1_x001",
                        "bbox": [20, 1700, 300, 1750],
                        "text": "하단 고지",
                    }
                ],
            }
        ],
    }
    p3 = {
        "contract": {"version": "nh-ad-region-review-input-v6"},
        "document": {"doc_id": "DOC-FIN", "source_file": "fin.png", "file_type": "png"},
        "review_units": [{"product_id": "product_1", "region_ids": ["p1_r001"]}],
        "pages": [
            {
                "page_no": 1,
                "canvas": [1200, 1800],
                "regions": [
                    {
                        "region_id": "p1_r001",
                        "product_id": "product_1",
                        "bbox": [20, 40, 600, 120],
                        "selected_text": "원금과 이자 보호",
                        "labels": ["예금자보호"],
                        "kind": "text",
                        "needs_review": False,
                        "text_source": "ocr",
                    }
                ],
            }
        ],
    }
    return p1, p3


def parser_fin_current_pair():
    p1, p3 = parser_fin_pair()
    p1["contract"]["version"] = "nh-ad-parse-evidence-v4"
    p3["contract"].update(
        version="nh-ad-region-review-input-v9", source_evidence_version="nh-ad-parse-evidence-v4"
    )
    region = p1["pages"][0]["regions"][0]
    region.update(
        product_id="product_1",
        semantic_labels=["예금자보호"],
        text_source="hwp_structure",
        review_reasons=["source_text_uncertain"],
    )
    selected = p3["pages"][0]["regions"][0]
    selected.update(needs_review=True, text_source="hwp", kind="table")
    region["kind"] = "table"
    region["table"] = {
        "source": "document_processor",
        "cells": [{"row": 0, "col": 0, "text": "원금과 이자 보호"}],
    }
    return p1, p3


class ParserContractAdapterTests(unittest.TestCase):
    def test_v6_v11_preserves_canonical_table_cells_and_rejects_mismatch(self):
        p1, p3 = parser_fin_current_pair()
        p1["contract"]["version"] = "nh-ad-parse-evidence-v6"
        p3["contract"].update(version="nh-ad-region-review-input-v11",
                              source_evidence_version="nh-ad-parse-evidence-v6")
        table = {"table_id": "table-1", "source": "hwp", "cells": [
            {"row": 0, "col": 0, "row_span": 1, "col_span": 1,
             "is_header": True, "text": "항목"},
            {"row": 1, "col": 0, "row_span": 1, "col_span": 1,
             "is_header": False, "text": "금리"},
        ], "row_texts": ["항목: 금리"]}
        p1_region = p1["pages"][0]["regions"][0]
        p3_region = p3["pages"][0]["regions"][0]
        p1_region["kind"] = p3_region["kind"] = "table"
        p1_region["table_view"] = copy.deepcopy(table)
        p3_region["table"] = copy.deepcopy(table)
        original = copy.deepcopy((p1, p3))

        with tempfile.TemporaryDirectory() as directory:
            first, third = Path(directory) / "p1.json", Path(directory) / "p3.json"
            first.write_text(json.dumps(p1), encoding="utf-8")
            third.write_text(json.dumps(p3), encoding="utf-8")
            integrated = combine(first, third)
        self.assertEqual((p1, p3), original)
        self.assertEqual(integrated["pages"][0]["regions"][0]["table"], table)

        p3_region["table"]["cells"][1]["text"] = "변조"
        with self.assertRaisesRegex(ValueError, "table view mismatch"):
            adapt_p1_p3(p1, p3)

    def test_v5_v10_preserves_each_file_route_and_digital_corrections(self):
        for file_type, source in (("hwp", "hwp"), ("pdf", "digital"), ("pdf", "ocr"), ("image", "ocr")):
            with self.subTest(file_type=file_type, source=source):
                p1, p3 = parser_fin_current_pair()
                p1["contract"]["version"] = "nh-ad-parse-evidence-v5"
                p3["contract"].update(version="nh-ad-region-review-input-v10",
                                      source_evidence_version="nh-ad-parse-evidence-v5")
                p1["file_type"] = p3["document"]["file_type"] = file_type
                region = p1["pages"][0]["regions"][0]
                region["digital_anchor"] = {"missing_lines": ["source addition"]}
                p1["pages"][0]["digital_anchor_stats"] = {"missing": 1}
                p3["pages"][0]["regions"][0]["text_source"] = source
                before = copy.deepcopy((p1, p3))
                adapted, selected = adapt_p1_p3(p1, p3)
                self.assertEqual((p1, p3), before)
                actual = adapted["pages"][0]["regions"][0]
                self.assertEqual(actual["bbox"], region["bbox"])
                self.assertEqual(actual["lines"][0]["bbox"], region["lines"][0]["bbox"])
                observation = selected["pages"][0]["regions"][0]["parser_observations"]
                self.assertEqual(observation["digital_anchor"], region["digital_anchor"])
                self.assertEqual(observation["page_digital_anchor_stats"], {"missing": 1})
                p3["pages"][0]["regions"][0]["bbox"] = [1, 2, 3, 4]
                with self.assertRaisesRegex(ValueError, "bbox mismatch"):
                    adapt_p1_p3(p1, p3)

    def test_current_layout_and_coordinate_provenance_reach_model_without_attestation(self):
        from run_operational_e2e import evidence_documents
        from run_gemma_exhaustive_dgx import _compact_model_request
        from test_operational_rag_contracts import request_row

        for layout, expected_role in (
            ("text", "ADVERTISEMENT_CONTENT"),
            ("header", "PAGE_CHROME"),
            ("footer", "PAGE_CHROME"),
        ):
            with self.subTest(layout=layout), tempfile.TemporaryDirectory() as directory:
                p1, p3 = parser_fin_current_pair()
                page = p1["pages"][0]
                page.pop("parse_route")
                page.update(
                    processing_route="hwp_html_pdf_digital",
                    structure_probe={"coordinate_surface": "rendered_pdf"},
                    origin={"render": {"engine": "chromium"}},
                )
                raw = page["regions"][0]
                raw.pop("label")
                raw.update(
                    layout_observation={"label": layout, "score": 0.97},
                    bbox_source="html_dom",
                    bbox_quality="block",
                    review_reasons=[],
                )
                raw["lines"][0]["text"] = "첫 번째 문단\n두 번째 문단"
                selected = p3["pages"][0]["regions"][0]
                selected.update(selected_text=raw["lines"][0]["text"], needs_review=False)
                before = copy.deepcopy((p1, p3))
                first, third = Path(directory) / "p1.json", Path(directory) / "p3.json"
                first.write_text(json.dumps(p1), encoding="utf-8")
                third.write_text(json.dumps(p3), encoding="utf-8")
                ad = combine(first, third)
                self.assertEqual((p1, p3), before)
                self.assertEqual(ad["pages"][0]["parse_route"], "hwp_html_pdf_digital")
                _, fine = search_docs(ad)
                doc = evidence_documents([d for d in fine if d["region_id"] == "p1_r001"])[0]
                self.assertEqual(doc["source_role"], expected_role)
                observations = doc["parser_observations"]
                self.assertEqual(observations["layout_observation"]["label"], layout)
                self.assertEqual(observations["coordinate_surface"], "rendered_pdf")
                self.assertEqual(observations["render_engine"], "chromium")
                self.assertEqual(observations["bbox_source"], "html_dom")
                self.assertEqual(observations["source_line_shape"]["multiline_records"], 1)
                self.assertEqual(
                    observations["source_line_shape"]["physical_line_verification"], "NOT_ATTESTED"
                )
                row = request_row(["C-1"])
                payload = json.loads(row["messages"][1]["content"])
                payload["documents"] = [doc]
                row["messages"][1]["content"] = json.dumps(payload)
                messages, _ = _compact_model_request(row)
                wire = json.loads(messages[1]["content"])["documents"][0]
                self.assertEqual(wire["parser_observations"], observations)

    def test_parser_fin_v4_v9_preserves_region_hints_quality_table_and_model_input(self):
        from run_operational_e2e import evidence_documents

        raw_p1, raw_p3 = parser_fin_current_pair()
        before = copy.deepcopy((raw_p1, raw_p3))
        with tempfile.TemporaryDirectory() as directory:
            first, third = Path(directory) / "p1.json", Path(directory) / "p3.json"
            first.write_text(json.dumps(raw_p1, ensure_ascii=False), encoding="utf-8")
            third.write_text(json.dumps(raw_p3, ensure_ascii=False), encoding="utf-8")
            integrated = combine(first, third)
        self.assertEqual((raw_p1, raw_p3), before)
        region = integrated["pages"][0]["regions"][0]
        self.assertEqual(region["labels"], [])
        self.assertEqual(region["parser_label_hints"], ["예금자보호"])
        self.assertEqual(region["kind"], "table")
        self.assertEqual(region["text_source"], "hwp")
        self.assertTrue(region["text_selection"]["needs_review"])
        self.assertIn("source_text_uncertain", region["text_selection"]["reason"])
        self.assertEqual(
            region["table"]["cells"], raw_p1["pages"][0]["regions"][0]["table"]["cells"]
        )
        coarse, fine = search_docs(integrated)
        self.assertEqual(fine[0]["parser_label_hints"], ["예금자보호"])
        self.assertEqual(fine[0]["text_source"], "hwp")
        # The model envelope must not silently discard the newly retained hints.
        docs = evidence_documents(fine)
        self.assertEqual(docs[0]["parser_label_hints"], ["예금자보호"])
        self.assertEqual(docs[0]["kind"], "table")

    def test_parser_fin_v4_v9_rejects_cross_contract_geometry_and_identity_changes(self):
        changes = [
            ("document", lambda a, b: b["document"].update(source_file="other.png")),
            ("canvas", lambda a, b: b["pages"][0].update(canvas=[900, 1800])),
            ("bbox", lambda a, b: b["pages"][0]["regions"][0].update(bbox=[30, 40, 600, 120])),
            ("owner", lambda a, b: b["pages"][0]["regions"][0].update(product_id="other")),
            (
                "version",
                lambda a, b: b["contract"].update(
                    source_evidence_version="nh-ad-parse-evidence-v3"
                ),
            ),
            ("kind", lambda a, b: b["pages"][0]["regions"][0].update(kind="grid_guess")),
        ]
        for name, change in changes:
            with self.subTest(name=name):
                p1, p3 = parser_fin_current_pair()
                change(p1, p3)
                with self.assertRaises(ValueError):
                    adapt_p1_p3(p1, p3)

    def test_parser_fin_v4_v9_never_promotes_selected_text_to_exact_ocr_line(self):
        p1, p3 = parser_fin_current_pair()
        p3["pages"][0]["regions"][0]["selected_text"] = "모델이 선택한 다른 표현"
        with tempfile.TemporaryDirectory() as directory:
            first, third = Path(directory) / "p1.json", Path(directory) / "p3.json"
            first.write_text(json.dumps(p1), encoding="utf-8")
            third.write_text(json.dumps(p3), encoding="utf-8")
            integrated = combine(first, third)
        _, fine = search_docs(integrated)
        self.assertEqual(fine[0]["span_status"], "region_level_selected_text")
        self.assertEqual(
            integrated["pages"][0]["regions"][0]["lines"][0]["text"], "원금과 이자 보호"
        )

    def test_parser_fin_unknown_or_mixed_revisions_fail_closed(self):
        for first, third in [
            ("nh-ad-parse-evidence-v3", "nh-ad-region-review-input-v9"),
            ("nh-ad-parse-evidence-v4", "nh-ad-region-review-input-v6"),
            ("nh-ad-parse-evidence-v5", "nh-ad-region-review-input-v11"),
            ("nh-ad-parse-evidence-v4", "nh-ad-region-review-input-v10"),
            ("nh-ad-parse-evidence-v5", "nh-ad-region-review-input-v9"),
        ]:
            with self.subTest(pair=(first, third)):
                p1, p3 = parser_fin_current_pair()
                p1["contract"]["version"], p3["contract"]["version"] = first, third
                with self.assertRaisesRegex(ValueError, "unsupported parser contract pair"):
                    adapt_p1_p3(p1, p3)

    def test_parser_fin_v3_v6_preserves_bbox_and_p1_only_lines(self):
        p1, p3 = adapt_p1_p3(*parser_fin_pair())
        self.assertEqual(p1["pages"][0]["canvas_w"], 1200)
        self.assertEqual(p1["pages"][0]["canvas_h"], 1800)
        self.assertEqual(p1["pages"][0]["regions"][0]["bbox"], [20, 40, 600, 120])
        self.assertEqual(p3["pages"][0]["regions"][0]["line_refs"], ["p1/r1/L1"])
        self.assertEqual(p3["pages"][0]["unassigned_text"][0]["line_ref"], "p1/u/L1")
        self.assertEqual(p3["pages"][0]["regions"][0]["labels"], [])
        self.assertEqual(p3["unverified_recovery_candidates"][0]["page_no"], 1)
        self.assertEqual(p3["unverified_recovery_candidates"][0]["candidate_id"], "p1_x001")

    def test_parser_fin_v3_v6_combines_without_promoting_vlm_bbox(self):
        p1, p3 = parser_fin_pair()
        p3["pages"][0]["regions"][0]["selected_text"] = "VLM 교정 문구"
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "p1.json", Path(directory) / "p3.json"
            a.write_text(json.dumps(p1, ensure_ascii=False), encoding="utf-8")
            b.write_text(json.dumps(p3, ensure_ascii=False), encoding="utf-8")
            integrated = combine(a, b)
        region = integrated["pages"][0]["regions"][0]
        self.assertEqual(region["bbox"], [20, 40, 600, 120])
        self.assertEqual(region["lines"][0]["bbox"], [25, 45, 580, 90])
        self.assertEqual(region["final_text"], "VLM 교정 문구")
        _, fine = search_docs(integrated)
        self.assertEqual(fine[0]["span_status"], "region_level_selected_text")

    def test_invalid_label_refs_are_removed_without_losing_text_or_valid_labels(self):
        valid = {"line_refs": ["p1/R-1/L000"], "sources": ["parser"]}
        for invalid in (
            {"line_refs": ["p2/other/L000"]},
            {"line_refs": []},
            {"line_refs": ["p1/R-1/L000", "p1/R-1/L000"]},
            {**valid, "line_from": -1, "line_to": 0},
            {**valid, "line_from": 0, "line_to": 1},
            {**valid, "line_from": False, "line_to": 0},
            {**valid, "line_from": 0},
        ):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as directory:
                p1, p3 = external_pair()
                p3["pages"][0]["regions"][0]["labels"].append(
                    {
                        "label_id": "invalid",
                        "label": "wrong field",
                        "spans": [invalid],
                    }
                )
                first, third = Path(directory) / "p1.json", Path(directory) / "p3.json"
                first.write_text(json.dumps(p1), encoding="utf-8")
                third.write_text(json.dumps(p3), encoding="utf-8")
                before = first.read_bytes(), third.read_bytes()
                combined = combine(first, third)
                region = combined["pages"][0]["regions"][0]
                self.assertTrue(region["text_selection"]["needs_review"])
                self.assertEqual(len(region["labels"]), 1)
                self.assertEqual(region["final_text"], "표시 문구")
                for doc in sum(search_docs(combined), []):
                    self.assertEqual([label["label_id"] for label in doc["labels"]], ["T-1"])
                    self.assertTrue(doc["text_selection"]["needs_review"])
                self.assertEqual(before, (first.read_bytes(), third.read_bytes()))

    def test_noncontiguous_label_refs_preserve_exact_selected_subset(self):
        p1, p3 = external_pair()
        original = p1["pages"][0]["regions"][0]["lines"][0]
        lines = [
            {**original, "text": text, "line_ref": f"p1/R-1/L{i:03d}"}
            for i, text in enumerate(("적용 이율", "고객 부담 비용 없음", "연 4.2%"))
        ]
        p1["pages"][0]["regions"][0]["lines"] = lines
        region = p3["pages"][0]["regions"][0]
        region["line_refs"] = [line["line_ref"] for line in lines]
        region["selected_text"] = "적용 이율\n연 4.2%"
        region["labels"][0]["spans"] = [
            {"line_refs": region["line_refs"][::2], "sources": ["parser"]}
        ]
        with tempfile.TemporaryDirectory() as directory:
            first, third = Path(directory) / "p1.json", Path(directory) / "p3.json"
            first.write_text(json.dumps(p1), encoding="utf-8")
            third.write_text(json.dumps(p3), encoding="utf-8")
            combined = combine(first, third)
        self.assertEqual(combined["pages"][0]["regions"][0]["lines"][1]["labels"], [])
        coarse, fine = search_docs(combined)
        self.assertEqual(coarse[0]["line_refs"], region["line_refs"][::2])
        self.assertTrue(all(doc["labels"] for doc in fine))

    def test_rejects_duplicate_pages_regions_and_phantom_p3_lines(self):
        for mutation in (
            "p1_page",
            "p3_page",
            "p1_region",
            "p3_region",
            "ghost_region",
            "ghost_line",
        ):
            with self.subTest(mutation=mutation):
                p1, p3 = external_pair()
                if mutation in ("p1_page", "p3_page"):
                    target = p1 if mutation == "p1_page" else p3
                    target["pages"].append(copy.deepcopy(target["pages"][0]))
                elif mutation in ("p1_region", "p3_region"):
                    target = p1 if mutation == "p1_region" else p3
                    target["pages"][0]["regions"].append(
                        copy.deepcopy(target["pages"][0]["regions"][0])
                    )
                elif mutation == "ghost_region":
                    p3["pages"][0]["regions"].append({"region_id": "ghost", "line_refs": []})
                else:
                    p3["pages"][0]["unassigned_text"].append(
                        {"line_ref": "ghost", "selected_text": "unowned"}
                    )
                with self.assertRaises(ValueError):
                    adapt_p1_p3(p1, p3)

    def test_selection_and_span_precision_reach_model_without_raising_parser_trust(self):
        from run_operational_e2e import evidence_documents
        from run_gemma_exhaustive_dgx import _compact_model_request

        for needs_review in (True, False):
            with self.subTest(needs_review=needs_review):
                p1, p3 = external_pair()
                selection = {
                    "needs_review": needs_review,
                    "selection_status": "selected",
                    "confidence": 0.4,
                    "reason": "source comparison",
                }
                p3["pages"][0]["regions"][0].update(selection)
                with tempfile.TemporaryDirectory() as directory:
                    a, b = Path(directory) / "p1.json", Path(directory) / "p3.json"
                    a.write_text(json.dumps(p1), encoding="utf-8")
                    b.write_text(json.dumps(p3), encoding="utf-8")
                    integrated = combine(a, b)
                self.assertEqual(
                    integrated["document"]["routing_metadata"]["product_group"]["status"],
                    "inferred",
                )
                self.assertEqual(
                    integrated["document"]["routing_metadata"]["template_id"]["status"], "inferred"
                )
                coarse, fine = search_docs(integrated)
                schema = json.loads(
                    (
                        Path(__file__).resolve().parents[1]
                        / "schemas/ad-evidence-search-v1.schema.json"
                    ).read_text(encoding="utf-8")
                )
                for doc in [*coarse, *fine]:
                    self.assertFalse(set(doc) - set(schema["properties"]))
                    self.assertEqual(doc["text_selection"], selection)
                docs = evidence_documents(fine)
                payload = {"documents": docs, "rules": [{"item_id": "generic"}]}
                messages, _ = _compact_model_request(
                    {
                        "requested_item_ids": ["generic"],
                        "messages": [
                            {"role": "system", "content": "test"},
                            {"role": "user", "content": json.dumps(payload)},
                        ],
                    }
                )
                wire_payload = json.loads(messages[1]["content"])
                if needs_review:
                    self.assertEqual(wire_payload["documents"], [])
                    wire = wire_payload["uncertain_context"][0]
                    self.assertFalse(wire["citable"])
                    self.assertEqual(wire["text_selection"], selection)
                else:
                    wire = wire_payload["documents"][0]
                    self.assertEqual(
                        wire_payload["reading_contexts"][wire["text_selection_ref"]], selection
                    )
                self.assertEqual(wire["span_status"], "parser_line_exact")

    def test_external_pair_adapts_without_creating_visibility_measurements(self):
        p1, p3 = adapt_p1_p3(*external_pair())
        self.assertEqual(p1["reading_evidence_contract"]["version"], "nh-ad-review-evidence-v6")
        self.assertEqual(p3["contract"]["version"], "nh-ad-review-region-input-v1")
        self.assertEqual(p1["pages"][0]["regions"][0]["lines"][0]["parser_text"], "표시 문구")
        self.assertNotIn("physical_width_mm", p1["pages"][0])
        self.assertNotIn("visibility", p1["pages"][0]["regions"][0])

    def test_corrected_region_text_does_not_become_line_exact(self):
        from run_operational_e2e import evidence_documents
        from run_gemma_exhaustive_dgx import _compact_model_request

        p1, p3 = external_pair()
        p3["pages"][0]["regions"][0]["selected_text"] = "교정된 새로운 문구"
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "p1.json", Path(directory) / "p3.json"
            a.write_text(json.dumps(p1), encoding="utf-8")
            b.write_text(json.dumps(p3), encoding="utf-8")
            integrated = combine(a, b)
        _, fine = search_docs(integrated)
        docs = evidence_documents(fine)
        self.assertEqual(docs[0]["span_status"], "region_level_selected_text")
        messages, aliases = _compact_model_request(
            {
                "requested_item_ids": ["generic"],
                "messages": [
                    {"role": "system", "content": "test"},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"documents": docs, "rules": [{"item_id": "generic"}]}
                        ),
                    },
                ],
            }
        )
        payload = json.loads(messages[1]["content"])
        self.assertEqual(payload["documents"], [])
        wire = payload["uncertain_context"][0]
        self.assertEqual(wire["span_status"], "region_level_selected_text")
        self.assertEqual(wire["text"], "교정된 새로운 문구")
        self.assertFalse(wire["citable"])
        self.assertEqual(docs[0]["line_texts"], {"p1/R-1/L000": "표시 문구"})
        self.assertEqual(aliases["ref_to_line"], {})

    def test_combine_accepts_external_pair_and_records_adapter_provenance(self):
        p1, p3 = external_pair()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            p1_path, p3_path = root / "p1.json", root / "p3.json"
            p1_path.write_text(json.dumps(p1, ensure_ascii=False), encoding="utf-8")
            p3_path.write_text(json.dumps(p3, ensure_ascii=False), encoding="utf-8")
            integrated = combine(p1_path, p3_path)
            # This value is persisted before RAG execution. Internal helper
            # sets must never leak into the external JSON contract.
            json.dumps(integrated, ensure_ascii=False)
        region = integrated["pages"][0]["regions"][0]
        self.assertIsInstance(region["lines"][0]["labels"], list)
        self.assertEqual(region["final_text"], "표시 문구")
        self.assertIsNone(region["visibility"])
        self.assertEqual(
            integrated["diagnostics"]["parser_contract_adapter"]["source_p1_contract"],
            "nh-ad-parse-evidence-v1",
        )

    def test_adapter_rejects_missing_p3_line_ownership(self):
        p1, p3 = external_pair()
        p3["pages"][0]["regions"][0]["line_refs"] = []
        with self.assertRaisesRegex(ValueError, "line ownership"):
            adapt_p1_p3(p1, p3)

    def test_unassigned_canonical_line_reaches_search_and_full_transcript(self):
        p1, p3 = external_pair()
        p1["pages"][0]["unassigned_lines"] = [
            {
                "line_ref": "p1/unassigned/L1",
                "text": "Additional canonical disclosure",
                "bbox": [10, 90, 250, 120],
                "source": "ocr",
            }
        ]
        p3["pages"][0]["unassigned_text"] = [
            {
                "line_ref": "p1/unassigned/L1",
                "selected_text": "Additional canonical disclosure",
                "selected_source": "ocr_parser",
            }
        ]
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "p1.json", Path(directory) / "p3.json"
            a.write_text(json.dumps(p1), encoding="utf-8")
            b.write_text(json.dumps(p3), encoding="utf-8")
            integrated = combine(a, b)
        before = json.dumps(integrated, sort_keys=True)
        coarse, fine = search_docs(integrated)
        for rows in (coarse, fine):
            row = next(row for row in rows if "p1/unassigned/L1" in row["line_refs"])
            self.assertIn("Additional canonical disclosure", row["text_canonical"])
            self.assertEqual(
                row["line_texts"]["p1/unassigned/L1"], "Additional canonical disclosure"
            )
            self.assertEqual(row["line_bboxes"]["p1/unassigned/L1"], [10, 90, 250, 120])
            self.assertEqual(row["labels"], [])
        self.assertEqual(before, json.dumps(integrated, sort_keys=True))

    def test_adapter_allows_layout_only_p1_region_omitted_from_p3(self):
        p1, p3 = external_pair()
        p1["pages"][0]["regions"].append(
            {
                "region_id": "R-IMAGE",
                "bbox": [300, 300, 600, 600],
                "label": "illustration",
                "is_illustrative": True,
                "lines": [],
            }
        )

        adapted_p1, adapted_p3 = adapt_p1_p3(p1, p3)

        self.assertEqual(len(adapted_p1["pages"][0]["regions"]), 2)
        self.assertEqual(len(adapted_p3["pages"][0]["regions"]), 1)

    def test_adapter_keeps_bbox_backed_p3_text_as_region_level_evidence(self):
        p1, p3 = external_pair()
        p1["pages"][0]["regions"].append(
            {
                "region_id": "R-IMAGE",
                "bbox": [300, 300, 600, 600],
                "lines": [],
            }
        )
        p3["pages"][0]["regions"].append(
            {
                "region_id": "R-IMAGE",
                "selected_text": "invented",
                "line_refs": [],
                "labels": [],
            }
        )

        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "p1.json", Path(directory) / "p3.json"
            a.write_text(json.dumps(p1), encoding="utf-8")
            b.write_text(json.dumps(p3), encoding="utf-8")
            integrated = combine(a, b)
            _, fine = search_docs(integrated)

        region = next(
            row for row in integrated["pages"][0]["regions"] if row["region_id"] == "R-IMAGE"
        )
        self.assertEqual(region["final_text"], "invented")
        self.assertEqual(region["bbox"], [300, 300, 600, 600])
        self.assertEqual(region["line_refs"], [])
        view = next(row for row in fine if row["region_id"] == "R-IMAGE")
        self.assertEqual(view["span_status"], "region_level_selected_text")
        self.assertEqual(view["line_refs"], [])
        self.assertEqual(view["bbox"], [300, 300, 600, 600])

    def test_adapter_rejects_p3_text_without_p1_geometry(self):
        p1, p3 = external_pair()
        p1["pages"][0]["regions"].append(
            {
                "region_id": "R-NO-GEOMETRY",
                "bbox": None,
                "lines": [],
            }
        )
        p3["pages"][0]["regions"].append(
            {
                "region_id": "R-NO-GEOMETRY",
                "selected_text": "invented",
                "line_refs": [],
                "labels": [],
            }
        )

        with self.assertRaisesRegex(ValueError, "geometry-free P1 region"):
            adapt_p1_p3(p1, p3)
