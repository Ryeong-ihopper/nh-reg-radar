"""Synthetic wire checks: structural decoding must not choose a legal verdict."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_operational_rag_contracts import gemma, request_row
from rag.judgment.output_contract import response_format


class OutputContractTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"NH_JUDGE_RESPONSE_FORMAT": "json_schema"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.row = request_row(["TEST-A"])
        p = json.loads(self.row["messages"][1]["content"])
        p["rules"][0]["condition_contract"] = {"applicability_conditions": [],
            "review_conditions": [], "obligation_checks": [{"obligation_id": "O1"}]}
        p["evidence_scope"] = {"TEST-A": {"evidence_ids": ["E-1"], "complete_ad_scan": False}}
        self.row["messages"][1]["content"] = json.dumps(p)
        messages, _ = gemma._compact_model_request(self.row)
        self.compact = json.loads(messages[1]["content"])
        self.schema = response_format(self.compact)["json_schema"]["schema"]
        self.result_schema = self.schema["properties"]["results"]["items"]

    def sample(self):
        return {"results": [{"rule_ref": "R1", "scope_check": {"scope_ref": "SCOPE",
            "status": "UNDETERMINED", "evidence_refs": [], "metadata_fields": []},
            "condition_checks": [], "review_condition_checks": [],
            "verdict": "UNDETERMINED", "requirement_checks": [],
            "reason": "추가 입력 필요", "confidence": "LOW"}]}

    def test_empty_or_missing_result_rejected(self):
        self.assertEqual(self.schema["required"], ["results"])
        array = self.schema["properties"]["results"]
        self.assertEqual((array["minItems"], array["maxItems"]), (1, 1))
        self.assertEqual(set(self.result_schema["required"]), set(self.sample()["results"][0]))
        self.assertFalse(self.result_schema["additionalProperties"])

    def test_unknown_gate_can_abstain_without_obligations(self):
        props = self.result_schema["properties"]
        self.assertIn("UNDETERMINED", props["scope_check"]["properties"]["status"]["enum"])
        self.assertEqual(props["requirement_checks"].get("minItems", 0), 0)

    def test_all_verdicts_remain_possible(self):
        for verdict, status, basis in (("COMPLIANT", "SATISFIED", "OBSERVED"),
                ("VIOLATION", "MISSING", "ABSENCE"), ("UNDETERMINED", "UNDETERMINED", "UNKNOWN")):
            props = self.result_schema["properties"]
            checks = props["requirement_checks"]["items"]["properties"]
            self.assertIn(verdict, props["verdict"]["enum"])
            self.assertIn(status, checks["status"]["enum"])
            self.assertIn(basis, checks["finding_basis"]["enum"])
            self.assertEqual(checks["obligation_ref"]["enum"], ["O1"])

    def test_unknown_alias_and_invented_condition_rejected(self):
        props = self.result_schema["properties"]
        self.assertEqual(props["scope_check"]["properties"]["evidence_refs"]["items"]["enum"], ["E1", "L1"])
        self.assertEqual(props["condition_checks"]["maxItems"], 0)
        self.assertEqual(props["review_condition_checks"]["maxItems"], 0)

    def test_format_switch_invalidates_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "input.jsonl"
            p.write_text(json.dumps(self.row), encoding="utf-8")
            checkpoint = Path(directory) / "checkpoint.json"
            checkpoint.write_text(json.dumps(gemma.checkpoint_payload(input_path=p,
                host=None, model="test", rows_by_id={})), encoding="utf-8")
            with patch.dict(os.environ, {"NH_JUDGE_RESPONSE_FORMAT": "json_object"}):
                self.assertEqual(response_format(self.compact), {"type": "json_object"})
                with self.assertRaisesRegex(RuntimeError, "response_format"):
                    gemma.load_checkpoint(checkpoint, input_path=p, host=None, model="test")

    def test_unknown_mode_rejected_not_silently_downgraded(self):
        with patch.dict(os.environ, {"NH_JUDGE_RESPONSE_FORMAT": "typo"}):
            with self.assertRaises(ValueError):
                response_format(self.compact)

    def test_nonempty_gate_contract_and_legacy_shape(self):
        p = copy.deepcopy(self.compact)
        p["rules"][0]["output_check_refs"]["condition_checks"] = ["A1"]
        p["rules"][0]["output_check_refs"].pop("requirement_checks")
        props = response_format(p)["json_schema"]["schema"]["properties"]["results"]["items"]["properties"]
        self.assertEqual(props["condition_checks"]["items"]["properties"]["condition_ref"]["enum"], ["A1"])
        self.assertNotIn("obligation_ref", props["requirement_checks"]["items"]["required"])
