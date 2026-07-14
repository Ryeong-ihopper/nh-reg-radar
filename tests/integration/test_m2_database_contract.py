from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "apps/backend/migrations/versions/0002_m2_auth_advertisement_audit.py"
MANIFEST = ROOT / "tests/fixtures/m2/trace-manifest.json"


class M2DatabaseContractTests(unittest.TestCase):
    def test_owner_revision_is_bounded_and_seed_free(self) -> None:
        text = MIGRATION.read_text(encoding="utf-8")
        created = re.findall(r'op\.create_table\(\s*"([a-z_]+)"', text)
        self.assertEqual(
            created,
            [
                "departments",
                "roles",
                "users",
                "user_roles",
                "refresh_tokens",
                "common_codes",
                "advertisements",
                "advertisement_revisions",
                "advertisement_files",
                "audit_logs",
            ],
        )
        self.assertIn('down_revision: str | None = "0001_schema_only_base"', text)
        self.assertNotRegex(text, r"""(?i)op\.(?:bulk_insert|execute)\(\s*["']INSERT\b""")
        self.assertNotRegex(text, r"(?i)\b(?:CREATE ROLE|ALTER ROLE|DROP ROLE)\b")
        self.assertTrue(
            {"reviews", "review_jobs", "standards", "evidences", "reports"}.isdisjoint(created)
        )
        for column in ("storage_provider", "bucket", "object_key", "checksum_sha256"):
            self.assertIn(f'sa.Column("{column}"', text)
        self.assertNotIn('sa.Column("file_path"', text)
        self.assertNotIn('sa.Column("stored_file_name"', text)
        self.assertIn(
            '"idx_refresh_tokens_active",\n        "refresh_tokens",\n'
            '        ["user_id", "revoked_at", "expires_at"]',
            text,
        )
        self.assertIn('sa.Column("token_version", sa.Integer(), nullable=False)', text)

    def test_manifest_matches_migration_owner_boundary(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["migration"],
            {
                "revision": "0002_m2_auth_advertisement_audit",
                "downRevision": "0001_schema_only_base",
                "path": "apps/backend/migrations/versions/0002_m2_auth_advertisement_audit.py",
                "ownedTables": [
                    "app.departments",
                    "app.roles",
                    "app.users",
                    "app.user_roles",
                    "app.refresh_tokens",
                    "app.common_codes",
                    "app.advertisements",
                    "app.advertisement_revisions",
                    "app.advertisement_files",
                    "audit.audit_logs",
                ],
            },
        )

    def test_common_and_dev_seeds_are_idempotent_and_separated(self) -> None:
        common = (ROOT / "apps/backend/seeds/common.sql").read_text(encoding="utf-8")
        dev = (ROOT / "apps/backend/seeds/dev.sql").read_text(encoding="utf-8")
        migration = MIGRATION.read_text(encoding="utf-8")

        self.assertIn("ON CONFLICT", common)
        self.assertIn("ON CONFLICT", dev)
        self.assertNotIn("USR-SYNTH", common)
        self.assertNotIn("product@example.invalid", migration)
        self.assertNotRegex(common + dev, r"(?i)(customer|client)[-_ ]?(secret|token|password)")

    def test_seed_entrypoints_parse_and_dev_seed_refuses_prod(self) -> None:
        for name in ("seed-common-data.sh", "seed-dev-data.sh"):
            subprocess.run(["bash", "-n", str(ROOT / "scripts" / name)], check=True)

        result = subprocess.run(
            ["bash", str(ROOT / "scripts/seed-dev-data.sh")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            env={"PATH": "/usr/bin:/bin", "NH_ENVIRONMENT": "prod"},
            check=False,
        )
        self.assertEqual(result.returncode, 64)
        self.assertIn("NH_ENVIRONMENT=dev", result.stderr)

    def test_runtime_grants_are_dml_only(self) -> None:
        text = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("GRANT USAGE ON SCHEMA app, audit TO app, readonly", text)
        self.assertIn(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app, audit TO app",
            text,
        )
        self.assertNotRegex(text, r"GRANT .*\b(?:CREATE|TRUNCATE|REFERENCES|TRIGGER)\b.* TO app")


if __name__ == "__main__":
    _ = unittest.main()
