from __future__ import annotations

import json
import unittest
from pathlib import Path

from rag.judgment.execution_request_builder import (
    build_execution_requests,
    request_counts,
)


ROOT = Path(__file__).resolve().parents[2]


class ExecutionRequestBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        document = json.loads((
            ROOT / "temp/current-execution-plans-20260921-v5/canonical-execution-plans.json"
        ).read_text(encoding="utf-8"))
        cls.plans = document["plans"]
        cls.context = {"advertisement_id": "AD-1", "product_id": "P-1",
                       "revision_id": "R-1", "scope_id": "ALL-PAGES"}

    def _evidence(self, plan_id: str, role: str = "ADVERTISEMENT_TEXT"):
        return [{"evidence_id": f"{plan_id}-E1", "plan_ref": plan_id,
                 "context": self.context, "source_role": role,
                 "content": "direct advertisement excerpt"}]

    def test_builder_preserves_plan_evidence_namespaces_and_families(self):
        selected = ["C-018", "D-240", "TPL-MAP-029"]
        evidence = {plan_id: self._evidence(plan_id) for plan_id in selected}
        requests = build_execution_requests(
            self.plans, context=self.context, evidence_by_plan=evidence,
            selected_plan_ids=selected, max_items=4, max_complexity=12)
        self.assertEqual(3, request_counts(requests)["plans"])
        for request in requests:
            self.assertTrue(request["response_contract"]["overall_verdict_forbidden"])
            for item in request["plan_inputs"]:
                self.assertTrue(all(row["plan_ref"] == item["plan"]["plan_ref"]
                                    for row in item["evidence"]))

    def test_builder_rejects_cross_revision_and_cross_plan_evidence(self):
        row = self._evidence("C-018")[0]
        row["context"] = {**self.context, "revision_id": "R-2"}
        with self.assertRaisesRegex(ValueError, "context differs"):
            build_execution_requests(self.plans, context=self.context,
                                     evidence_by_plan={"C-018": [row]},
                                     selected_plan_ids=["C-018"])
        row["context"] = self.context
        row["plan_ref"] = "D-240"
        with self.assertRaisesRegex(ValueError, "bound to its plan"):
            build_execution_requests(self.plans, context=self.context,
                                     evidence_by_plan={"C-018": [row]},
                                     selected_plan_ids=["C-018"])

    def test_rule_example_and_answer_cannot_be_advertisement_evidence(self):
        row = self._evidence("C-018", role="RULE_EXAMPLE")[0]
        with self.assertRaisesRegex(ValueError, "cannot be a rule"):
            build_execution_requests(self.plans, context=self.context,
                                     evidence_by_plan={"C-018": [row]},
                                     selected_plan_ids=["C-018"])


if __name__ == "__main__":
    unittest.main()
