"""Loopback demo adapter: original NH UI -> real parser -> canonical RAG service.

This does not replace the production PostgreSQL/Redis worker. Local state is
durable JSON; no gold or fixture predictions are used by execution.
"""
from __future__ import annotations

import ctypes
import copy
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.concurrency import run_in_threadpool
from nh_ad_backend.domain import Advertisement, AdvertisementFile
from nh_ad_backend.results import ResultAnnotation, ResultEvidence, ResultItem
from nh_ad_backend.reviews import Review, ReviewBundle, ReviewJob, ReviewStep
from nh_ad_backend.services import ServiceError

from local_hwp_preview import convert_hwp_to_pdf
from operational_hwp_html import HTML_CSP, static_hwp_html
from operational_locations import (extraction_status, frozen_rule_metadata, load_template_appropriate_judgments,
                                   page_asset, saved_workspace, valid_box, with_rendered_line_locations)

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "rag-pipeline"), str(ROOT / "rag-pipeline/tools")]
from rag.parsing.prepare_inputs import combine  # noqa: E402
from rag.parsing.source_structure import namespace_structure  # noqa: E402
from rag.templates.catalog import TemplateCatalog  # noqa: E402
from rag.contracts.validation import validate_ad_intake, validate_integrated_input  # noqa: E402
from rag.judgment.product_context import product_contexts, resolve_product_templates  # noqa: E402
from rag.api.service import (  # noqa: E402
    OperationalReviewService, ServiceConfig, TERMINAL_STATES, write_json_atomic,
)

FULL_REVIEW = {"REQUIRED_PHRASE", "INTEREST_RATE", "MISLEADING_EXPRESSION", "PRODUCT_CONSISTENCY", "VISIBILITY"}
PARSER_REUSE_PARENT_STATUSES = {
    "FAILED", "FAILED_FINAL", "COMPLETED", "COMPLETED_WITH_WARNINGS",
}
MARKER = r"\s*\[(?:정식|잠정)\]\s*$"


def executable_template_names(plans_path: Path) -> list[str]:
    """Intake may only offer templates the judgment catalog can execute.

    A template section without an execution plan is a dead option: routing
    validation rejects it and the runner raises before judgment. The plan
    template name carries a review-status marker which is not part of the
    routing key, so it is stripped here as it is in the catalog loader.
    """
    document = json.loads(plans_path.read_text(encoding="utf-8"))
    names = []
    for plan in document.get("plans") or []:
        if (plan.get("source") or {}).get("source_kind") != "TEMPLATE":
            continue
        raw = str(((plan.get("source") or {}).get("product_template")) or "")
        name = re.sub(MARKER, "", raw).strip()
        if name and name not in names:
            names.append(name)
    return names

PRODUCTS = {
    "LOAN": "대출성",
    "DEPOSIT": "예금성",
    "SAVINGS": "예금성",
    "DEMAND_DEPOSIT": "예금성",
    "INVESTMENT": "투자성",
}
STEP_NAMES = ["입력 파일 확인", "OCR/VLM 파싱 (영역·라벨)", "파싱 결과 통합·검증 및 청킹 준비",
              "템플릿 전체 항목 판정 요청", "원문 근거 검색·Gemma 판정", "실제 결과 저장"]


def registration_review_date(created_at: datetime) -> str:
    """Freeze review day at the original service registration, in Korea time."""
    # Legacy persisted naive timestamps are UTC, like the repository clock.
    registered = created_at if created_at.tzinfo else created_at.replace(tzinfo=UTC)
    return registered.astimezone(timezone(timedelta(hours=9))).date().isoformat()


def template_sections_from_hwpx(path: Path) -> list[str]:
    """Use the same first-class template catalog as the judgment runner."""
    catalog = TemplateCatalog.from_hwpx(path)
    sections = [row["template_section"] for row in catalog.document["entries"]]
    values = {value for value in sections if value.startswith(("예금성", "대출성", "투자성"))}
    if not values:
        raise ValueError("template HWPX contains no supported detailed product classifications")
    return sorted(values)


def parser_layout(document, *, source: str) -> dict:
    """Project only truthful parser boxes; never infer missing coordinates."""
    pages = []
    for page in document.get("pages", []):
        width, height = int(page.get("canvas_w") or 0), int(page.get("canvas_h") or 0)
        regions = []
        asset_id, source_page_no = page_asset(document, page)
        for region in page.get("regions", []):
            evidence_id = str(region.get("evidence_id") or "")
            if asset_id is None and "#asset:" in evidence_id:
                asset_id = evidence_id.split("#asset:", 1)[1].split(":p", 1)[0]
            lines = []
            for line in region.get("lines", []):
                box = line.get("bbox")
                if valid_box(box, width, height):
                    lines.append({
                        "line_ref": line.get("line_ref"),
                        "text": line.get("text") or line.get("parser_text") or "",
                        "bbox": box,
                        "text_source": line.get("text_source") or line.get("source"),
                        "confidence": line.get("confidence", line.get("ocr_confidence")),
                    })
            box = region.get("bbox")
            if valid_box(box, width, height):
                evidence = region.get("text_evidence") or {}
                primary = evidence.get("parser_primary_text") or {}
                regions.append({
                    "region_id": region.get("region_id"),
                    "bbox": box,
                    "layout_label": (region.get("layout") or {}).get("label"),
                    "text": region.get("final_text") or primary.get("text") or "",
                    "lines": lines,
                })
        # Unassigned OCR lines still have real source coordinates. Represent
        # each as its own display-only region, without a fabricated union box.
        for index, line in enumerate(page.get("unassigned_lines", [])):
            if valid_box(line.get("bbox"), width, height):
                display_id = line.get("line_ref") or f"visual-p{page.get('page_no', len(pages)+1)}-{index}"
                regions.append({"region_id": f"unassigned:{display_id}",
                    "bbox": line["bbox"], "layout_label": None, "text": line.get("text", ""),
                    "lines": [{"line_ref": line.get("line_ref"), "text": line.get("text") or line.get("parser_text") or "",
                               "bbox": line["bbox"], "text_source": line.get("text_source"),
                               "confidence": line.get("confidence")} ]})
        pages.append({
            "page_no": int(page.get("page_no") or len(pages) + 1),
            "asset_id": asset_id,
            "source_page_no": source_page_no,
            "canvas_w": width,
            "canvas_h": height,
            "regions": regions,
        })
    return {
        "schema_version": "operational-parser-layout-v1",
        "source": source,
        "coordinate_basis": "rendered_original_200dpi",
        "pages": pages,
        "counts": {
            "pages": len(pages),
            "regions": sum(len(page["regions"]) for page in pages),
            "lines": sum(len(region["lines"]) for page in pages for region in page["regions"]),
        },
    }


def parser_runner_layout(config: dict) -> dict[str, str]:
    """Describe one supported parser runner without guessing output paths."""
    runner = str(config.get("parser_runner") or "nh_parsing_test_batch")
    if runner == "nh_parsing_test_batch":
        return {"runner": runner, "p1_dir": "json", "p3_dir": "review_region_input", "raw_dir": "json"}
    if runner == "nh_ad_parser_cli":
        return {"runner": runner, "p1_dir": "evidence", "p3_dir": "review-input", "raw_dir": "parse"}
    if runner == "nh_parser_fin":
        profile = config.get("parser_contract_profile", "region-v6")
        if profile not in {"region-v6", "region-v9"}:
            raise ValueError("unsupported parser_contract_profile")
        return {"runner": runner, "p1_dir": "final", "p3_dir": "final", "raw_dir": "raw",
                "contract_profile": profile}
    raise ValueError(f"unsupported parser_runner: {runner!r}")


def parser_fin_output_stem(source: Path) -> str:
    """Mirror nh-parser-fin's stable, filesystem-safe output basename."""
    return "".join(char if char.isalnum() or char in "-_." else "_" for char in source.name)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def restore_dates(row, fields):
    value = dict(row)
    for field in fields:
        if value.get(field):
            value[field] = datetime.fromisoformat(value[field])
    return value


class ReviewCanceled(RuntimeError):
    """Expected user cancellation; never turn it into an execution failure."""


class ReviewPaused(RuntimeError):
    """Expected process shutdown; persist the review for restart instead of failing it."""


TRANSIENT_CONNECTION_FAILURE_PREFIXES = (
    "SEARCH_CONNECTION_UNAVAILABLE:",
    "EMBEDDING_CONNECTION_UNAVAILABLE:",
    "MODEL_CONNECTION_UNAVAILABLE:",
)


class ExecutionBridge:
    def __init__(self, services, state_dir, config_path, projector):
        self.services, self.projector = services, projector
        # Parser subprocesses run from parser_cwd, so every bridge-owned path
        # must be absolute. Relative paths would otherwise resolve inside the
        # parser repository and make an input directory look like one missing
        # extensionless file.
        self.root = (Path(state_dir) / "execution").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.config = read_json(config_path)
        self.parser_layout_config = parser_runner_layout(self.config)
        self.lock = threading.RLock()
        self.layout_lock = threading.Lock()
        cfg = self.config
        model_env = cfg.get("model_env", {})
        if not isinstance(model_env, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in model_env.items()
        ):
            raise ValueError("model_env must be a string-to-string object")
        review_workers = int(cfg.get("review_workers", os.environ.get("NH_RAG_QUEUE_WORKERS", "2")))
        parser_workers = int(cfg.get("parser_workers", os.environ.get("NH_PARSER_WORKERS", "2")))
        # Spark sustained three concurrent diagnostic calls without contract
        # or transport errors. Match the canonical RAG service default so one
        # advertisement does not leave model capacity idle.
        model_workers = int(cfg.get("model_workers", os.environ.get("NH_RAG_MODEL_WORKERS", "4")))
        source_policy = str(cfg.get("source_policy") or "template-only")
        if source_policy not in {"template-only", "template-plus-v2"}:
            raise ValueError("source_policy must be template-only or template-plus-v2")
        if review_workers < 1 or model_workers < 1 or parser_workers < 1:
            raise ValueError("review_workers, model_workers and parser_workers must be positive")
        self.pool = ThreadPoolExecutor(max_workers=review_workers, thread_name_prefix="nh-web-review")
        # Parser calls use shared GPU/OCR endpoints.  Bound all advertisement
        # jobs together so a multi-file card cannot multiply remote load.
        self.parser_workers = parser_workers
        self.parser_slots = threading.BoundedSemaphore(parser_workers)
        self.routes, self.links, self.decisions = {}, {}, {}
        self.active = set()
        self.stopping = threading.Event()
        self.rag = OperationalReviewService(ServiceConfig(
            jobs_dir=self.root / "rag-jobs", regulation_path=Path(cfg.get("regulation_path") or "."),
            es_url=cfg.get("es_url", ""), es_index=cfg.get("es_index", ""), model=cfg["model"],
            source_policy=source_policy,
            decision_guide_path=Path(cfg["decision_guide_path"]) if cfg.get("decision_guide_path") else None,
            candidate_activation_policy_path=(
                Path(cfg["candidate_activation_policy_path"])
                if cfg.get("candidate_activation_policy_path")
                else None
            ),
            canonical_plans_path=Path(cfg.get(
                "canonical_plans_path",
                ROOT / "rag-pipeline/config/canonical-execution-plans-v2.json",
            )),
            catalog_migration_path=Path(cfg.get(
                "catalog_migration_path",
                ROOT / "rag-pipeline/config/operational-catalog-migration-v1.json",
            )),
            rule_dispositions_path=Path(cfg.get(
                "rule_dispositions_path",
                ROOT / "rag-pipeline/config/operational-rule-dispositions-v1.json",
            )),
            template_hwpx_path=Path(cfg["template_source_path"]) if cfg.get("template_source_path") else None,
            template_methodology_dir=(
                Path(cfg["template_methodology_dir"])
                if cfg.get("template_methodology_dir")
                else None
            ),
            dgx_host=cfg.get("dgx_host"), dgx_key=Path(cfg["dgx_key"]) if cfg.get("dgx_key") else None,
            model_env=model_env,
            workers=model_workers, queue_workers=review_workers,
            vector_cache_dir=Path(cfg["vector_cache_dir"]).resolve() if cfg.get("vector_cache_dir") else None,
            judgment_batch_size=4, job_timeout_seconds=3600,
        ))
        template_source = cfg.get("template_source_path")
        if template_source:
            self.templates = template_sections_from_hwpx(Path(template_source))
            self.template_source = {
                "kind": "hwpx_template",
                "path": str(Path(template_source)),
                "sha256": hashlib.sha256(Path(template_source).read_bytes()).hexdigest(),
            }
        else:
            # Compatibility fallback only.  A configured HWPX source takes
            # precedence because it is the detailed intake taxonomy supplied
            # by the review team. Source-less runs retain the v2 legacy path.
            import openpyxl
            book = openpyxl.load_workbook(cfg["regulation_path"], read_only=True, data_only=True)
            try:
                rows = book["신규규칙후보"].iter_rows(values_only=True)
                header = list(next(rows))
                column = header.index("섹션")
                self.templates = sorted({str(row[column]) for row in rows if row[column] and
                                         str(row[column]).startswith(("예금성", "대출성", "투자성"))})
            finally:
                book.close()
            self.template_source = {"kind": "v2_section_compatibility_fallback"}
        plans_path = self.rag.config.canonical_plans_path
        if plans_path:
            # Card sections exist in the HWPX intake taxonomy but carry no
            # execution plan, and ETF/ELB carry plans without an HWPX
            # section. Offer exactly what can be judged.
            executable = executable_template_names(Path(plans_path))
            if executable:
                self.template_source = {
                    **self.template_source,
                    "intake_scope": "canonical_execution_plan_templates",
                    "hwpx_only_sections": sorted(set(self.templates) - set(executable)),
                    "plan_only_templates": sorted(set(executable) - set(self.templates)),
                }
                self.templates = executable
        guide_source = cfg.get("template_appropriate_judgment_path")
        if guide_source:
            guide_path = Path(guide_source)
            self.template_appropriate_judgments = load_template_appropriate_judgments(guide_path)
            self.template_appropriate_judgment_sha256 = hashlib.sha256(guide_path.read_bytes()).hexdigest()
        else:
            self.template_appropriate_judgments = {}
            self.template_appropriate_judgment_sha256 = None
        self.product_classifications = [
            {
                "code": value,
                "label": value,
                # Same prefix basis as PRODUCTS. A section whose prefix
                # matches no product group is not offered at all, because
                # routing validation would reject it.
                "productGroup": next(
                    (group for group, prefix in (("LOAN", "대출성"),
                                                 ("INVESTMENT", "투자성"),
                                                 ("DEPOSIT", "예금성"))
                     if value.startswith(prefix)),
                    None,
                ),
            }
            for value in self.templates
        ]
        self.product_classifications = [row for row in self.product_classifications
                                        if row["productGroup"]]
        self.restore()
        services.reviews.queue = self
        original_request = services.reviews.request

        def request(actor, advertisement_id, **kwargs):
            with self.lock:
                ad = services.advertisements.get(actor, advertisement_id, kwargs["trace_id"])
                self.validate_request(ad, kwargs)
                return original_request(actor, advertisement_id, **kwargs)

        services.reviews.request = request

    def parser_command(self, source_dir, output, *, visual: bool = False, template_id=None):
        """Build the selected parser command; values come only from private config."""
        runner = self.parser_layout_config["runner"]
        root = Path(self.config["parser_root"]).resolve()
        source_dir = Path(source_dir).resolve()
        output = Path(output).resolve()
        if runner == "nh_ad_parser_cli":
            command = [self.config["parser_python"], "-u", str(root / "tools" / "parse.py"),
                       "--input", str(source_dir), "--out", str(output)]
            if visual:
                command.extend(["--region-reading", "off", "--parse-only"])
            else:
                if not template_id:
                    raise ValueError("PARSER_TEMPLATE_REQUIRED: 사용자 선택 템플릿이 필요합니다")
                command.extend(["--template-id", template_id])
            return command
        if runner == "nh_parser_fin":
            command = [self.config["parser_python"], "-u", str(root / "run.py"),
                       "--input", str(source_dir), "--run-name", output.name]
            command.append("--compact-output" if self.parser_layout_config.get("contract_profile") == "region-v9"
                           else "--with-vlm")
            return command
        if not visual:
            raise ValueError("PARSER_TEMPLATE_UNSUPPORTED: 사용자 템플릿을 받는 nh_ad_parser_cli가 필요합니다")
        scope = "visual" if visual else "upload"
        return [self.config["parser_python"], str(root / "tools" / "run_parsing_batch.py"),
                "--input-root", f"{scope}={source_dir}", "--out", str(output), "--max-attempts", "1"]

    def parser_outputs(self, output):
        layout = self.parser_layout_config
        if layout["runner"] == "nh_parser_fin":
            directory = output / layout["p1_dir"]
            return (list(directory.glob("*.p1.json")), list(directory.glob("*.p3.json")))
        return (list((output / layout["p1_dir"]).glob("*.json")),
                list((output / layout["p3_dir"]).glob("*.json")))

    def parser_raw_outputs(self, output):
        return list((output / self.parser_layout_config["raw_dir"]).glob("*.json"))

    def parser_output_name_matches(self, path, source):
        if self.parser_layout_config["runner"] == "nh_ad_parser_cli":
            return path.stem == source.stem
        if self.parser_layout_config["runner"] == "nh_parser_fin":
            return path.name == parser_fin_output_stem(source) + ".p1.json"
        return path.name == source.name

    def parser_p3_matches(self, p1_path, candidate):
        if self.parser_layout_config["runner"] == "nh_parser_fin":
            return candidate.name == p1_path.name.removesuffix(".p1.json") + ".p3.json"
        return candidate.name == p1_path.name

    def parser_output_root(self, output):
        """Return the P1/P3 root for either supported parser runner."""
        output = Path(output)
        if self.parser_layout_config["runner"] == "nh_parsing_test_batch":
            return output / "upload"
        return output

    def parsed_assets(self, files, source_by_file, output):
        """Accept validated, nonempty P1/P3 pairs; retain partial batch output."""
        p1s, p3s = self.parser_outputs(self.parser_output_root(output))
        completed, missing = {}, {}
        for file in files:
            matches = [path for path in p1s if self.parser_output_name_matches(path, source_by_file[file.file_id])]
            if len(matches) != 1:
                missing[file.file_id] = "P1 산출물이 없거나 하나가 아닙니다"
                continue
            p1_path = matches[0]
            p3_matches = [path for path in p3s if self.parser_p3_matches(p1_path, path)]
            if len(p3_matches) != 1:
                missing[file.file_id] = "P3 산출물이 없거나 하나가 아닙니다"
                continue
            try:
                self.read_parser_asset(p1_path, p3_matches[0])
            except (OSError, ValueError):
                missing[file.file_id] = "PARSER_INPUT_UNREADABLE: 유효한 심의 원문 영역이 없습니다. 파서 로그를 확인하세요"
                continue
            completed[file.file_id] = (p1_path, p3_matches[0])
        return completed, missing

    @staticmethod
    def read_parser_asset(p1_path, p3_path):
        """An output file alone does not prove that parsing succeeded.

        Partial documents and text without geometry remain reviewable. Empty
        or unassigned-only output cannot supply scoped advertisement evidence.
        """
        document = combine(p1_path, p3_path)
        if not any(
            str(region.get("final_text") or "").strip()
            for page in document.get("pages", [])
            for region in page.get("regions", [])
        ):
            raise ValueError("PARSER_INPUT_UNREADABLE: no reviewable advertisement regions")
        return document

    def execute_parser(self, source_dir, output, log_path, *, template_id=None):
        """Run one parser input directory and retain its raw log for audit."""
        env = dict(os.environ)
        env.update(self.config.get("parser_env", {}))
        if self.parser_layout_config["runner"] == "nh_parser_fin":
            env["NH_OUTPUT_ROOT"] = str(Path(output).resolve().parent)
            env.setdefault("NH_MEDIA_DIR", str((Path(output).resolve().parent / "media")))
            if self.parser_layout_config.get("contract_profile") == "region-v9":
                env["HWP_RENDER_DIR"] = str(Path(output).resolve() / "render")
                env["HWP_REVIEW_DIR"] = str(Path(output).resolve() / "review-html")
        env["PYTHONIOENCODING"] = "utf-8"
        with Path(log_path).open("w", encoding="utf-8") as log:
            try:
                command = self.parser_command(source_dir, output, template_id=template_id)
                sources = list(Path(source_dir).iterdir())
                if (self.parser_layout_config["runner"] == "nh_parser_fin"
                        and self.parser_layout_config.get("contract_profile") == "region-v6" and len(sources) == 1
                        and sources[0].suffix.lower() in {".hwp", ".hwpx"}):
                    if not template_id:
                        raise ValueError("PARSER_TEMPLATE_REQUIRED: native HWP requires the selected template")
                    native = subprocess.run([
                        self.config["parser_python"], str(ROOT / "scripts/parse_hwp_native.py"),
                        "--source", str(sources[0].resolve()), "--output", str(Path(output).resolve()),
                        "--parser-root", str(self.config["parser_root"]), "--template-id", str(template_id),
                    ], cwd=Path(self.config["parser_cwd"]).resolve(), env=env,
                        stdout=log, stderr=subprocess.STDOUT, timeout=3600,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                    if native.returncode != 3:
                        return native.returncode
                return subprocess.run(
                    command,
                    cwd=Path(self.config["parser_cwd"]).resolve(), env=env,
                    stdout=log, stderr=subprocess.STDOUT, timeout=3600,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                ).returncode
            except subprocess.TimeoutExpired:
                log.write("\nPARSER_TIMEOUT: parser exceeded 3600 seconds\n")
                return 124
            except OSError as exc:
                log.write(f"\nPARSER_START_FAILED: {exc}\n")
                return 126

    def retry_missing_parser_assets(self, files, source_by_file, missing, directory, *, template_id=None):
        """Retry only assets absent from a failed/incomplete batch, once each."""
        retry_root = Path(directory) / "parser-retry"
        recovered, attempts = {}, []
        by_id = {file.file_id: file for file in files}
        for file_id, initial_reason in missing.items():
            file = by_id[file_id]
            retry_dir = retry_root / file_id
            retry_source = retry_dir / "source"
            retry_output = retry_dir / "output"
            retry_source.mkdir(parents=True, exist_ok=True)
            source = source_by_file[file_id]
            retry_copy = retry_source / source.name
            shutil.copy2(source, retry_copy)
            with self.parser_slots:
                returncode = self.execute_parser(retry_source, retry_output, retry_dir / "parser.log", template_id=template_id)
            found, still_missing = self.parsed_assets([file], {file_id: retry_copy}, retry_output)
            if file_id in found:
                recovered[file_id] = found[file_id]
                self.capture_parser_page_images(file, found[file_id][0], found[file_id][1], directory)
            attempts.append({
                "file_id": file_id,
                "file_name": file.original_file_name,
                "initial_reason": initial_reason,
                "returncode": returncode,
                "status": "RECOVERED" if file_id in found else "FAILED",
                "failure_reason": still_missing.get(file_id),
                "log": str((retry_dir / "parser.log").relative_to(directory)),
            })
        write_json_atomic(retry_root / "parser-retry.json", {
            "version": "parser-asset-retry-v1",
            "attempted_at": datetime.now(UTC).isoformat(),
            "max_attempts_per_asset": 1,
            "attempts": attempts,
        })
        return recovered, attempts

    def parse_assets_in_parallel(self, files, source_by_file, directory, *, template_id=None):
        """Parse a multi-file advertisement independently with one shared limit.

        The external parser's folder mode is serial.  Independent inputs retain
        per-file P1/P3 provenance and allow a long page set to use the same two
        parser slots already allocated to the operational server.
        """
        initial_root = Path(directory) / "parser-initial"
        canonical_output = Path(directory) / "parser"

        def parse_asset(file):
            asset_root = initial_root / file.file_id
            asset_source = asset_root / "source"
            asset_output = asset_root / "output"
            asset_source.mkdir(parents=True, exist_ok=True)
            source = source_by_file[file.file_id]
            copied = asset_source / source.name
            shutil.copy2(source, copied)
            with self.parser_slots:
                returncode = self.execute_parser(asset_source, asset_output, asset_root / "parser.log", template_id=template_id)
            found, missing = self.parsed_assets([file], {file.file_id: copied}, asset_output)
            return file, returncode, found.get(file.file_id), missing.get(file.file_id)

        completed, missing, attempts = {}, {}, []
        with ThreadPoolExecutor(max_workers=min(self.parser_workers, len(files))) as executor:
            futures = {executor.submit(parse_asset, file): file for file in files}
            for future in futures:
                file, returncode, pair, reason = future.result()
                if pair:
                    completed[file.file_id] = pair
                    self.capture_parser_page_images(file, pair[0], pair[1], directory)
                    for path, directory_name in zip(pair, (self.parser_layout_config["p1_dir"], self.parser_layout_config["p3_dir"])):
                        destination = canonical_output / directory_name / path.name
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(path, destination)
                else:
                    missing[file.file_id] = reason or "개별 파서 산출물이 없습니다"
                attempts.append({
                    "file_id": file.file_id,
                    "file_name": file.original_file_name,
                    "returncode": returncode,
                    "status": "COMPLETED" if pair else "FAILED",
                    "failure_reason": reason,
                    "log": str((initial_root / file.file_id / "parser.log").relative_to(directory)),
                })
        write_json_atomic(initial_root / "parser-initial.json", {
            "version": "parser-asset-parallel-v1",
            "max_workers": self.parser_workers,
            "attempts": attempts,
        })
        (Path(directory) / "parser.log").write_text(
            "복수 파일 병렬 파싱 요약\n" + "\n".join(
                f"{row['file_name']}: {row['status']} ({row['log']})" for row in attempts
            ) + "\n",
            encoding="utf-8",
        )
        return completed, missing, 0 if all(row["returncode"] == 0 for row in attempts) else 1

    def save_hwp_html(self, file, raw, directory, *, basis, parser_hashes=None):
        destination = Path(directory) / 'hwp-html'
        destination.mkdir(parents=True, exist_ok=True)
        if not re.fullmatch(r'FILE-[\w-]+', file.file_id):
            raise ValueError('invalid HWP asset identity')
        path = destination / f'{file.file_id}.html'
        temporary = path.with_suffix('.pending')
        temporary.write_bytes(raw)
        temporary.replace(path)
        write_json_atomic(path.with_suffix('.json'), {
            'version': 'operational-hwp-html-v1', 'asset_id': file.file_id,
            'source_sha256': file.checksum, 'html_sha256': hashlib.sha256(raw).hexdigest(),
            'basis': basis, 'parser_hashes': parser_hashes or {},
            'coordinate_policy': 'HTML_TEXT_MATCH_ONLY',
        })

    def capture_parser_hwp_html(self, file, p1_path, p3_path, directory):
        if Path(file.original_file_name).suffix.lower() not in {'.hwp', '.hwpx'}:
            return
        output = Path(p1_path).parent.parent.resolve()
        p1 = read_json(p1_path)
        paths = {str((((page.get('origin') or {}).get('render') or {}).get('review_surface') or {}).get('html_path') or '')
                 for page in p1.get('pages', [])}
        paths.discard('')
        if len(paths) != 1:
            return
        path = Path(paths.pop()).resolve()
        if not path.is_relative_to((output / 'review-html').resolve()) or path.suffix.lower() != '.html':
            raise ValueError('parser HWP HTML escaped its output directory')
        with self.layout_lock:
            self.save_hwp_html(file, path.read_bytes(), directory, basis='PARSER_AUTHORED_HTML',
                parser_hashes={'p1_sha256': hashlib.sha256(Path(p1_path).read_bytes()).hexdigest(),
                               'p3_sha256': hashlib.sha256(Path(p3_path).read_bytes()).hexdigest()})

    def hwp_review_html(self, review_id, asset_id):
        bundle = self.services.reviews.repository.get(review_id)
        ad = self.services.repository.get_advertisement(bundle.review.advertisement_id)
        files = [file for file in ad.files if file.file_id == asset_id and file.file_type == 'ADVERTISEMENT']
        if len(files) != 1 or not re.fullmatch(r'FILE-[\w-]+', asset_id):
            raise ServiceError(404, 'HWP_HTML_NOT_FOUND', '해당 광고의 HWP 원본이 없습니다.')
        file = files[0]
        if Path(file.original_file_name).suffix.lower() not in {'.hwp', '.hwpx'}:
            raise ServiceError(422, 'HWP_HTML_UNSUPPORTED', 'HTML 본문 표시는 HWP/HWPX 원본에서 사용합니다.')
        directory = self.root / 'runs' / review_id
        with self.layout_lock:
            path = directory / 'hwp-html' / f'{asset_id}.html'
            metadata = path.with_suffix('.json')
            if not metadata.is_file():
                if self.parser_layout_config['runner'] != 'nh_parser_fin' or not self.config.get('parser_python'):
                    raise ServiceError(503, 'HWP_HTML_UNAVAILABLE', '현재 파서의 HTML 본문 생성을 사용할 수 없습니다.')
                # Older reviews have no saved parser HTML. Materialize the same
                # immutable original and create only its HTML, never a new verdict.
                output = directory / 'hwp-html' / asset_id
                output.mkdir(parents=True, exist_ok=True)
                source = output / (asset_id + Path(file.original_file_name).suffix.lower())
                with self.services.advertisements.storage.open(file.storage_key) as stream, source.open('wb') as target:
                    shutil.copyfileobj(stream, target)
                if hashlib.sha256(source.read_bytes()).hexdigest() != file.checksum:
                    raise ServiceError(409, 'HWP_HTML_MISMATCH', '저장 원본의 체크섬을 확인할 수 없습니다.')
                env = dict(os.environ)
                env.update(self.config.get('parser_env', {}))
                env['PYTHONIOENCODING'] = 'utf-8'
                with (output / 'html.log').open('w', encoding='utf-8') as log:
                    result = subprocess.run([self.config['parser_python'], str(ROOT / 'scripts/render_hwp_review_html.py'),
                        '--source', str(source.resolve()), '--output', str(output.resolve()),
                        '--parser-root', str(Path(self.config['parser_root']).resolve())],
                        cwd=self.config.get('parser_cwd') or self.config['parser_root'], env=env,
                        stdout=log, stderr=subprocess.STDOUT, timeout=120,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                generated = list(output.glob('*.review.html'))
                if result.returncode or len(generated) != 1:
                    raise ServiceError(503, 'HWP_HTML_UNAVAILABLE', 'HWP HTML 본문을 생성하지 못했습니다.')
                self.save_hwp_html(file, generated[0].read_bytes(), directory, basis='DISPLAY_ONLY_SOURCE_HTML')
            binding = read_json(metadata)
            raw = path.read_bytes()
            if (binding.get('version') != 'operational-hwp-html-v1'
                    or binding.get('asset_id') != asset_id or binding.get('source_sha256') != file.checksum
                    or binding.get('html_sha256') != hashlib.sha256(raw).hexdigest()):
                raise ServiceError(409, 'HWP_HTML_MISMATCH', '저장 원본과 HTML 본문의 연결이 일치하지 않습니다.')
            return static_hwp_html(raw.decode('utf-8-sig'))

    def capture_parser_page_images(self, file, p1_path, p3_path, directory):
        """Keep the exact compact-output PNG used to establish each v9 canvas."""
        p3 = read_json(p3_path)
        if (p3.get("contract") or {}).get("version") != "nh-ad-region-review-input-v9":
            return
        from PIL import Image
        output = Path(p1_path).parent.parent
        destination = Path(directory) / "parser-page-images"
        destination.mkdir(parents=True, exist_ok=True)
        try:
            self.capture_parser_hwp_html(file, p1_path, p3_path, directory)
        except (OSError, ValueError, KeyError) as exc:
            write_json_atomic(destination / f'{file.file_id}-html-error.json',
                              {'code': 'HWP_HTML_UNAVAILABLE', 'detail': str(exc)})
        try:
            p1 = read_json(p1_path)
            rows = read_json(output / "media-index.json")
            pages = {page["page_no"]: page for page in p1["pages"]}
            captured = []
            for number, page in pages.items():
                matches = [row for row in rows if row.get("source_file") == p1.get("source_file")
                           and row.get("page_no") == number]
                if len(matches) != 1:
                    raise ValueError("parser page image ownership is ambiguous")
                name = matches[0]["image_name"]
                if not isinstance(name, str) or Path(name).name != name:
                    raise ValueError("invalid parser image filename")
                image = (output / "images" / name).resolve()
                if not image.is_relative_to((output / "images").resolve()):
                    raise ValueError("parser page image escaped its output directory")
                with Image.open(image) as loaded:
                    if loaded.format != "PNG" or list(loaded.size) != page.get("canvas"):
                        raise ValueError("parser page image does not match its P1 canvas")
                target = destination / f"{file.file_id}-p{number}.png"
                shutil.copyfile(image, target)
                captured.append({"asset_id": file.file_id, "source_page_no": number,
                    "path": str(target.relative_to(directory)).replace("\\", "/"),
                    "canvas": page["canvas"], "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                    "source_sha256": file.checksum,
                    "p1_sha256": hashlib.sha256(Path(p1_path).read_bytes()).hexdigest(),
                    "p3_sha256": hashlib.sha256(Path(p3_path).read_bytes()).hexdigest()})
            with self.layout_lock:
                manifest = destination / "manifest.json"
                previous = read_json(manifest).get("pages", []) if manifest.is_file() else []
                write_json_atomic(manifest, {"version": "operational-parser-page-images-v1",
                    "pages": [row for row in previous if row["asset_id"] != file.file_id] + captured})
        except (OSError, ValueError, KeyError) as exc:
            # Valid semantic evidence survives a presentation failure. Its v9
            # preview URL fails explicitly instead of showing another render.
            write_json_atomic(destination / f"{file.file_id}-error.json",
                              {"code": "PARSER_PAGE_IMAGE_UNAVAILABLE", "detail": str(exc)})

    @staticmethod
    def with_parser_preview_paths(review_id, layout, integrated):
        current_assets = {row["file_id"] for row in (integrated.get("diagnostics") or {}).get("assets", [])
                          if (row.get("source_parser_contracts") or {}).get("source_p3_contract")
                          == "nh-ad-region-review-input-v9"}
        value = copy.deepcopy(layout)
        for page in value.get("pages", []):
            if page.get("asset_id") in current_assets:
                page["preview_path"] = f"/operational/reviews/{review_id}/parser-page/{page['page_no']}"
        return value

    def parser_page_image(self, review_id, page_no):
        """Resolve a review-owned, hash-bound image; never trust a URL file path."""
        directory = self.root / "runs" / review_id
        integrated = read_json(directory / "integrated.json")
        pages = [row for row in integrated.get("pages", []) if row["page_no"] == page_no]
        if len(pages) != 1:
            raise ServiceError(404, "PARSER_PAGE_NOT_FOUND", "해당 심의의 원문 페이지가 없습니다.")
        page = pages[0]
        asset_id = page.get("asset_id")
        source_page = page.get("source_page_no", page_no)
        assets = [row for row in (integrated.get("diagnostics") or {}).get("assets", [])
                  if row.get("file_id") == asset_id]
        if len(assets) != 1:
            raise ServiceError(409, "PARSER_PAGE_MISMATCH", "원문 근거의 출처를 확인할 수 없습니다.")
        expected = assets[0]
        bundle = self.services.reviews.repository.get(review_id)
        advertisement_id = bundle.review.advertisement_id
        ad = self.services.repository.get_advertisement(advertisement_id)
        files = [file for file in ad.files if file.file_id == asset_id and file.file_type == "ADVERTISEMENT"]
        if len(files) != 1:
            raise ServiceError(404, "PARSER_PAGE_NOT_FOUND", "원문 파일 소유권을 확인할 수 없습니다.")
        seen = set()
        for _ in range(16):
            if directory in seen:
                break
            seen.add(directory)
            manifest_path = directory / "parser-page-images" / "manifest.json"
            if manifest_path.is_file():
                candidates = [row for row in read_json(manifest_path).get("pages", [])
                              if row["asset_id"] == asset_id and row["source_page_no"] == source_page]
                if len(candidates) == 1:
                    row = candidates[0]
                    path = (directory / row["path"]).resolve()
                    if (not path.is_relative_to((directory / "parser-page-images").resolve())
                            or row.get("source_sha256") != files[0].checksum
                            or row.get("p1_sha256") != expected.get("p1_sha256")
                            or row.get("p3_sha256") != expected.get("p3_sha256")
                            or row.get("canvas") != [page.get("canvas_w"), page.get("canvas_h")]
                            or not path.is_file()
                            or hashlib.sha256(path.read_bytes()).hexdigest() != row.get("sha256")):
                        raise ServiceError(409, "PARSER_PAGE_MISMATCH", "저장 원문과 파서 좌표의 연결이 일치하지 않습니다.")
                    return path
            reuse = directory / "parser-reuse.json"
            if not reuse.is_file():
                break
            value = read_json(reuse)
            parent_id = value.get("parser_source_review_id")
            parent = self.services.reviews.repository.get(parent_id) if isinstance(parent_id, str) else None
            if (value.get("version") != "validated-parent-parser-reuse-v1"
                    or value.get("advertisement_id") != advertisement_id or parent is None
                    or parent.review.advertisement_id != advertisement_id):
                break
            directory = self.root / "runs" / parent_id
        raise ServiceError(503, "PARSER_PAGE_IMAGE_UNAVAILABLE", "파서가 사용한 원문 화면을 확인할 수 없습니다.")

    def validate_request(self, ad, options):
        if ad.product_group not in PRODUCTS:
            raise ServiceError(
                422,
                "PRODUCT_GROUP_REQUIRED",
                "예금·대출·투자 상품군을 확인해 주세요. 이벤트만으로는 상품군을 확정할 수 없습니다.",
            )
        if options.get("include_suggestion") or options.get("include_opinion_draft"):
            raise ServiceError(422, "UNSUPPORTED_OUTPUT", "현재 실행기는 문구 추천·심의 의견 초안을 생성하지 않습니다. 해당 옵션을 꺼 주세요.")
        selected = set(options.get("review_types") or FULL_REVIEW) - {"OCR_QUALITY"}
        if selected != FULL_REVIEW:
            raise ServiceError(422, "FULL_REVIEW_REQUIRED", "선택한 템플릿의 모든 항목을 검토합니다. 전체 검토 범위를 선택해 주세요.")
        if (
            not options.get("parent_review_id")
            and options.get("standard_effective_date") not in (None, date.today())
        ):
            raise ServiceError(422, "FIXED_REGULATION_VERSION", "심의일은 광고 최초 등록일이며, 현재 연결된 템플릿을 사용합니다.")
        files = [f for f in ad.files if f.file_type == "ADVERTISEMENT"]
        if not files or len(files) != len(ad.files):
            raise ServiceError(422, "ADVERTISEMENT_ASSETS_REQUIRED", "자동심의에는 동일 광고를 구성하는 광고 원본 파일만 등록해 주세요. 상품설명서·약관 대조는 아직 연결되지 않았습니다.")
        for file in files:
            if Path(file.original_file_name).suffix.lower() not in {".pdf", ".png", ".jpg", ".jpeg", ".hwp", ".hwpx"}:
                raise ServiceError(422, "FILE_NOT_SUPPORTED", "파서가 지원하지 않는 파일 형식입니다.")

    def persist(self, *, results_changed=False):
        with self.lock:
            results_path = self.root / "web-results.json"
            if results_changed or not results_path.is_file():
                write_json_atomic(
                    results_path,
                    [asdict(row) for row in self.services.results.repository._items],
                )
            value = {"version": 3, "routing": self.routes, "links": self.links,
                      "decisions": self.decisions,
                      "advertisements": [asdict(ad) for ad in list(self.services.repository.advertisements.values())],
                      "reviews": [asdict(b) for b in list(self.services.reviews.repository._items.values())],
                      "results_file": results_path.name}
            # Only local typed dataclasses are serialized; no executable pickle.
            write_json_atomic(self.root / "web-state.json", json.loads(json.dumps(value, default=str)))

    def delete_review(self, current, review_id):
        """Delete one terminal local review without touching its advertisement."""
        if not set(current.roles).intersection({"COMPLIANCE_REVIEWER", "SYSTEM_ADMIN"}):
            raise ServiceError(403, "FORBIDDEN", "준법 검토자 또는 시스템 관리자만 심의 결과를 삭제할 수 있습니다.")
        bundle = self.services.reviews.status(current, review_id, "delete-review")
        if bundle.job.status in {"PENDING", "RUNNING", "RETRY_PENDING", "STALE"}:
            raise ServiceError(409, "REVIEW_IN_PROGRESS", "진행 중인 심의는 중단이 완료된 뒤 삭제할 수 있습니다.")
        ad = self.services.repository.get_advertisement(bundle.review.advertisement_id)
        with self.lock:
            if review_id in self.active:
                raise ServiceError(409, "REVIEW_IN_PROGRESS", "진행 중인 심의는 중단이 완료된 뒤 삭제할 수 있습니다.")
            link = self.links.get(review_id, {})
            targets = [self.root / "runs" / review_id]
            rag_job_id = str(link.get("rag_job_id") or "")
            if rag_job_id:
                targets.append(self.root / "rag-jobs" / rag_job_id)
            for target in targets:
                resolved = target.resolve()
                if target.is_dir() and (self.root.resolve() in resolved.parents):
                    shutil.rmtree(resolved)
            self.links.pop(review_id, None)
            self.decisions.pop(review_id, None)
            self.services.reviews.repository._items.pop(review_id, None)
            self.services.results.repository._items = [
                item for item in self.services.results.repository._items
                if item.review_id != review_id
            ]
            remaining = sorted(
                (item for item in self.services.reviews.repository._items.values()
                 if item.review.advertisement_id == ad.advertisement_id),
                key=lambda item: item.review.review_round,
                reverse=True,
            )
            latest = remaining[0] if remaining else None
            ad.latest_review_id = latest.review.review_id if latest else None
            ad.review_status = latest.review.status if latest else "UPLOADED"
            self.persist(results_changed=True)
        return ad.advertisement_id

    def delete_latest_review(self, current, advertisement_id):
        """Delete the newest review shown by one advertisement list row."""
        reviews = self.services.reviews.list(current, advertisement_id, "delete-latest-review")
        if not reviews:
            raise ServiceError(404, "NOT_FOUND", "삭제할 심의 결과가 없습니다.")
        return self.delete_review(current, reviews[0].review_id)

    def delete_advertisement(self, current, advertisement_id):
        """Delete one local advertisement and every advertisement-owned artifact."""
        if not set(current.roles).intersection({"COMPLIANCE_REVIEWER", "SYSTEM_ADMIN"}):
            raise ServiceError(403, "FORBIDDEN", "준법 검토자 또는 시스템 관리자만 광고를 삭제할 수 있습니다.")
        advertisement = self.services.repository.get_advertisement(advertisement_id)
        if advertisement is None:
            raise ServiceError(404, "NOT_FOUND", "삭제할 광고가 없습니다.")
        reviews = [
            bundle for bundle in self.services.reviews.repository._items.values()
            if bundle.review.advertisement_id == advertisement_id
        ]
        review_ids = {bundle.review.review_id for bundle in reviews}
        if any(
            bundle.job.status in {"PENDING", "RUNNING", "RETRY_PENDING", "STALE"}
            or bundle.review.review_id in self.active
            for bundle in reviews
        ):
            raise ServiceError(409, "REVIEW_IN_PROGRESS", "진행 중인 심의는 중단이 완료된 뒤 광고를 삭제할 수 있습니다.")

        with self.lock:
            reviews = [
                bundle for bundle in self.services.reviews.repository._items.values()
                if bundle.review.advertisement_id == advertisement_id
            ]
            review_ids = {bundle.review.review_id for bundle in reviews}
            if any(
                bundle.job.status in {"PENDING", "RUNNING", "RETRY_PENDING", "STALE"}
                or bundle.review.review_id in self.active
                for bundle in reviews
            ):
                raise ServiceError(409, "REVIEW_IN_PROGRESS", "진행 중인 심의는 중단이 완료된 뒤 광고를 삭제할 수 있습니다.")
            rag_job_ids = {
                str((self.links.get(review_id) or {}).get("rag_job_id") or "")
                for review_id in review_ids
            } - {""}
            fine_hashes = set()
            for rag_job_id in rag_job_ids:
                fine_path = self.root / "rag-jobs" / rag_job_id / "input" / "evidence_fine.jsonl"
                if fine_path.is_file():
                    fine_hashes.add(hashlib.sha256(fine_path.read_bytes()).hexdigest())

            remaining_fine_hashes = set()
            for review_id, link in self.links.items():
                if review_id in review_ids:
                    continue
                rag_job_id = str((link or {}).get("rag_job_id") or "")
                fine_path = self.root / "rag-jobs" / rag_job_id / "input" / "evidence_fine.jsonl"
                if fine_path.is_file():
                    remaining_fine_hashes.add(hashlib.sha256(fine_path.read_bytes()).hexdigest())

            targets = [self.root / "runs" / review_id for review_id in review_ids]
            targets.extend(self.root / "rag-jobs" / rag_job_id for rag_job_id in rag_job_ids)
            for target in targets:
                resolved = target.resolve()
                if target.is_dir() and self.root.resolve() in resolved.parents:
                    shutil.rmtree(resolved)

            cache_dir = self.rag.config.vector_cache_dir
            if cache_dir:
                cache_root = Path(cache_dir).resolve()
                for fine_hash in fine_hashes - remaining_fine_hashes:
                    for pattern in (
                        f"evidence-fine-{fine_hash}.*",
                        f"query-context-{fine_hash}-*.*",
                    ):
                        for cache_file in cache_root.glob(pattern):
                            if cache_file.is_file() and cache_file.resolve().parent == cache_root:
                                cache_file.unlink(missing_ok=True)

            for review_id in review_ids:
                self.links.pop(review_id, None)
                self.decisions.pop(review_id, None)
                self.services.reviews.repository._items.pop(review_id, None)
            self.services.results.repository._items = [
                item for item in self.services.results.repository._items
                if item.review_id not in review_ids
            ]
            files = self.services.repository.delete_advertisement(advertisement_id)
            if files is None:
                raise ServiceError(404, "NOT_FOUND", "삭제할 광고가 없습니다.")
            for file in files:
                self.services.advertisements.storage.delete(file.storage_key)
            self.routes.pop(advertisement_id, None)
            self.persist(results_changed=True)
        return advertisement_id

    def restore(self):
        path = self.root / "web-state.json"
        if not path.is_file():
            return
        data = read_json(path)
        self.routes, self.links = data["routing"], data["links"]
        self.decisions = data.get("decisions", {})
        for row in data["advertisements"]:
            row = restore_dates(row, ["created_at"])
            row["files"] = [AdvertisementFile(**f) for f in row["files"]]
            self.services.repository.advertisements[row["advertisement_id"]] = Advertisement(**row)
        resumable = []
        for row in data["reviews"]:
            review = restore_dates(row["review"], ["requested_at", "completed_at"])
            review["standard_effective_date"] = date.fromisoformat(review["standard_effective_date"])
            job = restore_dates(row["job"], ["timeout_at", "next_retry_at", "updated_at"])
            steps = []
            for step in row["steps"]:
                step = restore_dates(step, ["timeout_at"])
                step["review_step_id"] = UUID(step["review_step_id"])
                steps.append(ReviewStep(**step))
            bundle = ReviewBundle(Review(**review), ReviewJob(**job), steps)
            self.services.reviews.repository._items[bundle.review.review_id] = bundle
            failure = str(bundle.job.failed_reason or "")
            if (
                bundle.job.status == "FAILED"
                and bundle.job.failed_reason_code == "OPERATIONAL_EXECUTION_FAILED"
                and failure.startswith(TRANSIENT_CONNECTION_FAILURE_PREFIXES)
            ):
                # Migrate reviews failed by the former five-minute dependency
                # timeout. These were transport waits, not review failures.
                bundle.review.status = "ANALYSIS_REQUESTED"
                bundle.review.completed_at = None
                bundle.job.status = "RETRY_PENDING"
                bundle.job.failed_reason_code = None
                bundle.job.failed_reason = None
                bundle.job.is_retryable = True
                for step in bundle.steps:
                    if step.status == "FAILED":
                        step.status = "RETRY_PENDING"
                        step.failed_reason_code = None
                self.services.repository.get_advertisement(
                    bundle.review.advertisement_id
                ).review_status = "ANALYSIS_REQUESTED"
                self.links.setdefault(bundle.review.review_id, {}).update(
                    recovered_transient_connection_failure=True,
                )
            if bundle.job.status in {"PENDING", "RUNNING", "RETRY_PENDING"}:
                resumable.append(bundle)
        embedded_results = data.get("results")
        if embedded_results is None:
            results_path = self.root / str(data.get("results_file") or "web-results.json")
            stored_results = read_json(results_path) if results_path.is_file() else []
        else:
            stored_results = embedded_results
        self.services.results.repository._items = []
        for row in stored_results:
            row["evidences"] = tuple(ResultEvidence(**e) for e in row["evidences"])
            row["annotation"] = ResultAnnotation(**row["annotation"]) if row["annotation"] else None
            self.services.results.repository.add(ResultItem(**row))
        self.persist(results_changed=embedded_results is not None)
        for bundle in resumable:
            review_id = bundle.review.review_id
            routing = dict(
                (self.links.get(review_id) or {}).get("routing")
                or self.routes.get(bundle.review.advertisement_id, {})
            )
            self.active.add(review_id)
            self.pool.submit(self.run, bundle, routing)

    def pause_for_shutdown(self):
        """Ask bridge workers to save resumable state during a normal web shutdown."""
        self.stopping.set()
        # Workers observe ``stopping`` at each bridge boundary and persist
        # RETRY_PENDING. Do not make the ASGI shutdown wait on a parser/model
        # call that is already in progress.
        self.pool.shutdown(wait=False)

    def publish(self, message):
        with self.lock:
            if message.review_id in self.active:
                return
            self.active.add(message.review_id)
            bundle = self.services.reviews.repository.get(message.review_id)
            ad = self.services.repository.get_advertisement(bundle.review.advertisement_id)
            ad.latest_review_id, ad.review_status = message.review_id, "ANALYSIS_REQUESTED"
            routing = dict(self.routes.get(ad.advertisement_id, {}))
            for step, name in zip(bundle.steps, STEP_NAMES):
                step.step_name = name
                step.timeout_at = datetime.now(UTC) + timedelta(hours=2)
            bundle.job.timeout_at = datetime.now(UTC) + timedelta(hours=2)
            self.links[message.review_id] = {
                "routing": routing,
                "queued_at": datetime.now(UTC).isoformat(),
                "template_appropriate_judgment_sha256": self.template_appropriate_judgment_sha256,
            }
            self.persist()
            self.pool.submit(self.run, bundle, routing)

    def stage(self, bundle, index):
        with self.lock:
            if bundle.job.status == "CANCELED":
                raise ReviewCanceled("CANCELED_BY_USER")
            if self.stopping.is_set():
                raise ReviewPaused("SERVER_STOPPED")
            bundle.review.status, bundle.job.status = "ANALYZING", "RUNNING"
            bundle.job.current_step = bundle.steps[index].step_code
            bundle.job.progress_rate = round(index / len(bundle.steps) * 100, 1)
            bundle.job.updated_at = datetime.now(UTC)
            for i, step in enumerate(bundle.steps):
                step.status = "COMPLETED" if i < index else "RUNNING" if i == index else "PENDING"
            self.services.repository.get_advertisement(bundle.review.advertisement_id).review_status = "ANALYZING"
            self.persist()

    def wait_for_search_backend(self, bundle):
        """Wait visibly for search transport before consuming parser/model work."""
        if self.rag.config.source_policy == "template-only":
            return  # Template enumeration and ad evidence retrieval do not use the v2 ES index.
        step = next(row for row in bundle.steps if row.step_code == bundle.job.current_step)
        original_name = step.step_name
        waiting = False
        try:
            while True:
                if bundle.job.status == "CANCELED":
                    raise ReviewCanceled("CANCELED_BY_USER")
                try:
                    with urllib.request.urlopen(self.config["es_url"].rstrip("/"), timeout=5) as response:
                        payload = json.load(response)
                    if not isinstance(payload, dict) or "cluster_name" not in payload or "version" not in payload:
                        raise RuntimeError("SEARCH_ENDPOINT_INVALID: 검색 서버 주소의 응답이 Elasticsearch가 아닙니다.")
                    return
                except urllib.error.HTTPError as exc:
                    if exc.code not in {429, 502, 503, 504}:
                        raise RuntimeError(f"SEARCH_ENDPOINT_REJECTED: 검색 서버 HTTP {exc.code}") from exc
                except (urllib.error.URLError, TimeoutError, ConnectionError):
                    pass
                if False:  # Connection loss is a wait state, not a review failure.
                    raise RuntimeError("SEARCH_CONNECTION_UNAVAILABLE: 검색 서버 연결이 5분 동안 복구되지 않았습니다. 검색 터널·서비스를 확인하세요. 기존 파싱 결과는 보존됩니다.")
                if not waiting:
                    with self.lock:
                        step.step_name = original_name + " · 검색 서버 연결 복구 대기"
                        bundle.job.updated_at = datetime.now(UTC)
                        self.persist()
                    waiting = True
                if self.stopping.wait(2):
                    raise ReviewPaused("SERVER_STOPPED")
        finally:
            if waiting:
                with self.lock:
                    step.step_name = original_name
                    self.persist()

    def wait_for_judgment_backends(self, bundle):
        """Wait for directly configured BGE and Gemma HTTP services.

        The search cluster can be healthy while either model endpoint is still
        starting after a Spark reboot.  Detect that state before spending time
        on parsing or submitting a RAG job.  SSH-fallback-only profiles have no
        directly probeable endpoint here and retain the client-level fallback.
        """
        dependencies = []
        model_env = self.config.get("model_env") or {}
        bge_endpoint = str(model_env.get("NH_GPU_BGE_ENDPOINT") or "").rstrip("/")
        ssh_host = self.config.get("dgx_host")
        ssh_key = self.config.get("dgx_key")
        probe_kind = "http"
        if not bge_endpoint and ssh_host and ssh_key:
            bge_endpoint = str(
                model_env.get("NH_GPU_BGE_REMOTE_ENDPOINT")
                or model_env.get("DGX_BGE_ENDPOINT")
                or "http://127.0.0.1:8103"
            ).rstrip("/")
            probe_kind = "ssh"
        if bge_endpoint:
            dependencies.append((
                "EMBEDDING",
                "BGE",
                [(probe_kind, bge_endpoint + "/health")],
                lambda value: isinstance(value, dict)
                and value.get("device") == "cuda"
                and value.get("embedding_model") == "BAAI/bge-m3"
                and value.get("embedding_dimension") == 1024
                and value.get("max_seq_length") == 1024,
            ))
        gemma_endpoint = str(model_env.get("NH_GPU_GEMMA_ENDPOINT") or "")
        probe_kind = "http"
        if not gemma_endpoint and ssh_host and ssh_key:
            gemma_endpoint = str(
                model_env.get("NH_GPU_GEMMA_REMOTE_ENDPOINT")
                or model_env.get("DGX_GEMMA_REMOTE_ENDPOINT")
                or "http://127.0.0.1:8102/v1/chat/completions"
            )
            probe_kind = "ssh"
        if gemma_endpoint:
            parsed = urllib.parse.urlsplit(gemma_endpoint)
            path = parsed.path.rstrip("/")
            if path.endswith("/v1/chat/completions"):
                path = path[: -len("/chat/completions")]
            else:
                path = path.rsplit("/", 1)[0] if "/" in path else "/v1"
            models_url = urllib.parse.urlunsplit(
                (parsed.scheme, parsed.netloc, path.rstrip("/") + "/models", "", "")
            )
            dependencies.append((
                "MODEL",
                "Gemma",
                [(probe_kind, models_url)],
                lambda value: isinstance(value, dict)
                and any(
                    isinstance(row, dict) and row.get("id") == self.config.get("model")
                    for row in value.get("data", [])
                ),
            ))
        for code, label, probes, validator in dependencies:
            self._wait_for_json_dependency(bundle, code, label, probes, validator)

    def _read_ssh_json(self, url):
        remote = (
            "import sys,urllib.request;"
            f"sys.stdout.buffer.write(urllib.request.urlopen({url!r},timeout=10).read())"
        )
        completed = subprocess.run(
            [
                "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                "-i", str(self.config["dgx_key"]), str(self.config["dgx_host"]),
                "python3", "-c", shlex.quote(remote),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=25,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if completed.returncode:
            raise ConnectionError("remote dependency is not ready")
        return json.loads(completed.stdout.decode("utf-8"))

    def _wait_for_json_dependency(self, bundle, code, label, probes, validator):
        step = next(row for row in bundle.steps if row.step_code == bundle.job.current_step)
        original_name = step.step_name
        waiting = False
        try:
            while True:
                if bundle.job.status == "CANCELED":
                    raise ReviewCanceled("CANCELED_BY_USER")
                rejected = []
                for kind, url in probes:
                    try:
                        if kind == "ssh":
                            payload = self._read_ssh_json(url)
                        else:
                            with urllib.request.urlopen(url, timeout=5) as response:
                                payload = json.load(response)
                        if validator(payload):
                            return
                        rejected.append("invalid response")
                    except urllib.error.HTTPError as exc:
                        if exc.code not in {429, 502, 503, 504}:
                            rejected.append(f"HTTP {exc.code}")
                    except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError):
                        pass
                if rejected and len(rejected) == len(probes):
                    raise RuntimeError(
                        f"{code}_ENDPOINT_INVALID: {label} service returned "
                        + ", ".join(rejected)
                    )
                if False:  # Dependency startup may outlive the web request process.
                    raise RuntimeError(
                        f"{code}_CONNECTION_UNAVAILABLE: {label} service did not recover within 5 minutes"
                    )
                if not waiting:
                    with self.lock:
                        step.step_name = original_name + f" · {label} 연결 복구 대기"
                        bundle.job.updated_at = datetime.now(UTC)
                        self.persist()
                    waiting = True
                if self.stopping.wait(2):
                    raise ReviewPaused("SERVER_STOPPED")
        finally:
            if waiting:
                with self.lock:
                    step.step_name = original_name
                    self.persist()

    def cancel(self, actor, review_id, reason):
        """Stop after the current blocking parser/model call returns safely."""
        bundle = self.services.reviews.status(actor, review_id, "operational-cancel")
        with self.lock:
            if bundle.job.status not in {"PENDING", "RUNNING", "RETRY_PENDING", "STALE"}:
                raise ServiceError(409, "REVIEW_NOT_RUNNING", "진행 중인 검토만 중단할 수 있습니다.")
            bundle.job.status = "CANCELED"
            bundle.job.failed_reason_code = "CANCELED_BY_USER"
            bundle.job.failed_reason = reason or "사용자가 검토 중단을 요청했습니다."
            bundle.job.is_retryable = True
            bundle.job.updated_at = datetime.now(UTC)
            bundle.review.status = "REVIEW_CANCELED"
            bundle.review.completed_at = bundle.job.updated_at
            for step in bundle.steps:
                if step.status in {"PENDING", "RUNNING"}:
                    step.status, step.failed_reason_code = "CANCELED", "CANCELED_BY_USER"
            self.services.repository.get_advertisement(bundle.review.advertisement_id).review_status = "UPLOADED"
            self.links.setdefault(review_id, {}).update(
                canceled_at=bundle.job.updated_at.isoformat(),
                cancellation_reason=bundle.job.failed_reason,
            )
            self.active.discard(review_id)
            self.persist()
        return bundle

    def rebuild_result_projection(self, review_id: str) -> int:
        """Recreate viewer annotations from an immutable saved model result.

        This is deliberately a projection-only repair: it never invokes the
        parser, search, or model.  It protects the UI boundary from losing a
        valid parser line reference while serializing a completed review.
        """
        link = self.links.get(review_id) or {}
        result_path = Path(str(link.get("result_file") or ""))
        integrated_path = self.root / "runs" / review_id / "integrated.json"
        if not result_path.is_file() or not integrated_path.is_file():
            raise ServiceError(409, "RESULT_PROJECTION_UNAVAILABLE", "저장된 판정 또는 파싱 결과가 없습니다.")
        bundle = self.services.reviews.repository.get(review_id)
        ad = self.services.repository.get_advertisement(bundle.review.advertisement_id)
        result, document = read_json(result_path), read_json(integrated_path)
        requests_path = result_path.parent / "02_judgment_requests.jsonl"
        requests = [json.loads(line) for line in requests_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        source_file = next(file for file in ad.files if file.file_type == "ADVERTISEMENT")
        ad_results = [row for row in result["ads"] if row["ad_id"] == ad.advertisement_id]
        if not ad_results:
            raise ServiceError(409, "RESULT_PROJECTION_UNAVAILABLE", "저장된 결과에 광고 판정이 없습니다.")
        self.services.results.repository._items = [
            item for item in self.services.results.repository._items
            if item.review_id != review_id
        ]
        for ad_result in ad_results:
            scope_id = ad_result.get("scope_id") or ad_result["ad_id"]
            payloads = [json.loads(row["messages"][1]["content"]) for row in requests if row.get("ad_id") == scope_id]
            rules = {rule["item_id"]: rule for payload in payloads for rule in payload["rules"]}
            evidence = {item["evidence_id"]: item for payload in payloads for item in payload["documents"]}
            self.projector(
                self.services, document,
                [item for item in ad_result["candidates"] if item["status"] == "predicted"],
                rules, evidence, review_id, source_file.file_id,
                review_id.removeprefix("REV-"), model=self.config["model"],
                product_id=ad_result.get("product_id"), product_name=ad_result.get("product_name"),
            )
        self.persist(results_changed=True)
        return sum(
            item.review_id == review_id and item.annotation is not None
            for item in self.services.results.repository._items
        )

    def fail(self, bundle, code, message, *, save=True):
        bundle.job.status, bundle.review.status = "FAILED", "REVIEW_FAILED"
        bundle.job.failed_reason_code, bundle.job.failed_reason = code, message
        bundle.job.updated_at, bundle.job.is_retryable = datetime.now(UTC), True
        for step in bundle.steps:
            if step.status == "RUNNING":
                step.status, step.failed_reason_code = "FAILED", code
        ad = self.services.repository.get_advertisement(bundle.review.advertisement_id)
        ad.review_status = "REVIEW_FAILED"
        if save:
            self.persist()

    def merge_asset_documents(self, ad, asset_documents):
        """Make independently parsed assets one evidence-safe advertisement."""
        if not asset_documents:
            raise ValueError("no parsed advertisement assets")
        pages, candidates, asset_provenance, asset_pages = [], [], [], {}
        relations = []
        page_no = 0
        for file, integrated in asset_documents:
            validate_integrated_input(integrated)
            relations.extend(namespace_structure(integrated.get("relations") or [], file.file_id))
            first_page = page_no + 1
            parser_ad_id = integrated["document"]["ad_id"]
            asset_provenance.append({
                "file_id": file.file_id,
                "file_name": file.original_file_name,
                "parser_doc_id": parser_ad_id,
                "source_parser_contracts": copy.deepcopy((integrated.get("diagnostics") or {}).get("parser_contract_adapter") or {}),
                "p1_sha256": integrated["contract"]["sources"]["p1_sha256"],
                "p3_sha256": integrated["contract"]["sources"]["p3_sha256"],
                "complete_document_read": (integrated.get("quality") or {}).get("complete_document_read"),
            })
            for page in integrated["pages"]:
                page_no += 1
                value = namespace_structure(page, file.file_id)
                value["page_no"] = page_no
                value["source_page_no"] = page["page_no"]
                value["asset_id"] = file.file_id
                value["source_file"] = file.original_file_name
                for region in value.get("regions", []):
                    old_region = str(region["region_id"])
                    region["region_id"] = f"{file.file_id}:{old_region}"
                    region["evidence_id"] = f"{ad.advertisement_id}#asset:{file.file_id}:p{page_no}:{old_region}"
                pages.append(value)
            asset_pages[file.file_id] = {"start": first_page, "end": page_no}
            for candidate in integrated.get("unverified_recovery_candidates") or []:
                value = copy.deepcopy(candidate)
                source_page_no = value.get("page_no")
                if isinstance(source_page_no, int) and source_page_no >= 1:
                    value["source_page_no"] = source_page_no
                    value["page_no"] = first_page + source_page_no - 1
                value["asset_id"] = file.file_id
                value["source_file"] = file.original_file_name
                candidates.append(value)
        hashes = "".join(row["p1_sha256"] + row["p3_sha256"] for row in asset_provenance).encode("utf-8")
        result = {
            "contract": {
                "version": "nh-ad-review-integrated-input-v1",
                "sources": {
                    "p1_contract": "nh-ad-review-evidence-v6",
                    "p3_contract": "nh-ad-review-region-input-v1",
                    "p1_sha256": hashlib.sha256(b"p1" + hashes).hexdigest(),
                    "p3_sha256": hashlib.sha256(b"p3" + hashes).hexdigest(),
                },
                "review_unit": "original parser region; asset identity preserved",
                "final_text_policy": "P3 review_text selected per asset from P1 judge policy",
            },
            "document": {
                "ad_id": ad.advertisement_id,
                "source_file": ad.advertisement_name,
                "file_type": "multi_asset" if len(asset_documents) > 1 else asset_documents[0][1]["document"].get("file_type"),
                "dataset_group": None,
                "input_relative_path": None,
                "routing_metadata": {},
            },
            "pages": pages,
            "relations": relations,
            "unverified_recovery_candidates": candidates,
            "diagnostics": {"assets": asset_provenance, "asset_pages": asset_pages},
            "quality": {
                "line_count": sum(
                    sum(len(region.get("lines") or []) for region in page.get("regions") or [])
                    + len(page.get("unassigned_lines") or [])
                    for page in pages
                ),
                "line_partition_exact": True,
                "region_count": sum(len(page.get("regions") or []) for page in pages),
                "empty_region_count": sum(not str(region.get("final_text") or "").strip() for page in pages for region in page.get("regions") or []),
            },
        }
        validate_integrated_input(result)
        return result

    def parser_intake(self, template_id):
        intake = {"version": "user-template-labeling-v5", "template_id": template_id}
        if self.parser_layout_config.get("contract_profile") == "region-v9":
            revision = self.config.get("parser_revision")
            if not isinstance(revision, str) or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
                raise ValueError("PARSER_REVISION_REQUIRED: region-v9 requires a pinned upstream commit")
            intake.update(version="user-template-labeling-v6", parser_contract_profile="region-v9",
                          parser_revision=revision)
        return intake

    def validate_parser_template(self, p1_path, p3_path, template_id):
        if self.parser_layout_config["runner"] == "nh_parser_fin":
            if self.parser_layout_config.get("contract_profile") == "region-v9":
                p1, p3 = read_json(p1_path), read_json(p3_path)
                if ((p1.get("contract") or {}).get("version"), (p3.get("contract") or {}).get("version")) != (
                    "nh-ad-parse-evidence-v4", "nh-ad-region-review-input-v9"
                ):
                    raise ValueError("PARSER_CONTRACT_MISMATCH: region-v9 requires P1 v4/P3 v9")
            p1_template = read_json(p1_path).get("template") or {}
            p3_template = (read_json(p3_path).get("document") or {}).get("template") or {}
            if p1_template != p3_template:
                raise ValueError("PARSER_TEMPLATE_MISMATCH: nh-parser-fin P1/P3 observations differ")
            # nh-parser-fin currently infers its own template and has no CLI
            # option for the user's selection.  The saved intake value remains
            # authoritative downstream; inferred semantic labels are not
            # promoted to exact evidence by the contract adapter.
            return
        for template in (
            read_json(p1_path).get("template") or {},
            (read_json(p3_path).get("document") or {}).get("template") or {},
        ):
            if template.get("template_id") != template_id or template.get("source") != "user_provided":
                raise ValueError("PARSER_TEMPLATE_MISMATCH: 파서 템플릿이 사용자 선택값과 다릅니다")

    def reuse_parent_parser_output(self, ad, directory, source_by_file, parent_review_id, *, template_id=None):
        """Reuse a terminal parent's complete parser boundary after strict validation.

        This recovery path is only for an immutable rerun of the same
        advertisement. A retry may itself only contain a validated
        ``parser-reuse.json`` pointer, so that audited lineage is followed
        until the review that owns the physical P1/P3 files is reached. It
        never reuses judgments or integrated/RAG outputs.
        """
        if not parent_review_id:
            return None
        files = [file for file in ad.files if file.file_type == "ADVERTISEMENT"]
        source_review_id = parent_review_id
        lineage = []
        seen = set()
        for _ in range(16):
            if source_review_id in seen:
                return None
            seen.add(source_review_id)
            parent = self.services.reviews.repository.get(source_review_id)
            if (
                parent is None
                or parent.review.advertisement_id != ad.advertisement_id
                or parent.job.status not in PARSER_REUSE_PARENT_STATUSES
            ):
                return None
            lineage.append(source_review_id)
            parent_directory = self.root / "runs" / source_review_id
            if template_id is not None:
                intake_path = parent_directory / "parser-intake.json"
                if not intake_path.is_file() or read_json(intake_path) != self.parser_intake(template_id):
                    return None
            parent_output = parent_directory / "parser"
            if self.parser_layout_config["runner"] == "nh_parsing_test_batch":
                parent_output = parent_output / "upload"
            p1s, p3s = self.parser_outputs(parent_output)
            p3_by_name = {
                (path.name.removesuffix(".p3.json") + ".p1.json"
                 if self.parser_layout_config["runner"] == "nh_parser_fin" else path.name): path
                for path in p3s
            }
            if len(p1s) == len(files) and set(path.name for path in p1s) == set(p3_by_name):
                break
            reuse_path = parent_directory / "parser-reuse.json"
            if not reuse_path.is_file():
                return None
            try:
                reuse = read_json(reuse_path)
            except (OSError, ValueError, json.JSONDecodeError):
                return None
            if (
                reuse.get("version") != "validated-parent-parser-reuse-v1"
                or reuse.get("advertisement_id") != ad.advertisement_id
                or not isinstance(reuse.get("parser_source_review_id") or reuse.get("parent_review_id"), str)
            ):
                return None
            source_review_id = reuse.get("parser_source_review_id") or reuse["parent_review_id"]
        else:
            return None
        assets = []
        output_hashes = []
        for file in files:
            source = source_by_file[file.file_id]
            matches = [path for path in p1s if self.parser_output_name_matches(path, source)]
            if len(matches) != 1:
                return None
            p1_path = matches[0]
            p3_path = p3_by_name[p1_path.name]
            if template_id is not None:
                try:
                    self.validate_parser_template(p1_path, p3_path, template_id)
                except ValueError:
                    return None
            try:
                document = self.read_parser_asset(p1_path, p3_path)
            except (OSError, ValueError):
                return None
            assets.append((file, document))
            output_hashes.append({
                "file_id": file.file_id,
                "source_sha256": file.checksum,
                "p1_sha256": hashlib.sha256(p1_path.read_bytes()).hexdigest(),
                "p3_sha256": hashlib.sha256(p3_path.read_bytes()).hexdigest(),
            })
        integrated = self.merge_asset_documents(ad, assets)
        write_json_atomic(directory / "parser-reuse.json", {
            "version": "validated-parent-parser-reuse-v1",
            "parent_review_id": parent_review_id,
            "parser_source_review_id": source_review_id,
            "review_lineage": lineage,
            "advertisement_id": ad.advertisement_id,
            "reason": "terminal parent parser outputs complete; downstream stages rerun",
            "assets": output_hashes,
        })
        (directory / "parser.log").write_text(
            f"원본 검토 {source_review_id}의 P1/P3를 부모 재실행 {parent_review_id}에서 "
            "원본 체크섬·계약·줄 소유권 검증 후 재사용했습니다.\n",
            encoding="utf-8",
        )
        return integrated

    def parse(self, ad, directory, *, parent_review_id=None, template_id=None):
        if not template_id:
            raise ValueError("PARSER_TEMPLATE_REQUIRED: 사용자 선택 템플릿이 필요합니다")
        # Validate runner support before copying assets or attempting reuse.
        self.parser_command(directory / "source", directory / "parser", template_id=template_id)
        integrated_path = directory / "integrated.json"
        intake_path = directory / "parser-intake.json"
        if integrated_path.is_file() and intake_path.is_file():
            try:
                resumed = read_json(integrated_path)
                validate_integrated_input(resumed)
                source_dir = directory / "source"
                source_matches = {
                    file.file_id: [
                        path for path in source_dir.glob(f"{file.file_id}_*")
                        if hashlib.sha256(path.read_bytes()).hexdigest() == file.checksum
                    ]
                    for file in ad.files if file.file_type == "ADVERTISEMENT"
                }
                if (
                    read_json(intake_path) == self.parser_intake(template_id)
                    and resumed.get("document", {}).get("ad_id") == ad.advertisement_id
                    and source_matches
                    and all(len(paths) == 1 for paths in source_matches.values())
                ):
                    layout_path = directory / "parser-layout.json"
                    if layout_path.is_file():
                        self.attach_rendered_line_observation(resumed, read_json(layout_path))
                    return resumed
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                pass
        write_json_atomic(directory / "parser-intake.json", self.parser_intake(template_id))
        files = [file for file in ad.files if file.file_type == "ADVERTISEMENT"]
        source_dir = directory / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        source_by_file = {}
        for file in files:
            filename = Path(file.original_file_name.replace("\\", "/")).name
            if filename in {"", ".", ".."}:
                raise ValueError("invalid original filename")
            source = source_dir / f"{file.file_id}_{filename}"
            with self.services.advertisements.storage.open(file.storage_key) as stream:
                body = stream.read()
            if hashlib.sha256(body).hexdigest() != file.checksum:
                raise ValueError("stored source checksum mismatch")
            source.write_bytes(body)
            source_by_file[file.file_id] = source
        reused = self.reuse_parent_parser_output(
            ad, directory, source_by_file, parent_review_id,
            template_id=template_id,
        )
        if reused is not None:
            layout = self.prepare_optional_parser_layout(source_by_file[files[0].file_id], directory, reused)
            if layout:
                self.attach_rendered_line_observation(reused, layout)
            return reused
        output = directory / "parser"
        if len(files) > 1:
            completed, missing, batch_returncode = self.parse_assets_in_parallel(files, source_by_file, directory, template_id=template_id)
        else:
            with self.parser_slots:
                batch_returncode = self.execute_parser(source_dir, output, directory / "parser.log", template_id=template_id)
            completed, missing = self.parsed_assets(files, source_by_file, output)
            for file in files:
                if file.file_id in completed:
                    p1_path, p3_path = completed[file.file_id]
                    self.capture_parser_page_images(file, p1_path, p3_path, directory)
        retry_attempts = []
        if missing:
            recovered, retry_attempts = self.retry_missing_parser_assets(files, source_by_file, missing, directory, template_id=template_id)
            completed.update(recovered)
            missing = {file_id: reason for file_id, reason in missing.items() if file_id not in recovered}
        if missing:
            names = [
                f"{next(file.original_file_name for file in files if file.file_id == file_id)} ({reason})"
                for file_id, reason in missing.items()
            ]
            write_json_atomic(directory / "parser-failure.json", {
                "version": "parser-asset-failure-v1",
                "batch_returncode": batch_returncode,
                "failed_assets": [{"file_id": file_id, "reason": reason} for file_id, reason in missing.items()],
                "retry_attempts": retry_attempts,
            })
            raise RuntimeError("PARSER_ASSET_FAILED: " + "; ".join(names) + ". 성공 파일은 보존됐으며 실패 파일만 1회 재시도했습니다.")
        assets = []
        for file in files:
            p1_path, p3_path = completed[file.file_id]
            self.validate_parser_template(p1_path, p3_path, template_id)
            assets.append((file, combine(p1_path, p3_path)))
        integrated = self.merge_asset_documents(ad, assets)
        # Parser-layout is a presentation artifact. A temporary rendering or
        # visual-parser failure must not discard an otherwise valid review.
        layout = self.prepare_optional_parser_layout(source_by_file[files[0].file_id], directory, integrated)
        if layout:
            self.attach_rendered_line_observation(integrated, layout)
        return integrated

    def apply_intake_scopes(self, ad, document, intake):
        """Convert saved asset/page scopes into parser evidence ownership."""
        intake = validate_ad_intake(intake)
        media_codes = list(intake.get("media_codes") or [])
        if media_codes:
            # The registration UI calls this value 광고유형, while the
            # judgment contract calls the same delivery/creative classification
            # media_type.  Preserve the user's selection as confirmed intake
            # metadata instead of silently dropping it between the two schemas.
            document["document"].setdefault("routing_metadata", {})["media_type"] = {
                "value": media_codes[0] if len(media_codes) == 1 else media_codes,
                "source": "web_user",
                "status": "provided",
            }
        asset_pages = (document.get("diagnostics") or {}).get("asset_pages") or {}
        evidence_by_asset = {}
        for page in document["pages"]:
            for region in page.get("regions") or []:
                asset_id = str(region["evidence_id"]).split(":p", 1)[0].removeprefix(f"{ad.advertisement_id}#asset:")
                evidence_by_asset.setdefault(asset_id, []).append((page["page_no"], region["evidence_id"]))

        def evidence(scopes):
            rows = []
            for scope in scopes:
                asset_id = scope["asset_id"]
                ranges = scope["page_ranges"]
                if ranges is None:
                    rows.extend(item[1] for item in evidence_by_asset.get(asset_id, []))
                    continue
                if any(page.get("parse_route") == "native_hwp"
                       and asset_pages[asset_id]["start"] <= page["page_no"] <= asset_pages[asset_id]["end"]
                       for page in document["pages"]):
                    raise ValueError("HWP_PHYSICAL_SCOPE_UNAVAILABLE: native text cannot be assigned to physical page ranges")
                offset = asset_pages[asset_id]["start"] - 1
                for start, end in ((item["start"], item["end"]) for item in ranges):
                    rows.extend(item[1] for item in evidence_by_asset.get(asset_id, []) if offset + start <= item[0] <= offset + end)
            return list(dict.fromkeys(rows))

        products = []
        for product in intake["products"]:
            classification = product["product_classification_code"]
            selected, context, complete = resolve_product_templates(product, available_templates=self.templates)
            products.append({
                "product_id": product["product_id"],
                "product_name": product.get("product_name") or product["product_id"],
                "routing_metadata": {
                    "product_group": {"value": product["product_group"], "source": "web_user", "status": "provided"},
                    "product_subtype": {"value": classification, "source": "web_user", "status": "provided"},
                    "template_id": {"value": classification, "source": "product_classification_mapping", "status": "verified"},
                    "selected_templates": {"value": selected, "source": "web_user_product_composition", "status": "provided"},
                    "product_context": {"value": context or "STANDALONE", "source": "product_classification_mapping", "status": "verified"},
                    "underlying_products_complete": {"value": complete, "source": "web_user", "status": "provided"},
                },
                "evidence_ids": evidence(product["asset_scopes"]),
            })
        document["document"]["products"] = products
        document["document"]["shared_evidence_ids"] = evidence(intake["shared_asset_scopes"])
        validate_integrated_input(document)
        return document

    def prepare_optional_parser_layout(self, source, directory, integrated):
        """A preview failure cannot discard validated semantic source text."""
        try:
            return self.prepare_parser_layout(source, directory, integrated)
        except Exception as exc:  # retried lazily by the parser-layout endpoint
            write_json_atomic(directory / "parser-layout-error.json",
                              {"code": "PARSER_LAYOUT_UNAVAILABLE", "detail": str(exc)})
            return None

    @staticmethod
    def attach_rendered_line_observation(integrated, layout):
        """Record only a complete, exact semantic-line to rendered-line projection."""
        assets = (integrated.get("diagnostics") or {}).get("asset_pages") or {}
        if len(assets) != 1:
            return integrated
        asset_id = next(iter(assets))
        projected = with_rendered_line_locations(integrated, layout, asset_id)
        mappings = projected.get("display_line_locations") or {}
        refs = [
            line.get("line_ref")
            for page in integrated.get("pages", [])
            for region in page.get("regions", [])
            for line in region.get("lines", [])
            if line.get("line_ref") and str(line.get("text") or "").strip()
        ]
        if not refs or any(ref not in mappings for ref in refs):
            return integrated
        integrated.setdefault("diagnostics", {})["rendered_line_projection"] = {
            "verified": True,
            "method": "EXACT_RENDERED_TEXT",
            "semantic_line_count": len(refs),
            "rendered_line_count": sum(len(mappings[ref]) for ref in refs),
        }
        return integrated

    def prepare_parser_layout(self, source, directory, integrated):
        """Build the visual parser projection used by the bbox demonstration."""
        target = directory / "parser-layout.json"
        if target.is_file():
            existing = read_json(target)
            if all(
                "asset_id" in page and "source_page_no" in page
                for page in existing.get("pages", [])
            ):
                return existing
        direct = parser_layout(integrated, source="P1+P3 integrated parser output")
        if (source.suffix.lower() in {".hwp", ".hwpx"}
                and len((integrated.get("diagnostics") or {}).get("asset_pages") or {}) == 1
                and any(page.get("parse_route") == "native_hwp" for page in integrated.get("pages", []))):
            from hwp_pdf_layout import load_or_render
            layout = load_or_render(source, directory, self.services.hwp_preview)
            asset_id = next(iter(integrated["diagnostics"]["asset_pages"]))
            for page in layout["pages"]:
                page["asset_id"] = asset_id
            write_json_atomic(target, layout)
            return layout
        if direct["counts"]["lines"] or direct["counts"]["regions"]:
            write_json_atomic(target, direct)
            return direct
        if source.suffix.lower() not in {".hwp", ".hwpx"}:
            write_json_atomic(target, direct)
            return direct

        # The current HWP semantic parser preserves text/style but has no page
        # canvas.  Render the same source to PDF, then run the parser's visual
        # route solely for demonstrable region/line coordinates.  This visual
        # projection never replaces the semantic text used by search/judgment.
        with self.layout_lock, tempfile.TemporaryDirectory(prefix="nh-parser-layout-") as temp:
            if target.is_file():
                return read_json(target)
            visual_input = Path(temp) / "input"
            visual_input.mkdir()
            pdf = visual_input / "rendered-original.pdf"
            pdf.write_bytes(convert_hwp_to_pdf(source.read_bytes(), source.name))
            output = directory / "parser-visual"
            env = dict(os.environ)
            env.update(self.config.get("parser_env", {}))
            env["REGION_READING_MODE"] = "off"
            env["PYTHONIOENCODING"] = "utf-8"
            command = self.parser_command(visual_input, output, visual=True)
            with (directory / "parser-visual.log").open("w", encoding="utf-8") as log:
                result = subprocess.run(
                    command,
                    cwd=self.config["parser_cwd"],
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=3600,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            raw_root = output / "visual" if self.parser_layout_config["runner"] == "nh_parsing_test_batch" else output
            outputs = self.parser_raw_outputs(raw_root)
            if result.returncode or len(outputs) != 1:
                raise RuntimeError("PARSER_VISUAL_LAYOUT_FAILED: HWP bbox 보강에 실패했습니다.")
            visual = read_json(outputs[0])
            layout = parser_layout(visual, source="HWP 200-DPI render + parser visual projection")
            if not layout["counts"]["regions"]:
                raise RuntimeError("PARSER_VISUAL_LAYOUT_EMPTY: 표시할 파서 bbox가 없습니다.")
            write_json_atomic(target, layout)
            return layout

    def review_parser_layout(self, review_id):
        bundle = self.services.reviews.repository.get(review_id)
        ad = self.services.repository.get_advertisement(bundle.review.advertisement_id)
        directory = self.root / "runs" / review_id
        target = directory / "parser-layout.json"
        if target.is_file():
            existing = read_json(target)
            if all(
                "asset_id" in page and "source_page_no" in page
                for page in existing.get("pages", [])
            ):
                return existing
        integrated_path = directory / "integrated.json"
        if not integrated_path.is_file():
            raise ServiceError(409, "PARSER_LAYOUT_PENDING", "파서 결과가 아직 준비되지 않았습니다.")
        file = next(f for f in ad.files if f.file_type == "ADVERTISEMENT")
        source_dir = directory / "source"
        source = source_dir / Path(file.original_file_name.replace("\\", "/")).name
        if not source.is_file():
            stored_sources = sorted(source_dir.glob(f"{file.file_id}_*"))
            if stored_sources:
                source = stored_sources[0]
            else:
                raise ServiceError(404, "PARSER_SOURCE_MISSING", "파서 원본을 찾을 수 없습니다.")
        return self.prepare_parser_layout(source, directory, read_json(integrated_path))

    def run(self, bundle, routing):
        directory = self.root / "runs" / bundle.review.review_id
        directory.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        if os.name == "nt":
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
        try:
            if bundle.job.status == "CANCELED":
                raise ReviewCanceled("CANCELED_BY_USER")
            if self.stopping.is_set():
                raise ReviewPaused("SERVER_STOPPED")
            self.stage(bundle, 0)
            self.wait_for_search_backend(bundle)
            self.wait_for_judgment_backends(bundle)
            ad = self.services.repository.get_advertisement(bundle.review.advertisement_id)
            self.stage(bundle, 1)
            document = self.parse(
                ad,
                directory,
                parent_review_id=bundle.review.parent_review_id,
                template_id=routing.get("internal_template_id"),
            )
            if bundle.job.status == "CANCELED":
                raise ReviewCanceled("CANCELED_BY_USER")
            if routing.get("intake"):
                document = self.apply_intake_scopes(ad, document, routing["intake"])
            parse_seconds = time.monotonic() - started
            self.stage(bundle, 2)
            write_json_atomic(directory / "integrated.json", document)
            overrides = {"product_group": {"value": PRODUCTS[ad.product_group], "source": "web_user", "status": "provided"}}
            if routing.get("internal_template_id"):
                overrides["product_subtype"] = {
                    "value": routing["product_classification_code"],
                    "source": "web_user",
                    "status": "provided",
                }
                overrides["template_id"] = {
                    "value": routing["internal_template_id"],
                    "source": "product_classification_mapping",
                    "status": "verified",
                }
            # No automatic promotion of parser/filename template or ambiguous media metadata.
            self.stage(bundle, 3)
            self.wait_for_search_backend(bundle)
            self.wait_for_judgment_backends(bundle)
            job = self.submit_rag({"schema_version": "operational-review-request-v1", "client_request_id": bundle.review.review_id,
                                   "review_date": registration_review_date(ad.created_at),
                                   "review_date_basis": "advertisement_registration_date",
                                   "document": document, "routing_overrides": overrides, "execute_model": True})
            with self.lock:
                self.links[bundle.review.review_id].update(rag_job_id=job["job_id"], parse_seconds=round(parse_seconds, 3))
            self.stage(bundle, 4)
            while job["status"] not in TERMINAL_STATES:
                if bundle.job.status == "CANCELED":
                    raise ReviewCanceled("CANCELED_BY_USER")
                if self.stopping.wait(2):
                    raise ReviewPaused("SERVER_STOPPED")
                job = self.rag.store.read(job["job_id"])
                checkpoint = self.rag.store.directory(job["job_id"]) / f"attempt-{job['attempt']}" / "03_judgment_responses.json.checkpoint.json"
                if checkpoint.is_file():
                    try:
                        completed = read_json(checkpoint)["completed_logical_requests"]
                    except (OSError, ValueError, KeyError):
                        continue  # A diagnostic read must not interrupt model execution.
                    label = f"하이브리드 검색·Gemma 판정 (응답 저장 {completed}묶음)"
                    if bundle.steps[4].step_name != label:
                        bundle.steps[4].step_name = label
                        bundle.job.updated_at = datetime.now(UTC)
                        self.persist()
            if job["status"] not in {"COMPLETED", "COMPLETED_WITH_WARNINGS"}:
                raise RuntimeError(f"RAG_{job['status']}: 일부 결과가 미완료입니다. 성공한 원출력은 작업 폴더에 보존됩니다.")
            self.stage(bundle, 5)
            result = self.rag.result(job["job_id"])
            root = self.rag.store.directory(job["job_id"])
            requests_path = root / f"attempt-{job['attempt']}" / "02_judgment_requests.jsonl"
            requests = [json.loads(line) for line in requests_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            ad_results = [a for a in result["ads"] if a["ad_id"] == ad.advertisement_id]
            if not ad_results:
                raise RuntimeError("RAG result does not contain the submitted advertisement")
            candidates = [
                candidate
                for ad_result in ad_results
                for candidate in ad_result["candidates"]
                if candidate["status"] == "predicted"
            ]
            source_file = next(f for f in ad.files if f.file_type == "ADVERTISEMENT")
            with self.lock:
                if bundle.job.status == "CANCELED":
                    raise ReviewCanceled("CANCELED_BY_USER")
                for ad_result in ad_results:
                    scope_id = ad_result.get("scope_id") or ad_result["ad_id"]
                    scoped_requests = [row for row in requests if row.get("ad_id") == scope_id]
                    scoped_payloads = [json.loads(row["messages"][1]["content"]) for row in scoped_requests]
                    scoped_rules = {r["item_id"]: r for p in scoped_payloads for r in p["rules"]}
                    scoped_evidence = {d["evidence_id"]: d for p in scoped_payloads for d in p["documents"]}
                    scoped_candidates = [
                        candidate
                        for candidate in ad_result["candidates"]
                        if candidate["status"] == "predicted"
                    ]
                    self.projector(
                        self.services,
                        document,
                        scoped_candidates,
                        scoped_rules,
                        scoped_evidence,
                        bundle.review.review_id,
                        source_file.file_id,
                        bundle.review.review_id.removeprefix("REV-"),
                        model=self.config["model"],
                        product_id=ad_result.get("product_id"),
                        product_name=ad_result.get("product_name"),
                    )
                # Rebuild from the immutable saved result before completion is
                # exposed.  This makes the persisted viewer projection the
                # source-of-truth output and prevents a transient in-memory
                # projection from silently dropping parser annotations.
                self.links[bundle.review.review_id]["result_file"] = str(root / job["result_file"])
                located_annotations = self.rebuild_result_projection(bundle.review.review_id)
                output_failures = sum(
                    1 for row in ad_results for candidate in row.get("candidates", [])
                    if candidate.get("status") == "OUTPUT_FAILURE"
                )
                bundle.review.status, bundle.job.status = "REVIEW_COMPLETED", ("COMPLETED_WITH_WARNINGS" if output_failures else "COMPLETED")
                bundle.review.completed_at = bundle.job.updated_at = datetime.now(UTC)
                bundle.review.standard_version_ids = ("STDVER-V2",)
                bundle.job.progress_rate, bundle.job.is_retryable = 100, bool(output_failures)
                has_pending = output_failures or any(
                    row.get("review_candidates") or any(
                        rule.get("reason") != "routing did not select this rule's template section"
                        for rule in row.get("deferred_rules", [])
                    )
                    for row in ad_results
                )
                risk = "HIGH" if any(c["judgment"]["verdict"] == "VIOLATION" for c in candidates) else "CHECK_REQUIRED" if has_pending or any(c["judgment"]["verdict"] == "UNDETERMINED" for c in candidates) else "LOW"
                bundle.review.overall_risk_level = ad.overall_risk_level = risk
                ad.review_status = "REVIEW_COMPLETED"
                for step in bundle.steps:
                    step.status = "COMPLETED"
                self.links[bundle.review.review_id].update(total_seconds=round(time.monotonic()-started, 3),
                    result_file=str(root / job["result_file"]), completed_at=bundle.review.completed_at.isoformat(),
                    predicted_count=len(candidates),
                    located_annotation_count=located_annotations,
                    output_failure_count=output_failures,
                    partial_result_warning=(f"규칙 {output_failures}건은 모델 출력 계약 실패로 결과를 생성하지 못했습니다. 해당 건은 임의로 판단불가 처리하지 않았습니다." if output_failures else None),
                    deferred_count=sum(len(row.get("deferred_rules", [])) for row in ad_results),
                    deferred_rules=[rule for row in ad_results for rule in row.get("deferred_rules", [])])
                self.persist()
        except ReviewCanceled:
            # Cancellation is persisted before this worker observes it.
            pass
        except ReviewPaused:
            # A web-process shutdown or tunnel maintenance is not a review
            # failure. Keep the same review ID and let restore() resume it.
            with self.lock:
                now = datetime.now(UTC)
                bundle.review.status = "ANALYSIS_REQUESTED"
                bundle.review.completed_at = None
                bundle.job.status = "RETRY_PENDING"
                bundle.job.updated_at = now
                bundle.job.failed_reason_code = None
                bundle.job.failed_reason = None
                bundle.job.is_retryable = True
                for step in bundle.steps:
                    if step.status == "RUNNING":
                        step.status = "RETRY_PENDING"
                        step.failed_reason_code = None
                ad = self.services.repository.get_advertisement(bundle.review.advertisement_id)
                ad.review_status = "ANALYSIS_REQUESTED"
                self.links.setdefault(bundle.review.review_id, {}).update(
                    paused_at=now.isoformat(),
                    pause_reason="SERVER_STOPPED",
                )
                self.persist()
        except Exception as exc:
            import traceback
            (directory / "failure.log").write_text(traceback.format_exc(), encoding="utf-8")
            self.fail(bundle, "OPERATIONAL_EXECUTION_FAILED", str(exc)[:400])
        finally:
            with self.lock:
                self.active.discard(bundle.review.review_id)
            if os.name == "nt":
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)

    def submit_rag(self, request):
        """Resume a failed idempotent RAG job instead of replaying its failure."""
        job = self.rag.submit(request)
        if job.get("idempotent_replay") and job["status"] in {"FAILED", "INTERRUPTED"}:
            job = self.rag.retry(job["job_id"])
        return job

    def install(self, backend):
        def actor(request):
            header = request.headers.get("authorization", "")
            return self.services.auth.authenticate(header.removeprefix("Bearer "))

        @backend.get("/operational/capabilities")
        async def capabilities(request: Request):
            actor(request)
            return {"enabled": True, "productClassifications": self.product_classifications,
                    "productClassificationSource": {
                        key: value for key, value in self.template_source.items() if key != "path"
                    },
                    "regulation": ("내부 심의 템플릿 + 규제목록 v2" if
                                   self.rag.config.source_policy == "template-plus-v2" else
                                   "내부 심의 템플릿"),
                    "sourcePolicy": self.rag.config.source_policy,
                    "productContexts": product_contexts(),
                    "evidencePolicy": "LABEL_LEXICAL_AND_LEXICAL_BASELINE",
                    "progressMeaning": "완료한 단계 비율이며 남은 시간의 비율이 아닙니다."}

        @backend.put("/operational/advertisements/{advertisement_id}/routing")
        async def routing(advertisement_id: str, request: Request):
            current = actor(request)
            ad = self.services.advertisements.get(current, advertisement_id, "local-routing")
            body = await request.json()
            expected_fields = {"product_classification_code"}
            if not isinstance(body, dict) or set(body) != expected_fields:
                raise ServiceError(422, "INVALID_ROUTING", "상세 상품군을 지정해야 합니다.")
            classification = body["product_classification_code"]
            if not isinstance(classification, str) or not classification:
                raise ServiceError(422, "INVALID_PRODUCT_CLASSIFICATION", "상세 상품군을 선택해 주세요.")
            if classification not in self.templates or not classification.startswith(PRODUCTS.get(ad.product_group, "!")):
                raise ServiceError(422, "INVALID_PRODUCT_CLASSIFICATION", "상품군에 맞는 상세 상품군을 선택해 주세요.")
            with self.lock:
                self.routes[advertisement_id] = {
                    "product_classification_code": classification,
                    "internal_template_id": classification,
                }
                self.persist()
            return {"saved": True}

        @backend.get("/operational/review-worklist")
        async def review_worklist(request: Request):
            actor(request)
            plans_path = self.rag.config.canonical_plans_path
            if not plans_path:
                raise ServiceError(503, 'REVIEW_WORKLIST_UNAVAILABLE', '정본 기준 설정을 확인해야 합니다.')
            worklist_path = Path(plans_path).parent / 'review-worklist-v1.json'
            if not worklist_path.is_file():
                raise ServiceError(503, 'REVIEW_WORKLIST_UNAVAILABLE', '구조화 작업대장이 아직 연결되지 않았습니다.')
            value = read_json(worklist_path)
            if value.get('canonical_source_binding_sha256') != read_json(Path(plans_path)).get('source_binding_sha256'):
                raise ServiceError(503, 'REVIEW_WORKLIST_SOURCE_CHANGED', '정본 변경에 맞춰 작업대장을 갱신해야 합니다.')
            return {**value, 'sourcePolicy': self.rag.config.source_policy}

        @backend.put("/operational/advertisements/{advertisement_id}/intake")
        async def intake(advertisement_id: str, request: Request):
            current = actor(request)
            ad = self.services.advertisements.get(current, advertisement_id, "local-intake")
            body = await request.json()
            try:
                value = validate_ad_intake(body)
            except ValueError as exc:
                raise ServiceError(422, "INVALID_AD_INTAKE", str(exc)) from exc
            expected_assets = {file.file_id for file in ad.files if file.file_type == "ADVERTISEMENT"}
            actual_assets = {row["asset_id"] for row in value["assets"]}
            if actual_assets != expected_assets:
                raise ServiceError(422, "INVALID_AD_INTAKE", "등록된 광고 원본 파일과 자산 범위가 일치하지 않습니다.")
            for product in value["products"]:
                code = product["product_classification_code"]
                prefix = product["product_group"]
                if code not in self.templates or not code.startswith(prefix):
                    raise ServiceError(422, "INVALID_PRODUCT_CLASSIFICATION", "상품군에 맞는 상세 상품군을 선택해 주세요.")
                try:
                    resolve_product_templates(product, available_templates=self.templates)
                except ValueError as exc:
                    raise ServiceError(422, "INVALID_PRODUCT_CONTEXT", str(exc)) from exc
            with self.lock:
                current_route = dict(self.routes.get(advertisement_id, {}))
                current_route["intake"] = value
                self.routes[advertisement_id] = current_route
                self.persist()
            return {"saved": True}

        @backend.get("/operational/reviews/{review_id}/execution")
        async def execution(review_id: str, request: Request):
            self.services.reviews.status(actor(request), review_id, "local-execution")
            link = dict(self.links.get(review_id, {}))
            if link.get("result_file") and "deferred_rules" not in link:
                result = read_json(link["result_file"])
                ad = result["ads"][0]
                link["deferred_rules"] = ad.get("deferred_rules", [])
                link["deferred_count"] = len(link["deferred_rules"])
            return {k: v for k, v in link.items() if k != "result_file"}

        @backend.get("/operational/reviews/{review_id}/export.json")
        async def export_review_json(review_id: str, request: Request):
            current = actor(request)
            bundle = self.services.reviews.status(current, review_id, "export-review-result")
            if bundle.review.status != "REVIEW_COMPLETED":
                raise ServiceError(409, "REVIEW_NOT_COMPLETED", "완료된 검토 결과만 내보낼 수 있습니다.")
            ad = self.services.repository.get_advertisement(bundle.review.advertisement_id)
            workspace = await result_workspace(review_id, request)
            link = self.links.get(review_id, {})
            result_file = link.get("result_file")
            raw_result = read_json(result_file) if result_file and Path(result_file).exists() else {}
            payload = {
                "schema_version": "operational-review-export-v2",
                "review": {"review_id": review_id, "advertisement_id": ad.advertisement_id,
                           "advertisement_name": ad.advertisement_name, "completed_at": bundle.review.completed_at},
                "results": workspace["rows"],
                "review_candidates": workspace["review_candidate_rows"],
                "deferred_rules": workspace["deferred_rules"],
                "excluded_rows": workspace["excluded_rows"],
                "execution_omissions": workspace["execution_omissions"],
                "extraction_status": workspace["extraction_status"],
                "source_results": [row for row in raw_result.get("ads", [])
                                   if row["ad_id"] == ad.advertisement_id],
                "execution": {
                    "status": bundle.job.status,
                    "output_failure_count": workspace["output_failure_count"],
                    "output_failure_pairs": workspace["output_failure_pairs"],
                    "partial_result_warning": link.get("partial_result_warning"),
                    "deferred_count": len(workspace["deferred_rules"]),
                },
            }
            return JSONResponse(json.loads(json.dumps(payload, default=str)), headers={
                "Content-Disposition": f'attachment; filename="review-{review_id}.json"',
            })

        @backend.post("/operational/reviews/{review_id}/rebuild-annotations")
        async def rebuild_annotations(review_id: str, request: Request):
            current = actor(request)
            if not set(current.roles).intersection({"COMPLIANCE_REVIEWER", "SYSTEM_ADMIN"}):
                raise ServiceError(403, "FORBIDDEN", "결과 위치 복구 권한이 없습니다.")
            bundle = self.services.reviews.status(current, review_id, "rebuild-result-annotations")
            if bundle.review.status != "REVIEW_COMPLETED":
                raise ServiceError(409, "REVIEW_NOT_COMPLETED", "완료된 검토 결과만 위치를 복구할 수 있습니다.")
            with self.lock:
                count = self.rebuild_result_projection(review_id)
            return {"review_id": review_id, "located_annotations": count}

        @backend.post("/operational/reviews/{review_id}/cancel")
        async def cancel_review(review_id: str, request: Request):
            current = actor(request)
            body = await request.json()
            if not isinstance(body, dict) or set(body) - {"reason"}:
                raise ServiceError(422, "INVALID_CANCELLATION", "중단 사유만 입력할 수 있습니다.")
            reason = str(body.get("reason") or "").strip()
            if len(reason) > 1000:
                raise ServiceError(422, "INVALID_CANCELLATION", "중단 사유는 1,000자 이하여야 합니다.")
            bundle = self.cancel(current, review_id, reason)
            return {"review_id": bundle.review.review_id, "job_status": bundle.job.status,
                    "review_status": bundle.review.status, "message": bundle.job.failed_reason}

        @backend.delete("/operational/reviews/{review_id}", status_code=204)
        async def delete_review(review_id: str, request: Request):
            self.delete_review(actor(request), review_id)
            return None

        @backend.delete("/operational/advertisements/{advertisement_id}/latest-review", status_code=204)
        async def delete_latest_review(advertisement_id: str, request: Request):
            self.delete_latest_review(actor(request), advertisement_id)
            return None

        @backend.delete("/operational/advertisements/{advertisement_id}", status_code=204)
        async def delete_advertisement(advertisement_id: str, request: Request):
            self.delete_advertisement(actor(request), advertisement_id)
            return None

        @backend.get("/operational/reviews/{review_id}/parser-layout")
        async def review_parser_layout(review_id: str, request: Request):
            actor(request)
            self.services.reviews.status(actor(request), review_id, "local-parser-layout")
            try:
                layout = self.review_parser_layout(review_id)
                integrated_path = self.root / "runs" / review_id / "integrated.json"
                integrated = read_json(integrated_path) if integrated_path.is_file() else {}
                return self.with_parser_preview_paths(review_id, layout, integrated)
            except ServiceError:
                raise
            except Exception as exc:
                raise ServiceError(503, "PARSER_LAYOUT_UNAVAILABLE", str(exc)[:300]) from exc

        @backend.get("/operational/reviews/{review_id}/parser-page/{page_no}")
        async def review_parser_page(review_id: str, page_no: int, request: Request):
            self.services.reviews.status(actor(request), review_id, "local-parser-page")
            try:
                path = self.parser_page_image(review_id, page_no)
                return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-store"})
            except ServiceError:
                raise
            except (OSError, ValueError, KeyError) as exc:
                raise ServiceError(503, "PARSER_PAGE_IMAGE_UNAVAILABLE", "파서 원문 화면을 읽을 수 없습니다.") from exc

        @backend.get('/operational/reviews/{review_id}/hwp-html/{asset_id}')
        async def review_hwp_html(review_id: str, asset_id: str, request: Request):
            self.services.reviews.status(actor(request), review_id, 'local-hwp-html')
            try:
                html = await run_in_threadpool(self.hwp_review_html, review_id, asset_id)
                return HTMLResponse(html, headers={'Cache-Control': 'no-store',
                    'Content-Security-Policy': HTML_CSP, 'X-Content-Type-Options': 'nosniff'})
            except ServiceError:
                raise
            except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
                raise ServiceError(503, 'HWP_HTML_UNAVAILABLE', 'HWP HTML 본문을 읽을 수 없습니다.') from exc

        @backend.get("/operational/reviews/{review_id}/workspace")
        async def result_workspace(review_id: str, request: Request):
            bundle = self.services.reviews.status(actor(request), review_id, "result-workspace")
            link = self.links.get(review_id, {})
            raw, payloads, integrated, discovery = {}, [], {}, {}
            rule_metadata = {}
            reading_audits = {}
            if link.get("result_file"):
                result_path = Path(link["result_file"])
                raw = read_json(result_path)
                freeze_path = result_path.with_name('FREEZE_BEFORE_PREDICTION.json')
                if freeze_path.is_file():
                    freeze = read_json(freeze_path)
                    if freeze.get('configuration', {}).get('source_policy') != 'template-only':
                        rule_metadata = dict(frozen_rule_metadata(self.config['regulation_path'], freeze))
                    catalog_path = result_path.with_name('00_template_catalog.json')
                    if catalog_path.is_file():
                        catalog = read_json(catalog_path)
                        hashes = {item.get('sha256') for item in freeze.get('inputs', [])}
                        if (catalog.get('source') or {}).get('sha256') in hashes:
                            guide_matches_review = (
                                bool(self.template_appropriate_judgment_sha256)
                                and link.get('template_appropriate_judgment_sha256')
                                == self.template_appropriate_judgment_sha256
                            )
                            for entry in catalog.get('entries', []):
                                fields = entry.get('fields') or {}
                                label = (fields.get('label') or {}).get('text', '')
                                metadata = {'title': label}
                                methodology = entry.get('methodology') or {}
                                if methodology.get('appropriate_judgment'):
                                    metadata['appropriate_judgment'] = methodology['appropriate_judgment']
                                elif guide_matches_review:
                                    key = (entry.get('template_section', ''), label)
                                    if key in self.template_appropriate_judgments:
                                        metadata['appropriate_judgment'] = self.template_appropriate_judgments[key]
                                rule_metadata[entry['item_id']] = metadata
                discovery_path = result_path.with_name("01_discovery.json")
                if discovery_path.is_file():
                    discovery = read_json(discovery_path)
                for response_name in ("03_judgment_responses.json", "06_recovery_responses.json"):
                    response_path = result_path.with_name(response_name)
                    if response_path.is_file():
                        for response in read_json(response_path).get("rows", []):
                            for guard in response.get("reading_quality_guards", []):
                                original = guard.get("original_result") or {}
                                reading_audits[(response.get("ad_id"), guard.get("item_id"))] = {
                                    "verdict": original.get("verdict"), "reason": original.get("reason"),
                                    "status": "WITHHELD_BY_READING_GUARD",
                                }
                requests_path = result_path.parent / "02_judgment_requests.jsonl"
                if requests_path.exists():
                    for request_line in requests_path.read_text(encoding="utf-8").splitlines():
                        if request_line.strip():
                            payloads.append(json.loads(json.loads(request_line)["messages"][1]["content"]))
                integrated_path = self.root / "runs" / review_id / "integrated.json"
                if integrated_path.exists():
                    integrated = read_json(integrated_path)
                    layout_path = integrated_path.with_name("parser-layout.json")
                    ad = self.services.repository.get_advertisement(bundle.review.advertisement_id)
                    files = [file for file in ad.files if file.file_type == "ADVERTISEMENT"]
                    if (len(files) == 1 and layout_path.is_file()
                            and Path(files[0].original_file_name).suffix.lower() in {".hwp", ".hwpx"}):
                        integrated = with_rendered_line_locations(
                            integrated, read_json(layout_path), files[0].file_id)
            value = saved_workspace(raw, payloads, integrated, bundle.review.advertisement_id, discovery, reading_audits, rule_metadata)
            # Extraction diagnostics also exist on parser failures without a
            # judgment result. Never replay parsing or infer success for them.
            directory = self.root / "runs" / review_id
            if not integrated and (directory / "integrated.json").is_file():
                integrated = read_json(directory / "integrated.json")
            ad = self.services.repository.get_advertisement(bundle.review.advertisement_id)
            failure_path = directory / "parser-failure.json"
            value["extraction_status"] = extraction_status(integrated,
                [{"file_id": file.file_id, "file_name": file.original_file_name}
                 for file in ad.files if file.file_type == "ADVERTISEMENT"],
                read_json(failure_path) if failure_path.is_file() else None)
            value.pop("source_ads", None)
            return {"available": True, "source_type": "GEMMA", "is_model_output": True,
                    "source_policy": (raw.get("audit", {}).get("rule_sources", {}).get("policy")
                                      or "template-plus-v2"),
                    **value, "status": bundle.review.status,
                    "output_failure_count": len(value["output_failure_pairs"]),
                    "partial_result_warning": link.get("partial_result_warning"),
                    "human_decision": self.decisions.get(review_id)}

        @backend.put("/operational/reviews/{review_id}/decision")
        async def final_human_decision(review_id: str, request: Request):
            current = actor(request)
            if not set(current.roles).intersection({"COMPLIANCE_REVIEWER", "SYSTEM_ADMIN"}):
                raise ServiceError(403, "FORBIDDEN", "최종 승인·반려는 준법 검토자만 할 수 있습니다.")
            bundle = self.services.reviews.status(current, review_id, "human-final-decision")
            if bundle.review.status != "REVIEW_COMPLETED":
                raise ServiceError(409, "REVIEW_NOT_COMPLETED", "AI 검토가 완료된 뒤 최종 판단할 수 있습니다.")
            body = await request.json()
            if not isinstance(body, dict) or set(body) - {"decision", "comment"}:
                raise ServiceError(422, "INVALID_DECISION", "승인·반려와 검토 의견만 입력할 수 있습니다.")
            decision = body.get("decision")
            comment = str(body.get("comment") or "").strip()
            if decision not in {"APPROVED", "REJECTED"}:
                raise ServiceError(422, "INVALID_DECISION", "최종 판단은 승인 또는 반려여야 합니다.")
            if decision == "REJECTED" and not comment:
                raise ServiceError(422, "DECISION_COMMENT_REQUIRED", "반려 사유를 입력해 주세요.")
            if len(comment) > 1000:
                raise ServiceError(422, "DECISION_COMMENT_TOO_LONG", "검토 의견은 1,000자 이하여야 합니다.")
            with self.lock:
                if review_id in self.decisions:
                    raise ServiceError(409, "DECISION_ALREADY_RECORDED", "이미 최종 판단이 기록되어 변경할 수 없습니다.")
                value = {
                    "decision": decision,
                    "comment": comment or None,
                    "reviewer_id": current.user_id,
                    "decided_at": datetime.now(UTC).isoformat(),
                    "ai_result_unchanged": True,
                }
                self.decisions[review_id] = value
                self.persist()
            return value

        @backend.middleware("http")
        async def scoped_writes(request: Request, call_next):
            path = request.url.path.removeprefix("/api/v1")
            allowed = ("/auth/" in path or
                request.method == "POST" and (path == "/advertisements" or
                    re.fullmatch(r"/advertisements/ADV-[\w-]+/reviews", path) or
                    re.fullmatch(r"/reviews/REV-[\w-]+/rerun", path) or
                    re.fullmatch(r"/operational/reviews/REV-[\w-]+/rebuild-annotations", path)) or
                request.method == "POST" and re.fullmatch(r"/operational/reviews/REV-[\w-]+/cancel", path) or
                request.method == "PUT" and (re.fullmatch(r"/operational/advertisements/ADV-[\w-]+/(routing|intake)", path) or
                    re.fullmatch(r"/operational/reviews/REV-[\w-]+/decision", path)) or
                request.method == "DELETE" and (
                    re.fullmatch(r"/operational/reviews/REV-[\w-]+", path) or
                    re.fullmatch(r"/operational/advertisements/ADV-[\w-]+", path) or
                    re.fullmatch(r"/operational/advertisements/ADV-[\w-]+/latest-review", path)))
            if request.method not in {"GET", "HEAD", "OPTIONS"} and not allowed:
                return JSONResponse({"code": "NOT_CONNECTED", "message": "현재 로컬 실행은 광고 등록·자동심의·재분석만 연결되어 있습니다."}, status_code=409)
            response = await call_next(request)
            if allowed and response.status_code < 400 and "/auth/" not in path:
                self.persist()
            return response
