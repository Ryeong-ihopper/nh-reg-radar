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

from rag.api.service import (  # noqa: E402
    JobStore,
    OperationalReviewService,
    ServiceConfig,
    TransientPipelineError,
    apply_routing_overrides,
)
from rag.contracts.validation import validate_search_collections  # noqa: E402
from rag.parsing.prepare_inputs import _fine_views, compact, product_scoped_documents, search_docs  # noqa: E402
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
    def test_template_only_requires_template_but_not_v2_and_freezes_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            template = root / "template.hwpx"
            template.write_bytes(b"source existence fixture; ingestion tested separately")
            config = ServiceConfig(jobs_dir=root / "jobs", regulation_path=root / "missing.xlsx",
                                   es_url="", es_index="", model="model", template_hwpx_path=template)
            service = OperationalReviewService(config)
            self.addCleanup(service.executor.shutdown, wait=True)
            with mock.patch.object(service.executor, "submit"):
                job = service.submit({"schema_version": "operational-review-request-v1",
                                      "document": integrated_input(), "execute_model": False,
                                      "routing_overrides": {"product_group": "예금성"}})
            self.assertEqual(service.store.request(job["job_id"])["source_policy"], "template-only")
            template.unlink()
            with self.assertRaisesRegex(RuntimeError, "requires a general template"):
                OperationalReviewService(config)

    def test_transport_failure_is_classified_for_automatic_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            regulation = root / "regulation.xlsx"
            regulation.write_bytes(b"placeholder")
            service = OperationalReviewService(ServiceConfig(
                jobs_dir=root / "jobs", regulation_path=regulation, source_policy="template-plus-v2",
                es_url="http://search.invalid", es_index="rules", model="model",
            ))
            self.addCleanup(service.executor.shutdown, wait=True)
            completed = SimpleNamespace(
                returncode=1,
                stdout="",
                stderr="urllib.error.URLError: connection refused",
            )
            with mock.patch("rag.api.service.subprocess.run", return_value=completed):
                with self.assertRaises(TransientPipelineError):
                    service._invoke(
                        directory=root,
                        attempt=1,
                        label="pipeline",
                        command=["python", "pipeline.py"],
                    )

    def test_service_requeues_running_job_after_process_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            regulation = root / "regulation.xlsx"
            regulation.write_bytes(b"placeholder")
            jobs = root / "jobs"
            store = JobStore(jobs)
            job = store.create({"document": {}})
            store.update(job["job_id"], status="RUNNING", attempt=1)
            with mock.patch.object(OperationalReviewService, "_run") as run:
                service = OperationalReviewService(ServiceConfig(source_policy="template-plus-v2",
                    jobs_dir=jobs, regulation_path=regulation,
                    es_url="http://search.invalid", es_index="rules", model="model",
                ))
                service.executor.shutdown(wait=True)
            run.assert_called_once_with(job["job_id"])
            self.assertEqual(service.store.read(job["job_id"])["status"], "QUEUED")

    def test_only_complete_contract_valid_result_can_survive_tail_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result_path = Path(directory) / "04_operational_results.json"
            complete = {
                "schema_version": "operational-e2e-result-v1",
                "audit": {
                    "model": {},
                    "search": {},
                    "rule_sources": {},
                    "guardrails": {},
                },
                "counts": {
                    "ads": 0,
                    "requested_pairs": 0,
                    "predicted_pairs": 0,
                    "output_failures": 0,
                },
                "ads": [],
            }
            result_path.write_text(json.dumps(complete), encoding="utf-8")
            self.assertEqual(
                OperationalReviewService._complete_saved_result(result_path),
                complete,
            )
            complete["counts"]["output_failures"] = 1
            result_path.write_text(json.dumps(complete), encoding="utf-8")
            self.assertIsNone(
                OperationalReviewService._complete_saved_result(result_path)
            )

    def test_retry_selects_latest_previous_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            older = root / "attempt-1" / "03_judgment_responses.json.checkpoint.json"
            latest = root / "attempt-2" / "03_judgment_responses.json.checkpoint.json"
            older.parent.mkdir()
            latest.parent.mkdir()
            older.write_text("{}", encoding="utf-8")
            latest.write_text("{}", encoding="utf-8")
            self.assertEqual(
                OperationalReviewService._previous_checkpoint(root, 3), latest
            )
            self.assertIsNone(
                OperationalReviewService._previous_checkpoint(root, 1)
            )

    def test_explicit_review_date_is_validated_frozen_and_idempotency_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            regulation = root / 'rules.xlsx'
            regulation.write_bytes(b'synthetic')
            service = OperationalReviewService(ServiceConfig(jobs_dir=root/'jobs', regulation_path=regulation, source_policy="template-plus-v2",
                es_url='http://search.invalid', es_index='synthetic', model='synthetic'))
            self.addCleanup(service.executor.shutdown)
            request = {'schema_version':'operational-review-request-v1', 'client_request_id':'DATE-TEST',
                       'document': integrated_input(), 'routing_overrides': {'product_group':'예금성'},
                       'review_date':'2026-04-12', 'execute_model':False}
            with mock.patch.object(service.executor, 'submit'):
                first = service.submit(request)
                saved = json.loads((service.store.directory(first['job_id'])/'request.json').read_text(encoding='utf8'))
                self.assertEqual(saved['review_date'], '2026-04-12')
                self.assertTrue(service.submit(request)['idempotent_replay'])
                registered = service.submit({**request, 'client_request_id': 'REGISTERED',
                                             'review_date_basis': 'advertisement_registration_date'})
                stored = json.loads((service.store.directory(registered['job_id'])/'request.json').read_text(encoding='utf8'))
                self.assertEqual(stored['review_date_basis'], 'advertisement_registration_date')
                with self.assertRaisesRegex(ValueError, 'different input'):
                    service.submit({**request, 'client_request_id': 'REGISTERED',
                                    'review_date_basis': 'explicit_review_date'})
                with self.assertRaisesRegex(ValueError, 'different input'):
                    service.submit({**request,'review_date':'2026-04-13'})
                for value in ('2026-02-30','20260412',12):
                    with self.subTest(value=value), self.assertRaises(ValueError):
                        service.submit({**request,'review_date':value})

    def test_model_environment_is_passed_to_pipeline_process(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            regulation = root / "regulation.xlsx"
            regulation.write_bytes(b"placeholder")
            service = OperationalReviewService(
                ServiceConfig(source_policy="template-plus-v2",
                    jobs_dir=root / "jobs",
                    regulation_path=regulation,
                    es_url="http://search.invalid",
                    es_index="rules",
                    model="model",
                    dgx_host="audit-host.invalid",
                    dgx_key="audit-key",
                    model_env={"NH_GPU_GEMMA_ENDPOINT": "http://gpu.invalid/v1"},
                )
            )
            completed = SimpleNamespace(returncode=0, stdout="", stderr="")
            with mock.patch(
                "rag.api.service.subprocess.run", return_value=completed
            ) as run:
                service._invoke(
                    directory=root,
                    attempt=1,
                    label="environment",
                    command=["python", "--version"],
                )
            self.assertEqual(
                run.call_args.kwargs["env"]["NH_GPU_GEMMA_ENDPOINT"],
                "http://gpu.invalid/v1",
            )
            self.assertEqual(run.call_args.kwargs["env"]["DGX_HOST"], "audit-host.invalid")
            self.assertEqual(run.call_args.kwargs["env"]["DGX_SSH_KEY"], "audit-key")
            service.executor.shutdown(wait=True)

    def test_request_must_confirm_product_group(self) -> None:
        document = integrated_input()
        with self.assertRaises(ValueError):
            apply_routing_overrides(document, {})
        updated = apply_routing_overrides(document, {"product_group": "예금성"})
        self.assertEqual(
            updated["document"]["routing_metadata"]["product_group"]["status"],
            "provided",
        )

    def test_business_context_overrides_remain_confirmed_metadata(self) -> None:
        updated = apply_routing_overrides(
            integrated_input(),
            {
                "product_group": "예금성",
                "review_stage": "사전심의",
                "association_pre_review": "대상",
                "external_evidence_available": False,
            },
        )
        routing = updated["document"]["routing_metadata"]
        self.assertEqual(routing["review_stage"]["value"], "사전심의")
        self.assertEqual(routing["review_stage"]["status"], "provided")
        self.assertFalse(routing["external_evidence_available"]["value"])

    def test_multi_product_input_expands_to_isolated_product_scopes(self) -> None:
        document = integrated_input()
        evidence_id = document["pages"][0]["regions"][0]["evidence_id"]
        document["document"]["products"] = [
            {
                "product_id": "P-1",
                "product_name": "상품 A",
                "routing_metadata": {"template_id": "TEMPLATE-A"},
                "evidence_ids": [],
            },
            {
                "product_id": "P-2",
                "product_name": "상품 B",
                "routing_metadata": {"template_id": "TEMPLATE-B"},
                "evidence_ids": [],
            },
        ]
        document["document"]["shared_evidence_ids"] = [evidence_id]
        scopes = product_scoped_documents(document)
        self.assertEqual(len(scopes), 2)
        self.assertEqual(
            {scope["document"]["product_id"] for scope in scopes},
            {"P-1", "P-2"},
        )
        scoped_evidence_ids = {
            scope["pages"][0]["regions"][0]["evidence_id"] for scope in scopes
        }
        self.assertEqual(len(scoped_evidence_ids), 2)
        self.assertEqual(
            {
                scope["pages"][0]["regions"][0]["source_evidence_id"]
                for scope in scopes
            },
            {evidence_id},
        )
        self.assertNotEqual(scopes[0]["document"]["ad_id"], scopes[1]["document"]["ad_id"])
        coarse, fine = [], []
        for scope in scopes:
            scoped_coarse, scoped_fine = search_docs(scope)
            coarse.extend(scoped_coarse)
            fine.extend(scoped_fine)
        validate_search_collections(scopes, coarse, fine)

    def test_single_product_scope_preserves_unassigned_parser_lines(self) -> None:
        document = integrated_input()
        evidence_id = document["pages"][0]["regions"][0]["evidence_id"]
        document["unverified_recovery_candidates"] = [
            {"page_no": 1, "text": "검증 전 후보", "status": "unverified"}
        ]
        document["pages"][0]["unassigned_lines"] = [
            {
                "line_ref": "p1/unassigned/L00",
                "text": ">",
                "bbox": [0, 90, 5, 95],
                "text_source": "ocr",
                "confidence": 0.9,
                "style": None,
                "labels": [],
            }
        ]
        document["quality"]["line_count"] = 2
        document["document"]["products"] = [
            {
                "product_id": "P-1",
                "product_name": "단일 상품",
                "routing_metadata": {"template_id": "TEMPLATE-A"},
                "evidence_ids": [evidence_id],
            }
        ]
        document["document"]["shared_evidence_ids"] = []

        scopes = product_scoped_documents(document)

        self.assertEqual(len(scopes), 1)
        self.assertEqual(
            scopes[0]["pages"][0]["unassigned_lines"][0]["line_ref"],
            "p1/unassigned/L00",
        )
        self.assertEqual(scopes[0]["quality"]["line_count"], 2)
        self.assertEqual(
            scopes[0]["unverified_recovery_candidates"][0]["text"],
            "검증 전 후보",
        )

    def test_multi_product_scope_rejects_unverified_recovery_candidates(self) -> None:
        document = integrated_input()
        evidence_id = document["pages"][0]["regions"][0]["evidence_id"]
        document["unverified_recovery_candidates"] = [
            {"page_no": 1, "text": "소유권 불명", "status": "unverified"}
        ]
        document["document"]["products"] = [
            {"product_id": "P-1", "product_name": "상품 A", "routing_metadata": {}, "evidence_ids": []},
            {"product_id": "P-2", "product_name": "상품 B", "routing_metadata": {}, "evidence_ids": []},
        ]
        document["document"]["shared_evidence_ids"] = [evidence_id]

        with self.assertRaisesRegex(ValueError, "unverified recovery candidates"):
            product_scoped_documents(document)

    def test_fine_views_preserve_selected_region_text_when_lines_differ(self) -> None:
        region = integrated_input()["pages"][0]["regions"][0]
        region["final_text"] = "가입기간 12개월\n가입금액 1천원~30만원"
        region["line_refs"] = ["L-1", "L-2", "L-3"]
        region["lines"] = [
            {"line_ref": "L-1", "text": "가입기간 12개월", "labels": []},
            {"line_ref": "L-2", "text": "W", "labels": []},
            {"line_ref": "L-3", "text": "가입금액 1천원~30만원", "labels": []},
        ]

        views = _fine_views(region)

        self.assertEqual(
            compact("".join(view["text_canonical"] for view in views)),
            compact(region["final_text"]),
        )
        self.assertTrue(all(view["span_status"] == "selected_text_line_aligned" for view in views))
        self.assertTrue(all(view["line_refs"] == ["L-1", "L-3"] for view in views))

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
