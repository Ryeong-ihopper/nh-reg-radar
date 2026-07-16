from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / "infra/postgres/init/010-bootstrap-roles.sh"
MIGRATION_ENV = ROOT / "apps/backend/migrations/env.py"
BASE_REVISION = ROOT / "apps/backend/migrations/versions/0001_schema_only_base.py"
PRODUCT_CI = ROOT / ".github/workflows/ci.yml"
LOCAL_DEV = ROOT / "scripts/local-dev.sh"
DEV_COMPOSE = ROOT / "compose.dev.yml"
DEV_ENV = ROOT / ".env.dev.example"
README = ROOT / "README.md"


class DatabaseBootstrapContractTests(unittest.TestCase):
    def test_shell_entrypoints_parse(self) -> None:
        scripts = [
            BOOTSTRAP,
            ROOT / "scripts/db-bootstrap-privilege-probe.sh",
            ROOT / "scripts/db-privilege-probe.sh",
            ROOT / "scripts/run-migrations.sh",
            ROOT / "scripts/seed-common-data.sh",
            ROOT / "scripts/seed-dev-data.sh",
            LOCAL_DEV,
        ]
        for script in scripts:
            with self.subTest(script=script.relative_to(ROOT)):
                subprocess.run(["bash", "-n", str(script)], check=True)

    def test_local_dev_entrypoint_locks_bootstrap_order_and_browser_api(self) -> None:
        script = LOCAL_DEV.read_text(encoding="utf-8")
        compose = DEV_COMPOSE.read_text(encoding="utf-8")
        environment = DEV_ENV.read_text(encoding="utf-8")
        readme = README.read_text(encoding="utf-8")

        postgres = script.index("up --detach --wait postgres")
        migration = script.index("alembic -c alembic.ini upgrade head")
        common_seed = script.index("apps/backend/seeds/common.sql")
        dev_seed = script.index("apps/backend/seeds/dev.sql")
        complete_stack = script.index("up --detach --build --wait")
        self.assertLess(postgres, migration)
        self.assertLess(migration, common_seed)
        self.assertLess(common_seed, dev_seed)
        self.assertLess(dev_seed, complete_stack)
        self.assertIn("down --volumes --remove-orphans", script)
        self.assertIn("POSTGRES_DB must match the database name in both NH_DB URLs", script)
        self.assertNotIn("NH_DB_ADMIN_PASSWORD", script)
        self.assertNotIn("POSTGRES_BOOTSTRAP_PASSWORD", script)

        self.assertIn("VITE_API_BASE_URL:", compose)
        self.assertIn("VITE_API_BASE_URL=http://localhost:8000/api/v1", environment)
        self.assertIn("scripts/local-dev.sh up", readme)
        self.assertIn("scripts/local-dev.sh reset", readme)
        self.assertIn("product@example.invalid", readme)

    def test_bootstrap_owns_only_fixed_roles_and_database_grants(self) -> None:
        text = BOOTSTRAP.read_text()
        created_roles = set(re.findall(r"CREATE ROLE ([a-z]+) LOGIN", text))
        self.assertEqual(created_roles, {"app", "migration", "readonly", "admin"})
        self.assertNotIn("SUPERUSER PASSWORD", text)
        self.assertNotRegex(text, r"(?i)CREATE\s+(?:SCHEMA|TABLE)")
        self.assertNotIn('--dbname "$NH_DB', text)
        self.assertIn("NH_DB_REVOKE_BOOTSTRAP_LOGIN", text)
        self.assertIn("ALTER ROLE %I NOLOGIN", text)

    def test_alembic_base_is_schema_only_and_role_free(self) -> None:
        env_text = MIGRATION_ENV.read_text()
        revision_text = BASE_REVISION.read_text()
        self.assertIn('identity != "migration"', env_text)
        self.assertIn('"version_table_schema": "app"', env_text)
        self.assertEqual(
            set(re.findall(r'"(app|rag|validation|audit)"', revision_text)),
            {"app", "rag", "validation", "audit"},
        )
        combined = f"{env_text}\n{revision_text}"
        self.assertNotRegex(combined, r"(?i)(CREATE|ALTER|DROP)\s+ROLE")
        self.assertNotRegex(revision_text, r"(?i)CREATE\s+TABLE")

    def test_seed_boundaries_are_separate_and_dev_guarded(self) -> None:
        revision_text = BASE_REVISION.read_text().lower()
        self.assertNotIn("insert", revision_text)
        dev_seed = ROOT / "scripts/seed-dev-data.sh"
        result = subprocess.run(
            ["bash", str(dev_seed)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            env={"PATH": "/usr/bin:/bin", "NH_ENVIRONMENT": "prod"},
        )
        self.assertEqual(result.returncode, 64)
        self.assertIn("NH_ENVIRONMENT=dev", result.stderr)

    def test_privilege_probe_covers_required_denials(self) -> None:
        text = (ROOT / "scripts/db-privilege-probe.sh").read_text()
        labels = set(re.findall(r"'((?:migration|app|readonly) [^']+)'\n", text))
        self.assertEqual(
            labels,
            {
                "migration CREATE ROLE",
                "migration ALTER ROLE",
                "app DDL",
                "app role management",
                "readonly INSERT",
                "readonly UPDATE",
                "readonly DELETE",
                "readonly DDL",
            },
        )

    def test_privilege_probe_checks_migrated_objects_instead_of_empty_database(self) -> None:
        text = (ROOT / "scripts/db-privilege-probe.sh").read_text()
        self.assertNotIn('[[ "$table_count" == "0" ]]', text)
        for relation in (
            "app.users",
            "app.ocr_text_blocks",
            "rag.evidences",
            "validation.validation_datasets",
            "audit.audit_logs",
        ):
            self.assertIn(relation, text)
        self.assertIn("0009_operational_consistency", text)

    def test_product_ci_installs_openapi_tooling_before_python_contract_tests(self) -> None:
        text = PRODUCT_CI.read_text()
        install = text.index("npm ci --ignore-scripts")
        tests = text.index('uv run python -m pytest -m "not external_ai and not slow"')
        self.assertLess(install, tests)

    def test_bootstrap_probe_revokes_its_ephemeral_identity(self) -> None:
        text = (ROOT / "scripts/db-bootstrap-privilege-probe.sh").read_text()
        self.assertIn("ALTER ROLE %I NOLOGIN", text)
        self.assertIn("revoked bootstrap credential was unexpectedly reusable", text)


if __name__ == "__main__":
    unittest.main()
