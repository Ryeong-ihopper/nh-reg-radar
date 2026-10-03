"""Provider-free adapter tests; these fixtures are never runtime judgments."""
import hashlib
import json
import os
import sys
import tempfile
import unittest
from dataclasses import replace
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
    ReviewPaused, parser_fin_output_stem, parser_layout, parser_runner_layout, registration_review_date,
    with_parser_defaults,
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

    @staticmethod
    def parser_fin_pair(*, text="검토 원문", status="ok"):
        """Minimal synthetic parser-pipeline P1 v6/P3 v11 pair."""
        template = {"template_id": "예금성상품-적립식", "source": "user_provided"}
        box = [20, 40, 600, 120]
        first = {
            "contract": {"version": "nh-ad-parse-evidence-v6"},
            "doc_id": "DOC-test", "source_file": "input.pdf", "file_type": "pdf",
            "template": template,
            "pages": [{"page_no": 1, "canvas": [1200, 1800], "parse_route": "ocr", "parse_status": status,
                       "regions": [{"region_id": "p1_r001", "product_id": "product_1", "bbox": box,
                                    "lines": [{"line_ref": "p1/r1/L1", "text": text,
                                               "bbox": [25, 45, 580, 90], "source": "ocr"}]}],
                       "unassigned_lines": []}],
        }
        third = {
            "contract": {"version": "nh-ad-region-review-input-v11",
                         "source_evidence_version": "nh-ad-parse-evidence-v6"},
            "document": {"doc_id": "DOC-test", "source_file": "input.pdf", "file_type": "pdf",
                         "template": template},
            "review_units": [{"product_id": "product_1", "region_ids": ["p1_r001"]}],
            "pages": [{"page_no": 1, "canvas": [1200, 1800], "regions": [{
                "region_id": "p1_r001", "product_id": "product_1", "bbox": box, "selected_text": text,
                "labels": [], "kind": "text", "needs_review": False, "text_source": "ocr",
            }]}],
        }
        return first, third

    def write_parser_pair(self, output, source_name, *, text="검토 원문", status="ok"):
        """Write the pair where parser-pipeline's --compact-output puts it for source_name."""
        stem = parser_fin_output_stem(Path(source_name))
        paths = []
        for suffix, data in zip((".p1.json", ".p3.json"), self.parser_fin_pair(text=text, status=status)):
            path = Path(output) / "final" / (stem + suffix)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            paths.append(path)
        return paths

    def test_parser_pair_requires_text_but_not_complete_read(self):
        for text, status, accepted in (("원문", "ok", True), ("일부 원문", "partial", True),
                                       ("", "unreadable", False), (" \n", "ok", False)):
            with self.subTest(text=text, status=status):
                pair = self.write_parser_pair(self.root / "pair", "input.pdf", text=text, status=status)
                before = [path.read_bytes() for path in pair]
                if accepted:
                    document = self.bridge.read_parser_asset(*pair)
                    self.assertEqual(document["pages"][0]["regions"][0]["final_text"], text)
                    self.assertEqual(document["pages"][0]["regions"][0]["bbox"], [20, 40, 600, 120])
                else:
                    with self.assertRaisesRegex(ValueError, "PARSER_INPUT_UNREADABLE"):
                        self.bridge.read_parser_asset(*pair)
                self.assertEqual(before, [path.read_bytes() for path in pair])

    def test_empty_or_invalid_pair_is_retryable_not_completed(self):
        output = self.root / "pair"
        source = self.root / "input.pdf"
        for invalid in ("empty", "json", "ownership", "unassigned_only"):
            with self.subTest(invalid=invalid):
                pair = self.write_parser_pair(output, source.name, text="" if invalid == "empty" else "원문")
                if invalid == "json":
                    pair[1].write_text("{", encoding="utf-8")
                elif invalid == "ownership":
                    data = json.loads(pair[1].read_text(encoding="utf-8"))
                    data["pages"][0]["regions"][0]["product_id"] = "product_2"
                    pair[1].write_text(json.dumps(data), encoding="utf-8")
                elif invalid == "unassigned_only":
                    for index, path in enumerate(pair):
                        data = json.loads(path.read_text(encoding="utf-8"))
                        page = data["pages"][0]
                        page["regions"] = []
                        if index == 0:
                            page["unassigned_lines"] = [{"line_ref": "p1/u/L1", "text": "미배정 원문",
                                                         "bbox": [20, 1700, 300, 1750], "source": "ocr"}]
                        else:
                            data["review_units"] = [{"product_id": "product_1", "region_ids": []}]
                        path.write_text(json.dumps(data), encoding="utf-8")
                completed, missing = self.bridge.parsed_assets(self.ad.files, {"FILE-test": source}, output)
                self.assertEqual(completed, {})
                self.assertIn("PARSER_INPUT_UNREADABLE", missing["FILE-test"])

    def test_empty_parent_parser_output_is_not_reused(self):
        parent = self.request()
        parent.job.status = "FAILED"
        parent_dir = self.bridge.root / "runs" / parent.review.review_id
        self.write_parser_pair(parent_dir / "parser", "input.pdf", text="", status="unreadable")
        (parent_dir / "parser-intake.json").write_text(
            json.dumps(self.bridge.parser_intake("예금성상품-적립식")), encoding="utf-8")
        current = self.root / "new-run"
        self.assertIsNone(self.bridge.reuse_parent_parser_output(
            self.ad, current, {"FILE-test": self.root / "input.pdf"}, parent.review.review_id,
            template_id="예금성상품-적립식"))
        self.assertFalse((current / "parser-reuse.json").exists())
        self.write_parser_pair(parent_dir / "parser", "input.pdf", text="정상 원문", status="partial")
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
                         {"version": "user-template-labeling-v5", "template_id": "예금성상품-적립식"},
                         # v6 outputs were labelled with a parser-chosen template.
                         {**self.bridge.parser_intake("예금성상품-적립식"), "version": "user-template-labeling-v6"},
                         {"version": "old-policy", "template_id": "예금성상품-적립식"}):
            if manifest is not None:
                (parent_dir / "parser-intake.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.subTest(manifest=manifest):
                self.assertIsNone(self.bridge.reuse_parent_parser_output(
                    self.ad, current, {}, parent.review.review_id, template_id="예금성상품-적립식"))
        self.assertFalse((current / "parser-reuse.json").exists())

    def test_parser_must_echo_the_user_template_in_both_outputs(self):
        template = {"template_id": "예금성상품-적립식", "source": "user_provided"}
        for bad in ({**template, "source": "rules"}, {**template, "source": "vlm"},
                    {**template, "template_id": "대출성상품-상품명 노출"}):
            for index in (0, 1):
                with self.subTest(bad=bad, output="P1" if index == 0 else "P3"):
                    pair = self.write_parser_pair(self.root / "pair", "input.pdf")
                    self.bridge.validate_parser_template(*pair, "예금성상품-적립식")
                    data = json.loads(pair[index].read_text(encoding="utf-8"))
                    if index == 0:
                        data["template"] = bad
                    else:
                        data["document"]["template"] = bad
                    pair[index].write_text(json.dumps(data), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "PARSER_TEMPLATE_MISMATCH"):
                        self.bridge.validate_parser_template(*pair, "예금성상품-적립식")

    def test_app_template_name_is_translated_to_the_parser_catalog(self):
        self.bridge.config.update({"parser_python": "python"})
        eld = "예금성상품-지수연동예금(ELD)"
        command = self.bridge.parser_command(self.root, self.root / "out", template_id=eld)
        self.assertEqual(command[-2:], ["--template-id", "예금성상품-지수연동예금"])
        self.assertEqual(self.bridge.parser_intake(eld)["parser_template_id"], "예금성상품-지수연동예금")
        pair = self.write_parser_pair(self.root / "eld", "input.pdf")
        for path, key in zip(pair, ("template", "document")):
            data = json.loads(path.read_text(encoding="utf-8"))
            parent = data if key == "template" else data["document"]
            parent["template"] = {"template_id": "예금성상품-지수연동예금", "source": "user_provided"}
            path.write_text(json.dumps(data), encoding="utf-8")
        self.bridge.validate_parser_template(*pair, eld)

    def test_template_missing_from_parser_catalog_falls_back_to_parser_choice(self):
        catalog = self.root / "parser-pipeline" / "nh_parser_fin" / "templates" / "ad_templates.json"
        catalog.parent.mkdir(parents=True)
        catalog.write_text(json.dumps({"templates": {"예금성상품-적립식": {}, "예금성상품-지수연동예금": {}}},
                                      ensure_ascii=False), encoding="utf-8")
        self.bridge.config.update({"parser_python": "python"})
        for template, expected in (("예금성상품-적립식", "예금성상품-적립식"),
                                   ("예금성상품-지수연동예금(ELD)", "예금성상품-지수연동예금"),
                                   ("투자성상품-ETF", None), ("투자성상품-ELB", None)):
            with self.subTest(template=template):
                command = self.bridge.parser_command(self.root, self.root / "out", template_id=template)
                self.assertEqual(command[-1] if expected else None, expected)
                self.assertEqual("--template-id" in command, expected is not None)
                self.assertEqual(self.bridge.parser_intake(template)["parser_template_id"], expected)
        # The parser's own choice is accepted when P1 and P3 agree.
        pair = self.write_parser_pair(self.root / "etf", "input.pdf")
        for path, key in zip(pair, ("template", "document")):
            data = json.loads(path.read_text(encoding="utf-8"))
            parent = data if key == "template" else data["document"]
            parent["template"] = {"template_id": "투자성상품-퇴직연금 일반", "source": "vlm"}
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.bridge.validate_parser_template(*pair, "투자성상품-ETF")
        with self.assertRaisesRegex(ValueError, "PARSER_TEMPLATE_MISMATCH"):
            self.bridge.validate_parser_template(*pair, "예금성상품-적립식")
        data = json.loads(pair[1].read_text(encoding="utf-8"))
        data["document"]["template"] = {"template_id": "투자성상품-펀드", "source": "vlm"}
        pair[1].write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "PARSER_TEMPLATE_MISMATCH"):
            self.bridge.validate_parser_template(*pair, "투자성상품-ETF")
        with patch("operational_web_bridge.subprocess.run", return_value=Mock(returncode=0)):
            self.bridge.execute_parser(self.root, self.root / "out", self.root / "etf.log", template_id="투자성상품-ETF")
        self.assertIn("PARSER_TEMPLATE_AUTO", (self.root / "etf.log").read_text(encoding="utf-8"))

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
            "vector_cache_dir": str(self.root / "vector-cache"),
            # Hermetic: never pick up a developer's parser-pipeline/.venv.
            "parser_root": str(self.root / "parser-pipeline"),
            "parser_revision": "a" * 40,
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

    def test_failed_idempotent_rag_job_is_retried_for_same_review_id(self):
        rag = Mock()
        rag.submit.return_value = {
            "job_id": "RAG-existing",
            "status": "FAILED",
            "idempotent_replay": True,
        }
        rag.retry.return_value = {"job_id": "RAG-existing", "status": "QUEUED"}
        self.bridge.rag = rag

        job = self.bridge.submit_rag({"client_request_id": "REV-existing"})

        self.assertEqual(job["status"], "QUEUED")
        rag.retry.assert_called_once_with("RAG-existing")

    def test_completed_idempotent_rag_job_is_reused_without_retry(self):
        rag = Mock()
        rag.submit.return_value = {
            "job_id": "RAG-existing",
            "status": "COMPLETED",
            "idempotent_replay": True,
        }
        self.bridge.rag = rag

        job = self.bridge.submit_rag({"client_request_id": "REV-existing"})

        self.assertEqual(job["status"], "COMPLETED")
        rag.retry.assert_not_called()

    def test_in_repo_parser_is_the_only_runner(self):
        for config in ({}, {"parser_runner": "nh_parser_fin", "parser_contract_profile": "region-v11"}):
            layout = parser_runner_layout(config)
            self.assertEqual((layout["runner"], layout["p1_dir"], layout["p3_dir"], layout["contract_profile"]),
                             ("nh_parser_fin", "final", "final", "region-v11"))
        for runner in ("nh_parsing_test_batch", "nh_ad_parser_cli", "unknown"):
            with self.subTest(runner=runner), self.assertRaisesRegex(ValueError, "unsupported parser_runner"):
                parser_runner_layout({"parser_runner": runner})
        # Older profiles stay readable by the adapter but are never produced by a new run.
        for profile in ("region-v6", "region-v9", "region-v10", "guess-latest"):
            with self.subTest(profile=profile), self.assertRaisesRegex(ValueError, "unsupported parser_contract_profile"):
                parser_runner_layout({"parser_contract_profile": profile})

    def test_parser_paths_default_to_parser_pipeline_but_private_config_wins(self):
        defaults = with_parser_defaults({})
        self.assertEqual(Path(defaults["parser_root"]), ROOT / "parser-pipeline")
        self.assertEqual(defaults["parser_cwd"], defaults["parser_root"])
        venv = self.root / "parser-pipeline" / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        self.assertNotIn("parser_python", with_parser_defaults({"parser_root": str(self.root / "parser-pipeline")}))
        venv.parent.mkdir(parents=True)
        venv.write_bytes(b"")
        self.assertEqual(with_parser_defaults({"parser_root": str(self.root / "parser-pipeline")})["parser_python"],
                         str(venv))
        private = {"parser_root": "/opt/nh-parser", "parser_cwd": "/work", "parser_python": "/opt/python/bin/python"}
        self.assertEqual(with_parser_defaults(dict(private)), private)

    def test_parser_timeout_and_start_error_reach_asset_retry(self):
        self.bridge.config["parser_cwd"] = str(self.root)
        self.bridge.parser_command = Mock(return_value=["test-parser"])
        for error, code in [(subprocess.TimeoutExpired("test-parser", 3600), 124),
                            (OSError("test launch failure"), 126)]:
            with self.subTest(code=code), patch("operational_web_bridge.subprocess.run", side_effect=error):
                log = self.root / "failure.log"
                self.assertEqual(self.bridge.execute_parser(self.root, self.root, log), code)
                self.assertIn("PARSER_", log.read_text(encoding="utf-8"))

    def test_parser_command_uses_absolute_bridge_paths(self):
        parser_root = self.root / "parser"
        parser_root.mkdir()
        self.bridge.config.update({"parser_root": str(parser_root), "parser_python": "python"})

        command = self.bridge.parser_command(Path("relative-source"), Path("relative-output"), template_id="대출성상품-상품명 노출")

        self.assertEqual(command[1], "-u")
        self.assertTrue(Path(command[2]).is_absolute())
        self.assertTrue(Path(command[4]).is_absolute())
        self.assertEqual(command[3], "--input")
        self.assertEqual(command[5:], ["--run-name", "relative-output", "--compact-output",
                                       "--template-id", "대출성상품-상품명 노출"])
        self.assertNotIn("--template-id", self.bridge.parser_command(Path("s"), Path("o")))

    def test_parser_fin_command_and_output_pairing(self):
        parser_root = self.root / "parser-fin"
        parser_root.mkdir()
        self.bridge.config.update({"parser_root": str(parser_root), "parser_python": "python"})
        source, output = self.root / "source", self.root / "parser-output"
        command = self.bridge.parser_command(source, output, template_id="예금성상품-입출식")
        self.assertEqual(command[1:3], ["-u", str((parser_root / "run.py").resolve())])
        self.assertEqual(command[-5:], ["--run-name", "parser-output", "--compact-output",
                                        "--template-id", "예금성상품-입출식"])
        final = output / "final"
        final.mkdir(parents=True)
        (final / "ad_file.png.p1.json").write_text("{}", encoding="utf-8")
        (final / "ad_file.png.p3.json").write_text("{}", encoding="utf-8")
        p1s, p3s = self.bridge.parser_outputs(output)
        self.assertEqual([p.name for p in p1s], ["ad_file.png.p1.json"])
        self.assertEqual([p.name for p in p3s], ["ad_file.png.p3.json"])
        self.assertTrue(self.bridge.parser_output_name_matches(p1s[0], Path("ad file.png")))
        self.assertTrue(self.bridge.parser_p3_matches(p1s[0], p3s[0]))

    def test_native_hwp_never_assigns_logical_page_to_physical_scope(self):
        document = {"document": {}, "diagnostics": {"asset_pages": {"FILE-test": {"start": 1, "end": 1}}},
                    "pages": [{"page_no": 1, "parse_route": "native_hwp", "regions": [
                        {"evidence_id": "ADV-test#asset:FILE-test:p1:r1"}]}]}
        intake = {"schema_version": "operational-ad-intake-v1", "advertisement_name": "test", "media_codes": ["NOTICE"],
                  "assets": [{"asset_id": "FILE-test", "file_name": "input.hwp"}],
                  "products": [{"product_id": "P-1", "product_name": "test", "product_group": "예금성",
                                "product_classification_code": "예금성상품-적립식",
                                "asset_scopes": [{"asset_id": "FILE-test", "page_ranges": [{"start": 1, "end": 1}]}]}],
                  "shared_asset_scopes": [], "follow_up": None}
        with self.assertRaisesRegex(ValueError, "HWP_PHYSICAL_SCOPE_UNAVAILABLE"):
            self.bridge.apply_intake_scopes(self.ad, document, intake)

    def test_hwp_runs_through_parser_pipeline_once_and_pins_reuse(self):
        self.bridge.config.update(parser_python='python', parser_root=str(self.root), parser_cwd=str(self.root))
        source = self.root/'current-source'
        source.mkdir()
        (source/'input.hwp').write_bytes(b'test input')
        output = self.root/'output'
        with patch('operational_web_bridge.subprocess.run', return_value=Mock(returncode=0)) as run:
            self.assertEqual(self.bridge.execute_parser(source,output,self.root/'current.log',
                                                        template_id='예금성상품-적립식'),0)
        self.assertEqual(run.call_count,1)
        self.assertTrue(run.call_args.args[0][2].endswith('run.py'))
        self.assertEqual(run.call_args.kwargs['env']['HWP_RENDER_DIR'],str(output/'render'))
        self.assertEqual(run.call_args.kwargs['env']['NH_OUTPUT_ROOT'],str(output.resolve().parent))
        intake = self.bridge.parser_intake('예금성상품-적립식')
        self.assertEqual(intake['version'],'user-template-labeling-v7')
        self.assertIn('--template-id', run.call_args.args[0])
        self.assertEqual(intake['parser_revision'],'a'*40)
        self.bridge.config['parser_revision']='b'*40
        self.assertNotEqual(intake,self.bridge.parser_intake('예금성상품-적립식'))
        self.bridge.config.pop('parser_revision')
        with self.assertRaisesRegex(ValueError,'PARSER_REVISION_REQUIRED'):
            self.bridge.parser_intake('예금성상품-적립식')

    def test_parser_v11_profile_pins_revision_and_rejects_old_pair(self):
        self.assertEqual(self.bridge.parser_intake('template')['parser_contract_profile'], 'region-v11')
        first, third = self.write_parser_pair(self.root/'v11-pair', 'ad.pdf')
        self.bridge.validate_parser_template(first, third, '예금성상품-적립식')
        for old in (('nh-ad-parse-evidence-v5', 'nh-ad-region-review-input-v10'),
                    ('nh-ad-parse-evidence-v4', 'nh-ad-region-review-input-v9'),
                    ('nh-ad-review-evidence-v6', 'nh-ad-review-region-input-v1')):
            with self.subTest(old=old):
                for path, version in zip((first, third), old):
                    data = json.loads(path.read_text(encoding='utf-8'))
                    data['contract']['version'] = version
                    path.write_text(json.dumps(data), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'PARSER_CONTRACT_MISMATCH'):
                    self.bridge.validate_parser_template(first, third, '예금성상품-적립식')

    def test_parser_v10_page_preview_is_review_owned_canvas_bound_and_hash_verified(self):
        self.test_parser_page_preview_is_review_owned_canvas_bound_and_hash_verified('nh-ad-region-review-input-v10')

    def test_parser_v11_page_preview_is_review_owned_canvas_bound_and_hash_verified(self):
        self.test_parser_page_preview_is_review_owned_canvas_bound_and_hash_verified('nh-ad-region-review-input-v11')

    def test_parser_page_preview_is_review_owned_canvas_bound_and_hash_verified(self, version='nh-ad-region-review-input-v9'):
        from PIL import Image
        file=self.ad.files[0]
        bundle=self.request()
        directory=self.bridge.root/'runs'/bundle.review.review_id
        directory.mkdir(parents=True,exist_ok=True)
        output=directory/'parser-initial'/file.file_id/'output'
        (output/'final').mkdir(parents=True)
        (output/'images').mkdir()
        Image.new('RGB',(30,40),'white').save(output/'images'/'render.png')
        p1=output/'final'/'input.p1.json'
        p3=output/'final'/'input.p3.json'
        p1.write_text(json.dumps({'source_file':'input.hwp','pages':[{'page_no':1,'canvas':[30,40]}]}),encoding='utf-8')
        p3.write_text(json.dumps({'contract':{'version':version}}),encoding='utf-8')
        (output/'media-index.json').write_text(json.dumps([{'source_file':'input.hwp','page_no':1,'image_name':'render.png'}]))
        self.bridge.capture_parser_page_images(file,p1,p3,directory)
        integrated={'pages':[{'page_no':1,'asset_id':file.file_id,'source_page_no':1,'canvas_w':30,'canvas_h':40}],
                    'diagnostics':{'assets':[{'file_id':file.file_id,
                       'p1_sha256':hashlib.sha256(p1.read_bytes()).hexdigest(),
                       'p3_sha256':hashlib.sha256(p3.read_bytes()).hexdigest(),
                       'source_parser_contracts':{'source_p3_contract':version}}]}}
        (directory/'integrated.json').write_text(json.dumps(integrated))
        image=self.bridge.parser_page_image(bundle.review.review_id,1)
        self.assertEqual(image.read_bytes(),(output/'images'/'render.png').read_bytes())
        layout=self.bridge.with_parser_preview_paths(bundle.review.review_id, {'pages':integrated['pages']},integrated)
        self.assertIn('/parser-page/1',layout['pages'][0]['preview_path'])
        app=create_app(self.settings,self.services)
        self.bridge.install(app)
        token,_,_=self.services.auth.login(self.user.email,'test-password','local','test','test')
        with TestClient(app) as client:
            path=f'/operational/reviews/{bundle.review.review_id}/parser-page/1'
            self.assertEqual(client.get(path).status_code,401)
            response=client.get(path,headers={'Authorization':f'Bearer {token}'})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.content,image.read_bytes())
            self.assertEqual(response.headers['content-type'],'image/png')
        image.write_bytes(b'changed bytes')
        with self.assertRaises(ServiceError) as changed:
            self.bridge.parser_page_image(bundle.review.review_id,1)
        self.assertEqual(changed.exception.code,'PARSER_PAGE_MISMATCH')

    def test_hwp_html_is_authenticated_owned_hash_bound_and_static(self):
        from operational_hwp_html import static_hwp_html
        self.ad.files[0] = replace(self.ad.files[0], original_file_name='input.hwp')
        file = self.ad.files[0]
        bundle = self.request()
        directory = self.bridge.root / 'runs' / bundle.review.review_id
        raw = b'<html><head><meta http-equiv="refresh" content="0;url=https://outside.invalid"></head><body><p onclick="alert(1)">review text</p><script>fetch("https://outside.invalid")</script><img src="https://outside.invalid/a.png"><a href="javascript:alert(1)">link</a></body></html>'
        self.bridge.save_hwp_html(file,raw,directory,basis='PARSER_AUTHORED_HTML')
        html = self.bridge.hwp_review_html(bundle.review.review_id,file.file_id)
        self.assertIn('review text',html)
        self.assertNotIn('<script',html)
        self.assertNotIn('onclick',html)
        self.assertNotIn('outside.invalid',html)
        self.assertNotIn('javascript:',html)
        self.assertIn("script-src &#x27;none&#x27;",html)
        self.assertIn('text',static_hwp_html('<p>text</p>'))
        with self.assertRaises(ServiceError) as wrong:
            self.bridge.hwp_review_html(bundle.review.review_id,'FILE-other')
        self.assertEqual(wrong.exception.status_code,404)
        app=create_app(self.settings,self.services)
        self.bridge.install(app)
        token,_,_=self.services.auth.login(self.user.email,'test-password','local','test','test')
        path=f'/operational/reviews/{bundle.review.review_id}/hwp-html/{file.file_id}'
        with TestClient(app) as client:
            self.assertEqual(client.get(path).status_code,401)
            response=client.get(path,headers={'Authorization':f'Bearer {token}'})
            self.assertEqual(response.status_code,200)
            self.assertIn('text/html',response.headers['content-type'])
            self.assertIn("script-src 'none'",response.headers['content-security-policy'])
        (directory/'hwp-html'/f'{file.file_id}.html').write_bytes(b'changed')
        with self.assertRaises(ServiceError) as changed:
            self.bridge.hwp_review_html(bundle.review.review_id,file.file_id)
        self.assertEqual(changed.exception.code,'HWP_HTML_MISMATCH')

    def test_hwp_html_for_past_review_generates_only_html_and_reuses_it(self):
        raw=b'synthetic HWP'
        key=self.services.advertisements.storage.put(raw)
        self.ad.files[0]=replace(self.ad.files[0],original_file_name='past.hwp',storage_key=key,
                                 checksum=hashlib.sha256(raw).hexdigest())
        file=self.ad.files[0]
        bundle=self.request()
        self.bridge.config.update(parser_python='python', parser_root=str(self.root), parser_cwd=str(self.root))
        previous_links = json.loads(json.dumps(self.bridge.links))
        def render(command,**kwargs):
            output=Path(command[command.index('--output')+1])
            (output/'past.review.html').write_text('<html><head></head><body><p>past source</p></body></html>')
            return Mock(returncode=0)
        with patch('operational_web_bridge.subprocess.run',side_effect=render) as run:
            self.assertIn('past source',self.bridge.hwp_review_html(bundle.review.review_id,file.file_id))
            self.assertIn('past source',self.bridge.hwp_review_html(bundle.review.review_id,file.file_id))
        self.assertEqual(run.call_count,1)
        self.assertTrue(run.call_args.args[0][1].endswith('render_hwp_review_html.py'))
        self.assertNotIn('run.py',run.call_args.args[0])
        self.assertFalse((self.bridge.root/'runs'/bundle.review.review_id/'integrated.json').exists())
        self.assertEqual(self.bridge.links, previous_links)

    def test_missing_asset_retries_individually_and_keeps_batch_output(self):
        parser_root = self.root / "parser"
        parser_root.mkdir()
        self.bridge.config.update({"parser_root": str(parser_root), "parser_python": "python"})
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
        self.write_parser_pair(batch_output, sources["FILE-test"].name)
        completed, missing = self.bridge.parsed_assets(self.ad.files, sources, batch_output)
        self.assertEqual(set(completed), {"FILE-test"})
        self.assertEqual(set(missing), {"FILE-second"})

        def write_retry_output(retry_source, retry_output, log_path, *, template_id=None):
            self.assertEqual(template_id, "대출성상품-상품명 노출")
            source = next(Path(retry_source).iterdir())
            self.write_parser_pair(retry_output, source.name)
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
        self.bridge.config.update({"parser_root": str(parser_root), "parser_python": "python", "parser_workers": 2})
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
            self.write_parser_pair(asset_output, source.name)
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
        self.assertEqual(len(list((self.root / "run" / "parser" / "final").glob("*.p1.json"))), 2)
        self.assertEqual(len(list((self.root / "run" / "parser" / "final").glob("*.p3.json"))), 2)
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

    def test_delete_advertisement_removes_all_owned_state_files_and_embeddings(self):
        storage_key = self.services.advertisements.storage.put(b"original advertisement")
        self.ad.files[0] = replace(self.ad.files[0], storage_key=storage_key)
        first = self.request()
        first.job.status = "COMPLETED"
        first.review.status = "REVIEW_COMPLETED"
        self.bridge.active.discard(first.review.review_id)
        second = self.request()
        second.job.status = "FAILED"
        second.review.status = "REVIEW_FAILED"
        self.bridge.active.discard(second.review.review_id)
        fine_body = b'{"doc_id":"evidence-1","text_search":"advertisement text"}\n'
        fine_hash = hashlib.sha256(fine_body).hexdigest()
        cache_root = Path(self.bridge.rag.config.vector_cache_dir)
        cache_root.mkdir(parents=True)
        evidence_cache = cache_root / f"evidence-fine-{fine_hash}.f16.npy"
        context_cache = cache_root / f"query-context-{fine_hash}-scope.f16.npy"
        rule_cache = cache_root / "rules-shared.f16.npy"
        for path in (evidence_cache, context_cache, rule_cache):
            path.write_bytes(b"cache")
        for bundle, rag_job_id in ((first, "rag-first"), (second, "rag-second")):
            run_dir = self.bridge.root / "runs" / bundle.review.review_id
            fine_path = self.bridge.root / "rag-jobs" / rag_job_id / "input" / "evidence_fine.jsonl"
            run_dir.mkdir(parents=True)
            fine_path.parent.mkdir(parents=True)
            fine_path.write_bytes(fine_body)
            self.bridge.links[bundle.review.review_id] = {"rag_job_id": rag_job_id}
            self.bridge.decisions[bundle.review.review_id] = {"decision": "REJECTED"}
        self.bridge.routes[self.ad.advertisement_id] = {"product_group": "SAVINGS"}

        advertisement_id = self.bridge.delete_advertisement(self.actor, self.ad.advertisement_id)

        self.assertEqual(advertisement_id, self.ad.advertisement_id)
        self.assertIsNone(self.services.repository.get_advertisement(self.ad.advertisement_id))
        self.assertFalse(any(
            bundle.review.advertisement_id == self.ad.advertisement_id
            for bundle in self.services.reviews.repository._items.values()
        ))
        self.assertNotIn(self.ad.advertisement_id, self.bridge.routes)
        self.assertFalse(any(review_id in self.bridge.links for review_id in (first.review.review_id, second.review.review_id)))
        self.assertFalse(any(review_id in self.bridge.decisions for review_id in (first.review.review_id, second.review.review_id)))
        self.assertFalse((self.bridge.root / "runs" / first.review.review_id).exists())
        self.assertFalse((self.bridge.root / "rag-jobs" / "rag-second").exists())
        self.assertFalse(evidence_cache.exists())
        self.assertFalse(context_cache.exists())
        self.assertTrue(rule_cache.exists())
        with self.assertRaises(FileNotFoundError):
            self.services.advertisements.storage.open(storage_key)
        persisted = json.loads((self.bridge.root / "web-state.json").read_text(encoding="utf-8"))
        self.assertFalse(any(row["advertisement_id"] == self.ad.advertisement_id for row in persisted["advertisements"]))

    def test_delete_advertisement_preserves_shared_evidence_cache_and_rejects_active_review(self):
        bundle = self.request()
        with self.assertRaises(ServiceError) as active:
            self.bridge.delete_advertisement(self.actor, self.ad.advertisement_id)
        self.assertEqual(active.exception.code, "REVIEW_IN_PROGRESS")
        bundle.job.status = "FAILED"
        bundle.review.status = "REVIEW_FAILED"
        self.bridge.active.discard(bundle.review.review_id)
        fine_body = b'{"doc_id":"evidence-1","text_search":"same text"}\n'
        fine_hash = hashlib.sha256(fine_body).hexdigest()
        cache_root = Path(self.bridge.rag.config.vector_cache_dir)
        cache_root.mkdir(parents=True)
        evidence_cache = cache_root / f"evidence-fine-{fine_hash}.f16.npy"
        evidence_cache.write_bytes(b"cache")
        for review_id, rag_job_id in ((bundle.review.review_id, "rag-target"), ("REV-other", "rag-other")):
            fine_path = self.bridge.root / "rag-jobs" / rag_job_id / "input" / "evidence_fine.jsonl"
            fine_path.parent.mkdir(parents=True)
            fine_path.write_bytes(fine_body)
            self.bridge.links[review_id] = {"rag_job_id": rag_job_id}

        with patch.object(self.services.advertisements.storage, "delete"):
            self.bridge.delete_advertisement(self.actor, self.ad.advertisement_id)

        self.assertTrue(evidence_cache.exists())
        self.assertTrue((self.bridge.root / "rag-jobs" / "rag-other").exists())

    def test_delete_advertisement_http_route_removes_row_source(self):
        app = create_app(self.settings, self.services)
        self.bridge.install(app)
        bundle = self.request()
        bundle.job.status = "FAILED"
        bundle.review.status = "REVIEW_FAILED"
        self.bridge.active.discard(bundle.review.review_id)
        with patch.object(self.services.advertisements.storage, "delete"), TestClient(app) as client:
            token, _, _ = self.services.auth.login(
                self.user.email, "test-password", "local", "test", "test"
            )
            response = client.delete(
                f"/operational/advertisements/{self.ad.advertisement_id}",
                headers={"Authorization": f"Bearer {token}"},
            )

        self.assertEqual(response.status_code, 204)
        self.assertIsNone(self.services.repository.get_advertisement(self.ad.advertisement_id))

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
            route_body = {"product_classification_code": "예금성상품-적립식"}
            self.assertEqual(client.put(url, json=route_body).status_code, 401)
            token, _, _ = self.services.auth.login(self.user.email, "test-password", "local", "test", "test")
            headers = {"Authorization": f"Bearer {token}"}
            capabilities = client.get("/operational/capabilities", headers=headers).json()
            self.assertNotIn("templates", capabilities)
            self.assertEqual(capabilities["sourcePolicy"], "template-only")
            self.assertEqual(capabilities["regulation"], "내부 심의 템플릿")
            worklist_response = client.get('/operational/review-worklist', headers=headers)
            self.assertEqual(worklist_response.status_code, 200)
            worklist = worklist_response.json()
            self.assertEqual(305, len(worklist['rows']))
            self.assertEqual(239, worklist['counts']['templates'])
            self.assertEqual(32, worklist['counts']['supplement_32'])
            self.assertEqual(34, worklist['counts']['additional_34'])
            self.assertFalse(worklist['operationally_connected'])
            labels = {row["label"] for row in capabilities["productClassifications"]}
            self.assertEqual(len(labels), 17)
            self.assertTrue({"예금성상품-적립식", "대출성상품-상품명 노출",
                             "투자성상품-ETF", "투자성상품-ELB"} <= labels)
            self.assertFalse(any("카드" in label for label in labels))
            investment = next(
                row for row in capabilities["productClassifications"]
                if row["label"].startswith("투자성상품-")
            )
            self.assertEqual(investment["productGroup"], "INVESTMENT")
            self.assertEqual(client.put(url, headers=headers, json={**route_body, "product_classification_code": "대출성상품-상품명 노출"}).status_code, 422)
            self.assertEqual(client.put(url, headers=headers, json=route_body).status_code, 200)
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
        self.assertEqual(export.json()["extraction_status"], view.json()["extraction_status"])
        self.assertEqual([r["verdict"] for r in view.json()["rows"]], ["판단불가"])
        self.assertEqual([r['verdict'] for r in view.json()['excluded_rows']], ['미해당'])
        self.assertEqual(export.json()['excluded_rows'], view.json()['excluded_rows'])
        self.assertEqual(export.json()["execution"]["output_failure_count"], 1)
        self.assertEqual(export.json()["execution"]["output_failure_pairs"][0]["reason"], "invalid JSON")
        self.assertNotIn("source_ads", view.json())

    def test_parser_failure_workspace_exposes_failed_file_without_result(self):
        bundle = self.request()
        bundle.review.status, bundle.job.status = "REVIEW_FAILED", "FAILED"
        directory = self.bridge.root / "runs" / bundle.review.review_id
        directory.mkdir(parents=True)
        (directory / "parser-failure.json").write_text(json.dumps({
            "failed_assets": [{"file_id": "FILE-test", "reason": "internal path omitted"}]
        }), encoding="utf-8")
        before = (directory / "parser-failure.json").read_bytes()
        app = create_app(self.settings, self.services)
        self.bridge.install(app)
        token, _, _ = self.services.auth.login(self.user.email, "test-password", "local", "test", "test")
        with TestClient(app) as client:
            path = f"/operational/reviews/{bundle.review.review_id}/workspace"
            self.assertEqual(client.get(path).status_code, 401)
            response = client.get(path, headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 200)
        summary = response.json()["extraction_status"]
        self.assertEqual(summary["status"], "FAILED")
        self.assertEqual(summary["files"][0]["asset_id"], "FILE-test")
        self.assertEqual(summary["files"][0]["issues"], ["FILE_EXTRACTION_FAILED"])
        self.assertNotIn("internal path omitted", str(summary))
        self.assertEqual((directory / "parser-failure.json").read_bytes(), before)

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
