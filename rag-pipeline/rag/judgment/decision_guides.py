"""Validated judgment guidance that can explain, but never replace, v2 rules."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


VERSION = "review-decision-guide-v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_decision_guides(
    path: Path | None,
    *,
    regulation_path: Path,
    known_item_ids: Iterable[str],
) -> list[dict[str, Any]]:
    if path is None:
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != VERSION:
        raise ValueError(f"decision guide version must be {VERSION}")
    actual_regulation_hash = sha256(regulation_path)
    if value.get("regulation_v2_sha256") != actual_regulation_hash:
        raise ValueError("decision guide is not bound to the active regulation v2 snapshot")
    known = set(map(str, known_item_ids))
    guides = value.get("guides")
    if not isinstance(guides, list):
        raise ValueError("decision guide guides must be an array")
    seen = set()
    required_arrays = (
        "requirements",
        "compliant_examples",
        "violation_conditions",
        "review_conditions",
    )
    for index, raw in enumerate(guides):
        if not isinstance(raw, dict):
            raise ValueError(f"decision guide row {index} must be an object")
        guide_id = str(raw.get("guide_id") or "").strip()
        item_id = str(raw.get("item_id") or "").strip()
        if not guide_id or guide_id in seen:
            raise ValueError(f"decision guide row {index} has missing/duplicate guide_id")
        if item_id not in known:
            raise ValueError(f"decision guide {guide_id} references unknown v2 item {item_id}")
        if not str(raw.get("label") or "").strip():
            raise ValueError(f"decision guide {guide_id} has no label")
        for field in required_arrays:
            rows = raw.get(field)
            if not isinstance(rows, list) or (field == "requirements" and not rows):
                raise ValueError(f"decision guide {guide_id}.{field} is invalid")
            if any(not isinstance(row, str) or not row.strip() for row in rows):
                raise ValueError(f"decision guide {guide_id}.{field} contains empty text")
        applicability_conditions = raw.get("applicability_conditions", [])
        if not isinstance(applicability_conditions, list) or any(
            not isinstance(row, str) or not row.strip()
            for row in applicability_conditions
        ):
            raise ValueError(
                f"decision guide {guide_id}.applicability_conditions is invalid"
            )
        seen.add(guide_id)
    return guides


def attach_decision_guides(
    rules: list[dict[str, Any]], guides: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_item: dict[str, list[dict[str, Any]]] = {}
    for guide in guides:
        by_item.setdefault(str(guide["item_id"]), []).append(guide)
    for rule in rules:
        rule["decision_guides"] = by_item.get(str(rule["item_id"]), [])
        rule["decision_guide_policy"] = (
            "examples are non-exhaustive interpretation aids; "
            + ("the original HWPX template is an independent judgment source; v2 mapping is not required"
               if rule.get("source_sheet") == "HWPX_TEMPLATE"
               else "v2 remains authoritative for this v2 rule")
        )
    return rules
