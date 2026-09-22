"""Source-bound policy for promoting retrieved conditional v2 rules.

The policy does not decide whether an advertisement complies.  It only states
which source rows may move from discovery audit into either automated judgment
or a human visual-review queue after advertisement evidence retrieved the row.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "candidate-activation-policy-v1"
CONTENT_TIER = "PRODUCT_CONTENT_CONDITIONED_V2"
VISUAL_TIER = "HUMAN_VISUAL_REVIEW"
ALLOWED_TIERS = {CONTENT_TIER, VISUAL_TIER}
FORBIDDEN_KEYS = {
    "ad_id",
    "advertisement_id",
    "case_id",
    "expected_verdict",
    "gold",
    "researcher_answer",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def _source_text(rule: dict[str, Any]) -> str:
    return "\n".join(
        str(rule.get(field) or "")
        for field in ("title", "question", "criterion", "v2_note", "standard_guidance")
    )


def load_candidate_activation_policy(
    path: Path | None,
    *,
    regulation_path: Path,
    rules: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Load a version/source-bound activation policy and fail closed on drift."""
    if path is None:
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported candidate activation policy schema")
    forbidden = sorted(FORBIDDEN_KEYS & {key.lower() for key in _walk_keys(value)})
    if forbidden:
        raise ValueError(f"candidate policy contains answer/case fields: {forbidden}")
    source_hashes = set(value.get("regulation_sha256") or [])
    actual_hash = _sha256(regulation_path)
    if actual_hash not in source_hashes:
        raise ValueError(
            "candidate activation policy does not bind the active regulation source: "
            f"{actual_hash}"
        )
    rule_by_id = {str(rule["item_id"]): rule for rule in rules}
    result: dict[str, dict[str, Any]] = {}
    for entry in value.get("entries") or []:
        item_id = str(entry.get("item_id") or "")
        tier = str(entry.get("execution_tier") or "")
        fragment = str(entry.get("source_fragment") or "").strip()
        if not item_id or item_id in result:
            raise ValueError(f"missing or duplicate candidate policy item_id: {item_id!r}")
        if item_id not in rule_by_id:
            raise ValueError(f"candidate policy references unknown rule: {item_id}")
        if tier not in ALLOWED_TIERS:
            raise ValueError(f"unsupported candidate execution tier for {item_id}: {tier}")
        if len(fragment) < 8 or fragment not in _source_text(rule_by_id[item_id]):
            raise ValueError(
                f"candidate policy source fragment is not present in v2 row {item_id}"
            )
        if entry.get("activation") != "RETRIEVAL_HIT":
            raise ValueError(f"candidate policy {item_id} must activate by RETRIEVAL_HIT")
        triggers = entry.get("evidence_trigger_any") or []
        if tier == CONTENT_TIER and not triggers:
            raise ValueError(f"content-conditioned policy {item_id} needs evidence triggers")
        if (
            not isinstance(triggers, list)
            or any(
                not isinstance(trigger, str)
                or len(trigger.strip()) < 2
                or trigger.strip() not in _source_text(rule_by_id[item_id])
                for trigger in triggers
            )
        ):
            raise ValueError(
                f"candidate policy evidence triggers are not source-derived for {item_id}"
            )
        result[item_id] = dict(entry)
    return result


def _observed_source_trigger(row: dict[str, Any], entry: dict[str, Any]) -> bool:
    triggers = entry.get("evidence_trigger_any") or []
    if not triggers:
        return True
    evidence_text = "\n".join(
        str((event.get("trigger") or {}).get("text") or "")
        for event in row.get("trigger_evidence") or []
    )
    compact = "".join(evidence_text.split())
    return any("".join(trigger.split()) in compact for trigger in triggers)


def activated_retrieval_rows(
    retrieved_rows: Iterable[dict[str, Any]],
    policy: dict[str, dict[str, Any]],
    *,
    execution_tier: str,
) -> list[dict[str, Any]]:
    """Return retrieved rows authorized for one policy tier, preserving rank/evidence."""
    if execution_tier not in ALLOWED_TIERS:
        raise ValueError(f"unsupported candidate execution tier: {execution_tier}")
    return [
        {
            **row,
            "discovery_method": "source_bound_conditional_retrieval",
            "execution_tier": execution_tier,
            "activation_basis": policy[row["item_id"]]["source_fragment"],
        }
        for row in retrieved_rows
        if row["item_id"] in policy
        and policy[row["item_id"]]["execution_tier"] == execution_tier
        and _observed_source_trigger(row, policy[row["item_id"]])
    ]
