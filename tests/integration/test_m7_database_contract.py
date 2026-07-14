from __future__ import annotations

import hashlib
import os
import re
import socket
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "apps/backend/migrations/versions"
MIGRATION = MIGRATIONS / "0007_m7_validation_kpi.py"
PRIOR_MIGRATION_HASHES = {
    "0001_schema_only_base.py": "77924cec476e8827db46bf7abe8d569046511ddb11ba4977ddb999ab6ec9be31",
    "0002_m2_auth_advertisement_audit.py": "62af414340540037b935e59133eb5cb641dcdc7d68f5a536f9fe6dd1e9f64cd1",
    "0003_m3_standards_search.py": "2535911b01001784bf24972e0c5cba0ba5237e152794f0534de286842ac1ed45",
    "0004_m4_parser_ocr_jobs.py": "c6876ce907f18186a1eb04593f0771130362566d6d36efea3c45f1d479e8b1b0",
    "0005_m5_review_results.py": "0966a1beffce056ea45bac2fc4d187a2751c2394f7c17b0358b3f13fc5789761",
    "0006_m6_support_outputs.py": "426f7bb00d028d3f95601c724156322962be323c536e92403d905880e094c43f",
}
OWNED_TABLES = {
    "validation_datasets",
    "validation_judgments",
    "evaluations",
    "evaluation_metrics",
}
POSTGRES_READY_LOG = "database system is ready to accept connections"


def _run(*command: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=True,
        timeout=180,
    )


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _wait_for_final_postgres(name: str, url: str) -> None:
    last_identity: object | None = None
    stable_probes = 0
    logs = ""
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        logged = subprocess.run(
            ["docker", "logs", name],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        logs = f"{logged.stdout}\n{logged.stderr}"
        if logged.returncode == 0 and logs.count(POSTGRES_READY_LOG) >= 2:
            try:
                with psycopg.connect(url, connect_timeout=1) as connection:
                    identity = connection.execute("SELECT pg_postmaster_start_time()").fetchone()
            except psycopg.OperationalError:
                last_identity = None
                stable_probes = 0
            else:
                if identity == last_identity:
                    stable_probes += 1
                else:
                    last_identity = identity
                    stable_probes = 1
                if stable_probes >= 2:
                    return
        time.sleep(0.25)
    raise AssertionError(f"final PostgreSQL server did not become stable:\n{logs}")


@pytest.fixture(scope="module")
def postgres_urls() -> Iterator[dict[str, str]]:
    image = os.getenv("M7_POSTGRES_IMAGE", "postgres:16-alpine")
    name = f"nh-ad-m7-contract-{uuid4().hex[:10]}"
    port = _free_port()
    _run(
        "docker",
        "run",
        "--detach",
        "--rm",
        "--name",
        name,
        "--tmpfs",
        "/var/lib/postgresql/data:rw",
        "--publish",
        f"127.0.0.1:{port}:5432",
        "--env",
        "POSTGRES_USER=migration",
        "--env",
        "POSTGRES_PASSWORD=migration",
        image,
    )
    try:
        admin_url = f"postgresql://migration:migration@127.0.0.1:{port}/postgres"
        _wait_for_final_postgres(name, admin_url)
        for sql in (
            "CREATE ROLE app NOLOGIN",
            "CREATE ROLE readonly NOLOGIN",
            "CREATE DATABASE m7_clean OWNER migration",
            "CREATE DATABASE m7_upgrade OWNER migration",
        ):
            _run(
                "docker",
                "exec",
                name,
                "psql",
                "--username",
                "migration",
                "--dbname",
                "postgres",
                "--set",
                "ON_ERROR_STOP=1",
                "--command",
                sql,
            )
        yield {
            database: f"postgresql://migration:migration@127.0.0.1:{port}/{database}"
            for database in ("m7_clean", "m7_upgrade")
        }
    finally:
        try:
            subprocess.run(
                ["docker", "rm", "--force", name],
                capture_output=True,
                check=False,
                timeout=45,
            )
        except subprocess.TimeoutExpired:
            subprocess.Popen(  # noqa: S603 - fixed local Docker cleanup command
                ["docker", "rm", "--force", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


def _upgrade(url: str, target: str) -> None:
    env = os.environ.copy()
    env["NH_DB_MIGRATION_URL"] = url.replace("postgresql://", "postgresql+psycopg://", 1)
    _run("uv", "run", "alembic", "-c", "apps/backend/alembic.ini", "upgrade", target, env=env)


def _validation_tables(url: str) -> set[str]:
    with psycopg.connect(url) as connection:
        rows = connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='validation'"
        ).fetchall()
    return {str(row[0]) for row in rows}


def test_m7_migration_is_additive_and_owned_by_m7() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'down_revision: str | None = "0006_m6_support_outputs"' in source
    assert set(re.findall(r'op\.create_table\(\s*"([a-z_]+)"', source)) == OWNED_TABLES
    assert "ALTER TABLE" not in source.upper()
    assert "bulk_insert" not in source


def test_prior_migrations_remain_byte_identical() -> None:
    for name, expected in PRIOR_MIGRATION_HASHES.items():
        assert hashlib.sha256((MIGRATIONS / name).read_bytes()).hexdigest() == expected


def test_m7_migration_locks_version_snapshot_kpi_and_exclusion_invariants() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    for invariant in (
        "dataset_version > 0",
        "judgment_version > 0",
        "snapshot_hash",
        "dataset_snapshot_json",
        "judgment_snapshot_json",
        "exclusion_snapshot_json",
        "ai_result_snapshot_json",
        "version_snapshot_json",
        "evaluation_policy_snapshot_json",
        "LATEST_COMPLETED",
        "REQUIRED_PHRASE_ACCURACY",
        "MISLEADING_EXPRESSION_ACCURACY",
        "EVIDENCE_PRECISION",
        "HUMAN_AGREEMENT_RATE",
        "numerator",
        "denominator",
        "partial_count",
        "not_applicable",
        "ck_evaluation_metrics_not_applicable",
    ):
        assert invariant in source


def test_actual_postgres_clean_and_m6_to_m7_upgrades(postgres_urls: dict[str, str]) -> None:
    clean_url = postgres_urls["m7_clean"]
    _upgrade(clean_url, "0007_m7_validation_kpi")
    assert _validation_tables(clean_url) == OWNED_TABLES

    upgrade_url = postgres_urls["m7_upgrade"]
    _upgrade(upgrade_url, "0006_m6_support_outputs")
    assert _validation_tables(upgrade_url) == set()
    _upgrade(upgrade_url, "0007_m7_validation_kpi")
    assert _validation_tables(upgrade_url) == OWNED_TABLES

    with psycopg.connect(upgrade_url) as connection:
        revision = connection.execute("SELECT version_num FROM app.alembic_version").fetchone()
        nullable_scores = connection.execute(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema='validation' AND table_name='evaluation_metrics' "
            "AND column_name='score'"
        ).fetchone()
    assert revision == ("0007_m7_validation_kpi",)
    assert nullable_scores == ("YES",)
