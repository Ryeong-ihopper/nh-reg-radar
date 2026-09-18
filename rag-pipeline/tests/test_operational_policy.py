from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rag.judgment.policy import (  # noqa: E402
    confirmed_template,
    deterministic_facts,
    enforce_review_policy,
    require_confirmed_product_group,
    routing_field,
)


class OperationalPolicyTests(unittest.TestCase):
    def test_scalar_routing_is_never_silently_confirmed(self) -> None:
        self.assertEqual(routing_field("예금성")["status"], "inferred")
        with self.assertRaises(ValueError):
            require_confirmed_product_group({"product_group": "예금성"})

    def test_provided_routing_can_hard_gate(self) -> None:
        routing = {
            "product_group": {"value": "대출성", "status": "provided"},
            "template_id": {
                "value": "대출성상품-상품명 노출",
                "status": "confirmed",
            },
        }
        self.assertEqual(require_confirmed_product_group(routing), "대출성")
        self.assertEqual(confirmed_template(routing), "대출성상품-상품명 노출")

    def test_provided_investment_routing_can_hard_gate(self) -> None:
        routing = {
            "product_group": {"value": "투자성", "status": "provided"},
            "template_id": {
                "value": "투자성상품-개인종합자산관리계좌(ISA) 일반",
                "status": "confirmed",
            },
        }
        self.assertEqual(require_confirmed_product_group(routing), "투자성")

    def test_format_equivalents_are_observations(self) -> None:
        facts = deterministic_facts([
            {"text_canonical": "■ 유의사항\n준법감시인 심의필 0000-0000 (2026.09.01)"}
        ])
        self.assertTrue(facts["review_number_present"])
        self.assertEqual(facts["bullet_marker_count"], 1)
        self.assertEqual(facts["date_token_count"], 1)

    def test_bare_pre_review_placeholders_are_recognized(self) -> None:
        facts = deterministic_facts([{
            "text_canonical": (
                "2026-0000(심의일 : 2026. 00. 00.)\n"
                "유효기간 : 2026. 00. 00. ~ 2026. 00. 00."
            )
        }])
        self.assertTrue(facts["review_number_present"])
        self.assertTrue(facts["review_number_placeholder_present"])
        self.assertTrue(facts["review_validity_placeholder_range_present"])

    def test_parser_visibility_is_forwarded_without_recalculation(self) -> None:
        ad = {
            "pages": [{
                "page_no": 1,
                "physical_width_mm": 210,
                "physical_height_mm": 297,
                "regions": [{
                    "evidence_id": "AD-1#p1:r1",
                    "region_id": "r1",
                    "visibility": {"a4_or_larger": True, "minimum_font_pt": 7.9},
                }],
            }]
        }
        facts = deterministic_facts([], ad=ad)["parser_visibility"]
        self.assertFalse(facts["recalculated_by_review_pipeline"])
        self.assertEqual(
            facts["pages"][0]["regions"][0]["visibility"]["minimum_font_pt"],
            7.9,
        )

    def test_missing_parser_visibility_remains_missing(self) -> None:
        ad = {
            "pages": [{"page_no": 1, "regions": [{"region_id": "r1", "visibility": None}]}]
        }
        page = deterministic_facts([], ad=ad)["parser_visibility"]["pages"][0]
        self.assertEqual(page["regions"], [])

    def test_line_style_measurements_are_forwarded_without_recalculation(self) -> None:
        ad = {"pages": [{
            "page_no": 1, "canvas_w": 1000, "canvas_h": 1400, "dpi": 200,
            "regions": [{
                "evidence_id": "E-1", "region_id": "r1", "visibility": None,
                "lines": [{
                    "line_ref": "L-1", "bbox": [1, 2, 3, 4],
                    "style": {"size_pt_min": 7.9, "size_basis": "declared", "color": "#777777"},
                }],
            }],
        }]}
        facts = deterministic_facts([], ad=ad)["parser_visibility"]
        self.assertEqual(facts["pages"][0]["dpi"], 200)
        self.assertEqual(
            facts["pages"][0]["regions"][0]["line_styles"][0]["style"]["size_pt_min"],
            7.9,
        )

    def test_violations_never_bypass_researcher_review(self) -> None:
        row = {"verdict": "VIOLATION", "confidence": "HIGH", "needs_researcher_review": False}
        enforce_review_policy(row)
        self.assertTrue(row["needs_researcher_review"])


if __name__ == "__main__":
    unittest.main()
