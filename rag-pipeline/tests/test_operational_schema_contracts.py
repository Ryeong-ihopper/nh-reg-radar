from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rag.operational.contracts import (  # noqa: E402
    ContractError,
    validate_integrated_input,
    validate_operational_result,
    validate_search_collections,
)


def integrated_input():
    return {
        "contract": {
            "version": "nh-ad-review-integrated-input-v1",
            "sources": {
                "p1_contract": "nh-ad-review-evidence-v6",
                "p3_contract": "nh-ad-review-region-input-v1",
                "p1_sha256": "a" * 64,
                "p3_sha256": "b" * 64,
            },
            "review_unit": "original parser region",
            "final_text_policy": "P3 selected text",
        },
        "document": {
            "ad_id": "AD-1",
            "source_file": "sample.pdf",
            "file_type": "pdf",
            "dataset_group": None,
            "input_relative_path": "sample.pdf",
            "routing_metadata": {},
        },
        "pages": [{
            "page_no": 1,
            "canvas_w": 100,
            "canvas_h": 200,
            "dpi": 200,
            "parse_route": "ocr",
            "parse_status": "ok",
            "regions": [{
                "evidence_id": "AD-1#p1:r1",
                "region_id": "r1",
                "card_no": None,
                "bbox": [0, 0, 100, 20],
                "layout": None,
                "final_text": "광고 문구",
                "text_source": "parser_primary_text",
                "line_refs": ["p1/r1/L00"],
                "lines": [{
                    "line_ref": "p1/r1/L00",
                    "text": "광고 문구",
                    "bbox": [0, 0, 100, 20],
                    "text_source": "ocr",
                    "confidence": 0.99,
                    "style": None,
                    "labels": [],
                }],
                "labels": [],
                "assignment_status": "unassigned",
                "visibility": None,
                "table": None,
            }],
            "unassigned_lines": [],
        }],
        "unverified_recovery_candidates": [],
        "diagnostics": {},
        "quality": {
            "line_count": 1,
            "line_partition_exact": True,
            "region_count": 1,
            "empty_region_count": 0,
        },
    }


def judgment():
    return {
        "item_id": "C-001",
        "applicability": "APPLICABLE",
        "verdict": "COMPLIANT",
        "evidence_ids": ["AD-1#p1:r1"],
        "evidence_line_refs": ["p1/r1/L00"],
        "requirement_checks": [{}],
        "reason": "근거 확인",
        "confidence": "HIGH",
        "needs_researcher_review": False,
    }


class IntegratedInputContractTests(unittest.TestCase):
    def test_valid_integrated_input(self):
        self.assertEqual(validate_integrated_input(integrated_input())["document"]["ad_id"], "AD-1")

    def test_line_partition_mismatch_is_rejected(self):
        value = integrated_input()
        value["pages"][0]["regions"][0]["line_refs"] = ["wrong"]
        with self.assertRaises(ContractError):
            validate_integrated_input(value)

    def test_search_parent_must_exist(self):
        base = {
            "schema_version": "ad-evidence-search-v1",
            "ad_id": "AD-1",
            "doc_id": "AD-1#p1:r1",
            "view_type": "canonical_region",
            "text_canonical": "광고 문구",
            "text_search": "광고 문구",
            "line_refs": ["p1/r1/L00"],
            "labels": [],
            "routing_metadata": {},
        }
        fine = {**base, "doc_id": "fine-1", "parent_doc_id": "missing", "view_type": "fine_text"}
        with self.assertRaises(ContractError):
            validate_search_collections([integrated_input()], [base], [fine])


class OperationalResultContractTests(unittest.TestCase):
    def test_valid_result(self):
        value = {
            "schema_version": "operational-e2e-result-v1",
            "counts": {"ads": 1, "requested_pairs": 1, "predicted_pairs": 1, "output_failures": 0},
            "ads": [{
                "ad_id": "AD-1",
                "candidates": [{"item_id": "C-001", "status": "predicted", "judgment": judgment()}],
            }],
        }
        self.assertEqual(validate_operational_result(value)["counts"]["predicted_pairs"], 1)

    def test_count_mismatch_is_rejected(self):
        value = {
            "schema_version": "operational-e2e-result-v1",
            "counts": {"ads": 1, "requested_pairs": 2, "predicted_pairs": 1, "output_failures": 0},
            "ads": [{
                "ad_id": "AD-1",
                "candidates": [{"item_id": "C-001", "status": "predicted", "judgment": judgment()}],
            }],
        }
        with self.assertRaises(ContractError):
            validate_operational_result(value)


if __name__ == "__main__":
    unittest.main()
