# -*- coding: utf-8 -*-
"""Build small recovery requests and finalize an operational judgment run.

This tool is policy-neutral: it never changes a judgment and never reads gold.
It only retries advertisement-rule pairs that have no contract-valid model
result, then assembles all valid response files into the operational contract.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from model_result_io import load_results  # noqa: E402
from rag.contracts.validation import (  # noqa: E402
    OPERATIONAL_RESULT_VERSION,
    validate_operational_result,
)
from rag.judgment.policy import enforce_review_policy  # noqa: E402
from rag.judgment.applicability import partition_operational_candidates  # noqa: E402
from run_operational_e2e import decision_trace, rule_basis  # noqa: E402


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def expected_pairs(requests: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {
        (str(request["ad_id"]), str(item_id))
        for request in requests
        for item_id in request["requested_item_ids"]
    }


def build_recovery_requests(args: argparse.Namespace) -> None:
    requests = read_jsonl(args.requests)
    valid_results, _ = load_results(args.responses)
    expected = expected_pairs(requests)
    missing = expected - set(valid_results)
    recovery: list[dict[str, Any]] = []
    for request in requests:
        ad_id = str(request["ad_id"])
        payload = json.loads(request["messages"][1]["content"])
        rules = [
            rule
            for rule in payload["rules"]
            if (ad_id, str(rule["item_id"])) in missing
        ]
        for offset in range(0, len(rules), args.batch_size):
            batch = rules[offset : offset + args.batch_size]
            row = copy.deepcopy(request)
            row["request_id"] = (
                f"{request['request_id']}~recovery-{args.round}-"
                f"{offset // args.batch_size + 1}"
            )
            row["requested_item_ids"] = [str(rule["item_id"]) for rule in batch]
            batch_payload = copy.deepcopy(payload)
            batch_payload["request_id"] = row["request_id"]
            batch_payload["rules"] = batch
            scope = payload.get("evidence_scope")
            if isinstance(scope, dict):
                selected_scope = {
                    item_id: copy.deepcopy(scope[item_id])
                    for item_id in row["requested_item_ids"]
                    if item_id in scope
                }
                batch_payload["evidence_scope"] = selected_scope
                if len(selected_scope) == len(batch):
                    allowed_ids = {
                        str(evidence_id)
                        for item_scope in selected_scope.values()
                        for evidence_id in item_scope.get("evidence_ids", [])
                    }
                    batch_payload["documents"] = [
                        document for document in payload.get("documents", [])
                        if str(document.get("evidence_id")) in allowed_ids
                    ]
            row["messages"][1]["content"] = json.dumps(
                batch_payload,
                ensure_ascii=False,
            )
            recovery.append(row)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in recovery),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "recovery_requests_ready",
                "expected_pairs": len(expected),
                "valid_pairs": len(valid_results),
                "missing_pairs": len(missing),
                "recovery_requests": len(recovery),
                "batch_size": args.batch_size,
                "output": str(args.output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def finalize(args: argparse.Namespace) -> None:
    requests = read_jsonl(args.requests)
    template_bases = {}
    rules_by_pair = {}
    condition_contracts = {}
    rule_bases_by_pair = {}
    for request in requests:
        for item_id, basis in (request.get("rule_bases") or {}).items():
            rule_bases_by_pair[(request["ad_id"], item_id)] = basis
        for message in request.get("messages", []):
            if message.get("role") != "user":
                continue
            payload = json.loads(message["content"])
            for rule in payload.get("rules", []):
                rules_by_pair[(request["ad_id"], rule["item_id"])] = rule
                if rule.get("condition_contract"):
                    condition_contracts[(request["ad_id"], rule["item_id"])] = (
                        rule["condition_contract"]
                    )
                if rule.get("template_basis"):
                    template_bases[(request["ad_id"], rule["item_id"])] = rule["template_basis"]
    expected = expected_pairs(requests)
    model_results, result_sources = load_results(args.responses)
    extra = set(model_results) - expected
    if extra:
        raise RuntimeError(f"요청 밖 모델 결과가 있음: {sorted(extra)[:10]}")
    missing = sorted(expected - set(model_results))
    discovery = json.loads(args.discovery.read_text(encoding="utf-8"))
    freeze = json.loads(args.freeze.read_text(encoding="utf-8")) if args.freeze.is_file() else {}
    frozen_inputs = freeze.get("inputs") or []
    regulation_sha = str((frozen_inputs[0] if frozen_inputs else {}).get("sha256") or "")
    template_sha = next((
        str(row.get("sha256")) for row in frozen_inputs
        if str(row.get("path") or "").lower().endswith(".hwpx")
    ), None)
    discovery_by_ad = {str(row["ad_id"]): row for row in discovery["ads"]}
    requested_ads = sorted(discovery_by_ad)
    if {ad_id for ad_id, _ in expected} - set(discovery_by_ad):
        raise RuntimeError("검색 결과와 판정 요청의 광고 집합이 다름")
    final_ads = []
    for ad_id in requested_ads:
        pairs = sorted(
            (pair for pair in expected if pair[0] == ad_id),
            key=lambda pair: pair[1],
        )
        candidates = []
        supplemental_ids = {
            str(row["item_id"])
            for row in discovery_by_ad[ad_id].get("supplemental_v2_candidates", [])
        }
        template_ids = {
            str(row["item_id"])
            for row in discovery_by_ad[ad_id].get("template_candidates", [])
        }
        for pair in pairs:
            result = model_results.get(pair)
            if result:
                result = enforce_review_policy(result)
            candidates.append(
                {
                    "item_id": pair[1],
                    "rule_basis": rule_bases_by_pair.get(pair) or rule_basis(
                        rules_by_pair.get(pair, {"item_id": pair[1]}),
                        regulation_sha256=regulation_sha,
                        template_sha256=template_sha,
                    ),
                    "status": "predicted" if result else "OUTPUT_FAILURE",
                    "judgment": result,
                    "source": result_sources.get(pair),
                    "decision_trace": decision_trace(result, result_sources.get(pair)),
                    "discovery_tier": (
                        "TEMPLATE_PRIMARY" if pair[1] in template_ids else
                        "SUPPLEMENTAL_V2" if pair[1] in supplemental_ids else
                        "MAPPED_V2"
                    ),
                    **({"condition_contract": condition_contracts[pair]}
                       if pair in condition_contracts else {}),
                    **({"template_basis": template_bases[pair]} if pair in template_bases else {}),
                }
            )
        discovered = discovery_by_ad[ad_id]
        visible, review_candidates, excluded = partition_operational_candidates(candidates)
        final_ads.append(
            {
                "ad_id": discovered.get("source_ad_id") or ad_id,
                "scope_id": ad_id,
                "product_id": discovered.get("product_id"),
                "product_name": discovered.get("product_name"),
                "routing": discovered["routing"],
                "parser_coverage": discovered["parser_coverage"],
                "template_coverage": copy.deepcopy(discovered.get("template_coverage")),
                "deferred_rules": [
                    *discovered.get("template_scope_deferred", []),
                    *discovered.get("deferred_input_rules", []),
                    *discovered.get("applicability_pending", []),
                    *(
                        {
                            "item_id": item_id,
                            "reason": "routing did not select this rule's template section",
                        }
                        for item_id in discovered.get("deferred_template_rule_ids", [])
                    ),
                ],
                "candidates": visible,
                "review_candidates": review_candidates,
                "excluded_candidates": excluded,
            }
        )
    output = {
        "schema_version": OPERATIONAL_RESULT_VERSION,
        "status": "silver_researcher_review_required",
        "freeze": str(args.freeze),
        "audit": {
            "model": {
                "requested": (freeze.get("configuration") or {}).get("model"),
                "returned": sorted({
                    str(row.get("model_returned"))
                    for path in args.responses
                    for row in (json.loads(path.read_text(encoding="utf-8")).get("rows") or [])
                    if isinstance(row, dict) and row.get("model_returned")
                }),
                "temperature": (freeze.get("configuration") or {}).get("temperature", 0),
            },
            "search": {
                "engine": "Elasticsearch BM25 + BGE-M3 + RRF + bge-reranker-v2-m3",
                "index": (freeze.get("configuration") or {}).get("elasticsearch_index"),
                "rule_search_text_variant": (freeze.get("configuration") or {}).get("rule_search_text_variant"),
            },
            "rule_sources": {
                "regulation_v2_sha256": regulation_sha,
                "template_hwpx_sha256": template_sha,
            },
            "guardrails": {
                "decision_policy": "Only contract-valid model results are merged; recovery never edits semantic verdicts",
                "recovery_sources": [str(path) for path in args.responses],
            },
        },
        "assembled_at": datetime.now(timezone.utc).isoformat(),
        "response_sources": [str(path) for path in args.responses],
        "counts": {
            "ads": len(final_ads),
            "requested_pairs": len(expected),
            "predicted_pairs": len(model_results),
            "output_failures": len(missing),
        },
        "output_failure_pairs": [
            {
                "ad_id": discovery_by_ad[ad_id].get("source_ad_id") or ad_id,
                "scope_id": ad_id,
                "product_id": discovery_by_ad[ad_id].get("product_id"),
                "item_id": item_id,
            }
            for ad_id, item_id in missing
        ],
        "ads": final_ads,
    }
    validate_operational_result(output)
    write_json(args.output, output)
    print(
        json.dumps(
            {
                "status": "completed" if not missing else "completed_with_output_failures",
                "output": str(args.output),
                **output["counts"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build")
    build.add_argument("--requests", type=Path, required=True)
    build.add_argument("--responses", type=Path, action="append", required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--batch-size", type=int, default=4)
    build.add_argument("--round", type=int, default=1)
    build.set_defaults(handler=build_recovery_requests)

    finish = commands.add_parser("finalize")
    finish.add_argument("--requests", type=Path, required=True)
    finish.add_argument("--discovery", type=Path, required=True)
    finish.add_argument("--freeze", type=Path, required=True)
    finish.add_argument("--responses", type=Path, action="append", required=True)
    finish.add_argument("--output", type=Path, required=True)
    finish.set_defaults(handler=finalize)

    args = parser.parse_args()
    if getattr(args, "batch_size", 1) < 1:
        parser.error("--batch-size must be >= 1")
    args.handler(args)


if __name__ == "__main__":
    main()
