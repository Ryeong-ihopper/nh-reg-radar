from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rag.judgment.decision_guides import (  # noqa: E402
    attach_decision_guides,
    load_decision_guides,
)


class DecisionGuideTests(unittest.TestCase):
    def test_template_does_not_inherit_v2_authority(self) -> None:
        rules = attach_decision_guides([
            {"item_id": "template", "source_sheet": "HWPX_TEMPLATE"},
            {"item_id": "v2", "source_sheet": "execution"},
        ], [])
        self.assertIn("independent judgment source", rules[0]["decision_guide_policy"])
        self.assertNotIn("v2 remains authoritative", rules[0]["decision_guide_policy"])
        self.assertIn("v2 remains authoritative", rules[1]["decision_guide_policy"])

    def test_guides_are_bound_to_the_active_v2_item_and_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            regulation = root / "regulation-v2.xlsx"
            regulation.write_bytes(b"v2")
            guide = root / "guide.json"
            guide.write_text(
                json.dumps(
                    {
                        "schema_version": "review-decision-guide-v1",
                        "regulation_v2_sha256": hashlib.sha256(b"v2").hexdigest(),
                        "guides": [
                            {
                                "guide_id": "DG-1",
                                "item_id": "C-001",
                                "template_id": "대출성상품-상품명 노출",
                                "label": "회사명",
                                "applicability_conditions": [],
                                "requirements": ["회사명을 표시한다"],
                                "compliant_examples": ["NH농협은행"],
                                "violation_conditions": ["회사명이 없다"],
                                "violation_message": "회사명을 기재 바랍니다.",
                                "review_conditions": ["회사 주체가 모호하다"],
                                "review_message": "광고 주체 확인 필요",
                                "source_refs": ["업무 템플릿 1행"],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            guides = load_decision_guides(
                guide,
                regulation_path=regulation,
                known_item_ids=["C-001"],
            )
            rules = attach_decision_guides([{"item_id": "C-001"}], guides)
            self.assertEqual(rules[0]["decision_guides"][0]["guide_id"], "DG-1")

    def test_unknown_item_cannot_introduce_a_new_rule(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            regulation = root / "regulation-v2.xlsx"
            regulation.write_bytes(b"v2")
            guide = root / "guide.json"
            guide.write_text(
                json.dumps(
                    {
                        "schema_version": "review-decision-guide-v1",
                        "regulation_v2_sha256": hashlib.sha256(b"v2").hexdigest(),
                        "guides": [{
                            "guide_id": "DG-X",
                            "item_id": "CASE-SPECIFIC",
                            "label": "금지",
                            "requirements": ["검사"],
                            "compliant_examples": [],
                            "violation_conditions": [],
                            "review_conditions": [],
                        }],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "unknown v2 item"):
                load_decision_guides(
                    guide,
                    regulation_path=regulation,
                    known_item_ids=["C-001"],
                )

    def test_applicability_conditions_must_be_nonempty_strings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            regulation = root / "regulation-v2.xlsx"
            regulation.write_bytes(b"v2")
            guide = root / "guide.json"
            guide.write_text(
                json.dumps({
                    "schema_version": "review-decision-guide-v1",
                    "regulation_v2_sha256": hashlib.sha256(b"v2").hexdigest(),
                    "guides": [{
                        "guide_id": "DG-1",
                        "item_id": "C-001",
                        "label": "조건 검사",
                        "applicability_conditions": [""],
                        "requirements": ["검사"],
                        "compliant_examples": [],
                        "violation_conditions": [],
                        "review_conditions": [],
                    }],
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "applicability_conditions"):
                load_decision_guides(
                    guide,
                    regulation_path=regulation,
                    known_item_ids=["C-001"],
                )


if __name__ == "__main__":
    unittest.main()
