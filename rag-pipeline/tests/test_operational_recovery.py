from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

import recover_operational_judgments as recovery  # noqa: E402


def judgment(item_id: str) -> dict:
    return {
        "item_id": item_id,
        "applicability": "UNDETERMINED",
        "verdict": "UNDETERMINED",
        "evidence_ids": [],
        "evidence_line_refs": [],
        "requirement_checks": [{"requirement": "확인", "status": "UNDETERMINED"}],
        "reason": "판단 근거 부족",
        "confidence": "LOW",
        "needs_researcher_review": True,
    }


def response_row(ad_id: str, item_id: str) -> dict:
    return {
        "request_id": f"response:{item_id}",
        "ad_id": ad_id,
        "validation_errors": [],
        "parsed": {"ad_id": ad_id, "results": [judgment(item_id)]},
    }


class OperationalRecoveryTests(unittest.TestCase):
    def test_missing_pair_is_retried_and_multiple_responses_finalize(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            payload = {
                "request_id": "original:1",
                "ad_id": "AD-1",
                "documents": [],
                "rules": [{"item_id": "C-1"}, {"item_id": "C-2"}],
            }
            request = {
                "request_id": "original:1",
                "ad_id": "AD-1",
                "category": "PRESENCE",
                "requested_item_ids": ["C-1", "C-2"],
                "messages": [
                    {"role": "system", "content": "system"},
                    {"role": "user", "content": json.dumps(payload)},
                ],
            }
            requests = work / "requests.jsonl"
            requests.write_text(json.dumps(request) + "\n", encoding="utf-8")
            first = work / "first.json"
            recovery.write_json(first, {"rows": [response_row("AD-1", "C-1")]})
            retry = work / "retry.jsonl"
            recovery.build_recovery_requests(
                argparse.Namespace(
                    requests=requests,
                    responses=[first],
                    output=retry,
                    batch_size=1,
                    round=1,
                )
            )
            retry_row = recovery.read_jsonl(retry)[0]
            self.assertEqual(retry_row["requested_item_ids"], ["C-2"])

            second = work / "second.json"
            recovery.write_json(second, {"rows": [response_row("AD-1", "C-2")]})
            discovery = work / "discovery.json"
            recovery.write_json(
                discovery,
                {
                    "ads": [
                        {
                            "ad_id": "AD-1",
                            "routing": {},
                            "parser_coverage": "READY",
                        }
                    ]
                },
            )
            final = work / "final.json"
            recovery.finalize(
                argparse.Namespace(
                    requests=requests,
                    discovery=discovery,
                    freeze=work / "freeze.json",
                    responses=[first, second],
                    output=final,
                )
            )
            result = json.loads(final.read_text(encoding="utf-8"))
            self.assertEqual(result["counts"]["predicted_pairs"], 2)
            self.assertEqual(result["counts"]["output_failures"], 0)


if __name__ == "__main__":
    unittest.main()
