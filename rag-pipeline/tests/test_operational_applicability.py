import json
import sys
from pathlib import Path

import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rag.judgment.applicability import screen_rules, split_operational_candidates, validate_screen


def test_negative_requires_real_evidence():
    row = dict(item_id="sample", applicability="NOT_APPLICABLE", input_mode="TEXT", reason="not a joint ad", evidence_ids=[])
    with unittest.TestCase().assertRaisesRegex(ValueError, "without evidence"):
        validate_screen({"results": [row]}, [{"item_id": "sample"}], [{"evidence_id": "page1"}])
    row["evidence_ids"] = ["invented"]
    with unittest.TestCase().assertRaisesRegex(ValueError, "unknown"):
        validate_screen({"results": [row]}, [{"item_id": "sample"}], [{"evidence_id": "page1"}])


def test_incomplete_ad_cannot_establish_negative():
    def post(_):
        row = dict(item_id="sample", applicability="NOT_APPLICABLE", input_mode="TEXT", reason="no endorsement", evidence_ids=["page1"])
        return {"choices": [{"message": {"content": json.dumps({"results": [row]})}}]}
    rows, _ = screen_rules(rules=[{"item_id": "sample"}], documents=[{"evidence_id": "page1"}],
                          routing={}, complete_ad_scan=False, model="fake", post=post)
    assert rows["sample"]["applicability"] == "UNDETERMINED"


def test_failed_screen_never_removes_rules():
    rows, traces = screen_rules(rules=[{"item_id": "one"}, {"item_id": "two"}],
        documents=[], routing={}, complete_ad_scan=True, model="fake", post=lambda _: {})
    assert set(rows) == {"one", "two"}
    assert all(r["applicability"] == "UNDETERMINED" for r in rows.values())
    assert len(traces) == 5


def test_only_malformed_rows_are_retried():
    calls = []
    def post(request):
        payload = json.loads(request["messages"][1]["content"])
        ids = [r["item_id"] for r in payload["rules"]]
        calls.append(ids)
        rows = [dict(item_id=i, applicability="APPLICABLE", input_mode="TEXT",
                     reason="medium matches", evidence_ids=["page1"]) for i in ids]
        if len(calls) == 1:
            rows[1]["applicability"] = "PARTIAL"  # Invalid enum must not affect valid neighbor.
        return {"choices": [{"message": {"content": json.dumps({"results": rows})}}]}
    rows, _ = screen_rules(rules=[{"item_id": "one"}, {"item_id": "two"}],
        documents=[{"evidence_id": "page1"}], routing={}, complete_ad_scan=True, model="fake", post=post)
    assert calls == [["one", "two"], ["two"]]
    assert all(r["applicability"] == "APPLICABLE" for r in rows.values())


def test_operational_results_exclude_negatives_but_keep_unknown_and_failure():
    candidates = [
        {"item_id": "negative", "judgment": {"applicability": "NOT_APPLICABLE", "verdict": "NOT_APPLICABLE"}},
        {"item_id": "uncertain", "judgment": {"applicability": "UNDETERMINED", "verdict": "UNDETERMINED"}},
        {"item_id": "failure", "judgment": None},
        {"item_id": "positive", "judgment": {"applicability": "APPLICABLE", "verdict": "COMPLIANT"}},
    ]
    visible, excluded = split_operational_candidates(candidates)
    assert [r["item_id"] for r in visible] == ["uncertain", "failure", "positive"]
    assert [r["item_id"] for r in excluded] == ["negative"]
