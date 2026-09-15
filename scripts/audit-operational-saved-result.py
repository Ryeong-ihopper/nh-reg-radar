"""Audit one frozen operational run without changing predictions or invoking models."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "rag-pipeline"), str(ROOT / "rag-pipeline/tools")]
from operational_locations import saved_workspace  # noqa: E402
from rag.judgment.runtime_metrics import judgment_call_metrics  # noqa: E402
from rag.api.service import write_json_atomic  # noqa: E402


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--integrated", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.run_dir
    raw = read(root / "04_operational_results.json")
    responses = read(root / "03_judgment_responses.json")
    discovery = read(root / "01_discovery.json")
    requests = [json.loads(json.loads(line)["messages"][1]["content"])
                for line in (root / "02_judgment_requests.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    document = read(args.integrated)
    expected = {(request["ad_id"], rule["item_id"]) for request in requests for rule in request["rules"]}
    actual = [(ad.get("scope_id") or ad["ad_id"], row["item_id"])
              for ad in raw["ads"] for key in ("candidates", "review_candidates", "excluded_candidates")
              for row in ad.get(key, []) if row.get("status") == "predicted"]
    failures = {(row.get("scope_id") or row["ad_id"], row["item_id"]) for row in raw.get("output_failure_pairs", [])}
    assert len(actual) == len(set(actual)), "duplicate final predictions"
    assert set(actual) | failures == expected, "missing/unexpected final pairs"
    assert not set(actual) & failures, "same pair marked predicted and failed"
    errors = []
    scopes = {}
    for request in requests:
        docs = {doc["evidence_id"]: doc for doc in request["documents"]}
        for item_id, scope in request["evidence_scope"].items():
            ids = set(scope["evidence_ids"])
            refs = {ref for eid in ids for ref in docs[eid].get("line_refs", [])}
            scopes[(request["ad_id"], item_id)] = (ids, refs)
    for ad in raw["ads"]:
        for name in ("candidates", "review_candidates", "excluded_candidates"):
            for candidate in ad.get(name, []):
                if candidate.get("status") != "predicted":
                    continue
                ids, refs = scopes[(ad.get("scope_id") or ad["ad_id"], candidate["item_id"])]
                judgment = candidate["judgment"]
                for part in [judgment, *judgment.get("requirement_checks", [])]:
                    if set(part.get("evidence_ids", [])) - ids or set(part.get("evidence_line_refs", [])) - refs:
                        errors.append(candidate["item_id"])
    assert not errors, f"evidence outside frozen rule scope: {errors}"
    call_metrics = judgment_call_metrics(responses["rows"])
    reports = []
    for ad_id in sorted({ad["ad_id"] for ad in raw["ads"]}):
        value = saved_workspace(raw, requests, document, ad_id, discovery)
        reports.append({"advertisement_id": ad_id, "display_verdicts": dict(Counter(row["verdict"] for row in value["rows"])),
                        "display_rows": len(value["rows"]),
                        "rows_with_geometry": sum(bool(row["evidence_locations"]) for row in value["rows"]),
                        "approximate_region_rows": sum(any(box["precision"] == "REGION" for box in row["evidence_locations"]) for row in value["rows"]),
                        "deferred_by_reason": dict(Counter(row["deferred_kind"] for row in value["deferred_rules"]))})
    write_json_atomic(args.output, {"status": "CONTRACT_AND_PROJECTION_PASS", "evaluation_split": "DEV_REGRESSION",
        "not_a_semantic_accuracy_score": True, "expected_pairs": len(expected), "predicted_pairs": len(actual),
        "output_failure_pairs": len(failures), "out_of_scope_citations": 0,
        "calls_including_failed_parents": call_metrics,
        "runtime": read(root / "08_runtime_metrics.json"), "advertisements": reports,
        "artifacts_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in root.glob("*.json*") if path.is_file()}})
    print(json.dumps({"audit": str(args.output), "pairs": len(actual), "failures": len(failures), "physical_calls": call_metrics["physical_calls"]}))


if __name__ == "__main__":
    main()
