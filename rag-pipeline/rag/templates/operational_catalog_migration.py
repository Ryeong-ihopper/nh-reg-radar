"""Exact, reviewable mapping from canonical source rows to legacy runtime IDs."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any


def audit_catalog_migration(
    plans: list[dict[str, Any]], legacy_catalog: dict[str, Any]
) -> dict[str, Any]:
    legacy_entries = legacy_catalog.get("entries")
    if not isinstance(legacy_entries, list):
        raise ValueError("legacy catalog entries must be a list")
    by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for entry in legacy_entries:
        by_key[_legacy_key(entry)].append(entry)

    rows = []
    for plan in plans:
        if plan["source"]["source_kind"] != "TEMPLATE":
            rows.append(_row(plan, "NEW_SUPPLEMENTAL_PLAN", []))
            continue
        key = _plan_key(plan)
        matches = by_key.get(key, [])
        if len(matches) == 1:
            rows.append(_row(plan, "EXACT_LEGACY_ALIAS", [matches[0]["item_id"]]))
        elif matches:
            rows.append(_row(plan, "AMBIGUOUS_EXACT_SOURCE_ROW",
                             [entry["item_id"] for entry in matches]))
        else:
            rows.append(_row(plan, "NEW_OR_REVISED_SOURCE_ROW", []))
    counts = defaultdict(int)
    for row in rows:
        counts[row["migration_state"]] += 1
    return {
        "schema_version": "operational-catalog-migration-v1",
        "policy": {
            "matching": "EXACT_AFTER_FORMAT_ONLY_NORMALIZATION",
            "fuzzy_title_or_semantic_mapping": False,
            "aliases_do_not_activate_plans": True,
            "ambiguous_aliases_are_rejected": True,
        },
        "counts": {"canonical_plans": len(plans), **dict(sorted(counts.items()))},
        "rows": rows,
    }


def _row(plan: dict[str, Any], state: str, aliases: list[str]) -> dict[str, Any]:
    return {
        "plan_id": plan["plan_id"],
        "source_kind": plan["source"]["source_kind"],
        "product_template": plan["source"].get("product_template"),
        "label": plan["source"].get("label"),
        "source_sha256": plan["source_sha256"],
        "migration_state": state,
        "legacy_item_ids": aliases,
        "requires_review_before_activation": state != "EXACT_LEGACY_ALIAS",
    }


def _legacy_key(entry: dict[str, Any]) -> tuple[str, str, str]:
    fields = entry.get("fields") or {}
    return (_norm_section(entry.get("template_section")),
            _norm_text((fields.get("label") or {}).get("text")),
            _norm_example((fields.get("example") or {}).get("text")))


def _plan_key(plan: dict[str, Any]) -> tuple[str, str, str]:
    source = plan["source"]
    fields = source.get("source_fields") or {}
    return (_norm_section(source.get("product_template")),
            _norm_text(source.get("label") or fields.get("label")),
            _norm_example(fields.get("example")))


def _norm_section(value: Any) -> str:
    text = _norm_text(value)
    return re.sub(r"\s*\[(?:정식|잠정)\]\s*$", "", text)


def _norm_example(value: Any) -> str:
    text = _norm_text(value)
    return re.sub(r"^[-·•]\s*", "", text)


def _norm_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()
