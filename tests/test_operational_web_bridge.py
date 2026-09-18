"""Provider-free adapter tests; these fixtures are never runtime judgments."""
import json
import sys
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import Mock, patch
import subprocess
import zipfile

import openpyxl
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from operational_web_bridge import (  # noqa: E402
    ExecutionBridge, FULL_REVIEW, PARSER_REUSE_PARENT_STATUSES,
    ReviewPaused, parser_layout, parser_runner_layout, registration_review_date,
)
from nh_ad_backend.domain import Advertisement, AdvertisementFile, User  # noqa: E402
from nh_ad_backend.main import build_services, create_app  # noqa: E402
from nh_ad_backend.security import current_user, hash_password  # noqa: E402
from nh_ad_backend.services import ServiceError  # noqa: E402
from nh_ad_backend.settings import Settings  # noqa: E402


class BridgeTests(unittest.TestCase):
    def test_registration_review_day_uses_korea_timezone_and_preserves_legacy_utc(self):
        for timestamp, day in (("2026-04-10T14:59:59+00:00", "2026-04-10"),
                               ("2026-04-10T15:00:00+00:00", "2026-04-11"),
                               ("2026-04-11T23:00:00+09:00", "2026-04-11"),
                               ("2026-04-10T15:00:00", "2026-04-11")):
            with self.subTest(timestamp=timestamp):
                self.assertEqual(registration_review_date(datetime.fromisoformat(timestamp)), day)

    def test_rerun_submit_uses_original_ad_registration_not_review_request(self):
        self.ad.created_at = datetime(2026, 4, 10, 15, tzinfo=UTC)
        for requested in (datetime(2026, 4, 12, tzinfo=UTC), datetime(2026, 5, 1, tzinfo=UTC)):
            bundle = self.request()
            bundle.review.requested_at = requested
            with patch.object(self.bridge, "stage"), \
                    patch.object(self.bridge, "wait_for_search_backend"), \
                    patch.object(self.bridge, "wait_for_judgment_backends"), \
                    patch.object(self.bridge, "parse", return_value={}), \
                    patch.object(self.bridge.rag, "submit", side_effect=RuntimeError("stop after capture")) as submit:
                self.bridge.run(bundle, {})
            self.assertEqual(submit.call_args.args[0]["review_date"], "2026-04-11")
            self.assertEqual(submit.call_args.args[0]["review_date_basis"], "advertisement_registration_date")

    def write_parser_pair(self, output, name, *, text="검토 원문", status="ok"):
        template = {"template_id": "예금성상품-적립식", "source": "user_provided"}
        first = {
            "reading_evidence_contract": {"version": "nh-ad-review-evidence-v6"},
            "doc_id": "DOC-test", "source_file": "input.pdf", "file_type": "pdf",
            "template": template,
            "pages": [{"page_no": 1, "parse_status": status, "regions": [{
                "region_id": "r1", "lines": [{"line_ref": "p1/r1/L1", "text": text}],
            }]}],
        }
        third = {
            "contract": {"version": "nh-ad-review-region-input-v1"},
            "document": {"doc_id": "DOC-test", "template": template},
            "pages": [{"page_no": 1, "regions": [{
                "region_id": "r1", "review_text": text, "line_refs": ["p1/r1/L1"],
            }]}],
        }
        paths = []
        for folder, data in (("evidence", first), ("review-input", third)):
            path = Path(output) / folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data), encoding="utf-8")
            paths.append(path)
        return paths

    def test_parser_pair_requires_text_but_not_geometry_or_complete_read(self):
        for text, status, accepted in (("원문", "ok", True), ("일부 원문", "partial", True),
                                       ("", "unreadable", False), (" \n", "ok", False)):
            with self.subTest(text=text, status=status):
                pair = self.write_parser_pair(self.root / "pair", "input.json", text=text, status=status)
                before = [path.read_bytes() for path in pair]
                if accepted:
                    document = self.bridge.read_parser_asset(*pair)
                    self.assertEqual(document["pages"][0]["regions"][0]["final_text"], text)
                    self.assertIsNone(document["pages"][0]["regions"][0]["bbox"])
                else:
                    with self.assertRaisesRegex(ValueError, "PARSER_INPUT_UNREADABLE"):
                        self.bridge.read_parser_asset(*pair)
                self.assertEqual(before, [path.read_bytes() for path in pair])

    def test_empty_or_invalid_pair_is_retryable_not_completed(self):
        self.bridge.parser_layout_config = parser_runner_layout({"parser_runner": "nh_ad_parser_cli"})
        output = self.root / "pair"
        source = self.root / "input.pdf"
        for invalid in ("empty", "json", "ownership", "unassigned_only"):
            with self.subTest(invalid=invalid):
                pair = self.write_parser_pair(output, "input.json", text="" if invalid == "empty" else "원문")
                if invalid == "json":
                    pair[1].write_text("{", encoding="utf-8")
                elif invalid == "ownership":
                    data = json.loads(pair[1].read_text(encoding="utf-8"))
                    data["pages"][0]["regions"][0]["line_refs"] = ["other"]
                    pair[1].write_text(json.dumps(data), encoding="utf-8")
                elif invalid == "unassigned_only":
                    for index, path in enumerate(pair):
                        data = json.loads(path.read_text(encoding="utf-8"))
                        page = data["pages"][0]
                        page["regions"] = []
                        page["unassigned_lines" if index == 0 else "unassigned_text"] = [
                            {"line_ref": "p1/unknown/L1", "text": "미배정 원문"}]
                        path.write_text(json.dumps(data), encoding="utf-8")
                completed, missing = self.bridge.parsed_assets(self.ad.files, {"FILE-test": source}, output)
                self.assertEqual(completed, {})
                self.assertIn("PARSER_INPUT_UNREADABLE", missing["FILE-test"])

    def test_empty_parent_parser_output_is_not_reused(self):
        self.bridge.parser_layout_config = parser_runner_layout({"parser_runner": "nh_ad_parser_cli"})
        parent = self.request()
        parent.job.status = "FAILED"
        parent_dir = self.bridge.root / "runs" / parent.review.review_id
        self.write_parser_pair(parent_dir / "parser", "input.json", text="", status="unreadable")
        (parent_dir / "parser-intake.json").write_text(
            json.dumps(self.bridge.parser_intake("예금성상품-적립식")), encoding="utf-8")
        current = self.root / "new-run"
        self.assertIsNone(self.bridge.reuse_parent_parser_output(
            self.ad, current, {"FILE-test": self.root / "input.pdf"}, parent.review.review_id,
            template_id="예금성상품-적립식"))
        self.assertFalse((current / "parser-reuse.json").exists())
        self.write_parser_pair(parent_dir / "parser", "input.json", text="정상 원문", status="partial")
        current.mkdir()
        self.assertIsNotNone(self.bridge.reuse_parent_parser_output(
            self.ad, current, {"FILE-test": self.root / "input.pdf"}, parent.review.review_id,
            template_id="예금성상품-적립식"))
        self.assertTrue((current / "parser-reuse.json").exists())

    def test_missing_or_changed_user_template_prevents_parent_parser_reuse(self):
        parent = self.request()
        parent.job.status = "COMPLETED"
        parent_dir = self.bridge.root / "runs" / parent.review.review_id
        parent_dir.mkdir(parents=True)
        current = self.root / "new-run"
        for manifest in (None, self.bridge.parser_intake("대출성상품-상품명 노출"),
                         {"version": "user-template-labeling-v1", "template_id": "예금성상품-적립식"},
                         {"version": "user-template-labeling-v2", "template_id": "예금성상품-적립식"},
                         {"version": "user-template-labeling-v3", "template_id": "예금성상품-적립식"},
                         {"version": "user-template-labeling-v4", "template_id": "예금성상품-적립식"},
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
        def template_cell(y, x, text):
            return (f'<tc><subList><p><run><t>{text}</t></run></p></subList>'
                    f'<cellAddr rowAddr="{y}" colAddr="{x}"/><cellSpan rowSpan="1" colSpan="1"/></tc>')
        template_xml = '<sec>'
        for title in (
            "예금성상품-적립식",
            "대출성상품-상품명 노출",
            "투자성상품-개인종합자산관리계좌(ISA) 일반",
        ):
            template_xml += f'<p><run><t>[{title}]</t></run></p><tbl rowCnt="2" colCnt="4">'
            for y, values in enumerate((("구분", "예시문구", "필수여부", "기재요령"),
                                        ("상품명", "일반상품", "O", "상품명 표시"))):
                template_xml += '<tr>' + ''.join(template_cell(y, x, value) for x, value in enumerate(values)) + '</tr>'
            template_xml += '</tbl>'
        with zipfile.ZipFile(self.root / "template.hwpx", "w") as archive:
            archive.writestr("Contents/section0.xml", template_xml + '</sec>')
        (self.root / "config.json").write_text(json.dumps({
            "template_source_path": str(self.root / "template.hwpx"),
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

    def test_process_shutdown_persists_review_for_same_id_resume(self):
        bundle = self.request()
        with patch.object(self.bridge, "stage", side_effect=ReviewPaused("SERVER_STOPPED")):
            self.bridge.run(bundle, {})
        self.assertEqual(bundle.review.status, "ANALYSIS_REQUESTED")
        self.assertEqual(bundle.job.status, "RETRY_PENDING")
        self.assertIsNone(bundle.job.failed_reason_code)
        self.assertEqual(self.ad.review_status, "ANALYSIS_REQUESTED")
        self.assertEqual(
            self.bridge.links[bundle.review.review_id]["pause_reason"],
            "SERVER_STOPPED",
        )

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
        self.write_parser_pair(batch_output, first_output_name)
        completed, missing = self.bridge.parsed_assets(self.ad.files, sources, batch_output)
        self.assertEqual(set(completed), {"FILE-test"})
        self.assertEqual(set(missing), {"FILE-second"})

        def write_retry_output(retry_source, retry_output, log_path, *, template_id=None):
            self.assertEqual(template_id, "대출성상품-상품명 노출")
            source = next(Path(retry_source).iterdir())
            self.write_parser_pair(retry_output, f"{source.stem}.json")
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
            self.write_parser_pair(asset_output, f"{source.stem}.json")
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

    def test_delete_terminal_review_preserves_ad_and_restores_previous_round(self):
        first = self.request()
        first.job.status = "COMPLETED"
        first.review.status = "REVIEW_COMPLETED"
        self.bridge.active.discard(first.review.review_id)
        second = self.request()
        second.job.status = "FAILED"
        second.review.status = "REVIEW_FAILED"
        self.bridge.active.discard(second.review.review_id)
        run_dir = self.bridge.root / "runs" / second.review.review_id
        rag_dir = self.bridge.root / "rag-jobs" / "rag-delete"
        run_dir.mkdir(parents=True)
        rag_dir.mkdir(parents=True)
        self.bridge.links[second.review.review_id] = {"rag_job_id": "rag-delete"}
        self.bridge.decisions[second.review.review_id] = {"decision": "REJECTED"}
        self.bridge.persist()

        advertisement_id = self.bridge.delete_review(self.actor, second.review.review_id)

        self.assertEqual(advertisement_id, self.ad.advertisement_id)
        self.assertIsNone(self.services.reviews.repository.get(second.review.review_id))
        self.assertIsNotNone(self.services.reviews.repository.get(first.review.review_id))
        self.assertEqual(self.ad.latest_review_id, first.review.review_id)
        self.assertEqual(self.ad.review_status, "REVIEW_COMPLETED")
        self.assertNotIn(second.review.review_id, self.bridge.links)
        self.assertNotIn(second.review.review_id, self.bridge.decisions)
        self.assertFalse(run_dir.exists())
        self.assertFalse(rag_dir.exists())

    def test_delete_review_rejects_active_job_and_unprivileged_actor(self):
        bundle = self.request()
        with self.assertRaises(ServiceError) as active:
            self.bridge.delete_review(self.actor, bundle.review.review_id)
        self.assertEqual(active.exception.code, "REVIEW_IN_PROGRESS")
        bundle.job.status = "FAILED"
        self.bridge.active.discard(bundle.review.review_id)
        user = User("product", "product", "product@localhost", hash_password("test-password"),
                    "DPT-T", "Test", ("PRODUCT_DEPARTMENT_USER",))
        self.services.repository.users[user.user_id] = user
        with self.assertRaises(ServiceError) as denied:
            self.bridge.delete_review(current_user(user), bundle.review.review_id)
        self.assertEqual(denied.exception.code, "FORBIDDEN")
        self.assertIsNotNone(self.services.reviews.repository.get(bundle.review.review_id))

    def test_delete_latest_review_uses_newest_round_for_advertisement_list(self):
        first = self.request()
        first.job.status = "COMPLETED"
        first.review.status = "REVIEW_COMPLETED"
        self.bridge.active.discard(first.review.review_id)
        second = self.request()
        second.job.status = "FAILED"
        second.review.status = "REVIEW_FAILED"
        self.bridge.active.discard(second.review.review_id)

        advertisement_id = self.bridge.delete_latest_review(self.actor, self.ad.advertisement_id)

        self.assertEqual(advertisement_id, self.ad.advertisement_id)
        self.assertIsNone(self.services.reviews.repository.get(second.review.review_id))
        self.assertIsNotNone(self.services.reviews.repository.get(first.review.review_id))

    def test_delete_latest_review_http_route_passes_scoped_write_guard(self):
        app = create_app(self.settings, self.services)
        self.bridge.install(app)
        bundle = self.request()
        bundle.job.status = "FAILED"
        bundle.review.status = "REVIEW_FAILED"
        self.bridge.active.discard(bundle.review.review_id)
        with TestClient(app) as client:
            path = f"/operational/advertisements/{self.ad.advertisement_id}/latest-review"
            self.assertEqual(client.delete(path).status_code, 401)
            token, _, _ = self.services.auth.login(
                self.user.email, "test-password", "local", "test", "test"
            )
            response = client.delete(path, headers={"Authorization": f"Bearer {token}"})

        self.assertEqual(response.status_code, 204)
        self.assertIsNone(self.services.reviews.repository.get(bundle.review.review_id))
        self.assertEqual(self.ad.review_status, "UPLOADED")

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

    def test_restart_resumes_interrupted_job_and_preserves_upload(self):
        bundle = self.request()
        self.bridge.stage(bundle, 1)
        state = json.loads((self.root / "state" / "execution" / "web-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["version"], 3)
        self.assertNotIn("results", state)
        self.assertTrue((self.root / "state" / "execution" / "web-results.json").is_file())
        other = build_services(self.settings)
        with patch.object(ExecutionBridge, "run") as run:
            restored = ExecutionBridge(other, self.root / "state", self.root / "config.json", Mock())
            restored.pool.shutdown(wait=True)
        run.assert_called_once()
        self.addCleanup(restored.pool.shutdown, wait=True)
        self.addCleanup(restored.rag.executor.shutdown, wait=True)
        value = other.reviews.repository.get(bundle.review.review_id)
        self.assertEqual(value.job.status, "RUNNING")
        self.assertEqual(value.review.status, "ANALYZING")
        self.assertEqual(other.repository.get_advertisement("ADV-test").files[0].checksum, "abc")

    def test_restart_recovers_review_failed_by_legacy_connection_timeout(self):
        bundle = self.request()
        self.bridge.stage(bundle, 0)
        self.bridge.fail(
            bundle,
            "OPERATIONAL_EXECUTION_FAILED",
            "SEARCH_CONNECTION_UNAVAILABLE: search tunnel was offline",
        )
        other = build_services(self.settings)
        with patch.object(ExecutionBridge, "run") as run:
            restored = ExecutionBridge(
                other, self.root / "state", self.root / "config.json", Mock()
            )
            restored.pool.shutdown(wait=True)
        run.assert_called_once()
        self.addCleanup(restored.pool.shutdown, wait=True)
        self.addCleanup(restored.rag.executor.shutdown, wait=True)
        value = other.reviews.repository.get(bundle.review.review_id)
        self.assertEqual(value.job.status, "RETRY_PENDING")
        self.assertEqual(value.review.status, "ANALYSIS_REQUESTED")
        self.assertIsNone(value.job.failed_reason_code)
        self.assertTrue(
            restored.links[bundle.review.review_id][
                "recovered_transient_connection_failure"
            ]
        )

    def test_process_restart_reuses_same_review_parser_output_after_validation(self):
        template_id = "예금성상품-적립식"
        body = b"immutable-source"
        original = self.ad.files[0]
        self.ad.files[0] = AdvertisementFile(
            original.file_id,
            original.file_type,
            original.original_file_name,
            original.storage_key,
            original.mime_type,
            original.file_size,
            __import__("hashlib").sha256(body).hexdigest(),
        )
        directory = self.root / "resume-run"
        source = directory / "source" / "FILE-test_input.pdf"
        source.parent.mkdir(parents=True)
        source.write_bytes(body)
        integrated = {"document": {"ad_id": self.ad.advertisement_id}, "saved": True}
        (directory / "integrated.json").write_text(json.dumps(integrated), encoding="utf-8")
        (directory / "parser-intake.json").write_text(
            json.dumps(self.bridge.parser_intake(template_id)), encoding="utf-8"
        )
        with patch("operational_web_bridge.validate_integrated_input"), patch.object(
            self.bridge, "parser_command", return_value=["parser"]
        ), patch.object(self.bridge, "execute_parser") as execute:
            resumed = self.bridge.parse(
                self.ad, directory, template_id=template_id
            )
        self.assertEqual(resumed, integrated)
        execute.assert_not_called()

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
            self.assertEqual(capabilities["sourcePolicy"], "template-plus-v2")
            self.assertEqual(capabilities["regulation"], "내부 심의 템플릿 + 규제목록 v2")
            self.assertEqual(
                {row["label"] for row in capabilities["productClassifications"]},
                {
                    "예금성상품-적립식",
                    "대출성상품-상품명 노출",
                    "투자성상품-개인종합자산관리계좌(ISA) 일반",
                },
            )
            investment = next(
                row for row in capabilities["productClassifications"]
                if row["label"].startswith("투자성상품-")
            )
            self.assertEqual(investment["productGroup"], "INVESTMENT")
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
        with patch.object(self.bridge, "wait_for_search_backend"), patch.object(
            self.bridge, "wait_for_judgment_backends"
        ):
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

    def test_complete_rendered_line_projection_becomes_a_structural_observation(self):
        document = {
            "diagnostics": {"asset_pages": {"FILE-one": {"start": 1, "end": 1}}},
            "pages": [{"page_no": 1, "regions": [{"lines": [
                {"line_ref": "FILE-one::L1", "text": "첫 유의사항", "bbox": None},
                {"line_ref": "FILE-one::L2", "text": "둘째 유의사항", "bbox": None},
            ]}], "unassigned_lines": []}],
        }
        layout = {
            "source": "HWP 200-DPI render + parser visual projection",
            "pages": [{"page_no": 1, "canvas_w": 100, "canvas_h": 100,
                "regions": [{"lines": [
                    {"text": "첫 유의사항", "bbox": [1, 1, 80, 10]},
                    {"text": "둘째 유의사항", "bbox": [1, 20, 80, 30]},
                ]}]}],
        }

        self.bridge.attach_rendered_line_observation(document, layout)

        self.assertEqual(document["diagnostics"]["rendered_line_projection"], {
            "verified": True, "method": "EXACT_RENDERED_TEXT",
            "semantic_line_count": 2, "rendered_line_count": 2,
        })

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
        self.assertEqual([r["verdict"] for r in view.json()["rows"]], ["판단불가"])
        self.assertEqual([r['verdict'] for r in view.json()['excluded_rows']], ['미해당'])
        self.assertEqual(export.json()['excluded_rows'], view.json()['excluded_rows'])
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

    def test_preview_raw_unassigned_line_without_canonical_reference_is_display_only(self):
        from test_operational_locations import source
        document = source()
        document['pages'][0]['regions'] = []
        line = document['pages'][0]['unassigned_lines'][0]
        line.pop('line_ref')
        value = parser_layout(document, source='visual-only')
        projected = value['pages'][0]['regions'][0]['lines'][0]
        self.assertIsNone(projected['line_ref'])
        self.assertEqual(projected['bbox'], line['bbox'])
        self.assertEqual(value['counts']['lines'], 1)

    def test_optional_preview_failure_preserves_semantic_input(self):
        from unittest.mock import patch
        document = {'semantic': 'preserved'}
        with patch.object(self.bridge, 'prepare_parser_layout', side_effect=KeyError('line_ref')):
            self.assertIsNone(self.bridge.prepare_optional_parser_layout(Path('source.hwp'), self.root, document))
        self.assertEqual(document, {'semantic': 'preserved'})
        self.assertEqual(json.loads((self.root/'parser-layout-error.json').read_text(encoding='utf8'))['code'],
                         'PARSER_LAYOUT_UNAVAILABLE')


if __name__ == "__main__":
    unittest.main()
