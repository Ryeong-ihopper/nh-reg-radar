"""Offline evaluation of frozen discovery and rule-scoped evidence, never runtime input."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ARTIFACTS = ("01_discovery.json", "02_judgment_requests.jsonl")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_search(directory: Path) -> dict:
    """Seal predictions without accepting or reading any evaluation references."""
    manifest = {"version": 1, "files": {name: digest(directory / name) for name in ARTIFACTS}}
    with (directory / "RETRIEVAL_FREEZE.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
    return manifest


def evaluate_search(directory: Path, references_path: Path) -> dict:
    """Read references only after verifying both frozen prediction artifacts."""
    manifest = json.loads((directory / "RETRIEVAL_FREEZE.json").read_text(encoding="utf-8"))
    if set(manifest["files"]) != set(ARTIFACTS):
        raise ValueError("Incomplete retrieval freeze")
    for name in ARTIFACTS:
        if digest(directory / name) != manifest["files"][name]:
            raise ValueError("Frozen search artifact changed: " + name)
    discovery = json.loads((directory / ARTIFACTS[0]).read_text(encoding="utf-8"))
    requests = [json.loads(line) for line in (directory / ARTIFACTS[1]).read_text(
        encoding="utf-8").splitlines() if line.strip()]
    reference = json.loads(references_path.read_text(encoding="utf-8"))
    ads = {ad["ad_id"]: ad for ad in discovery["ads"]}
    scoped = {}
    for request in requests:
        body = json.loads(request["messages"][1]["content"])
        for rule in body["rules"]:
            item = rule["item_id"]
            key = (body["ad_id"], item)
            if key in scoped:
                raise ValueError("Duplicate advertisement/rule prediction")
            allowed = set(body["evidence_scope"][item]["evidence_ids"])
            scoped[key] = [doc for doc in body["documents"] if doc["evidence_id"] in allowed]
    results = []
    seen = set()
    for target in reference["targets"]:
        key = (target["ad_id"], target["item_id"])
        if key in seen:
            raise ValueError("Duplicate evaluation target")
        seen.add(key)
        ad = ads[key[0]]
        item = key[1]
        budget = ad.get("candidate_budget", {})
        supplemental = set(budget.get("selected_ids", [])) | set(budget.get("deferred_ids", []))
        supplemental.update(row["item_id"] for row in ad.get("supplemental_v2_candidates", []))
        mapped = {row["item_id"] for row in ad.get("presence_and_style", [])}
        template = {row["item_id"] for row in ad.get("template_candidates", [])}
        method = ("SUPPLEMENTAL_SEARCH" if item in supplemental else
                  "TEMPLATE_ENUMERATION" if item in template else
                  "MAPPED_ENUMERATION" if item in mapped else "NOT_DISCOVERED")
        state = ("REQUESTED" if key in scoped else
                 "AUDIT_ONLY" if (budget.get("method") == "discovery_audit_only_v1"
                                  and item in budget.get("deferred_ids", [])) else
                 "BUDGET_DEFERRED" if item in budget.get("deferred_ids", []) else
                 "INPUT_DEFERRED" if any(row["item_id"] == item for row in ad.get("deferred_input_rules", [])) else
                 "NOT_REQUESTED")
        documents = scoped.get(key, [])
        groups = []
        for group in target.get("evidence_groups", []):
            # Each group is conjunctive; a batched prompt's other rule evidence
            # is never counted as a hit for this rule.
            exact, text_only, uncertain = [], [], []
            for expected in group["lines"]:
                matching = [doc for doc in documents
                            if doc.get("line_texts", {}).get(expected["line_ref"]) == expected["text"]]
                if matching:
                    exact.append(expected["line_ref"])
                    if all(doc.get("text_selection", {}).get("needs_review") is not False for doc in matching):
                        uncertain.append(expected["line_ref"])
                elif any(expected["text"] in doc.get("text", "") for doc in documents):
                    text_only.append(expected["line_ref"])
            total = len(group["lines"])
            groups.append({"name": group["name"], "expected_lines": total,
                           "exact_lines": exact, "text_only_lines": text_only,
                           "uncertain_lines": uncertain,
                           "text_complete": bool(total) and len(exact) + len(text_only) == total,
                           "exact_complete": bool(total) and len(exact) == total,
                           "verified_complete": bool(total) and len(exact) == total and not uncertain})
        results.append({"ad_id": key[0], "item_id": item, "discovery_method": method,
                        "request_state": state, "evidence_groups": groups})
    return {"version": 1, "purpose": reference["purpose"],
            "prediction_files": manifest["files"], "reference_sha256": digest(references_path),
            "targets": results, "not_claimed": "judgment accuracy, exhaustive recall, or holdout accuracy"}
