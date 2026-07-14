import base64
import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, text

from conftest import JWT_SECRET, PASSWORD
from nh_ad_backend.main import build_services, create_app
from nh_ad_backend.security import hash_password
from nh_ad_backend.settings import Settings


pytestmark = pytest.mark.skipif(
    "M2_INTEGRATION_DB_URL" not in os.environ or "M2_INTEGRATION_S3_ENDPOINT" not in os.environ,
    reason="isolated PostgreSQL and MinIO endpoints are required",
)


def _settings() -> Settings:
    return Settings(
        app_env="test",
        nh_db_runtime_url=SecretStr(os.environ["M2_INTEGRATION_DB_URL"]),
        jwt_secret=SecretStr(JWT_SECRET),
        cors_allowed_origins="http://localhost:5173",
        object_storage_endpoint=os.environ["M2_INTEGRATION_S3_ENDPOINT"],
        object_storage_access_key=SecretStr(os.environ["M2_INTEGRATION_S3_ACCESS_KEY"]),
        object_storage_secret_key=SecretStr(os.environ["M2_INTEGRATION_S3_SECRET_KEY"]),
        ad_originals_bucket=os.environ["M2_INTEGRATION_S3_BUCKET"],
    )


def _database_fixture(url: str) -> Iterator[None]:
    engine = create_engine(url)
    password_hash = hash_password(PASSWORD, salt=b"0123456789abcdef")
    cleanup = text("""
        DELETE FROM audit.audit_logs WHERE user_id LIKE 'M2-IT-%';
        DELETE FROM app.refresh_tokens WHERE user_id LIKE 'M2-IT-%';
        DELETE FROM app.advertisement_files WHERE advertisement_id IN
          (SELECT advertisement_id FROM app.advertisements WHERE owner_user_id LIKE 'M2-IT-%');
        DELETE FROM app.advertisements WHERE owner_user_id LIKE 'M2-IT-%';
        DELETE FROM app.user_roles WHERE user_id LIKE 'M2-IT-%';
        DELETE FROM app.users WHERE user_id LIKE 'M2-IT-%';
        DELETE FROM app.departments WHERE department_id LIKE 'M2-IT-%';
    """)
    with engine.begin() as connection:
        connection.execute(cleanup)
        connection.execute(
            text("""
            INSERT INTO app.departments (department_id,department_name,is_active)
            VALUES ('M2-IT-A','Integration A',true),('M2-IT-B','Integration B',true)
        """)
        )
        connection.execute(
            text("""
            INSERT INTO app.roles (role_id,role_name,is_active)
            VALUES ('PRODUCT_DEPARTMENT_USER','Product',true)
            ON CONFLICT (role_id) DO NOTHING
        """)
        )
        for suffix in ("A", "B"):
            connection.execute(
                text("""
                INSERT INTO app.users
                (user_id,auth_provider,user_name,email,password_hash,department_id,user_status,
                 auth_token_version,failed_login_count)
                VALUES (:user_id,'LOCAL',:user_id,:email,:password_hash,:department_id,'ACTIVE',1,0)
            """),
                {
                    "user_id": f"M2-IT-{suffix}",
                    "email": f"m2-{suffix.casefold()}@example.invalid",
                    "password_hash": password_hash,
                    "department_id": f"M2-IT-{suffix}",
                },
            )
            connection.execute(
                text("""
                INSERT INTO app.user_roles (user_role_id,user_id,role_id)
                VALUES (gen_random_uuid(),:user_id,'PRODUCT_DEPARTMENT_USER')
            """),
                {"user_id": f"M2-IT-{suffix}"},
            )
    try:
        yield
    finally:
        with engine.begin() as connection:
            connection.execute(cleanup)
        engine.dispose()


def test_actual_postgres_minio_http_vertical_slice() -> None:
    settings = _settings()
    assert settings.nh_db_runtime_url is not None
    db_url = settings.nh_db_runtime_url.get_secret_value()
    for _ in _database_fixture(db_url):
        services = build_services(settings)
        with TestClient(create_app(settings, services)) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"email": "m2-a@example.invalid", "password": PASSWORD},
            )
            assert login.status_code == 200, login.text
            token = login.json()["accessToken"]
            png = base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            )
            created = client.post(
                "/api/v1/advertisements",
                headers={"Authorization": f"Bearer {token}"},
                data={
                    "advertisementName": "Integration advertisement",
                    "productGroup": "SAVINGS",
                    "advertisementType": "MOBILE_BANNER",
                    "departmentId": "M2-IT-A",
                },
                files={"advertisementFile": ("integration.png", png, "image/png")},
            )
            assert created.status_code == 201, created.text
            file_id = created.json()["files"][0]["fileId"]
            downloaded = client.get(
                f"/api/v1/files/{file_id}/download",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert downloaded.status_code == 200 and downloaded.content == png

            other_login = client.post(
                "/api/v1/auth/login",
                json={"email": "m2-b@example.invalid", "password": PASSWORD},
            )
            other_token = other_login.json()["accessToken"]
            denied = client.get(
                f"/api/v1/files/{file_id}/download",
                headers={"Authorization": f"Bearer {other_token}"},
            )
            assert denied.status_code == 403

            advertisement = services.repository.get_advertisement(created.json()["advertisementId"])
            assert advertisement is not None
            with create_engine(db_url).connect() as connection:
                metadata = (
                    connection.execute(
                        text("""
                        SELECT storage_provider,bucket,object_key,checksum_sha256
                          FROM app.advertisement_files WHERE file_id=:file_id
                    """),
                        {"file_id": file_id},
                    )
                    .mappings()
                    .one()
                )
            assert metadata["storage_provider"] == "minio"
            assert metadata["bucket"] == settings.ad_originals_bucket
            assert str(metadata["object_key"]).startswith("advertisements/")
            assert len(metadata["checksum_sha256"]) == 64
            for file in advertisement.files:
                services.advertisements.storage.delete(file.storage_key)
