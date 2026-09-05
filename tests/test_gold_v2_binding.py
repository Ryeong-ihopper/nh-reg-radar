# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from validate_gold_v2_binding import validate_rows  # noqa: E402


CURRENT = {
    "C-001": {
        "id": "C-001",
        "title": "title",
        "question": "question",
        "criterion": "criterion",
    }
}


class GoldV2BindingTests(unittest.TestCase):
    def test_old_gold_without_snapshot_is_not_evaluation_ready(self):
        result = validate_rows([{"ad_id": "A", "item_id": "C-001"}], CURRENT, "sha")[0]
        self.assertEqual(result["status"], "UNBOUND")

    def test_exact_snapshot_is_bound(self):
        row = {
            "ad_id": "A",
            "item_id": "C-001",
            "regulation_binding": {
                "regulation_sha256": "sha",
                "item_id": "C-001",
                "title": "title",
                "question": "question",
                "criterion": "criterion",
            },
        }
        self.assertEqual(validate_rows([row], CURRENT, "sha")[0]["status"], "BOUND")

    def test_same_id_with_changed_meaning_is_drift(self):
        row = {
            "ad_id": "A",
            "item_id": "C-001",
            "regulation_binding": {
                "regulation_sha256": "sha",
                "item_id": "C-001",
                "title": "old title",
                "question": "question",
                "criterion": "criterion",
            },
        }
        self.assertEqual(validate_rows([row], CURRENT, "sha")[0]["status"], "DRIFT")


if __name__ == "__main__":
    unittest.main()
