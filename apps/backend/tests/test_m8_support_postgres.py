"""Actual PostgreSQL restart round-trip for durable M6 support outputs."""

import base64
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import zlib
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, text

from nh_ad_backend.api import ApplicationServices
from nh_ad_backend.domain import CurrentUser
from nh_ad_backend.main import create_app
from nh_ad_backend.repository import PostgresRepository
from nh_ad_backend.reviews import InMemoryReviewQueue, PostgresReviewRepository, ReviewService
from nh_ad_backend.search import HybridSearch, InMemorySearchBackend
from nh_ad_backend.security import TokenService, hash_password
from nh_ad_backend.services import AdvertisementService, AuthService, ServiceError
from nh_ad_backend.settings import Settings
from nh_ad_backend.standards import InMemoryStandardRepository, StandardService
from nh_ad_backend.storage import PrivateFileStorage
from nh_ad_backend.support import PostgresSupportRepository, SupportService


ROOT = Path(__file__).parents[3]
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def png_with_payload(payload: bytes) -> bytes:
    chunk = len(payload).to_bytes(4, "big") + b"tEXt" + payload
    chunk += (zlib.crc32(b"tEXt" + payload) & 0xFFFFFFFF).to_bytes(4, "big")
    return PNG[:33] + chunk + PNG[-12:]


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


def wait_for_postgres(name: str, url: str) -> None:
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(url, connect_timeout=1) as connection:
                connection.execute("SELECT 1")
            return
        except psycopg.OperationalError:
            time.sleep(0.25)
    logs = subprocess.run(
        ["docker", "logs", name], capture_output=True, text=True, check=False, timeout=5
    )
    raise AssertionError(f"PostgreSQL did not become ready:\n{logs.stdout}\n{logs.stderr}")


@pytest.fixture(scope="module")
def postgres_url() -> Iterator[str]:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = int(listener.getsockname()[1])
    name = f"nh-ad-m8-support-{uuid4().hex[:10]}"
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
        os.getenv("M8_POSTGRES_IMAGE", "postgres:16-alpine"),
    )
    raw_url = f"postgresql://migration:migration@127.0.0.1:{port}/postgres"
    try:
        wait_for_postgres(name, raw_url)
        for role in ("app", "readonly"):
            role_options = "LOGIN PASSWORD 'app'" if role == "app" else "NOLOGIN"
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
                f"CREATE ROLE {role} {role_options}",
            )
        env = os.environ.copy()
        env["NH_DB_MIGRATION_URL"] = raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
        run(
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "apps/backend/alembic.ini",
            "upgrade",
            "head",
            env=env,
        )
        yield f"postgresql+psycopg://app:app@127.0.0.1:{port}/postgres"
    finally:
        subprocess.run(
            ["docker", "rm", "--force", name], capture_output=True, check=False, timeout=45
        )


def test_postgres_support_outputs_and_revision_survive_service_restart(
    postgres_url: str,
    tmp_path: Path,
) -> None:
    now = datetime(2026, 7, 15, 1, 0, tzinfo=UTC)
    engine = create_engine(postgres_url, pool_pre_ping=True)
    with engine.begin() as connection:
        password_hash = hash_password("SecurePassword!42", salt=b"0123456789abcdef")
        connection.execute(
            text(
                "INSERT INTO app.departments (department_id,department_name) "
                "VALUES ('DPT-M8','M8 상품부')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO app.roles (role_id,role_name) "
                "VALUES ('COMPLIANCE_REVIEWER','준법 검토자')"
            )
        )
        connection.execute(
            text("""
                INSERT INTO app.users
                (user_id,auth_provider,user_name,email,password_hash,department_id,user_status)
                VALUES ('m8-user','LOCAL','M8 담당','m8@example.com',:password_hash,
                        'DPT-M8','ACTIVE')
            """),
            {"password_hash": password_hash},
        )
        connection.execute(
            text(
                "INSERT INTO app.user_roles (user_role_id,user_id,role_id) "
                "VALUES (:id,'m8-user','COMPLIANCE_REVIEWER')"
            ),
            {"id": uuid4()},
        )
    actor = CurrentUser(
        "m8-user",
        "M8 담당",
        "DPT-M8",
        "M8 상품부",
        ("COMPLIANCE_REVIEWER",),
        1,
    )
    counter = iter(range(1, 100))
    base_repository = PostgresRepository(engine, storage_provider="local", bucket="test")
    advertisements = AdvertisementService(
        base_repository,
        PrivateFileStorage(tmp_path / "objects"),
        now=lambda: now,
        identifier=lambda prefix: f"{prefix}-M8-{next(counter):04d}",
    )
    advertisement = advertisements.create(
        actor,
        advertisement_name="M8 durability",
        product_group="SAVINGS",
        advertisement_type="MOBILE_BANNER",
        department_id="DPT-M8",
        channel_type=None,
        memo=None,
        uploads=(("ADVERTISEMENT", "original.png", "image/png", __import__("io").BytesIO(PNG)),),
        trace_id="req-m8-ad",
    )
    reviews = ReviewService(
        PostgresReviewRepository(engine),
        advertisements,
        InMemoryReviewQueue(),
        now=lambda: now,
        identifier=lambda prefix: f"{prefix}-M8-{next(counter):04d}",
    )
    review = reviews.request(
        actor,
        advertisement.advertisement_id,
        standard_effective_date=now.date(),
        review_types=None,
        include_suggestion=True,
        include_opinion_draft=True,
        request_memo=None,
        trace_id="req-m8-review",
    )
    revision = advertisements.create_revision(
        actor,
        advertisement.advertisement_id,
        revision_memo="확정 표현 완화",
        upload=(
            "revised.png",
            "image/png",
            __import__("io").BytesIO(png_with_payload(b"revision")),
        ),
        trace_id="req-m8-revision",
    )
    with engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO app.review_items
                (review_item_id,review_id,review_type,target_text,normalized_target_text,
                 result_status,risk_level,risk_policy_version,risk_reason_codes,risk_score_detail,
                 evidence_status,reason,recommendation,engine_type,engine_version,result_json,created_at)
                VALUES ('ITEM-M8',:review_id,'MISLEADING_EXPRESSION','국내 최고','국내 최고',
                        'NEEDS_REVISION','HIGH','risk-v1','[\"ABSOLUTE\"]'::jsonb,'{}'::jsonb,
                        'NOT_REQUIRED','확정 표현','조건부 표현','RULE','fixture-v1','{}'::jsonb,:now)
            """),
            {"review_id": review.review.review_id, "now": now},
        )
        connection.execute(
            text("""
                INSERT INTO app.suggestions
                (suggestion_id,review_id,review_item_id,original_text,suggested_text,
                 suggestion_reason,suggestion_type,evidence_ids,decision_status,created_at)
                VALUES ('SUG-M8',:review_id,'ITEM-M8','국내 최고','조건 충족 시 우대',
                        '확정 표현 완화','SOFTENING','[]'::jsonb,'PENDING',:now)
            """),
            {"review_id": review.review.review_id, "now": now},
        )

    first = SupportService(
        PostgresSupportRepository(engine),
        audit_sink=base_repository.add_audit_event,
        reviews=reviews,
        advertisements=advertisements,
        now=lambda: now,
    )
    first.decide(
        actor,
        "SUG-M8",
        {"decisionStatus": "MODIFIED_AND_USED", "finalText": "조건 충족 시 우대 제공"},
        "req-m8-decision",
    )
    draft = first.create_draft(actor, review.review.review_id, {}, "req-m8-draft")
    first.update_draft(
        actor,
        draft["draftId"],
        {"finalContent": "최종 검토 의견"},
        "req-m8-draft-update",
    )
    pdf = first.create_report(
        actor,
        review.review.review_id,
        {"format": "PDF", "includeSuggestions": True, "includeOpinionDraft": True},
        "req-m8-report",
    )
    comparison = first.create_comparison(
        actor,
        advertisement.advertisement_id,
        {"baseReviewId": review.review.review_id, "revisionId": revision.revision_id},
        "req-m8-comparison",
    )
    first.decide(
        actor,
        "SUG-M8",
        {"decisionStatus": "REJECTED"},
        "req-m8-second-decision",
    )

    restarted = SupportService(
        PostgresSupportRepository(engine),
        audit_sink=base_repository.add_audit_event,
        reviews=reviews,
        advertisements=advertisements,
        now=lambda: now,
    )
    assert (
        restarted.list_suggestions(actor, review.review.review_id)[0]["decisionStatus"]
        == "REJECTED"
    )
    assert (
        restarted.drafts_for(actor, review.review.review_id)[0]["finalContent"] == "최종 검토 의견"
    )
    stored_pdf = restarted.get_report(actor, pdf["reportId"])
    source = restarted.get_report(actor, stored_pdf["sourceReportId"])
    assert source["snapshotHash"] == stored_pdf["snapshotHash"] == pdf["snapshotHash"]
    payload, report_format = restarted.download_report(
        actor, stored_pdf["reportId"], "req-m8-download"
    )
    canonical = json.dumps(
        json.loads(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    assert report_format == "PDF"
    assert f"sha256:{hashlib.sha256(canonical).hexdigest()}" == stored_pdf["snapshotHash"]
    assert restarted.get_comparison(actor, comparison["comparisonId"]) == comparison
    assert (
        base_repository.get_revision(revision.revision_id).advertisement_id
        == advertisement.advertisement_id
    )  # type: ignore[union-attr]
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM app.suggestion_decisions WHERE suggestion_id='SUG-M8'")
            ).scalar_one()
            == 2
        )
        assert connection.execute(text("SELECT COUNT(*) FROM app.reports")).scalar_one() == 2
        assert connection.execute(text("SELECT COUNT(*) FROM app.comparisons")).scalar_one() == 1

    def fresh_services() -> ApplicationServices:
        fresh_repository = PostgresRepository(engine, storage_provider="local", bucket="test")
        fresh_advertisements = AdvertisementService(
            fresh_repository, PrivateFileStorage(tmp_path / "objects")
        )
        fresh_reviews = ReviewService(
            PostgresReviewRepository(engine), fresh_advertisements, InMemoryReviewQueue()
        )
        return ApplicationServices(
            repository=fresh_repository,
            auth=AuthService(
                fresh_repository,
                TokenService("m8-test-jwt-secret-with-more-than-thirty-two-characters"),
            ),
            advertisements=fresh_advertisements,
            standards=StandardService(
                InMemoryStandardRepository(),
                HybridSearch(
                    keyword=InMemorySearchBackend("OPENSEARCH"),
                    vector=InMemorySearchBackend("QDRANT"),
                ),
            ),
            reviews=fresh_reviews,
            support=SupportService(
                PostgresSupportRepository(engine),
                audit_sink=fresh_repository.add_audit_event,
                reviews=fresh_reviews,
                advertisements=fresh_advertisements,
            ),
        )

    settings = Settings(
        app_env="test",
        jwt_secret=SecretStr("m8-test-jwt-secret-with-more-than-thirty-two-characters"),
        cors_allowed_origins="http://localhost:5173",
        refresh_cookie_secure=False,
    )
    with TestClient(create_app(settings, fresh_services())) as first_app:
        token = first_app.post(
            "/api/v1/auth/login",
            json={"email": "m8@example.com", "password": "SecurePassword!42"},
        ).json()["accessToken"]
        headers = {"Authorization": f"Bearer {token}"}
        assert (
            first_app.get(f"/api/v1/reports/{pdf['reportId']}", headers=headers).json()[
                "snapshotHash"
            ]
            == pdf["snapshotHash"]
        )
    with TestClient(create_app(settings, fresh_services())) as restarted_app:
        token = restarted_app.post(
            "/api/v1/auth/login",
            json={"email": "m8@example.com", "password": "SecurePassword!42"},
        ).json()["accessToken"]
        headers = {"Authorization": f"Bearer {token}"}
        downloaded = restarted_app.get(
            f"/api/v1/reports/{pdf['reportId']}/download", headers=headers
        )
        assert downloaded.status_code == 200 and downloaded.content == payload
        assert (
            restarted_app.get(
                f"/api/v1/comparisons/{comparison['comparisonId']}", headers=headers
            ).json()
            == comparison
        )

    def concurrent_revision(index: int) -> int:
        stored = advertisements.create_revision(
            actor,
            advertisement.advertisement_id,
            revision_memo=f"동시 수정 {index}",
            upload=(
                f"concurrent-{index}.png",
                "image/png",
                __import__("io").BytesIO(png_with_payload(f"concurrent-{index}".encode())),
            ),
            trace_id=f"req-m8-concurrent-{index}",
        )
        return stored.revision_no

    with ThreadPoolExecutor(max_workers=2) as executor:
        revision_numbers = list(executor.map(concurrent_revision, (1, 2)))
    assert sorted(revision_numbers) == [2, 3]

    second_advertisement = advertisements.create(
        actor,
        advertisement_name="M8 other",
        product_group="SAVINGS",
        advertisement_type="MOBILE_BANNER",
        department_id="DPT-M8",
        channel_type=None,
        memo=None,
        uploads=(
            (
                "ADVERTISEMENT",
                "other.png",
                "image/png",
                __import__("io").BytesIO(png_with_payload(b"other")),
            ),
        ),
        trace_id="req-m8-other",
    )
    second_revision = advertisements.create_revision(
        actor,
        second_advertisement.advertisement_id,
        revision_memo=None,
        upload=(
            "other-revised.png",
            "image/png",
            __import__("io").BytesIO(png_with_payload(b"other-revision")),
        ),
        trace_id="req-m8-other-revision",
    )
    with pytest.raises(ServiceError) as raised:
        restarted.create_comparison(
            actor,
            advertisement.advertisement_id,
            {"baseReviewId": review.review.review_id, "revisionId": second_revision.revision_id},
            "req-m8-wrong-revision",
        )
    assert raised.value.status_code == 400
    engine.dispose()


def test_postgres_qa_session_filters_accept_a_review_id_parameter(postgres_url: str) -> None:
    """Regression for #27: PostgreSQL must be able to type the review filter parameter.

    `(:review_id IS NULL OR ...)` left the bind parameter untyped, so PostgreSQL failed
    at planning time with `AmbiguousParameter` and the API returned a plain 500 whenever
    the Q&A screen filtered by review. Planning fails regardless of stored rows, so this
    exercises both filters against the real database without seeding sessions.
    """
    engine = create_engine(postgres_url, pool_pre_ping=True)
    repository = PostgresSupportRepository(engine)
    actor = CurrentUser(
        "qa-filter-user",
        "QA 필터",
        "DPT-M8",
        "M8 상품부",
        ("COMPLIANCE_REVIEWER",),
        1,
    )

    assert repository.list_questions(actor, "REV-does-not-exist") == []
    assert repository.list_questions(actor) == []
    assert repository.session_belongs_to(actor, "QA-does-not-exist", "REV-does-not-exist") is False
    assert repository.session_belongs_to(actor, "QA-does-not-exist", None) is False

    engine.dispose()
