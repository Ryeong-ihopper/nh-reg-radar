"""Persistent asynchronous job service for the canonical RAG pipeline."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rag.operational.contracts import validate_integrated_input, validate_job_status
from rag.operational.policy import require_confirmed_product_group, routing_field
from rag.operational.prepare_inputs import search_docs


ROOT = Path(__file__).resolve().parents[2]
TERMINAL_STATES = {
    "COMPLETED",
    "COMPLETED_WITH_WARNINGS",
    "PLANNED",
    "INPUT_REQUIRED",
    "FAILED",
    "INTERRUPTED",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


@dataclass(frozen=True)
class ServiceConfig:
    jobs_dir: Path
    regulation_path: Path
    es_url: str
    es_index: str
    model: str
    dgx_host: str | None = None
    dgx_key: Path | None = None
    workers: int = 4
    queue_workers: int = 1
    judgment_batch_size: int = 8
    evidence_per_rule: int = 3
    prohibition_max_candidates: int = 30
    job_timeout_seconds: int = 1800
    max_attempts: int = 3


def config_from_env() -> ServiceConfig:
    regulation = os.environ.get("NH_REGULATION_V2_PATH")
    es_index = os.environ.get("NH_RAG_ES_INDEX")
    if not regulation or not es_index:
        raise RuntimeError("NH_REGULATION_V2_PATH and NH_RAG_ES_INDEX are required")
    return ServiceConfig(
        jobs_dir=Path(os.environ.get("NH_RAG_JOBS_DIR", "runtime/rag-jobs")),
        regulation_path=Path(regulation),
        es_url=os.environ.get("NH_RAG_ES_URL", "http://127.0.0.1:19201"),
        es_index=es_index,
        model=os.environ.get("DGX_GEMMA_MODEL", "gemma-4-26b-NVFP4-MTP"),
        dgx_host=os.environ.get("DGX_HOST"),
        dgx_key=Path(os.environ["DGX_SSH_KEY"]) if os.environ.get("DGX_SSH_KEY") else None,
        workers=int(os.environ.get("NH_RAG_MODEL_WORKERS", "4")),
        queue_workers=int(os.environ.get("NH_RAG_QUEUE_WORKERS", "1")),
        judgment_batch_size=int(os.environ.get("NH_RAG_JUDGMENT_BATCH_SIZE", "8")),
        evidence_per_rule=int(os.environ.get("NH_RAG_EVIDENCE_PER_RULE", "3")),
        prohibition_max_candidates=int(
            os.environ.get("NH_RAG_PROHIBITION_MAX_CANDIDATES", "30")
        ),
        job_timeout_seconds=int(os.environ.get("NH_RAG_JOB_TIMEOUT_SECONDS", "1800")),
        max_attempts=int(os.environ.get("NH_RAG_MAX_ATTEMPTS", "3")),
    )


class JobStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def directory(self, job_id: str) -> Path:
        try:
            uuid.UUID(job_id)
        except ValueError as exc:
            raise KeyError(job_id) from exc
        path = (self.root / job_id).resolve()
        if path.parent != self.root:
            raise KeyError(job_id)
        return path

    def create(self, request: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            client_request_id = request.get("client_request_id")
            index_path = None
            if client_request_id:
                index_path = self.root / ".idempotency" / (
                    hashlib.sha256(str(client_request_id).encode("utf-8")).hexdigest()
                    + ".json"
                )
                if index_path.is_file():
                    index = json.loads(index_path.read_text(encoding="utf-8"))
                    if index.get("input_sha256") != request.get("input_sha256"):
                        raise ValueError(
                            "client_request_id was already used with different input"
                        )
                    replay = self.read(str(index["job_id"]))
                    replay["idempotent_replay"] = True
                    return replay
            job_id = str(uuid.uuid4())
            directory = self.directory(job_id)
            directory.mkdir(parents=True)
            write_json_atomic(directory / "request.json", request)
            status = {
                "schema_version": "operational-review-job-v1",
                "job_id": job_id,
                "status": "QUEUED",
                "created_at": utc_now(),
                "updated_at": utc_now(),
                "attempt": 0,
                "progress": {"stage": "queued"},
            }
            write_json_atomic(directory / "status.json", status)
            if index_path:
                write_json_atomic(
                    index_path,
                    {
                        "client_request_id": client_request_id,
                        "input_sha256": request.get("input_sha256"),
                        "job_id": job_id,
                    },
                )
            return validate_job_status(status)

    def read(self, job_id: str) -> dict[str, Any]:
        path = self.directory(job_id) / "status.json"
        if not path.is_file():
            raise KeyError(job_id)
        return validate_job_status(json.loads(path.read_text(encoding="utf-8")))

    def request(self, job_id: str) -> dict[str, Any]:
        path = self.directory(job_id) / "request.json"
        if not path.is_file():
            raise KeyError(job_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def update(self, job_id: str, **changes: Any) -> dict[str, Any]:
        with self._lock:
            status = self.read(job_id)
            status.update(changes)
            status["updated_at"] = utc_now()
            validate_job_status(status)
            write_json_atomic(self.directory(job_id) / "status.json", status)
            return status

    def interrupt_stale_jobs(self) -> int:
        interrupted = 0
        for path in self.root.glob("*/status.json"):
            status = json.loads(path.read_text(encoding="utf-8"))
            if status.get("status") == "RUNNING":
                status["status"] = "INTERRUPTED"
                status["updated_at"] = utc_now()
                status["error"] = {
                    "code": "PROCESS_RESTARTED",
                    "message": "service restarted while the job was running; retry is available",
                }
                validate_job_status(status)
                write_json_atomic(path, status)
                interrupted += 1
        return interrupted


def apply_routing_overrides(
    document: dict[str, Any], overrides: dict[str, Any]
) -> dict[str, Any]:
    value = copy.deepcopy(document)
    routing = value["document"].setdefault("routing_metadata", {})
    allowed = {
        "product_group",
        "product_subtype",
        "template_id",
        "ad_type",
        "product_name_shown",
        "media_type",
    }
    unknown = set(overrides) - allowed
    if unknown:
        raise ValueError(f"unsupported routing overrides: {sorted(unknown)}")
    for field, raw in overrides.items():
        if isinstance(raw, dict):
            normalized = routing_field(raw, default_source="api_request")
            if normalized["status"] not in {"confirmed", "verified", "provided"}:
                raise ValueError(f"routing override {field} must be confirmed/provided")
        else:
            normalized = {"value": raw, "source": "api_request", "status": "provided"}
        routing[field] = normalized
    validate_integrated_input(value)
    normalized_routing = {
        field: routing_field(raw, default_source=routing.get("classification_source"))
        for field, raw in routing.items()
        if field != "classification_source"
    }
    require_confirmed_product_group(normalized_routing)
    return value


class OperationalReviewService:
    def __init__(self, config: ServiceConfig):
        self.config = config
        if not config.regulation_path.is_file():
            raise RuntimeError(f"regulation v2 not found: {config.regulation_path}")
        self.store = JobStore(config.jobs_dir)
        self.store.interrupt_stale_jobs()
        self.executor = ThreadPoolExecutor(max_workers=config.queue_workers)

    def submit(self, request: dict[str, Any]) -> dict[str, Any]:
        if request.get("schema_version") != "operational-review-request-v1":
            raise ValueError("schema_version must be operational-review-request-v1")
        allowed = {
            "schema_version",
            "client_request_id",
            "document",
            "routing_overrides",
            "execute_model",
        }
        if set(request) - allowed:
            raise ValueError(f"unsupported request fields: {sorted(set(request) - allowed)}")
        if "execute_model" in request and not isinstance(request["execute_model"], bool):
            raise ValueError("execute_model must be boolean")
        client_request_id = request.get("client_request_id")
        if client_request_id is not None and (
            not isinstance(client_request_id, str) or not client_request_id.strip()
        ):
            raise ValueError("client_request_id must be a non-empty string or null")
        document = request.get("document")
        if not isinstance(document, dict):
            raise ValueError("document must be an integrated-input object")
        validate_integrated_input(document)
        overrides = request.get("routing_overrides") or {}
        prepared = apply_routing_overrides(document, overrides)
        stored = {
            "schema_version": "operational-review-request-v1",
            "document": prepared,
            "execute_model": request.get("execute_model", True) is not False,
            "client_request_id": request.get("client_request_id"),
            "input_sha256": hashlib.sha256(
                json.dumps(prepared, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest(),
        }
        job = self.store.create(stored)
        if not job.get("idempotent_replay"):
            self.executor.submit(self._run, job["job_id"])
        return job

    def retry(self, job_id: str) -> dict[str, Any]:
        status = self.store.read(job_id)
        if status["status"] not in TERMINAL_STATES:
            raise ValueError("job is not in a retryable terminal state")
        if int(status.get("attempt") or 0) >= self.config.max_attempts:
            raise ValueError("job reached the maximum number of attempts")
        status = self.store.update(
            job_id,
            status="QUEUED",
            error=None,
            progress={"stage": "queued_for_retry"},
        )
        self.executor.submit(self._run, job_id)
        return status

    def result(self, job_id: str) -> dict[str, Any]:
        status = self.store.read(job_id)
        if status["status"] not in {"COMPLETED", "COMPLETED_WITH_WARNINGS", "PLANNED"}:
            raise ValueError(f"result is not ready: {status['status']}")
        path = self.store.directory(job_id) / str(status["result_file"])
        return json.loads(path.read_text(encoding="utf-8"))

    def _invoke(
        self,
        *,
        directory: Path,
        attempt: int,
        label: str,
        command: list[str],
        timeout: int = 7200,
    ) -> None:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        (directory / f"attempt-{attempt}-{label}.log").write_text(
            (completed.stdout or "")
            + "\n--- stderr ---\n"
            + (completed.stderr or ""),
            encoding="utf-8",
        )
        if completed.returncode:
            raise RuntimeError(
                f"{label} exited {completed.returncode}; "
                f"see attempt-{attempt}-{label}.log"
            )

    def _run(self, job_id: str) -> None:
        directory = self.store.directory(job_id)
        request = self.store.request(job_id)
        attempt = int(self.store.read(job_id).get("attempt") or 0) + 1
        self.store.update(
            job_id,
            status="RUNNING",
            attempt=attempt,
            started_at=utc_now(),
            progress={"stage": "preparing_search_documents"},
        )
        try:
            integrated_dir = directory / "input" / "integrated"
            integrated_dir.mkdir(parents=True, exist_ok=True)
            document = request["document"]
            write_json_atomic(integrated_dir / "advertisement.json", document)
            coarse, fine = search_docs(document)
            coarse_path = directory / "input" / "evidence_coarse.jsonl"
            fine_path = directory / "input" / "evidence_fine.jsonl"
            write_jsonl(coarse_path, coarse)
            write_jsonl(fine_path, fine)
            self.store.update(
                job_id,
                progress={
                    "stage": "discovering_and_judging",
                    "coarse_documents": len(coarse),
                    "fine_documents": len(fine),
                },
            )
            output_dir = directory / f"attempt-{attempt}"
            command = [
                sys.executable,
                str(ROOT / "tools" / "run_operational_e2e.py"),
                "--inputs-dir",
                str(integrated_dir),
                "--coarse",
                str(coarse_path),
                "--fine",
                str(fine_path),
                "--regulation",
                str(self.config.regulation_path),
                "--output-dir",
                str(output_dir),
                "--es-url",
                self.config.es_url,
                "--es-index",
                self.config.es_index,
                "--model",
                self.config.model,
                "--workers",
                str(self.config.workers),
                "--batch-size",
                str(self.config.judgment_batch_size),
                "--evidence-per-rule",
                str(self.config.evidence_per_rule),
                "--prohibition-max-candidates",
                str(self.config.prohibition_max_candidates),
            ]
            if request["execute_model"]:
                command.append("--execute-judgment")
            if self.config.dgx_host:
                command.extend(["--host", self.config.dgx_host])
            if self.config.dgx_key:
                command.extend(["--key", str(self.config.dgx_key)])
            self._invoke(
                directory=directory,
                attempt=attempt,
                label="pipeline",
                command=command,
                timeout=self.config.job_timeout_seconds,
            )
            if request["execute_model"]:
                result_name = f"attempt-{attempt}/04_operational_results.json"
                result = json.loads((directory / result_name).read_text(encoding="utf-8"))
                failures = int(result["counts"]["output_failures"])
                if failures:
                    self.store.update(
                        job_id,
                        progress={
                            "stage": "recovering_output_contract",
                            "missing_pairs": failures,
                        },
                    )
                    recovery_requests = output_dir / "05_recovery_requests.jsonl"
                    recovery_responses = output_dir / "06_recovery_responses.json"
                    recovered_result = output_dir / "07_operational_results_recovered.json"
                    self._invoke(
                        directory=directory,
                        attempt=attempt,
                        label="recovery-build",
                        command=[
                            sys.executable,
                            str(ROOT / "tools" / "recover_operational_judgments.py"),
                            "build",
                            "--requests",
                            str(output_dir / "02_judgment_requests.jsonl"),
                            "--responses",
                            str(output_dir / "03_judgment_responses.json"),
                            "--output",
                            str(recovery_requests),
                            "--batch-size",
                            "2",
                        ],
                    )
                    if recovery_requests.read_text(encoding="utf-8").strip():
                        recovery_command = [
                            sys.executable,
                            str(ROOT / "tools" / "run_gemma_exhaustive_dgx.py"),
                            "--input",
                            str(recovery_requests),
                            "--output",
                            str(recovery_responses),
                            "--model",
                            self.config.model,
                            "--workers",
                            str(min(self.config.workers, 2)),
                        ]
                        if self.config.dgx_host:
                            recovery_command.extend(["--host", self.config.dgx_host])
                        if self.config.dgx_key:
                            recovery_command.extend(["--key", str(self.config.dgx_key)])
                        self._invoke(
                            directory=directory,
                            attempt=attempt,
                            label="recovery-model",
                            command=recovery_command,
                        )
                        self._invoke(
                            directory=directory,
                            attempt=attempt,
                            label="recovery-finalize",
                            command=[
                                sys.executable,
                                str(ROOT / "tools" / "recover_operational_judgments.py"),
                                "finalize",
                                "--requests",
                                str(output_dir / "02_judgment_requests.jsonl"),
                                "--discovery",
                                str(output_dir / "01_discovery.json"),
                                "--freeze",
                                str(output_dir / "FREEZE_BEFORE_PREDICTION.json"),
                                "--responses",
                                str(output_dir / "03_judgment_responses.json"),
                                "--responses",
                                str(recovery_responses),
                                "--output",
                                str(recovered_result),
                            ],
                        )
                        result = json.loads(recovered_result.read_text(encoding="utf-8"))
                        failures = int(result["counts"]["output_failures"])
                        result_name = (
                            f"attempt-{attempt}/07_operational_results_recovered.json"
                        )
                state = "COMPLETED_WITH_WARNINGS" if failures else "COMPLETED"
            else:
                result_name = f"attempt-{attempt}/01_discovery.json"
                state = "PLANNED"
            self.store.update(
                job_id,
                status=state,
                completed_at=utc_now(),
                result_file=result_name,
                progress={"stage": "complete"},
            )
        except ValueError as exc:
            self.store.update(
                job_id,
                status="INPUT_REQUIRED",
                error={"code": "INPUT_REQUIRED", "message": str(exc)},
                progress={"stage": "stopped"},
            )
        except Exception as exc:  # pragma: no cover - exercised by process integration
            (directory / f"attempt-{attempt}-traceback.log").write_text(
                traceback.format_exc(), encoding="utf-8"
            )
            self.store.update(
                job_id,
                status="FAILED",
                error={"code": "PIPELINE_FAILED", "message": str(exc)},
                progress={"stage": "failed"},
            )
