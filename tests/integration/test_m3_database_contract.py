from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "apps/backend/migrations/versions/0003_m3_standards_search.py"
MANIFEST = ROOT / "tests/fixtures/m3/trace-manifest.json"


class M3DatabaseContractTests(unittest.TestCase):
    def test_owner_revision_is_bounded_seed_free_and_follows_m2(self) -> None:
        text = MIGRATION.read_text(encoding="utf-8")
        created = re.findall(r'op\.create_table\(\s*"([a-z_]+)"', text)
        self.assertEqual(
            created,
            [
                "standards",
                "standard_versions",
                "evidences",
                "evidence_chunks",
                "standard_reindex_jobs",
            ],
        )
        self.assertIn('down_revision: str | None = "0002_m2_auth_advertisement_audit"', text)
        self.assertNotRegex(text, r"""(?i)op\.(?:bulk_insert|execute)\(\s*["']INSERT\b""")
        self.assertNotRegex(text, r"(?i)\b(?:CREATE ROLE|ALTER ROLE|DROP ROLE)\b")

    def test_version_history_and_search_idempotency_constraints_are_locked(self) -> None:
        text = MIGRATION.read_text(encoding="utf-8")
        for constraint in (
            "uk_standard_versions",
            "uk_evidences_standard_version",
            "uk_evidence_chunks_version_no",
            "uk_evidence_chunks_qdrant_id",
            "uk_evidence_chunks_opensearch_id",
        ):
            self.assertIn(constraint, text)
        for column in (
            "standard_version_id",
            "effective_date",
            "expired_date",
            "qdrant_index_status",
            "opensearch_index_status",
            "search_schema_version",
            "opensearch_analyzer_version",
            "synonym_version",
        ):
            self.assertRegex(text, rf'sa\.Column\(\s*"{column}"')

    def test_manifest_matches_owner_boundary(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["migration"]["revision"], "0003_m3_standards_search")
        self.assertEqual(
            manifest["migration"]["ownedTables"],
            [
                "rag.standards",
                "rag.standard_versions",
                "rag.evidences",
                "rag.evidence_chunks",
                "rag.standard_reindex_jobs",
            ],
        )

    def test_seed_is_idempotent_synthetic_and_direct_text_only(self) -> None:
        seed = (ROOT / "apps/backend/seeds/m3_test.sql").read_text(encoding="utf-8")
        self.assertIn("ON CONFLICT", seed)
        self.assertIn("SYNTH", seed)
        self.assertNotRegex(seed, r"(?i)\b(?:pdf|hwp|hwpx|ocr|embedding provider)\b")
        self.assertNotRegex(seed, r"(?i)(customer|client)[-_ ]?(secret|token|password)")

    def test_runtime_grants_cover_rag_dml_without_ddl(self) -> None:
        text = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("GRANT USAGE ON SCHEMA rag TO app, readonly", text)
        self.assertIn(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA rag TO app",
            text,
        )
        self.assertNotRegex(text, r"GRANT .*\b(?:CREATE|TRUNCATE|REFERENCES|TRIGGER)\b.* TO app")


if __name__ == "__main__":
    _ = unittest.main()
