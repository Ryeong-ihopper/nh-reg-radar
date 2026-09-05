from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest import mock

from fastapi import HTTPException
from starlette.requests import Request


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rag.operational.service import JobStore, apply_routing_overrides  # noqa: E402
from tools import serve_operational_api as api  # noqa: E402


def integrated_input() -> dict:
    line_ref = "p1/r1/L00"
    return {
        "contract": {
            "version": "nh-ad-review-integrated-input-v1",
            "sources": {
                "p1_contract": "nh-ad-review-evidence-v6",
                "p3_contract": "nh-ad-review-region-input-v1",
                "p1_sha256": "a" * 64,
                "p3_sha256": "b" * 64,
            },
            "review_unit": "region",
            "final_text_policy": "judge selected",
        },
        "document": {
            "ad_id": "AD-1",
            "source_file": "ad.pdf",
            "file_type": "pdf",
            "dataset_group": None,
            "input_relative_path": None,
            "routing_metadata": {"product_group": "예금성"},
        },
        "pages": [
            {
                "page_no": 1,
                "canvas_w": 100,
                "canvas_h": 100,
                "dpi": 100,
                "parse_route": "ocr",
                "parse_status": "ok",
                "regions": [
                    {
                        "evidence_id": "AD-1#p1:r1",
                        "region_id": "r1",
                        "card_no": None,
                        "bbox": [0, 0, 50, 50],
                        "layout": None,
                        "final_text": "준법감시인 심의필 0000-0000",
                        "text_source": "parser",
                        "line_refs": [line_ref],
                        "lines": [
                            {
                                "line_ref": line_ref,
                                "text": "준법감시인 심의필 0000-0000",
                                "bbox": [0, 0, 50, 10],
                                "text_source": "ocr",
                                "confidence": 0.99,
                                "style": None,
                                "labels": [],
                            }
                        ],
                        "labels": [],
                        "assignment_status": "unassigned",
                        "visibility": None,
                        "table": None,
                    }
                ],
                "unassigned_lines": [],
            }
        ],
        "unverified_recovery_candidates": [],
        "diagnostics": {},
        "quality": {
            "line_count": 1,
            "line_partition_exact": True,
            "region_count": 1,
            "empty_region_count": 0,
        },
    }


class OperationalServiceTests(unittest.TestCase):
    def test_request_must_confirm_product_group(self) -> None:
        document = integrated_input()
        with self.assertRaises(ValueError):
            apply_routing_overrides(document, {})
        updated = apply_routing_overrides(document, {"product_group": "예금성"})
        self.assertEqual(
            updated["document"]["routing_metadata"]["product_group"]["status"],
            "provided",
        )

    def test_job_store_survives_process_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(Path(directory))
            job = store.create({"document": {}})
            store.update(job["job_id"], status="RUNNING")
            self.assertEqual(store.interrupt_stale_jobs(), 1)
            status = store.read(job["job_id"])
            self.assertEqual(status["status"], "INTERRUPTED")
            self.assertEqual(status["error"]["code"], "PROCESS_RESTARTED")
            request = json.loads(
                (store.directory(job["job_id"]) / "request.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(request, {"document": {}})

    def test_client_request_id_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(Path(directory))
            request = {
                "client_request_id": "CLIENT-1",
                "input_sha256": "a" * 64,
            }
            first = store.create(request)
            second = store.create(request)
            self.assertEqual(second["job_id"], first["job_id"])
            self.assertTrue(second["idempotent_replay"])
            with self.assertRaises(ValueError):
                store.create({**request, "input_sha256": "b" * 64})

    def test_http_submit_is_async_and_authenticated(self) -> None:
        fake = SimpleNamespace(
            config=SimpleNamespace(
                regulation_path=Path(__file__),
                queue_workers=1,
            ),
            submit=lambda _payload: {
                "schema_version": "operational-review-job-v1",
                "job_id": "00000000-0000-0000-0000-000000000001",
                "status": "QUEUED",
            },
        )
        with (
            mock.patch.dict("os.environ", {"NH_RAG_API_TOKEN": "secret"}),
            mock.patch.object(api, "config_from_env", return_value=object()),
            mock.patch.object(api, "OperationalReviewService", return_value=fake),
        ):
            app = api.create_app()
            route = next(route for route in app.routes if route.path == "/v1/reviews")
            self.assertFalse(route.dependant.query_params)

            body = json.dumps({"any": "payload"}).encode("utf-8")

            async def receive():
                return {"type": "http.request", "body": body, "more_body": False}

            request = Request(
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/v1/reviews",
                    "headers": [(b"content-type", b"application/json")],
                },
                receive,
            )
            with self.assertRaises(HTTPException):
                asyncio.run(route.endpoint(request, None))
            accepted = asyncio.run(route.endpoint(request, "secret"))
            self.assertEqual(accepted["status"], "QUEUED")


if __name__ == "__main__":
    unittest.main()
