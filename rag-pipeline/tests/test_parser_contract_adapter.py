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
        "pages": [{
            "page_no": 1, "canvas_w": 1000, "canvas_h": 1400, "dpi": 200,
            "parse_route": "ocr", "parse_status": "ok",
            "regions": [{
                "region_id": "R-1", "bbox": [10, 20, 210, 80], "label": "text",
                "layout_score": 0.95,
                "lines": [{
                    "line_ref": "p1/R-1/L000", "text": "표시 문구", "bbox": [10, 20, 210, 50],
                    "confidence": 0.99, "source": "ocr", "style": None,
                }],
                "text_evidence": {"parser_primary_text": "표시 문구"},
            }],
            "unassigned_lines": [],
            "recovery_candidates": [],
        }],
    }
    p3 = {
        "contract": {"version": "nh-ad-region-review-input-v1"},
        "document": {"doc_id": "DOC-1", "source_file": "advertisement.pdf", "file_type": "pdf"},
        "pages": [{
            "page_no": 1,
            "regions": [{
                "region_id": "R-1", "selected_text": "표시 문구", "selected_source": "ocr_parser",
                "line_refs": ["p1/R-1/L000"],
                "labels": [{
                    "label_id": "T-1", "label": "필수 표기",
                    "spans": [{"line_refs": ["p1/R-1/L000"], "sources": ["parser"]}],
                }],
            }],
            "unassigned_text": [],
        }],
        "unverified_recovery_candidates": [], "diagnostics": {}, "summary": {},
    }
    return p1, p3


class ParserContractAdapterTests(unittest.TestCase):
    def test_rejects_duplicate_pages_regions_and_phantom_p3_lines(self):
        for mutation in ("p1_page", "p3_page", "p1_region", "p3_region", "ghost_region", "ghost_line"):
            with self.subTest(mutation=mutation):
                p1, p3 = external_pair()
                if mutation in ("p1_page", "p3_page"):
                    target = p1 if mutation == "p1_page" else p3
                    target["pages"].append(copy.deepcopy(target["pages"][0]))
                elif mutation in ("p1_region", "p3_region"):
                    target = p1 if mutation == "p1_region" else p3
                    target["pages"][0]["regions"].append(copy.deepcopy(target["pages"][0]["regions"][0]))
                elif mutation == "ghost_region":
                    p3["pages"][0]["regions"].append({"region_id": "ghost", "line_refs": []})
                else:
                    p3["pages"][0]["unassigned_text"].append({"line_ref": "ghost", "selected_text": "unowned"})
                with self.assertRaises(ValueError):
                    adapt_p1_p3(p1, p3)

    def test_selection_and_span_precision_reach_model_without_raising_parser_trust(self):
        from run_operational_e2e import evidence_documents
        from run_gemma_exhaustive_dgx import _compact_model_request

        for needs_review in (True, False):
            with self.subTest(needs_review=needs_review):
                p1, p3 = external_pair()
                selection = {"needs_review": needs_review, "selection_status": "selected",
                             "confidence": 0.4, "reason": "source comparison"}
                p3["pages"][0]["regions"][0].update(selection)
                with tempfile.TemporaryDirectory() as directory:
                    a, b = Path(directory) / "p1.json", Path(directory) / "p3.json"
                    a.write_text(json.dumps(p1), encoding="utf-8")
                    b.write_text(json.dumps(p3), encoding="utf-8")
                    integrated = combine(a, b)
                self.assertEqual(integrated["document"]["routing_metadata"]["product_group"]["status"], "inferred")
                self.assertEqual(integrated["document"]["routing_metadata"]["template_id"]["status"], "inferred")
                coarse, fine = search_docs(integrated)
                schema = json.loads((Path(__file__).resolve().parents[1] / "schemas/ad-evidence-search-v1.schema.json").read_text(encoding="utf-8"))
                for doc in [*coarse, *fine]:
                    self.assertFalse(set(doc) - set(schema["properties"]))
                    self.assertEqual(doc["text_selection"], selection)
                docs = evidence_documents(fine)
                payload = {"documents": docs, "rules": [{"item_id": "generic"}]}
                messages, _ = _compact_model_request({"requested_item_ids": ["generic"],
                    "messages": [{"role": "system", "content": "test"},
                                 {"role": "user", "content": json.dumps(payload)}]})
                wire_payload = json.loads(messages[1]["content"])
                wire = wire_payload["documents"][0]
                self.assertEqual(wire_payload["reading_contexts"][wire["text_selection_ref"]], selection)
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
        messages, aliases = _compact_model_request({"requested_item_ids": ["generic"],
            "messages": [{"role": "system", "content": "test"}, {"role": "user", "content":
                         json.dumps({"documents": docs, "rules": [{"item_id": "generic"}]})}]})
        wire = json.loads(messages[1]["content"])["documents"][0]
        self.assertEqual(wire["span_status"], "region_level_selected_text")
        self.assertEqual(wire["text"], "교정된 새로운 문구")
        self.assertEqual(list(wire["lines"].values()), ["표시 문구"])
        self.assertEqual(aliases["ref_to_line"][next(iter(wire["lines"]))], "p1/R-1/L000")

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
        p1["pages"][0]["unassigned_lines"] = [{
            "line_ref": "p1/unassigned/L1", "text": "Additional canonical disclosure",
            "bbox": [10, 90, 250, 120], "source": "ocr",
        }]
        p3["pages"][0]["unassigned_text"] = [{
            "line_ref": "p1/unassigned/L1", "selected_text": "Additional canonical disclosure",
            "selected_source": "ocr_parser",
        }]
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
            self.assertEqual(row["line_texts"]["p1/unassigned/L1"], "Additional canonical disclosure")
            self.assertEqual(row["line_bboxes"]["p1/unassigned/L1"], [10, 90, 250, 120])
            self.assertEqual(row["labels"], [])
        self.assertEqual(before, json.dumps(integrated, sort_keys=True))

    def test_adapter_allows_layout_only_p1_region_omitted_from_p3(self):
        p1, p3 = external_pair()
        p1["pages"][0]["regions"].append({
            "region_id": "R-IMAGE",
            "bbox": [300, 300, 600, 600],
            "label": "illustration",
            "is_illustrative": True,
            "lines": [],
        })

        adapted_p1, adapted_p3 = adapt_p1_p3(p1, p3)

        self.assertEqual(len(adapted_p1["pages"][0]["regions"]), 2)
        self.assertEqual(len(adapted_p3["pages"][0]["regions"]), 1)

    def test_adapter_rejects_p3_text_assigned_to_layout_only_region(self):
        p1, p3 = external_pair()
        p1["pages"][0]["regions"].append({
            "region_id": "R-IMAGE", "bbox": [300, 300, 600, 600], "lines": [],
        })
        p3["pages"][0]["regions"].append({
            "region_id": "R-IMAGE", "selected_text": "invented", "line_refs": [], "labels": [],
        })

        with self.assertRaisesRegex(ValueError, "assigns text to empty P1 region"):
            adapt_p1_p3(p1, p3)
