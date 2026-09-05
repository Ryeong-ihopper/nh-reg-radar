# -*- coding: utf-8 -*-
"""Run advertisement -> rule discovery -> Gemma judgment as one auditable job.

The runner never reads gold, researcher feedback or case-specific mappings.
Unverified routing values may rank candidates but cannot remove either PoC
product family or a template T rule.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

import build_silver_requests as judgment_input  # noqa: E402
import hybrid_rule_retrieval as discovery  # noqa: E402
from model_result_io import load_results  # noqa: E402
from rag import build_items as v2_source  # noqa: E402
from rag.operational.contracts import (  # noqa: E402
    DISCOVERY_VERSION,
    FREEZE_VERSION,
    OPERATIONAL_RESULT_VERSION,
    validate_integrated_input,
    validate_operational_result,
    validate_search_collections,
)
from rag.operational.policy import (  # noqa: E402
    confirmed_template,
    deterministic_facts,
    enforce_review_policy,
    require_confirmed_product_group,
)
from regulation_v2_catalog import load_template_candidate_rules  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def ad_identity(ad: dict[str, Any]) -> str:
    return str(ad.get("ad_id") or (ad.get("document") or {}).get("ad_id") or "").strip()


def load_ads(directory: Path) -> dict[str, dict[str, Any]]:
    ads: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")):
        ad = json.loads(path.read_text(encoding="utf-8"))
        validate_integrated_input(ad)
        ad_id = ad_identity(ad)
        if not ad_id:
            raise ValueError(f"ad_id가 없는 입력: {path}")
        if ad_id in ads:
            raise ValueError(f"중복 ad_id: {ad_id}")
        ads[ad_id] = ad
    if not ads:
        raise ValueError(f"광고 JSON이 없음: {directory}")
    return ads


def parser_coverage(ad: dict[str, Any]) -> str:
    quality = ad.get("quality") or {}
    partial = bool(
        quality.get("unread_regions")
        or quality.get("empty_region_count")
        or ad.get("unverified_recovery_candidates")
        or (ad.get("diagnostics") or {}).get("empty_regions")
    )
    return "PARTIAL" if partial else "READY"


def routing_context(ad: dict[str, Any], product_route: dict[str, Any]) -> dict[str, Any]:
    """Preserve routing provenance without turning inferred values into hard gates."""
    context: dict[str, Any] = {"product_group": product_route}
    if isinstance(ad.get("routing"), dict):
        values = ad["routing"]
        quality = ad.get("routing_quality") or {}
        for field in ("template_id", "product_subtype", "ad_type", "product_name_shown", "media_type"):
            detail = quality.get(field) if isinstance(quality.get(field), dict) else {}
            value = values.get(field)
            context[field] = {
                "value": value,
                "source": detail.get("source"),
                "status": detail.get("status") or ("unknown" if value in (None, "") else "inferred"),
            }
        return context

    metadata = ((ad.get("document") or {}).get("routing_metadata") or {})
    classification_source = metadata.get("classification_source")
    for field in ("template_id", "product_subtype", "ad_type", "product_name_shown", "media_type"):
        raw = metadata.get(field)
        if isinstance(raw, dict):
            context[field] = {
                "value": raw.get("value"),
                "source": raw.get("source"),
                "status": raw.get("status") or "unknown",
            }
        else:
            context[field] = {
                "value": raw,
                "source": classification_source,
                "status": "unknown" if raw in (None, "") else "inferred",
            }
    return context


def select_ads(
    ads: dict[str, dict[str, Any]],
    coarse: list[dict[str, Any]],
    fine: list[dict[str, Any]],
    selected_ids: list[str],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if not selected_ids:
        return ads, coarse, fine
    requested = set(selected_ids)
    missing = sorted(requested - set(ads))
    if missing:
        raise ValueError(f"--ad-id not found in inputs: {missing}")
    return (
        {ad_id: ads[ad_id] for ad_id in sorted(requested)},
        [row for row in coarse if str(row.get("ad_id")) in requested],
        [row for row in fine if str(row.get("ad_id")) in requested],
    )


def evidence_documents(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in sorted(rows, key=lambda value: value["doc_id"]):
        output.append({
            "evidence_id": row["doc_id"],
            "page_no": row.get("page_no"),
            "region_id": row.get("region_id"),
            "labels": row.get("labels") or [],
            "line_refs": row.get("line_refs") or [],
            "text": row.get("text_canonical") or row.get("text_search") or "",
        })
    return output


def template_rule_doc(rule: dict[str, Any]) -> dict[str, Any]:
    parts = [
        rule.get("title"),
        rule.get("question"),
        rule.get("criterion"),
        rule.get("example_text"),
        rule.get("guide"),
    ]
    return {
        "doc_id": rule["item_id"],
        "item_id": rule["item_id"],
        "category": rule["category"],
        "category_label": rule["category_label"],
        "product_groups": rule["product_groups"],
        "product_subtype": rule.get("product_subtype"),
        "title": rule["title"],
        "question": rule["question"],
        "criterion": rule["criterion"],
        "search_text": " ".join(str(value).strip() for value in parts if str(value or "").strip()),
        "search_text_variant": "v2-template",
    }


def top_rule_evidence(
    item_id: str,
    *,
    rule_vector_by_id: dict[str, np.ndarray],
    ad_fine_rows: list[dict[str, Any]],
    fine_vector_by_id: dict[str, np.ndarray],
    trigger_ids: list[str],
    k: int,
) -> list[str]:
    """Select a small auditable evidence window for one rule."""
    vector = rule_vector_by_id[item_id]
    scored = sorted(
        (
            (
                float(np.dot(vector, fine_vector_by_id[row["doc_id"]])),
                str(row["doc_id"]),
            )
            for row in ad_fine_rows
        ),
        reverse=True,
    )
    ranked = [doc_id for _, doc_id in scored[:k]]
    return list(dict.fromkeys([*trigger_ids, *ranked]))


def t_rule_applies(rule: dict[str, Any], product_groups: list[str]) -> bool:
    allowed = set(rule.get("product_groups") or [])
    return "전체" in allowed or bool(allowed.intersection(product_groups))


def automated_input_ready(rule: dict[str, Any]) -> bool:
    """Whether the current integrated advertisement is sufficient for automation."""
    required_medium = str(rule.get("required_medium") or "").strip()
    input_requirement = str(rule.get("input_requirement") or "").strip()
    return (
        required_medium != "레이아웃"
        and "랜딩캡처" not in input_requirement
        and "원본형식" not in input_requirement
    )


def freeze_manifest(
    args: argparse.Namespace,
    *,
    request_path: Path,
    discovery_path: Path,
    ad_count: int,
) -> dict[str, Any]:
    code_paths = [
        Path(__file__),
        ROOT / "rag/operational/contracts.py",
        ROOT / "tools/hybrid_rule_retrieval.py",
        ROOT / "tools/build_ad_evidence_vectors.py",
        ROOT / "tools/run_gemma_exhaustive_dgx.py",
        ROOT / "tools/dgx_bge_client.py",
        ROOT / "tools/dgx_openai_client.py",
        ROOT / "tools/build_silver_requests.py",
        ROOT / "tools/regulation_v2_catalog.py",
        ROOT / "tools/model_result_io.py",
        ROOT / "rag/build_items.py",
    ]
    input_paths = [args.regulation, args.coarse, args.fine, request_path, discovery_path]
    return {
        "schema_version": FREEZE_VERSION,
        "frozen_before_prediction": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "ads": ad_count,
        "configuration": {
            "rule_search_text_variant": args.rule_search_text_variant,
            "per_chunk_k": args.per_chunk_k,
            "rrf_k": args.rrf_k,
            "batch_size": args.batch_size,
            "elasticsearch_url": args.es_url,
            "elasticsearch_index": args.es_index,
            "model": args.model,
            "temperature": 0,
        },
        "inputs": [
            {"path": str(path.resolve()), "sha256": sha256(path)} for path in input_paths
        ],
        "code": [
            {"path": str(path.resolve()), "sha256": sha256(path)} for path in code_paths
        ],
        "data_leakage_policy": (
            "prediction receives regulation-v2 plus advertisement evidence only; "
            "no gold, researcher O/X, ad-specific rule mapping or case answer"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs-dir", type=Path, required=True)
    parser.add_argument("--coarse", type=Path, required=True)
    parser.add_argument("--fine", type=Path, required=True)
    parser.add_argument("--regulation", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--es-url",
        default=os.environ.get("NH_RAG_ES_URL", "http://127.0.0.1:19201"),
    )
    parser.add_argument("--es-index", default=os.environ.get("NH_RAG_ES_INDEX"))
    parser.add_argument("--rule-search-text-variant", choices=("core", "expanded"), default="core")
    parser.add_argument("--per-chunk-k", type=int, default=5)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--evidence-per-rule", type=int, default=3)
    parser.add_argument("--prohibition-max-candidates", type=int, default=30)
    parser.add_argument(
        "--allow-provisional-routing",
        action="store_true",
        help="Debug only: fail open to both product groups when product_group is not confirmed.",
    )
    parser.add_argument("--execute-judgment", action="store_true")
    parser.add_argument("--host", default=os.environ.get("DGX_HOST"))
    parser.add_argument(
        "--key",
        type=Path,
        default=Path(os.environ["DGX_SSH_KEY"]) if os.environ.get("DGX_SSH_KEY") else None,
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("DGX_GEMMA_MODEL", "gemma-4-26b-NVFP4-MTP"),
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--ad-id",
        action="append",
        default=[],
        help="Process only this ad_id; repeat for multiple ads.",
    )
    args = parser.parse_args()
    if not args.es_index:
        parser.error("--es-index or NH_RAG_ES_INDEX is required")

    v2_source.set_agent_path(args.regulation)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    ads = load_ads(args.inputs_dir)
    coarse = read_jsonl(args.coarse)
    fine = sorted(read_jsonl(args.fine), key=lambda row: row["doc_id"])
    validate_search_collections(ads.values(), coarse, fine)
    ads, coarse, fine = select_ads(ads, coarse, fine, args.ad_id)
    coarse_by_ad: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    fine_by_ad: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in coarse:
        coarse_by_ad[str(row["ad_id"])].append(row)
    for row in fine:
        fine_by_ad[str(row["ad_id"])].append(row)
    if set(ads) != set(coarse_by_ad) or set(ads) != set(fine_by_ad):
        raise RuntimeError(
            "광고 입력/coarse/fine ad_id 집합 불일치: "
            f"input_only={sorted(set(ads)-set(coarse_by_ad))}, "
            f"coarse_only={sorted(set(coarse_by_ad)-set(ads))}, "
            f"fine_only={sorted(set(fine_by_ad)-set(ads))}"
        )

    items, _ = discovery.load_scope()
    cd_rules = judgment_input.load_cd_rules()
    t_rules = load_template_candidate_rules()
    rule_by_id = {row["item_id"]: row for row in [*cd_rules, *t_rules]}
    cd_rule_docs = discovery.rule_docs(
        items, search_text_variant=args.rule_search_text_variant
    )
    rule_docs = [
        *cd_rule_docs,
        *(template_rule_doc(rule) for rule in t_rules),
    ]
    model = discovery.load_model()
    rule_vectors, _, _ = discovery.load_or_encode(
        rule_docs,
        text_key="search_text",
        source=args.regulation,
        vectors_path=args.output_dir / "rule_vectors.f16.npy",
        meta_path=args.output_dir / "rule_vectors.meta.json",
        model=model,
        batch_size=4,
        force=False,
    )
    fine_vectors, _, _ = discovery.load_or_encode(
        fine,
        text_key="text_search",
        source=args.fine,
        vectors_path=args.output_dir / "fine_vectors.f16.npy",
        meta_path=args.output_dir / "fine_vectors.meta.json",
        model=model,
        batch_size=4,
        force=False,
    )
    discovery.ensure_rule_index(
        args.es_url,
        args.es_index,
        cd_rule_docs,
        rule_vectors[: len(cd_rule_docs)],
        source_sha=sha256(args.regulation),
    )
    fine_vector_by_id = {row["doc_id"]: vector for row, vector in zip(fine, fine_vectors)}
    rule_vector_by_id = {row["item_id"]: vector for row, vector in zip(rule_docs, rule_vectors)}

    discovery_ads = []
    requests = []
    requested_pairs: set[tuple[str, str]] = set()
    for ad_id in sorted(ads):
        route = discovery.routing_scope(coarse_by_ad[ad_id])
        route_context = routing_context(ads[ad_id], route)
        if args.allow_provisional_routing:
            candidate_groups = route["candidate_product_groups"]
        else:
            candidate_groups = [require_confirmed_product_group(route_context)]
            route = {
                **route,
                "candidate_product_groups": candidate_groups,
                "routing_provisional": False,
                "hard_route": True,
                "status": "routing_confirmed",
            }
            route_context["product_group"] = route
        product_items = [
            item for item in items if discovery.applicable_to_any(item, candidate_groups)
        ]
        deferred_input_rules = [
            {
                "item_id": item["id"],
                "required_medium": item["필요매체"],
                "input_requirement": item["입력요건"],
                "reason": "current integrated advertisement lacks required external/layout input",
            }
            for item in product_items
            if not automated_input_ready(rule_by_id[item["id"]])
        ]
        enumerated = [
            {
                "item_id": item["id"],
                "category": item["category"],
                "title": item["title"],
                "discovery_method": "confirmed_product_enumeration",
            }
            for item in product_items
            if item["category"] != "PROHIBIT"
            and automated_input_ready(rule_by_id[item["id"]])
        ]
        template_value = confirmed_template(route_context)
        template_candidates = [
            {
                "item_id": rule["item_id"],
                "category": rule["category"],
                "title": rule["title"],
                "discovery_method": "confirmed_template_enumeration",
            }
            for rule in t_rules
            if template_value
            and t_rule_applies(rule, candidate_groups)
            and rule.get("product_subtype") == template_value
        ]
        deferred_template_rules = [
            rule["item_id"]
            for rule in t_rules
            if t_rule_applies(rule, candidate_groups)
            and rule.get("product_subtype") != template_value
        ]
        prohibitions = discovery.discover_prohibitions(
            fine_by_ad[ad_id],
            fine_vector_by_id,
            candidate_groups,
            base_url=args.es_url,
            index=args.es_index,
            per_chunk_k=args.per_chunk_k,
            rrf_k=args.rrf_k,
            deterministic_item_ids=set(),
        )
        prohibitions = [
            row
            for row in prohibitions
            if automated_input_ready(rule_by_id[row["item_id"]])
        ][: args.prohibition_max_candidates]
        candidate_rows = [*enumerated, *template_candidates, *prohibitions]
        candidate_ids = list(dict.fromkeys(row["item_id"] for row in candidate_rows))
        missing_rule_defs = set(candidate_ids) - set(rule_by_id)
        if missing_rule_defs:
            raise RuntimeError(f"판정 정의가 없는 후보: {sorted(missing_rule_defs)}")
        fine_doc_by_id = {
            row["doc_id"]: evidence_documents([row])[0]
            for row in fine_by_ad[ad_id]
        }
        trigger_by_item = {
            row["item_id"]: [
                str((event.get("trigger") or {}).get("doc_id"))
                for event in row.get("trigger_evidence") or []
                if (event.get("trigger") or {}).get("doc_id") in fine_doc_by_id
            ]
            for row in prohibitions
        }
        evidence_by_item = {
            item_id: top_rule_evidence(
                item_id,
                rule_vector_by_id=rule_vector_by_id,
                ad_fine_rows=fine_by_ad[ad_id],
                fine_vector_by_id=fine_vector_by_id,
                trigger_ids=trigger_by_item.get(item_id, []),
                k=args.evidence_per_rule,
            )
            for item_id in candidate_ids
        }
        facts = deterministic_facts(fine_by_ad[ad_id])
        category_to_rules: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
        for item_id in candidate_ids:
            category_to_rules[rule_by_id[item_id]["category"]].append(rule_by_id[item_id])
        for category in ("PRESENCE", "PROHIBIT", "STYLE"):
            category_rules = sorted(category_to_rules[category], key=lambda row: row["item_id"])
            for offset in range(0, len(category_rules), args.batch_size):
                batch = category_rules[offset:offset + args.batch_size]
                request_id = f"operational:{ad_id}:{category}:{offset // args.batch_size + 1}"
                batch_evidence_ids = list(dict.fromkeys(
                    evidence_id
                    for rule in batch
                    for evidence_id in evidence_by_item[rule["item_id"]]
                ))
                docs = [fine_doc_by_id[evidence_id] for evidence_id in batch_evidence_ids]
                payload = {
                    "request_id": request_id,
                    "ad_id": ad_id,
                    "routing": route_context,
                    "parser_coverage": parser_coverage(ads[ad_id]),
                    "documents": docs,
                    "evidence_scope": {
                        rule["item_id"]: {
                            "evidence_ids": evidence_by_item[rule["item_id"]],
                            "complete_ad_scan": len(evidence_by_item[rule["item_id"]]) == len(fine_by_ad[ad_id]),
                        }
                        for rule in batch
                    },
                    "deterministic_facts": facts,
                    "rules": batch,
                }
                requests.append({
                    "request_id": request_id,
                    "ad_id": ad_id,
                    "category": category,
                    "requested_item_ids": [row["item_id"] for row in batch],
                    "messages": [
                        {"role": "system", "content": judgment_input.SYSTEM},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                })
                requested_pairs.update((ad_id, row["item_id"]) for row in batch)
        discovery_ads.append({
            "ad_id": ad_id,
            "routing": route_context,
            "parser_coverage": parser_coverage(ads[ad_id]),
            "counts": {
                "coarse": len(coarse_by_ad[ad_id]),
                "fine": len(fine_by_ad[ad_id]),
                "presence_and_style": len(enumerated),
                "template_candidates": len(template_candidates),
                "deferred_template_rules": len(deferred_template_rules),
                "deferred_input_rules": len(deferred_input_rules),
                "prohibition_candidates": len(prohibitions),
                "judgment_candidates": len(candidate_ids),
            },
            "presence_and_style": enumerated,
            "template_candidates": template_candidates,
            "deferred_template_rule_ids": deferred_template_rules,
            "deferred_input_rules": deferred_input_rules,
            "prohibition_candidates": prohibitions,
        })

    discovery_path = args.output_dir / "01_discovery.json"
    request_path = args.output_dir / "02_judgment_requests.jsonl"
    response_path = args.output_dir / "03_judgment_responses.json"
    final_path = args.output_dir / "04_operational_results.json"
    write_json(discovery_path, {
        "schema_version": DISCOVERY_VERSION,
        "gold_visible": False,
        "policy": {
            "unverified_routing": (
                "reject before model execution unless --allow-provisional-routing is explicitly set"
            ),
            "template": "judge only the exact independently confirmed template; otherwise defer",
            "presence_style": "enumerate automatable rules in the confirmed product group",
            "prohibition": "every fine ad chunk -> rule BM25+BGE-M3 -> RRF",
            "prohibition_recall_guard": "ranked candidates are capped and the cap is recorded",
            "evidence": "rule-to-ad BGE-M3 top-k plus prohibition trigger evidence",
            "absence": "a narrowed evidence window cannot prove absence; model must abstain",
            "required_inputs": (
                "rules requiring landing capture, layout, or original format are deferred "
                "instead of being sent to the text judgment model"
            ),
            "labels": "trace/ranking only, never exclusion",
        },
        "ads": discovery_ads,
    })
    request_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in requests),
        encoding="utf-8",
    )
    freeze_path = args.output_dir / "FREEZE_BEFORE_PREDICTION.json"
    write_json(freeze_path, freeze_manifest(
        args,
        request_path=request_path,
        discovery_path=discovery_path,
        ad_count=len(ads),
    ))

    if not args.execute_judgment:
        print(json.dumps({
            "status": "frozen_requests_ready",
            "ads": len(ads),
            "requests": len(requests),
            "pairs": len(requested_pairs),
            "freeze": str(freeze_path),
        }, ensure_ascii=False, indent=2))
        return

    command = [
        sys.executable,
        str(ROOT / "tools/run_gemma_exhaustive_dgx.py"),
        "--input", str(request_path),
        "--output", str(response_path),
        "--model", args.model,
        "--workers", str(args.workers),
    ]
    if args.host:
        command.extend(["--host", args.host])
    if args.key:
        command.extend(["--key", str(args.key)])
    subprocess.run(command, cwd=ROOT, check=True)
    model_results, result_sources = load_results([response_path])
    missing_pairs = sorted(requested_pairs - set(model_results))
    extra_pairs = sorted(set(model_results) - requested_pairs)
    if extra_pairs:
        raise RuntimeError(f"요청 밖 모델 결과가 있음: {extra_pairs[:10]}")
    final_ads = []
    discovery_by_ad = {row["ad_id"]: row for row in discovery_ads}
    for ad_id in sorted(ads):
        candidates = []
        for pair in sorted((pair for pair in requested_pairs if pair[0] == ad_id), key=lambda pair: pair[1]):
            result = model_results.get(pair)
            if result:
                result = enforce_review_policy(result)
            candidates.append({
                "item_id": pair[1],
                "status": "predicted" if result else "OUTPUT_FAILURE",
                "judgment": result,
                "source": result_sources.get(pair),
            })
        final_ads.append({
            "ad_id": ad_id,
            "routing": discovery_by_ad[ad_id]["routing"],
            "parser_coverage": discovery_by_ad[ad_id]["parser_coverage"],
            "deferred_rules": [
                *discovery_by_ad[ad_id]["deferred_input_rules"],
                *(
                    {
                        "item_id": item_id,
                        "reason": "template confirmation did not select this v2 section",
                    }
                    for item_id in discovery_by_ad[ad_id]["deferred_template_rule_ids"]
                ),
            ],
            "candidates": candidates,
        })
    final_result = {
        "schema_version": OPERATIONAL_RESULT_VERSION,
        "status": "silver_researcher_review_required",
        "freeze": str(freeze_path),
        "counts": {
            "ads": len(ads),
            "requested_pairs": len(requested_pairs),
            "predicted_pairs": len(model_results),
            "output_failures": len(missing_pairs),
        },
        "output_failure_pairs": [
            {"ad_id": ad_id, "item_id": item_id} for ad_id, item_id in missing_pairs
        ],
        "ads": final_ads,
    }
    validate_operational_result(final_result)
    write_json(final_path, final_result)
    print(json.dumps({
        "status": "completed",
        "output": str(final_path),
        "ads": len(ads),
        "predicted_pairs": len(model_results),
        "output_failures": len(missing_pairs),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
