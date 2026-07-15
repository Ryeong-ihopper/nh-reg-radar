from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROVIDER_FREE = ROOT / ".github/workflows/release-readiness.yml"
EXTERNAL_MANUAL = ROOT / ".github/workflows/external-ai-evaluation.yml"


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
