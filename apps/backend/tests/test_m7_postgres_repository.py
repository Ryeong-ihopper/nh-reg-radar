"""Actual PostgreSQL round-trip for the M7 runtime repository."""

import json
import os
import socket
import subprocess
import sys
import time
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from sqlalchemy import create_engine

from nh_ad_backend.domain import CurrentUser
from nh_ad_backend.validation import PostgresValidationRepository, ValidationService


ROOT = Path(__file__).parents[3]
FIXTURE = ROOT / "tests" / "fixtures" / "m7" / "validation-kpi-v1.json"
POSTGRES_READY_LOG = "database system is ready to accept connections"


def run(*command: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=180,
    )


def wait_for_final_postgres(name: str, url: str) -> None:
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
def postgres_url() -> Iterator[str]:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = int(listener.getsockname()[1])
    name = f"nh-ad-m7-runtime-{uuid4().hex[:10]}"
    run(
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
        os.getenv("M7_POSTGRES_IMAGE", "postgres:16-alpine"),
    )
    url = f"postgresql://migration:migration@127.0.0.1:{port}/postgres"
    try:
        wait_for_final_postgres(name, url)
        for sql in ("CREATE ROLE app NOLOGIN", "CREATE ROLE readonly NOLOGIN"):
            run(
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
        env = os.environ.copy()
        env["NH_DB_MIGRATION_URL"] = url.replace("postgresql://", "postgresql+psycopg://", 1)
        run(
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "apps/backend/alembic.ini",
            "upgrade",
            "0007_m7_validation_kpi",
            env=env,
        )
        with psycopg.connect(url) as connection:
            connection.execute(
                "INSERT INTO app.departments "
                "(department_id,department_name) VALUES ('DPT-C','준법부')"
            )
            connection.execute(
                "INSERT INTO app.users "
                "(user_id,auth_provider,user_name,email,department_id,user_status) "
                "VALUES ('reviewer','LOCAL','준법담당','review@example.com','DPT-C','ACTIVE')"
            )
        yield url.replace("postgresql://", "postgresql+psycopg://", 1)
    finally:
        try:
            subprocess.run(
                ["docker", "rm", "--force", name], capture_output=True, check=False, timeout=45
            )
        except subprocess.TimeoutExpired:
            subprocess.Popen(  # noqa: S603 - fixed local Docker cleanup command
                ["docker", "rm", "--force", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


def test_postgres_repository_round_trips_versioned_inputs_and_immutable_evaluation(
    postgres_url: str,
) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    counters: defaultdict[str, int] = defaultdict(int)

    def identifier(prefix: str) -> str:
        counters[prefix] += 1
        return f"{prefix}-M7-PG-{counters[prefix]:04d}"

    now = datetime(2026, 7, 14, 10, tzinfo=UTC)
    engine = create_engine(postgres_url, pool_pre_ping=True)
    repository = PostgresValidationRepository(engine)
    service = ValidationService(
        repository,
        now=lambda: now,
        identifier=identifier,
    )
    actor = CurrentUser("reviewer", "준법담당", "DPT-C", "준법부", ("COMPLIANCE_REVIEWER",), 1)
    dataset = service.create_dataset(
        actor,
        dataset_name="PostgreSQL synthetic",
        product_group="SAVINGS",
        advertisement_type="MOBILE_BANNER",
        advertisement_file={
            "fileName": "synthetic.png",
            "contentType": "image/png",
            "content": b"postgres-m7",
        },
        product_condition_file=None,
        human_review_comment=None,
        label_json=json.dumps({"cases": fixture["cases"]}),
        excluded=False,
        exclude_reason_code=None,
        exclude_reason_detail=None,
        trace_id="req-m7-pg",
    )
    service.create_judgments(
        actor,
        dataset.dataset_id,
        [
            {
                "targetText": "Synthetic judgment",
                "reviewType": "MISLEADING_EXPRESSION",
                "expectedStatus": "NEEDS_REVISION",
            }
        ],
        "req-m7-pg",
    )
    request = {
        "dataset_ids": [dataset.dataset_id],
        "metrics": fixture["targets"].keys(),
        "exclude_invalid_samples": True,
        "review_selection_policy": "LATEST_COMPLETED",
        "trace_id": "req-m7-pg",
    }
    first = service.create_evaluation(actor, **request)
    stored = service.get_evaluation(actor, first.evaluation_id, "req-m7-pg")
    service.create_judgments(
        actor,
        dataset.dataset_id,
        [
            {
                "targetText": "Synthetic judgment",
                "reviewType": "MISLEADING_EXPRESSION",
                "expectedStatus": "APPROPRIATE",
            }
        ],
        "req-m7-pg",
    )
    second = service.create_evaluation(actor, **request)
    engine.dispose()

    assert repository.list_datasets(0, 20)[1] == 1
    assert repository.list_judgments(dataset.dataset_id)[0].judgment_version == 2
    assert stored.snapshot_hash == first.snapshot_hash
    assert stored.metrics == first.metrics
    assert second.evaluation_id != first.evaluation_id
    assert second.snapshot_hash != first.snapshot_hash
