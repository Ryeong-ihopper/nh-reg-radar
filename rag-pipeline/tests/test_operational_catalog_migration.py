from __future__ import annotations

import unittest

from rag.templates.operational_catalog_migration import audit_catalog_migration


def plan(plan_id: str, section: str, label: str, example: str, kind: str = "TEMPLATE"):
    return {"plan_id": plan_id, "source_sha256": plan_id,
            "source": {"source_kind": kind, "product_template": section,
                       "label": label, "source_fields": {"example": example}}}


class OperationalCatalogMigrationTests(unittest.TestCase):
    def test_exact_mapping_allows_format_only_normalization(self):
        plans = [plan("P1", "예금성 [정식]", "회사명", "- NH농협은행")]
        legacy = {"entries": [{"item_id": "OLD-1", "template_section": "예금성",
                               "fields": {"label": {"text": "회사명"},
                                          "example": {"text": "NH농협은행"}}}]}
        report = audit_catalog_migration(plans, legacy)
        self.assertEqual("EXACT_LEGACY_ALIAS", report["rows"][0]["migration_state"])
        self.assertEqual(["OLD-1"], report["rows"][0]["legacy_item_ids"])

    def test_no_fuzzy_mapping_and_ambiguous_exact_rows_are_held(self):
        plans = [plan("P1", "예금성", "회사명 표기", "NH농협은행")]
        entry = {"item_id": "OLD-1", "template_section": "예금성",
                 "fields": {"label": {"text": "회사명"},
                            "example": {"text": "NH농협은행"}}}
        report = audit_catalog_migration(plans, {"entries": [entry]})
        self.assertEqual("NEW_OR_REVISED_SOURCE_ROW", report["rows"][0]["migration_state"])
        plans[0]["source"]["label"] = "회사명"
        report = audit_catalog_migration(plans, {"entries": [entry, {**entry, "item_id": "OLD-2"}]})
        self.assertEqual("AMBIGUOUS_EXACT_SOURCE_ROW", report["rows"][0]["migration_state"])

    def test_supplemental_plans_never_alias_template_rows(self):
        report = audit_catalog_migration(
            [plan("C-018", "", "수신거부", "", kind="SUPPLEMENTAL_V2")],
            {"entries": []})
        self.assertEqual("NEW_SUPPLEMENTAL_PLAN", report["rows"][0]["migration_state"])


if __name__ == "__main__":
    unittest.main()
