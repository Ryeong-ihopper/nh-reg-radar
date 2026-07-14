from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / "infra/postgres/init/010-bootstrap-roles.sh"
MIGRATION_ENV = ROOT / "apps/backend/migrations/env.py"
BASE_REVISION = ROOT / "apps/backend/migrations/versions/0001_schema_only_base.py"


class DatabaseBootstrapContractTests(unittest.TestCase):
    def test_shell_entrypoints_parse(self) -> None:
        scripts = [
            BOOTSTRAP,
            ROOT / "scripts/db-bootstrap-privilege-probe.sh",
            ROOT / "scripts/db-privilege-probe.sh",
            ROOT / "scripts/run-migrations.sh",
            ROOT / "scripts/seed-common-data.sh",
            ROOT / "scripts/seed-dev-data.sh",
        ]
        for script in scripts:
            with self.subTest(script=script.relative_to(ROOT)):
                subprocess.run(["bash", "-n", str(script)], check=True)

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

    def test_bootstrap_probe_revokes_its_ephemeral_identity(self) -> None:
        text = (ROOT / "scripts/db-bootstrap-privilege-probe.sh").read_text()
        self.assertIn("ALTER ROLE %I NOLOGIN", text)
        self.assertIn("revoked bootstrap credential was unexpectedly reusable", text)


if __name__ == "__main__":
    unittest.main()
