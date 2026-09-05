from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rag.operational.policy import (  # noqa: E402
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

    def test_format_equivalents_are_observations(self) -> None:
        facts = deterministic_facts([
            {"text_canonical": "■ 유의사항\n준법감시인 심의필 0000-0000 (2026.09.01)"}
        ])
        self.assertTrue(facts["review_number_present"])
        self.assertEqual(facts["bullet_marker_count"], 1)
        self.assertEqual(facts["date_token_count"], 1)

    def test_violations_never_bypass_researcher_review(self) -> None:
        row = {"verdict": "VIOLATION", "confidence": "HIGH", "needs_researcher_review": False}
        enforce_review_policy(row)
        self.assertTrue(row["needs_researcher_review"])


if __name__ == "__main__":
    unittest.main()
