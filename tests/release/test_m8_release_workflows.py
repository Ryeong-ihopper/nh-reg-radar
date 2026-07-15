from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROVIDER_FREE = ROOT / ".github/workflows/release-readiness.yml"
EXTERNAL_MANUAL = ROOT / ".github/workflows/external-ai-evaluation.yml"


def _run_provider_free_junit_gate(
    tmp_path: Path,
    junit: str,
    *,
    test_exit: int = 0,
) -> subprocess.CompletedProcess[str]:
    workflow = PROVIDER_FREE.read_text(encoding="utf-8")
    start_marker = "          TEST_EXIT=\"$test_exit\" python3 - <<'PY'\n"
    script = workflow.split(start_marker, maxsplit=1)[1].split("\n          PY", maxsplit=1)[0]
    junit_path = tmp_path / "provider-free-junit.xml"
    junit_path.write_text(junit, encoding="utf-8")
    script = textwrap.dedent(script)
    workflow_junit_path = 'Path("/tmp/g009-provider-free-junit.xml")'
    assert workflow_junit_path in script
    script = script.replace(workflow_junit_path, f"Path({str(junit_path)!r})")
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env={**os.environ, "TEST_EXIT": str(test_exit)},
        check=False,
        capture_output=True,
        text=True,
    )


def test_provider_free_release_gate_is_deterministic_and_secret_free() -> None:
    workflow = PROVIDER_FREE.read_text(encoding="utf-8")

    assert "pull_request:" in workflow
    assert "workflow_dispatch:" in workflow
    assert 'python -m pytest -m "not external_ai and not slow"' in workflow
    assert 'python -m pytest tests/e2e tests/release -m "not external_ai"' in workflow
    assert "governance/goal-manifests/G009-m8-release.json" in workflow
    assert "Run exact G009 provider-free evidence" in workflow
    assert "--junitxml=/tmp/g009-provider-free-junit.xml" in workflow
    assert "actual != expected" in workflow
    assert "provider-free count mismatch" in workflow
    assert '"failed": counts["failures"] + counts["errors"]' in workflow
    assert "scripts/check-doc-consistency.sh" in workflow
    assert "scripts/release-smoke.sh" in workflow
    assert 'NH_RUN_G011_DOCKER_REGRESSION: "1"' in workflow
    assert "npm --prefix apps/frontend run lint" in workflow
    assert "npm --prefix apps/frontend run typecheck" in workflow
    assert "npm --prefix apps/frontend run test" in workflow
    assert "npm --prefix apps/frontend run build" in workflow
    assert "npm run frontend:check" not in workflow
    assert "uv run mypy\n" in workflow
    assert "uv run mypy ." not in workflow
    assert "ruff format --check tests/release" in workflow
    assert "ruff format --check ." not in workflow
    assert "secrets." not in workflow
    assert "EXTERNAL_AI_API_KEY" not in workflow
    assert "pytest -m external_ai" not in workflow

    repeat_up = workflow.index("test_compose_bootstrap_repeat_up.py")
    recovery = workflow.index("scripts/release-smoke.sh")
    assert repeat_up < recovery


def test_provider_free_junit_gate_accepts_exact_manifest_counts(tmp_path: Path) -> None:
    result = _run_provider_free_junit_gate(
        tmp_path,
        '<testsuite tests="4" failures="0" errors="0" skipped="0" />',
    )

    assert result.returncode == 0, result.stderr
    assert "G009 provider-free counts verified" in result.stdout


def test_provider_free_junit_gate_rejects_skipped_tests(tmp_path: Path) -> None:
    result = _run_provider_free_junit_gate(
        tmp_path,
        '<testsuite tests="4" failures="0" errors="0" skipped="1" />',
    )

    assert result.returncode != 0
    assert "provider-free count mismatch" in result.stderr


def test_provider_free_junit_gate_rejects_error_tests(tmp_path: Path) -> None:
    result = _run_provider_free_junit_gate(
        tmp_path,
        '<testsuite tests="4" failures="0" errors="1" skipped="0" />',
    )

    assert result.returncode != 0
    assert "provider-free count mismatch" in result.stderr


def test_provider_free_junit_gate_rejects_partial_counts(tmp_path: Path) -> None:
    result = _run_provider_free_junit_gate(
        tmp_path,
        '<testsuite tests="4" failures="0" errors="0" />',
    )

    assert result.returncode != 0
    assert "missing required count attributes" in result.stderr


def test_provider_free_junit_gate_rejects_malformed_xml(tmp_path: Path) -> None:
    result = _run_provider_free_junit_gate(
        tmp_path,
        '<testsuite tests="4" failures="0" errors="0" skipped="0">',
    )

    assert result.returncode != 0
    assert "provider-free JUnit is unreadable" in result.stderr


def test_provider_free_junit_gate_rejects_nonzero_pytest_exit(tmp_path: Path) -> None:
    result = _run_provider_free_junit_gate(
        tmp_path,
        '<testsuite tests="4" failures="0" errors="0" skipped="0" />',
        test_exit=42,
    )

    assert result.returncode != 0
    assert "provider-free pytest failed with 42" in result.stderr


def test_external_engine_workflow_is_manual_sanitized_and_non_blocking() -> None:
    workflow = EXTERNAL_MANUAL.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "push:" not in workflow
    assert "environment: external-ai-manual" in workflow
    assert "python -m pytest -m external_ai" in workflow
    assert "external-ai-evidence.json" in workflow
    assert 'environment_mode": "manual_external_ai"' in workflow
    assert "provider_label" in workflow
    assert "model_label" in workflow
    assert "config_fingerprint" in workflow
    assert "dataset_id" in workflow
    assert "steps.metadata.outcome == 'success'" in workflow
    assert '"passed": max(' in workflow
    assert '"failed": counts["failures"] + counts["errors"]' in workflow
    assert '"skipped": counts["skipped"]' in workflow

    evidence_block = workflow.split("Create sanitized evidence", maxsplit=1)[1]
    evidence_block = evidence_block.split("Upload sanitized evidence", maxsplit=1)[0]
    assert "EXTERNAL_AI_API_KEY" not in evidence_block
    assert "secrets." not in evidence_block
    assert "/tmp/external-ai-pytest.log" not in workflow
