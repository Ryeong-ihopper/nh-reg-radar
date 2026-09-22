import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from rag.judgment.candidate_activation import (
    CONTENT_TIER,
    VISUAL_TIER,
    activated_retrieval_rows,
    load_candidate_activation_policy,
)


class CandidateActivationTests(unittest.TestCase):
    def fixture(self, root: Path):
        regulation = root / "regulation.xlsx"
        regulation.write_bytes(b"source")
        policy = root / "policy.json"
        policy.write_text(json.dumps({
            "schema_version": "candidate-activation-policy-v1",
            "regulation_sha256": [hashlib.sha256(b"source").hexdigest()],
            "entries": [{
                "item_id": "S-1",
                "execution_tier": CONTENT_TIER,
                "activation": "RETRIEVAL_HIT",
                "source_fragment": "조건이 실제로 표시된 경우",
                "evidence_trigger_any": ["조건"],
            }],
        }, ensure_ascii=False), encoding="utf-8")
        rules = [{"item_id": "S-1", "question": "조건이 실제로 표시된 경우 의무를 확인하는가?"}]
        return regulation, policy, rules

    def test_only_retrieved_policy_rows_are_activated(self):
        with tempfile.TemporaryDirectory() as directory:
            regulation, path, rules = self.fixture(Path(directory))
            policy = load_candidate_activation_policy(
                path, regulation_path=regulation, rules=rules
            )
            rows = activated_retrieval_rows(
                [
                    {"item_id": "S-1", "score": 1, "trigger_evidence": [
                        {"trigger": {"text": "광고에 조건 표시"}}
                    ]},
                    {"item_id": "S-2", "score": 2},
                ],
                policy,
                execution_tier=CONTENT_TIER,
            )
            self.assertEqual([row["item_id"] for row in rows], ["S-1"])
            self.assertEqual(rows[0]["execution_tier"], CONTENT_TIER)

    def test_semantic_hit_without_source_trigger_is_not_promoted(self):
        policy = {"S-1": {
            "execution_tier": CONTENT_TIER,
            "source_fragment": "영업실적을 표기한 경우",
            "evidence_trigger_any": ["영업실적"],
        }}
        rows = [{
            "item_id": "S-1",
            "trigger_evidence": [{"trigger": {"text": "상품의 일반적인 수익 안내"}}],
        }]
        self.assertEqual(
            activated_retrieval_rows(rows, policy, execution_tier=CONTENT_TIER), []
        )

    def test_source_hash_and_fragment_drift_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            regulation, path, rules = self.fixture(Path(directory))
            regulation.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "does not bind"):
                load_candidate_activation_policy(path, regulation_path=regulation, rules=rules)
            regulation.write_bytes(b"source")
            rules[0]["question"] = "different source wording"
            with self.assertRaisesRegex(ValueError, "not present"):
                load_candidate_activation_policy(path, regulation_path=regulation, rules=rules)

    def test_visual_tier_stays_distinct_from_model_tier(self):
        policy = {"V-1": {"execution_tier": VISUAL_TIER, "source_fragment": "배경 대비"}}
        rows = [{"item_id": "V-1"}]
        self.assertEqual(
            activated_retrieval_rows(rows, policy, execution_tier=CONTENT_TIER), []
        )
        self.assertEqual(
            activated_retrieval_rows(rows, policy, execution_tier=VISUAL_TIER)[0]["item_id"],
            "V-1",
        )
