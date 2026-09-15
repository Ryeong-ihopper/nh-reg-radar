from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from tools import run_operational_e2e as operational  # noqa: E402


class OperationalRerankingTests(unittest.TestCase):
    def test_reranker_reorders_without_threshold_deleting_candidates(self) -> None:
        candidates = [
            {"item_id": "D-1", "rank": 1, "trigger_evidence": [{"trigger": {"doc_id": "E-1"}}]},
            {"item_id": "D-2", "rank": 2, "trigger_evidence": [{"trigger": {"doc_id": "E-2"}}]},
        ]
        rules = {
            "D-1": {"item_id": "D-1", "title": "낮은 관련 규칙", "category": "PROHIBIT"},
            "D-2": {"item_id": "D-2", "title": "높은 관련 규칙", "category": "PROHIBIT"},
        }
        evidence = {
            "E-1": {"text_canonical": "광고문 1"},
            "E-2": {"text_canonical": "광고문 2"},
        }
        with mock.patch.object(
            operational, "dgx_rerank", return_value=np.asarray([0.1, 0.9])
        ):
            result = operational.rerank_prohibition_candidates(
                candidates,
                rules=rules,
                fine_documents=evidence,
                rrf_k=60,
                candidate_pool=80,
            )
        self.assertEqual([row["item_id"] for row in result], ["D-2", "D-1"])
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["reranker_rank"], 1)


if __name__ == "__main__":
    unittest.main()
