from __future__ import annotations

import json
import unittest
from pathlib import Path

from rag.judgment.operational_catalog import (
    audit_canonical_template_coverage,
    load_operational_catalog,
)
from rag.judgment.operational_selection import (
    activate_retrieved,
    confirmed_metadata_facts,
    select_supplemental_plans,
)


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "rag-pipeline" / "config"


def load_catalog():
    plans = json.loads((CONFIG / "canonical-execution-plans-v2.json").read_text(encoding="utf-8"))
    migration = json.loads((CONFIG / "operational-catalog-migration-v1.json").read_text(encoding="utf-8"))
    legacy_ids = [alias for row in migration["rows"] for alias in row["legacy_item_ids"]]
    legacy = [{
        "item_id": item_id, "source_sheet": "HWPX_TEMPLATE", "category": "PRESENCE",
        "category_label": "템플릿 점검", "product_groups": ["전체"],
        "product_subtype": "placeholder", "title": item_id, "question": item_id,
        "criterion": item_id, "required_medium": "텍스트", "input_requirement": "광고물",
        "template_basis": {"structure_status": "STRUCTURED", "source_ref": item_id},
    } for item_id in legacy_ids]
    supplement_ids = [p["plan_id"] for p in plans["plans"]
                      if p["source"]["source_kind"] != "TEMPLATE"]
    supplement_ids += ["D-190", "D-204"]
    v2 = [{
        "item_id": item_id, "source_sheet": "실행_점검항목", "category": "PRESENCE",
        "category_label": "표시", "product_groups": ["전체"], "title": item_id,
        "question": item_id, "criterion": item_id,
    } for item_id in supplement_ids]
    return load_operational_catalog(
        CONFIG / "canonical-execution-plans-v2.json",
        CONFIG / "operational-catalog-migration-v1.json",
        CONFIG / "operational-rule-dispositions-v1.json",
        legacy_template_rules=legacy,
        v2_rules=v2,
    )


class OperationalCanonicalCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()

    def test_catalog_replaces_legacy_template_inventory_and_loads_107_changes(self):
        self.assertEqual(271, self.catalog.counts["plans"])
        self.assertEqual(239, self.catalog.counts["templates"])
        self.assertEqual(32, self.catalog.counts["supplements"])
        self.assertEqual(107, self.catalog.counts["new_or_revised"])
        self.assertEqual(239, len({r["item_id"] for r in self.catalog.template_rules}))

    def test_methodology_basis_reaches_operational_template_rows(self):
        rules = {row["item_id"]: row for row in self.catalog.template_rules}
        mapped = rules["MTH-LOAN-NAMED-R04"]["template_basis"]["legal_basis_refs"]
        self.assertTrue(any("금융소비자 보호에 관한 법률 제22조" in ref for ref in mapped))
        self.assertTrue(any("은행 광고심의 기준" in ref for ref in mapped))
        guidance = rules["MTH-LOAN-NAMED-R23"]["template_basis"]["legal_basis_refs"]
        self.assertTrue(any("은행연합회 지도사항" in ref for ref in guidance))
        self.assertEqual([], rules["MTH-RETIREMENT-ETF-R16"]["template_basis"]["legal_basis_refs"])

    def test_aliases_are_provenance_on_one_target_result(self):
        self.assertIn("D-190", self.catalog.supplemental_rules["C-015"]["supporting_rules"])
        self.assertIn("D-204", self.catalog.supplemental_rules["C-099"]["supporting_rules"])
        self.assertNotIn("D-190", self.catalog.supplemental_rules)
        self.assertNotIn("D-204", self.catalog.supplemental_rules)

    def test_template_support_and_holds_are_not_active_supplements(self):
        for item_id in ("C-005", "D-225", "C-048", "D-198"):
            self.assertNotIn(item_id, self.catalog.supplemental_rules)
        self.assertEqual("CARD_ONLY_OUTSIDE_CURRENT_SCOPE",
                         self.catalog.dispositions["D-225"]["scope"])

    def test_metadata_first_selection_and_retrieval_activation(self):
        routing = {"media_type": {"value": "LMS", "status": "confirmed"}}
        selection = select_supplemental_plans(
            (self.catalog.plans[item_id] for item_id in self.catalog.supplemental_rules),
            product_groups=["투자성"],
            template_id="투자성상품-개인종합자산관리계좌(ISA) 신탁형 [정식]",
            routing=routing,
            layout_available=True,
        )
        self.assertIn("C-018", selection.enumerate_ids)
        self.assertIn("C-025", selection.enumerate_ids)
        self.assertNotIn("C-125", selection.enumerate_ids)
        self.assertIn("D-182", selection.retrieval_ids)
        self.assertIn("D-163", selection.retrieval_ids)
        self.assertIn("D-240", selection.human_ids)
        activated = activate_retrieved(
            [{"item_id": "D-182"}, {"item_id": "C-048"}], selection.retrieval_ids
        )
        self.assertEqual(["D-182"], [row["item_id"] for row in activated])

    def test_template_status_label_is_not_part_of_runtime_identity(self):
        routing = {"media_type": {"value": "WEB", "status": "confirmed"}}
        plan = next(plan for plan in self.catalog.plans.values()
                    if str((plan.get("source") or {}).get("product_template") or "").endswith("[정식]"))
        marked = str(plan["source"]["product_template"])
        plain = marked.removesuffix(" [정식]")
        marked_facts = confirmed_metadata_facts(
            plan, product_groups=["투자성"], template_id=marked, routing=routing)
        plain_facts = confirmed_metadata_facts(
            plan, product_groups=["투자성"], template_id=plain, routing=routing)
        marked_selected = next(row for row in marked_facts if row["basis"] == "template_id")
        plain_selected = next(row for row in plain_facts if row["fact_id"] == marked_selected["fact_id"])
        self.assertIs(marked_selected["value"], True)
        self.assertIs(plain_selected["value"], True)

    def test_unknown_media_defers_presence_rules_instead_of_misapplying(self):
        selection = select_supplemental_plans(
            (self.catalog.plans[item_id] for item_id in self.catalog.supplemental_rules),
            product_groups=["예금성"], template_id="예금성상품-입출식",
            routing={"media_type": {"value": None, "status": "unknown"}},
            layout_available=True,
        )
        pending = {row["item_id"] for row in selection.pending}
        self.assertIn("C-018", pending)
        self.assertIn("C-020", pending)

    def test_coverage_requires_every_selected_plan_to_be_requested_or_deferred(self):
        section = "예금성상품-입출식"
        selected = [r for r in self.catalog.template_rules if r["product_subtype"] == section]
        requested = [r["item_id"] for r in selected[:-1]]
        deferred = [{"item_id": selected[-1]["item_id"]}]
        result = audit_canonical_template_coverage(self.catalog, section, requested, deferred)
        self.assertEqual(0, result["missing_count"])
        with self.assertRaisesRegex(ValueError, "no disposition"):
            audit_canonical_template_coverage(self.catalog, section, requested, [])


if __name__ == "__main__":
    unittest.main()
