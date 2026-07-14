from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from nh_ad_backend.api import ApplicationServices
from nh_ad_backend.domain import User
from nh_ad_backend.main import create_app
from nh_ad_backend.repository import InMemoryRepository
from nh_ad_backend.security import LoginRateLimiter, TokenService, hash_password
from nh_ad_backend.services import AdvertisementService, AuthService
from nh_ad_backend.settings import Settings
from nh_ad_backend.storage import PrivateFileStorage


PASSWORD = "SecurePassword!42"
JWT_SECRET = "test-jwt-secret-with-more-than-thirty-two-characters"


class Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 7, 14, 6, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.value


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def repository() -> InMemoryRepository:
    password_hash = hash_password(PASSWORD, salt=b"0123456789abcdef")
    users = [
        User(
            "user-a",
            "상품담당A",
            "a@example.com",
            password_hash,
            "DPT-A",
            "상품부 A",
            ("PRODUCT_DEPARTMENT_USER",),
        ),
        User(
            "user-b",
            "상품담당B",
            "b@example.com",
            password_hash,
            "DPT-B",
            "상품부 B",
            ("PRODUCT_DEPARTMENT_USER",),
        ),
        User(
            "reviewer",
            "준법담당",
            "review@example.com",
            password_hash,
            "DPT-C",
            "준법부",
            ("COMPLIANCE_REVIEWER",),
        ),
        User(
            "admin",
            "관리자",
            "admin@example.com",
            password_hash,
            "DPT-C",
            "준법부",
            ("SYSTEM_ADMIN",),
        ),
        User(
            "standard",
            "기준담당",
            "standard@example.com",
            password_hash,
            "DPT-C",
            "준법부",
            ("STANDARD_MANAGER",),
        ),
    ]
    return InMemoryRepository(users)


@pytest.fixture
def services(repository: InMemoryRepository, clock: Clock, tmp_path: Path) -> ApplicationServices:
    tokens = TokenService(JWT_SECRET, now=clock)
    counter = iter(range(1, 100))
    return ApplicationServices(
        repository=repository,
        auth=AuthService(repository, tokens, now=clock, rate_limiter=LoginRateLimiter(clock)),
        advertisements=AdvertisementService(
            repository,
            PrivateFileStorage(tmp_path / "objects"),
            now=clock,
            identifier=lambda prefix: f"{prefix}-{next(counter):04d}",
        ),
    )


@pytest.fixture
def client(services: ApplicationServices) -> Iterator[TestClient]:
    application = create_app(
        Settings(
            app_env="test",
            jwt_secret=SecretStr(JWT_SECRET),
            cors_allowed_origins="http://localhost:5173",
            refresh_cookie_secure=False,
        ),
        services,
    )
    with TestClient(application) as test_client:
        yield test_client


def login(client: TestClient, email: str = "a@example.com") -> tuple[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
        headers={"x-request-id": "req-login"},
    )
    assert response.status_code == 200, response.text
    return response.json()["accessToken"], response.cookies["refreshToken"]
