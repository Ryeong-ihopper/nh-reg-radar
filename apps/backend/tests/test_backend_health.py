from fastapi.testclient import TestClient

from nh_ad_backend.main import create_app
from nh_ad_backend.settings import Settings


def test_health_reports_service_and_environment() -> None:
    client = TestClient(create_app(Settings(app_env="test", service_name="backend")))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "backend",
        "environment": "test",
    }


def test_health_is_not_a_capability_contract_path() -> None:
    client = TestClient(create_app(Settings(app_env="test")))

    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/health" not in response.json()["paths"]
