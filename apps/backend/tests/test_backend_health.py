import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from nh_ad_backend.main import create_app
from nh_ad_backend.results_openapi import RESULTS_OPENAPI
from nh_ad_backend.reviews_openapi import REVIEWS_OPENAPI
from nh_ad_backend.settings import Settings
from nh_ad_backend.standards_openapi import STANDARDS_OPENAPI
from nh_ad_backend.support_openapi import SUPPORT_OPENAPI
from nh_ad_backend.validation_openapi import VALIDATION_OPENAPI


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


def test_governed_openapi_fragments_have_distinct_domain_paths() -> None:
    fragments = {
        "standards": (STANDARDS_OPENAPI, "/standards"),
        "reviews": (REVIEWS_OPENAPI, "/reviews/{reviewId}/status"),
        "results": (RESULTS_OPENAPI, "/reviews/{reviewId}/summary"),
        "support": (SUPPORT_OPENAPI, "/qa/questions"),
        "validation": (VALIDATION_OPENAPI, "/validation/datasets"),
    }
    owners_by_path: dict[str, str] = {}

    for owner, (fragment, representative_path) in fragments.items():
        paths = fragment["paths"]
        assert representative_path in paths
        for path in paths:
            assert path not in owners_by_path, (
                f"{path} is owned by both {owners_by_path[path]} and {owner}"
            )
            owners_by_path[path] = owner


def test_runtime_openapi_semantically_matches_static_contract(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[3]
    static_process = subprocess.run(
        [
            "node",
            str(repository_root / "scripts/print_openapi_json.mjs"),
            str(repository_root / "openapi/openapi.yaml"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    static = json.loads(static_process.stdout)
    runtime = TestClient(create_app(Settings(app_env="test"))).get("/openapi.json").json()
    runtime_path = tmp_path / "runtime-openapi.json"
    runtime_path.write_text(json.dumps(runtime), encoding="utf-8")
    comparison = subprocess.run(
        [
            "python3",
            str(repository_root / "scripts/compare_openapi_contract.py"),
            str(repository_root / "openapi/openapi.yaml"),
            str(runtime_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert runtime["info"]["version"] == static["info"]["version"] == "0.8.0"
    assert _operations(runtime) == _operations(static)
    assert comparison.returncode == 0, comparison.stderr


def _operations(document: dict[str, object]) -> set[tuple[str, str, str]]:
    methods = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
    paths = document["paths"]
    assert isinstance(paths, dict)
    return {
        (path, method, operation["operationId"])
        for path, path_item in paths.items()
        if isinstance(path_item, dict)
        for method, operation in path_item.items()
        if method in methods and isinstance(operation, dict)
    }
