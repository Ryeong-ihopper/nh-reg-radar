"""Provider-free adapter tests; these fixtures are never runtime judgments."""
import json
import sys
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import Mock, patch
import subprocess

import openpyxl
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from operational_web_bridge import (  # noqa: E402
    ExecutionBridge, FULL_REVIEW, PARSER_REUSE_PARENT_STATUSES,
    parser_layout, parser_runner_layout,
)
from nh_ad_backend.domain import Advertisement, AdvertisementFile, User  # noqa: E402
from nh_ad_backend.main import build_services, create_app  # noqa: E402
from nh_ad_backend.security import current_user, hash_password  # noqa: E402
from nh_ad_backend.services import ServiceError  # noqa: E402
from nh_ad_backend.settings import Settings  # noqa: E402


class BridgeTests(unittest.TestCase):
    def test_missing_or_changed_user_template_prevents_parent_parser_reuse(self):
        parent = self.request()
        parent.job.status = "COMPLETED"
        parent_dir = self.bridge.root / "runs" / parent.review.review_id
        parent_dir.mkdir(parents=True)
        current = self.root / "new-run"
        for manifest in (None, self.bridge.parser_intake("대출성상품-상품명 노출"),
                         {"version": "user-template-labeling-v1", "template_id": "예금성상품-적립식"},
                         {"version": "user-template-labeling-v2", "template_id": "예금성상품-적립식"},
                         {"version": "old-policy", "template_id": "예금성상품-적립식"}):
            if manifest is not None:
                (parent_dir / "parser-intake.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.subTest(manifest=manifest):
                self.assertIsNone(self.bridge.reuse_parent_parser_output(
                    self.ad, current, {}, parent.review.review_id, template_id="예금성상품-적립식"))
        self.assertFalse((current / "parser-reuse.json").exists())

    def test_parser_must_echo_the_user_template_in_both_outputs(self):
        template = {"template_id": "예금성상품-적립식", "source": "user_provided"}
        p1, p3 = self.root / "p1.json", self.root / "p3.json"
        p1.write_text(json.dumps({"template": template}), encoding="utf-8")
        p3.write_text(json.dumps({"document": {"template": template}}), encoding="utf-8")
        self.bridge.validate_parser_template(p1, p3, "예금성상품-적립식")
        for bad in ({**template, "source": "rules"}, {**template, "template_id": "대출성상품-상품명 노출"}):
            p3.write_text(json.dumps({"document": {"template": bad}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "PARSER_TEMPLATE_MISMATCH"):
                self.bridge.validate_parser_template(p1, p3, "예금성상품-적립식")

    def test_parser_reuse_accepts_successful_terminal_parents(self):
        self.assertIn("COMPLETED", PARSER_REUSE_PARENT_STATUSES)
        self.assertIn("COMPLETED_WITH_WARNINGS", PARSER_REUSE_PARENT_STATUSES)
        self.assertNotIn("RUNNING", PARSER_REUSE_PARENT_STATUSES)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        book = openpyxl.Workbook()
        sheet = book.active
        sheet.title = "신규규칙후보"
        sheet.append(["섹션"])
        sheet.append(["예금성상품-적립식"])
        sheet.append(["대출성상품-상품명 노출"])
        book.save(self.root / "rules.xlsx")
        book.close()
        (self.root / "config.json").write_text(json.dumps({
            "regulation_path": str(self.root / "rules.xlsx"),
            "es_url": "http://localhost:9", "es_index": "test-only", "model": "test-only",
        }), encoding="utf-8")
        self.settings = Settings(app_env="test", private_storage_path=self.root / "private")
        self.services = build_services(self.settings)
        self.user = User("tester", "tester", "tester@localhost", hash_password("test-password"), "DPT-T", "Test", ("COMPLIANCE_REVIEWER",))
        self.services.repository.users[self.user.user_id] = self.user
        self.actor = current_user(self.user)
        self.ad = Advertisement("ADV-test", "test", "SAVINGS", "NOTICE", None, "DPT-T", "tester", "UPLOADED", None, datetime.now(UTC),
            files=[AdvertisementFile("FILE-test", "ADVERTISEMENT", "input.pdf", "x", "application/pdf", 100, "abc")])
        self.services.repository.add_advertisement(self.ad)
        self.bridge = ExecutionBridge(self.services, self.root / "state", self.root / "config.json", Mock())
        self.bridge.pool.shutdown(wait=True)
        self.bridge.pool = Mock()
        self.addCleanup(self.bridge.rag.executor.shutdown, wait=True)
        self.options = dict(standard_effective_date=None, review_types=tuple(FULL_REVIEW),
            include_suggestion=False, include_opinion_draft=False, request_memo=None, trace_id="test")

    def request(self):
        return self.services.reviews.request(self.actor, self.ad.advertisement_id, **self.options)

    def test_parser_runner_layouts_are_explicit(self):
        legacy = parser_runner_layout({})
        external = parser_runner_layout({"parser_runner": "nh_ad_parser_cli"})
        self.assertEqual((legacy["p1_dir"], legacy["p3_dir"]), ("json", "review_region_input"))
        self.assertEqual((external["p1_dir"], external["p3_dir"]), ("evidence", "review-input"))
        with self.assertRaises(ValueError):
            parser_runner_layout({"parser_runner": "unknown"})

    def test_parser_timeout_and_start_error_reach_asset_retry(self):
        self.bridge.config["parser_cwd"] = str(self.root)
        self.bridge.parser_command = Mock(return_value=["test-parser"])
        for error, code in [(subprocess.TimeoutExpired("test-parser", 3600), 124),
                            (OSError("test launch failure"), 126)]:
            with self.subTest(code=code), patch("operational_web_bridge.subprocess.run", side_effect=error):
                log = self.root / "failure.log"
                self.assertEqual(self.bridge.execute_parser(self.root, self.root, log), code)
                self.assertIn("PARSER_", log.read_text(encoding="utf-8"))

    def test_external_parser_command_uses_absolute_bridge_paths(self):
        parser_root = self.root / "parser"
        parser_root.mkdir()
        self.bridge.config.update({
            "parser_runner": "nh_ad_parser_cli",
            "parser_root": str(parser_root),
            "parser_python": "python",
        })
        self.bridge.parser_layout_config = parser_runner_layout(self.bridge.config)

        command = self.bridge.parser_command(Path("relative-source"), Path("relative-output"), template_id="대출성상품-상품명 노출")

        self.assertEqual(command[1], "-u")
        self.assertTrue(Path(command[2]).is_absolute())
        self.assertTrue(Path(command[4]).is_absolute())
        self.assertTrue(Path(command[6]).is_absolute())
        self.assertEqual(command[3], "--input")
        self.assertEqual(command[5], "--out")
        self.assertEqual(command[-2:], ["--template-id", "대출성상품-상품명 노출"])
        with self.assertRaisesRegex(ValueError, "PARSER_TEMPLATE_REQUIRED"):
            self.bridge.parser_command(self.root, self.root)
        visual = self.bridge.parser_command(self.root, self.root, visual=True)
        self.assertIn("--parse-only", visual)
        self.assertNotIn("--template-id", visual)

    def test_missing_asset_retries_individually_and_keeps_batch_output(self):
        parser_root = self.root / "parser"
        parser_root.mkdir()
        self.bridge.config.update({
            "parser_runner": "nh_ad_parser_cli",
            "parser_root": str(parser_root),
            "parser_python": "python",
        })
        self.bridge.parser_layout_config = parser_runner_layout(self.bridge.config)
        second = AdvertisementFile("FILE-second", "ADVERTISEMENT", "second.pdf", "y", "application/pdf", 100, "def")
        self.ad.files.append(second)
        source_dir = self.root / "source"
        source_dir.mkdir()
        sources = {
            "FILE-test": source_dir / "FILE-test_input.pdf",
            "FILE-second": source_dir / "FILE-second_second.pdf",
        }
        for path in sources.values():
            path.write_bytes(b"source")
        batch_output = self.root / "batch-output"
        for name in ("evidence", "review-input"):
            (batch_output / name).mkdir(parents=True)
        first_output_name = f"{sources['FILE-test'].stem}.json"
        (batch_output / "evidence" / first_output_name).write_text("{}", encoding="utf-8")
        (batch_output / "review-input" / first_output_name).write_text("{}", encoding="utf-8")
        completed, missing = self.bridge.parsed_assets(self.ad.files, sources, batch_output)
        self.assertEqual(set(completed), {"FILE-test"})
        self.assertEqual(set(missing), {"FILE-second"})

        def write_retry_output(retry_source, retry_output, log_path, *, template_id=None):
            self.assertEqual(template_id, "대출성상품-상품명 노출")
            source = next(Path(retry_source).iterdir())
            for name in ("evidence", "review-input"):
                (Path(retry_output) / name).mkdir(parents=True, exist_ok=True)
                (Path(retry_output) / name / f"{source.stem}.json").write_text("{}", encoding="utf-8")
            Path(log_path).write_text("retried", encoding="utf-8")
            return 0

        self.bridge.execute_parser = Mock(side_effect=write_retry_output)
        recovered, attempts = self.bridge.retry_missing_parser_assets(
            self.ad.files, sources, missing, self.root / "run",
            template_id="대출성상품-상품명 노출",
        )
        self.assertEqual(set(recovered), {"FILE-second"})
        self.assertEqual(attempts[0]["status"], "RECOVERED")
        self.assertEqual(self.bridge.execute_parser.call_count, 1)
        manifest = json.loads((self.root / "run" / "parser-retry" / "parser-retry.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["attempts"][0]["file_id"], "FILE-second")

    def test_multiple_assets_use_independent_bounded_parser_calls(self):
        parser_root = self.root / "parser"
        parser_root.mkdir()
        self.bridge.config.update({
            "parser_runner": "nh_ad_parser_cli",
            "parser_root": str(parser_root),
            "parser_python": "python",
            "parser_workers": 2,
        })
        self.bridge.parser_layout_config = parser_runner_layout(self.bridge.config)
        second = AdvertisementFile("FILE-second", "ADVERTISEMENT", "second.pdf", "y", "application/pdf", 100, "def")
        self.ad.files.append(second)
        source_dir = self.root / "source"
        source_dir.mkdir()
        sources = {
            "FILE-test": source_dir / "FILE-test_input.pdf",
            "FILE-second": source_dir / "FILE-second_second.pdf",
        }
        for path in sources.values():
            path.write_bytes(b"source")

        def write_output(asset_source, asset_output, log_path, *, template_id=None):
            self.assertEqual(template_id, "예금성상품-적립식")
            source = next(Path(asset_source).iterdir())
            for name in ("evidence", "review-input"):
                (Path(asset_output) / name).mkdir(parents=True, exist_ok=True)
                (Path(asset_output) / name / f"{source.stem}.json").write_text("{}", encoding="utf-8")
            Path(log_path).write_text("parsed", encoding="utf-8")
            return 0

        self.bridge.execute_parser = Mock(side_effect=write_output)
        completed, missing, returncode = self.bridge.parse_assets_in_parallel(
            self.ad.files, sources, self.root / "run",
            template_id="예금성상품-적립식",
        )
        self.assertEqual(set(completed), {"FILE-test", "FILE-second"})
        self.assertEqual(missing, {})
        self.assertEqual(returncode, 0)
        self.assertEqual(self.bridge.execute_parser.call_count, 2)
        self.assertEqual(len(list((self.root / "run" / "parser" / "evidence").glob("*.json"))), 2)
        manifest = json.loads((self.root / "run" / "parser-initial" / "parser-initial.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["max_workers"], 2)

    def test_request_enters_real_queue_and_duplicate_is_rejected(self):
        bundle = self.request()
        self.bridge.pool.submit.assert_called_once()
        self.assertEqual(self.ad.latest_review_id, bundle.review.review_id)
        with self.assertRaises(ServiceError) as ctx:
            self.request()
        self.assertEqual(ctx.exception.code, "REVIEW_ALREADY_RUNNING")

    def test_unsupported_options_do_not_silently_run(self):
        for key, value in [("include_suggestion", True), ("include_opinion_draft", True),
                           ("review_types", ("REQUIRED_PHRASE",)), ("standard_effective_date", date(2000, 1, 1))]:
            options = {**self.options, key: value}
            with self.subTest(key=key), self.assertRaises(ServiceError):
                self.bridge.validate_request(self.ad, options)
        self.assertFalse(self.bridge.pool.submit.called)

    def test_rerun_preserves_previous_effective_date(self):
        options = {
            **self.options,
            "standard_effective_date": date(2000, 1, 1),
            "parent_review_id": "REV-previous",
        }
        self.bridge.validate_request(self.ad, options)

    def test_ambiguous_product_and_extra_files_are_rejected(self):
        self.ad.product_group = "EVENT"
        with self.assertRaises(ServiceError):
            self.bridge.validate_request(self.ad, self.options)

    def test_multiple_advertisement_assets_are_accepted_and_evidence_is_namespaced(self):
        second = AdvertisementFile("FILE-second", "ADVERTISEMENT", "second.pdf", "y", "application/pdf", 100, "def")
        self.ad.files.append(second)
        self.bridge.validate_request(self.ad, self.options)
        def parsed(doc_id, source, text):
            return {
                "contract": {"version": "nh-ad-review-integrated-input-v1", "sources": {"p1_contract": "nh-ad-review-evidence-v6", "p3_contract": "nh-ad-review-region-input-v1", "p1_sha256": "a" * 64, "p3_sha256": "b" * 64}, "review_unit": "region", "final_text_policy": "selected"},
                "document": {"ad_id": doc_id, "source_file": source, "file_type": "pdf", "routing_metadata": {}},
                "pages": [{"page_no": 1, "canvas_w": 1, "canvas_h": 1, "dpi": 200, "parse_route": "ocr", "parse_status": "ok", "regions": [{"evidence_id": f"{doc_id}#p1:r1", "region_id": "r1", "card_no": None, "bbox": None, "layout": None, "final_text": text, "text_source": "ocr", "line_refs": ["p1/r1/L00"], "lines": [{"line_ref": "p1/r1/L00", "text": text, "bbox": None, "text_source": "ocr", "confidence": 1.0, "style": None, "labels": []}], "labels": [], "assignment_status": "unassigned", "visibility": None, "table": None}], "unassigned_lines": []}],
                "unverified_recovery_candidates": [], "diagnostics": {}, "quality": {"line_count": 1, "line_partition_exact": True, "region_count": 1, "empty_region_count": 0},
            }
        first_document = parsed("DOC-1", "input.pdf", "첫 자산")
        first_document["pages"][0]["unassigned_lines"] = [{
            "line_ref": "p1/unassigned/L00", "text": "미배정 줄", "bbox": None,
            "text_source": "ocr", "confidence": 1.0, "style": None, "labels": [],
        }]
        first_document["quality"]["line_count"] = 2
        first_document["unverified_recovery_candidates"] = [{
            "page_no": 1, "text": "검증 전 후보", "status": "unverified",
        }]
        value = self.bridge.merge_asset_documents(self.ad, [(self.ad.files[0], first_document), (second, parsed("DOC-2", "second.pdf", "둘째 자산"))])
        self.assertEqual(value["document"]["ad_id"], "ADV-test")
        self.assertEqual([page["page_no"] for page in value["pages"]], [1, 2])
        self.assertEqual(value["quality"]["line_count"], 3)
        self.assertEqual(value["pages"][0]["regions"][0]["line_refs"], ["FILE-test::p1/r1/L00"])
        self.assertEqual(value["pages"][1]["regions"][0]["line_refs"], ["FILE-second::p1/r1/L00"])
        self.assertEqual(value["unverified_recovery_candidates"][0]["asset_id"], "FILE-test")
        self.assertEqual(value["unverified_recovery_candidates"][0]["page_no"], 1)
        self.assertEqual(value["unverified_recovery_candidates"][0]["source_page_no"], 1)
        intake = {
            "schema_version": "operational-ad-intake-v1",
            "advertisement_name": "test",
            "media_codes": ["NOTICE"],
            "assets": [
                {"asset_id": "FILE-test", "file_name": "input.pdf"},
                {"asset_id": "FILE-second", "file_name": "second.pdf"},
            ],
            "products": [{
                "product_id": "P-1", "product_name": "test",
                "product_group": "예금성",
                "product_classification_code": "예금성상품-적립식",
                "asset_scopes": [
                    {"asset_id": "FILE-test", "page_ranges": None},
                    {"asset_id": "FILE-second", "page_ranges": None},
                ],
            }],
            "shared_asset_scopes": [], "follow_up": None,
        }
        scoped = self.bridge.apply_intake_scopes(self.ad, value, intake)
        self.assertEqual(
            scoped["document"]["routing_metadata"]["media_type"],
            {"value": "NOTICE", "source": "web_user", "status": "provided"},
        )
        self.ad.product_group = "SAVINGS"
        self.ad.files.append(AdvertisementFile("FILE-terms", "TERMS", "terms.pdf", "y", "application/pdf", 100, "def"))
        with self.assertRaises(ServiceError):
            self.bridge.validate_request(self.ad, self.options)

    def test_restart_marks_interrupted_job_failed_and_preserves_upload(self):
        bundle = self.request()
        self.bridge.stage(bundle, 1)
        other = build_services(self.settings)
        restored = ExecutionBridge(other, self.root / "state", self.root / "config.json", Mock())
        self.addCleanup(restored.pool.shutdown, wait=True)
        self.addCleanup(restored.rag.executor.shutdown, wait=True)
        value = other.reviews.repository.get(bundle.review.review_id)
        self.assertEqual(value.job.status, "FAILED")
        self.assertEqual(value.review.status, "REVIEW_FAILED")
        self.assertEqual(value.job.failed_reason_code, "PROCESS_RESTARTED")
        self.assertEqual(other.repository.get_advertisement("ADV-test").files[0].checksum, "abc")

    def test_routing_authenticated_scoped_and_frozen_on_request(self):
        app = create_app(self.settings, self.services)
        self.bridge.install(app)
        with TestClient(app) as client:
            url = "/operational/advertisements/ADV-test/routing"
            self.assertEqual(client.put(url, json={"product_classification_code": "예금성상품-적립식"}).status_code, 401)
            token, _, _ = self.services.auth.login(self.user.email, "test-password", "local", "test", "test")
            headers = {"Authorization": f"Bearer {token}"}
            capabilities = client.get("/operational/capabilities", headers=headers).json()
            self.assertNotIn("templates", capabilities)
            self.assertEqual(
                {row["label"] for row in capabilities["productClassifications"]},
                {"예금성상품-적립식", "대출성상품-상품명 노출"},
            )
            self.assertEqual(client.put(url, headers=headers, json={"product_classification_code": "대출성상품-상품명 노출"}).status_code, 422)
            self.assertEqual(client.put(url, headers=headers, json={"product_classification_code": "예금성상품-적립식"}).status_code, 200)
            intake = {
                "schema_version": "operational-ad-intake-v1", "advertisement_name": "test", "media_codes": ["NOTICE"],
                "assets": [{"asset_id": "FILE-test", "file_name": "input.pdf"}],
                "products": [{"product_id": "P-1", "product_name": "적립식 상품", "product_group": "예금성", "product_classification_code": "예금성상품-적립식", "asset_scopes": [{"asset_id": "FILE-test", "page_ranges": None}]}],
                "shared_asset_scopes": [], "follow_up": None,
            }
            self.assertEqual(client.put("/operational/advertisements/ADV-test/intake", headers=headers, json=intake).status_code, 200)
            bundle = self.request()
            self.assertEqual(self.bridge.links[bundle.review.review_id]["routing"]["product_classification_code"], "예금성상품-적립식")
            self.assertEqual(self.bridge.links[bundle.review.review_id]["routing"]["internal_template_id"], "예금성상품-적립식")
            self.assertEqual(self.bridge.links[bundle.review.review_id]["routing"]["intake"]["products"][0]["product_id"], "P-1")
            self.assertEqual(client.post("/reviews/REV-test/suggestions", headers=headers, json={}).status_code, 409)

    def test_parser_failure_never_becomes_success_or_verdict(self):
        bundle = self.request()
        self.bridge.parse = Mock(side_effect=RuntimeError("PARSER_FAILED"))
        self.bridge.run(bundle, {"internal_template_id": "대출성상품-상품명 노출"})
        self.assertEqual(self.bridge.parse.call_args.kwargs["template_id"], "대출성상품-상품명 노출")
        self.assertEqual(bundle.job.status, "FAILED")
        self.assertEqual(self.services.results.repository.list_items(bundle.review.review_id), [])
        self.assertEqual(self.bridge.projector.call_count, 0)

    def test_user_cancel_marks_job_terminal_without_projecting_results(self):
        app = create_app(self.settings, self.services)
        self.bridge.install(app)
        bundle = self.request()
        with TestClient(app) as client:
            token, _, _ = self.services.auth.login(
                self.user.email, "test-password", "local", "test", "test"
            )
            response = client.post(
                f"/operational/reviews/{bundle.review.review_id}/cancel",
                headers={"Authorization": f"Bearer {token}"}, json={},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(bundle.job.status, "CANCELED")
        self.assertEqual(bundle.review.status, "REVIEW_CANCELED")
        self.assertEqual(self.ad.review_status, "UPLOADED")
        self.assertNotIn(bundle.review.review_id, self.bridge.active)

    def test_human_final_decision_is_separate_immutable_and_audited(self):
        app = create_app(self.settings, self.services)
        self.bridge.install(app)
        bundle = self.request()
        bundle.review.status = "REVIEW_COMPLETED"
        with TestClient(app) as client:
            token, _, _ = self.services.auth.login(
                self.user.email, "test-password", "local", "test", "test"
            )
            headers = {"Authorization": f"Bearer {token}"}
            path = f"/operational/reviews/{bundle.review.review_id}/decision"
            rejected_without_reason = client.put(
                path, headers=headers, json={"decision": "REJECTED", "comment": ""}
            )
            self.assertEqual(rejected_without_reason.status_code, 422)
            approved = client.put(
                path, headers=headers, json={"decision": "APPROVED", "comment": "확인 완료"}
            )
            self.assertEqual(approved.status_code, 200)
            self.assertTrue(approved.json()["ai_result_unchanged"])
            self.assertEqual(approved.json()["reviewer_id"], self.user.user_id)
            self.assertEqual(
                client.put(path, headers=headers, json={"decision": "REJECTED", "comment": "변경"}).status_code,
                409,
            )

    def test_parser_layout_keeps_only_real_coordinate_evidence(self):
        document = {
            "pages": [{
                "page_no": 1,
                "canvas_w": 1000,
                "canvas_h": 2000,
                "regions": [
                    {
                        "region_id": "p1_r001",
                        "bbox": [10, 20, 300, 400],
                        "lines": [
                            {"line_ref": "p1/p1_r001/L00", "text": "실제 좌표", "bbox": [20, 30, 280, 60]},
                            {"line_ref": "p1/p1_r001/L01", "text": "좌표 없음", "bbox": None},
                        ],
                    },
                    {"region_id": "p1_r002", "bbox": None, "lines": []},
                ],
            }],
        }

        value = parser_layout(document, source="test")

        self.assertEqual(value["counts"], {"pages": 1, "regions": 1, "lines": 1})
        self.assertEqual(value["pages"][0]["regions"][0]["region_id"], "p1_r001")
        self.assertEqual(value["pages"][0]["regions"][0]["lines"][0]["line_ref"], "p1/p1_r001/L00")

    def test_workspace_and_download_share_saved_rows_including_partial_failures(self):
        bundle = self.request()
        bundle.review.status = "REVIEW_COMPLETED"
        bundle.job.status = "COMPLETED_WITH_WARNINGS"
        output = self.root / "result"
        output.mkdir()
        raw = {"ads": [{"ad_id": "ADV-test", "candidates": [
            {"item_id": "R1", "judgment": {"verdict": "NOT_APPLICABLE", "reason": "condition false"}},
            {"item_id": "R2", "judgment": {"verdict": "UNDETERMINED", "reason": "measurement unavailable"}},
            {"item_id": "R3", "status": "output_failure"}]}],
            "output_failure_pairs": [{"ad_id": "ADV-test", "item_id": "R3", "reason": "invalid JSON"}]}
        path = output / "04_operational_results.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        self.bridge.links[bundle.review.review_id] = {"result_file": str(path)}
        app = create_app(self.settings, self.services)
        self.bridge.install(app)
        token, _, _ = self.services.auth.login(self.user.email, "test-password", "local", "test", "test")
        with TestClient(app) as client:
            headers = {"Authorization": f"Bearer {token}"}
            prefix = f"/operational/reviews/{bundle.review.review_id}"
            view = client.get(prefix + "/workspace", headers=headers)
            export = client.get(prefix + "/export.json", headers=headers)
        self.assertEqual(view.status_code, 200)
        self.assertEqual(export.status_code, 200)
        self.assertEqual(export.json()["results"], view.json()["rows"])
        self.assertEqual([r["verdict"] for r in view.json()["rows"]], ["미해당", "판단불가"])
        self.assertEqual(export.json()["execution"]["output_failure_count"], 1)
        self.assertEqual(export.json()["execution"]["output_failure_pairs"][0]["reason"], "invalid JSON")
        self.assertNotIn("source_ads", view.json())

    def test_layout_page_with_only_unassigned_lines_keeps_asset_identity(self):
        from test_operational_locations import source
        document = source()
        document["pages"][0]["regions"] = []
        value = parser_layout(document, source="test")
        page = value["pages"][0]
        self.assertEqual((page["asset_id"], page["source_page_no"]), ("FILE-b", 1))
        self.assertEqual(value["counts"]["lines"], 1)


if __name__ == "__main__":
    unittest.main()
