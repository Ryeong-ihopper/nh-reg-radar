import base64
import hashlib
import hmac
import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from conftest import JWT_SECRET, PASSWORD, Clock, login
from nh_ad_backend.api import ApplicationServices
from nh_ad_backend.main import create_app
from nh_ad_backend.repository import InMemoryRepository
from nh_ad_backend.security import TokenError, TokenService
from nh_ad_backend.services import ServiceError
from nh_ad_backend.settings import Settings


def test_bearer_login_me_cookie_and_security_headers(client: TestClient) -> None:
    denied = client.get("/api/v1/users/me", headers={"x-request-id": "req-denied"})
    assert denied.status_code == 401
    assert denied.json()["traceId"] == "req-denied"
    assert denied.headers["cache-control"] == "no-store"

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "a@example.com", "password": PASSWORD},
    )
    assert response.status_code == 200
    assert response.json()["expiresIn"] == 1800
    cookie = response.headers["set-cookie"]
    assert "refreshToken=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert "Secure" not in cookie
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"

    me = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {response.json()['accessToken']}"},
    )
    assert me.status_code == 200
    assert me.headers["cache-control"] == "no-store"
    assert me.json() == {
        "userId": "user-a",
        "userName": "상품담당A",
        "departmentId": "DPT-A",
        "departmentName": "상품부 A",
        "roles": ["PRODUCT_DEPARTMENT_USER"],
    }


def test_refresh_rotation_origin_logout_and_version_revoke(
    client: TestClient,
    repository: InMemoryRepository,
) -> None:
    access, refresh_token = login(client)
    del access
    forbidden = client.post("/api/v1/auth/refresh", cookies={"refreshToken": refresh_token})
    assert forbidden.status_code == 403
    assert forbidden.headers["cache-control"] == "no-store"

    rotated = client.post(
        "/api/v1/auth/refresh",
        cookies={"refreshToken": refresh_token},
        headers={"Origin": "http://localhost:5173"},
    )
    assert rotated.status_code == 200
    assert rotated.cookies["refreshToken"] != refresh_token
    assert rotated.json()["user"] == {
        "userId": "user-a",
        "userName": "상품담당A",
        "departmentId": "DPT-A",
        "departmentName": "상품부 A",
        "roles": ["PRODUCT_DEPARTMENT_USER"],
    }
    replay = client.post(
        "/api/v1/auth/refresh",
        cookies={"refreshToken": refresh_token},
        headers={"Origin": "http://localhost:5173"},
    )
    assert replay.status_code == 401
    assert all(session.revoked_at is not None for session in repository.refresh_sessions.values())

    current_refresh = rotated.cookies["refreshToken"]
    repository.users["user-a"].auth_token_version += 1
    stale = client.post(
        "/api/v1/auth/refresh",
        cookies={"refreshToken": current_refresh},
        headers={"Referer": "http://localhost:5173/session"},
    )
    assert stale.status_code == 401
    assert all(session.revoked_at is not None for session in repository.refresh_sessions.values())

    _, logout_token = login(client)
    logout = client.post(
        "/api/v1/auth/logout",
        cookies={"refreshToken": logout_token},
        headers={"Origin": "http://localhost:5173"},
    )
    assert logout.status_code == 204
    assert logout.headers["cache-control"] == "no-store"


def test_consecutive_lockout_and_exact_unlock_boundary(
    services: ApplicationServices,
    repository: InMemoryRepository,
    clock: Clock,
) -> None:
    for _ in range(5):
        with pytest.raises(ServiceError) as error:
            services.auth.login("a@example.com", "wrong-password", "192.0.2.1", "pytest", "req")
        assert error.value.status_code == 401
    user = repository.users["user-a"]
    assert user.failed_login_count == 5
    assert user.locked_until == clock.value + timedelta(minutes=15)

    clock.value += timedelta(minutes=15)
    with pytest.raises(ServiceError):
        services.auth.login("a@example.com", "wrong-password", "192.0.2.1", "pytest", "req")
    assert user.failed_login_count == 1
    assert user.locked_until is None


def test_rate_limit_and_generic_failure(client: TestClient) -> None:
    bodies = []
    for _ in range(10):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "unknown@example.com", "password": "unknown-password"},
        )
        bodies.append(response.json())
        assert response.status_code == 401
    limited = client.post(
        "/api/v1/auth/login",
        json={"email": "unknown@example.com", "password": "unknown-password"},
    )
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0
    assert limited.headers["cache-control"] == "no-store"
    assert all("unknown@example.com" not in json.dumps(body) for body in bodies)


def test_jwt_rejects_malformed_claim_types(clock: Clock) -> None:
    service = TokenService(JWT_SECRET, now=clock)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": "user-a",
        "user_id": "other-user",
        "department_id": "DPT-A",
        "roles": ["PRODUCT_DEPARTMENT_USER"],
        "iat": int(clock.value.timestamp()),
        "exp": int((clock.value + timedelta(minutes=30)).timestamp()),
        "jti": "jti",
        "token_version": True,
    }

    def encode(value: object) -> str:
        return (
            base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode())
            .rstrip(b"=")
            .decode()
        )

    head, body = encode(header), encode(payload)
    signature = hmac.new(JWT_SECRET.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
    token = f"{head}.{body}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"
    with pytest.raises(TokenError):
        service.verify_access_token(token)


def test_product_boot_fails_closed_and_insecure_cookie_is_local_only() -> None:
    with pytest.raises(ValueError, match="NH_DB_RUNTIME_URL"):
        create_app(Settings())
    with pytest.raises(ValueError, match="production refresh cookies"):
        Settings(
            app_env="prod",
            refresh_cookie_secure=False,
            cors_allowed_origins="https://poc.example",
        )
    with pytest.raises(ValueError, match="local HTTP origins"):
        Settings(
            app_env="dev",
            refresh_cookie_secure=False,
            cors_allowed_origins="https://dev.example",
        )
    local = Settings(
        app_env="dev",
        refresh_cookie_secure=False,
        cors_allowed_origins="http://localhost:5173",
    )
    assert local.refresh_cookie_secure is False
