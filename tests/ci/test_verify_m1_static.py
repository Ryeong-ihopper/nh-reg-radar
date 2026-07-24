from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.ci.verify_m1_static import (
    VerificationError,
    verify_compose_json,
    verify_image_inspect_json,
    verify_namespaces,
    verify_privileged_ci_boundary,
)


DEV_ENV = """\
POSTGRES_DB=nh_ad_dev
MINIO_AD_BUCKET=dev-ad-originals
QDRANT_COLLECTION=dev_reference_chunks
OPENSEARCH_INDEX=dev_reference_docs
REDIS_KEY_PREFIX=dev:
"""
PROD_ENV = """\
POSTGRES_DB=nh_ad_prod
MINIO_AD_BUCKET=prod-ad-originals
QDRANT_COLLECTION=prod_reference_chunks
OPENSEARCH_INDEX=prod_reference_docs
REDIS_KEY_PREFIX=prod:
"""


class M1StaticVerificationTests(unittest.TestCase):
    def test_namespaces_require_distinct_values_for_every_resource_class(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dev = root / ".env.dev.example"
            prod = root / ".env.prod.example"
            dev.write_text(DEV_ENV, encoding="utf-8")
            prod.write_text(PROD_ENV, encoding="utf-8")

            verify_namespaces(dev, prod)

            prod.write_text(PROD_ENV.replace("nh_ad_prod", "nh_ad_dev"), encoding="utf-8")
            with self.assertRaisesRegex(VerificationError, "POSTGRES_DB is shared"):
                verify_namespaces(dev, prod)

    def test_normal_ci_job_cannot_receive_privileged_credential(self) -> None:
        workflow = """\
jobs:
  product-quality:
    runs-on: ubuntu-latest
    steps: []
  db-bootstrap-privilege-probe:
    runs-on: ubuntu-latest
    env:
      NH_DB_ADMIN_PASSWORD: ephemeral-ci-only
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ci.yml"
            path.write_text(workflow, encoding="utf-8")
            verify_privileged_ci_boundary(path)

            path.write_text(
                workflow.replace("steps: []", "env:\n      NH_DB_ADMIN_PASSWORD: leaked"),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(VerificationError, "product-quality"):
                verify_privileged_ci_boundary(path)

    def test_rendered_services_and_images_reject_privileged_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            compose_path = root / "compose.json"
            image_path = root / "images.json"
            compose = {
                "services": {
                    **{
                        name: {"environment": {"APP_ENV": "dev"}}
                        for name in ("backend", "worker", "frontend")
                    },
                    "db-bootstrap": {
                        "environment": {"NH_DB_REVOKE_BOOTSTRAP_LOGIN": "true"},
                        "command": [
                            'until pg_isready -h 127.0.0.1 -U "$$POSTGRES_USER"; do sleep 1; done'
                        ],
                    },
                    "postgres": {
                        "environment": {"POSTGRES_DB": "nh_ad_dev"},
                        "depends_on": {
                            "db-bootstrap": {"condition": "service_completed_successfully"}
                        },
                        "healthcheck": {"test": ["CMD-SHELL", "pg_isready -U app -d nh_ad_dev"]},
                    },
                    "opensearch": {"environment": {"DISABLE_SECURITY_PLUGIN": "true"}},
                }
            }
            images = [{"Id": "sha256:test", "Config": {"Env": ["APP_ENV=dev"]}}]
            compose_path.write_text(json.dumps(compose), encoding="utf-8")
            image_path.write_text(json.dumps(images), encoding="utf-8")
            verify_compose_json(compose_path)
            verify_image_inspect_json(image_path)

            compose["services"]["worker"]["environment"] = {"NH_DB_ADMIN_PASSWORD": "leaked"}
            compose_path.write_text(json.dumps(compose), encoding="utf-8")
            with self.assertRaisesRegex(VerificationError, "worker:NH_DB_ADMIN_PASSWORD"):
                verify_compose_json(compose_path)

    def test_rendered_compose_requires_one_shot_bootstrap_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "compose.json"
            services = {
                name: {"environment": {"APP_ENV": "dev"}}
                for name in ("backend", "worker", "frontend")
            }
            services["db-bootstrap"] = {
                "environment": {"NH_DB_REVOKE_BOOTSTRAP_LOGIN": "false"},
                "command": ["until pg_isready -h 127.0.0.1; do sleep 1; done"],
            }
            services["postgres"] = {
                "environment": {"POSTGRES_BOOTSTRAP_PASSWORD": "leaked"},
                "depends_on": {},
            }
            services["opensearch"] = {
                "environment": {
                    "DISABLE_SECURITY_PLUGIN": "false",
                    "plugins.security.disabled": "true",
                }
            }
            path.write_text(json.dumps({"services": services}), encoding="utf-8")
            with self.assertRaisesRegex(
                VerificationError,
                "db-bootstrap:NH_DB_REVOKE_BOOTSTRAP_LOGIN must be true.*"
                "db-bootstrap readiness must use POSTGRES_USER.*"
                "postgres must depend on successful one-shot db-bootstrap completion.*"
                "postgres healthcheck must use the app role.*"
                "postgres:POSTGRES_BOOTSTRAP_PASSWORD.*"
                "opensearch:DISABLE_SECURITY_PLUGIN must be true.*"
                "opensearch must not duplicate the security-disabled setting",
            ):
                verify_compose_json(path)


if __name__ == "__main__":
    unittest.main()
