"""Synthetic runtime wiring checks, without evaluation answers or ad fixtures."""
import json
import tempfile
import unittest
from pathlib import Path

import run_gemma_exhaustive_dgx as gemma
from rag.api.service import OperationalReviewService, ServiceConfig
from test_operational_rag_contracts import request_row


class OperationalOwnerGatesTests(unittest.TestCase):
    def expand(self, owners, *, fact_owner="LLM", fact_status="SATISFIED"):
        row = request_row(["SYNTHETIC"])
        payload = json.loads(row["messages"][1]["content"])
        payload["rules"][0]["condition_contract"] = {
            "scope_ref": "SCOPE", "scope_owner": "RULE",
            "applicability_conditions": [{"condition_id": "A1", "text": "synthetic trigger", "owner": fact_owner}],
            "applicability_logic": {"all": [{"fact": "A1"}]}, "review_conditions": [],
            "obligation_checks": [{"obligation_id": "O1", "text": "synthetic duty", "owners": owners}],
            "obligation_logic": {"all": [{"ref": "O1"}]},
        }
        row["messages"][1]["content"] = json.dumps(payload)
        _, aliases = gemma._compact_model_request(row)
        output = gemma._expand_model_response(row, {"results": [{
            "rule_ref": "R1", "scope_check": {"scope_ref": "SCOPE", "status": "MATCHED"},
            "condition_checks": [{"condition_ref": "A1", "status": fact_status, "evidence_refs": ["L1"]}],
            "review_condition_checks": [], "requirement_checks": [{"obligation_ref": "O1",
                "requirement": "synthetic duty", "status": "SATISFIED", "finding_basis": "OBSERVED",
                "evidence_refs": ["L1"], "reason": "'테스트 근거' 확인"}],
            "verdict": "COMPLIANT", "reason": "'테스트 근거' 확인", "confidence": "HIGH",
        }]}, aliases)
        return row, output

    def test_advertisement_atoms_can_pass_but_external_and_human_atoms_stay_unknown(self):
        for owners, expected in (({}, "COMPLIANT"), ({"human": True}, "UNDETERMINED"),
                                 ({"external_input": True}, "UNDETERMINED")):
            with self.subTest(owners=owners):
                _, output = self.expand(owners)
                self.assertEqual(expected, output["results"][0]["verdict"])

    def test_external_fact_cannot_be_asserted_from_advertisement_text(self):
        _, output = self.expand({}, fact_owner="LLM_EXTERNAL")
        self.assertEqual("UNDETERMINED", output["results"][0]["applicability"])

    def test_negative_gate_retains_its_own_evidence_for_scope_validation(self):
        row, output = self.expand({}, fact_status="NOT_SATISFIED")
        result = output["results"][0]
        self.assertEqual(["L-1"], result["condition_checks"][0]["evidence_line_refs"])
        result["condition_checks"][0]["evidence_line_refs"] = ["OTHER-PRODUCT-LINE"]
        self.assertTrue(any("조건 게이트" in e for e in gemma.validate(row, output)))

    def test_all_canonical_paths_cannot_be_disabled_or_point_to_missing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.touch()
            for policy in ("template-only", "template-plus-v2"):
                for values in ({"canonical_plans_path": None, "catalog_migration_path": None, "rule_dispositions_path": None},
                               {"canonical_plans_path": root / "missing.json"}):
                    with self.subTest(policy=policy, values=values), self.assertRaisesRegex(RuntimeError, "canonical"):
                        OperationalReviewService(ServiceConfig(jobs_dir=root / "jobs", regulation_path=source,
                            template_hwpx_path=source, source_policy=policy, es_url="unused", es_index="unused", model="unused", **values))
