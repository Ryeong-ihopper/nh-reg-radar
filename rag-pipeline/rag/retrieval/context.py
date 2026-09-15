"""Expand source context without using ad labels as legal applicability rules."""

from __future__ import annotations

from typing import Any


def expand_source_context(
    seed_ids: list[str], rows: list[dict[str, Any]], *, char_budget: int = 2400
):
    """Add complete sibling groups, never silently truncate a condition/table.

    This is source-region context, NOT a claim that all semantic dependencies
    have been discovered. Cross-region footnotes require explicit source links.
    The budget limits additions only; discovered trigger evidence is immutable.
    """
    if char_budget < 0:
        raise ValueError("context char budget must be non-negative")
    by_id = {row["doc_id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError("duplicate evidence doc_id")
    selected = list(dict.fromkeys(seed_ids))
    if any(doc_id not in by_id for doc_id in selected):
        raise ValueError("unknown seed evidence")
    groups = {}
    for row in rows:
        parent = row.get("parent_doc_id")
        if parent:
            key = (
                row.get("ad_id"),
                row.get("product_id"),
                row.get("source_file"),
                row.get("page_no"),
                parent,
            )
            groups.setdefault(key, []).append(row["doc_id"])
    pending, added, seen = [], [], set()
    remaining = char_budget
    for seed_id in list(selected):
        seed = by_id[seed_id]
        key = (
            seed.get("ad_id"),
            seed.get("product_id"),
            seed.get("source_file"),
            seed.get("page_no"),
            seed.get("parent_doc_id"),
        )
        if key in seen:
            continue
        seen.add(key)
        extra = [doc_id for doc_id in groups.get(key, []) if doc_id not in selected]
        chars = sum(len(str(by_id[doc_id].get("text_canonical") or "")) for doc_id in extra)
        if extra and (chars > remaining or char_budget == 0):
            pending.append(
                {
                    "seed_id": seed_id,
                    "reason": "source_context_budget",
                    "evidence_ids": extra,
                    "chars": chars,
                }
            )
        else:
            selected.extend(extra)
            added.extend(extra)
            remaining -= chars
    # Explicit parser-observed links only. No label/embedding guesses, no
    # traversal into another advertisement or product, no partial footnotes.
    relation_seen = set()
    relation_added = []
    by_scope_ref = {}
    for row in rows:
        for ref in row.get("line_refs") or []:
            by_scope_ref.setdefault((row.get("ad_id"), row.get("product_id"), str(ref)), []).append(row["doc_id"])
    for seed_id in list(selected):
        seed = by_id[seed_id]
        for relation in seed.get("source_relations") or []:
            if not isinstance(relation, dict):
                continue
            source_refs, target_refs = relation.get("from_line_ids"), relation.get("to_line_ids")
            if not (isinstance(source_refs, list) and source_refs and isinstance(target_refs, list) and target_refs
                    and isinstance(relation.get("type"), str)
                    and all(isinstance(ref, str) for ref in [*source_refs, *target_refs])):
                pending.append({"seed_id": seed_id, "reason": "invalid_source_relation"})
                continue
            key = (seed.get("ad_id"), seed.get("product_id"), relation.get("type"), tuple(source_refs), tuple(target_refs))
            if key in relation_seen:
                continue
            relation_seen.add(key)
            refs = [*source_refs, *target_refs]
            if not set(refs).intersection(seed.get("line_refs") or []):
                continue
            if relation.get("status") != "observed" or relation.get("type") not in {
                "header_for", "footnote_for", "continuation_of", "condition_context"}:
                pending.append({"seed_id": seed_id, "reason": "unverified_source_relation", "relation": relation})
                continue
            if any((key[0], key[1], ref) not in by_scope_ref for ref in refs):
                pending.append({"seed_id": seed_id, "reason": "relation_target_missing_or_outside_scope", "relation": relation})
                continue
            if any(len({(by_id[doc_id].get("source_file"), by_id[doc_id].get("page_no"))
                        for doc_id in by_scope_ref[(key[0], key[1], ref)]}) > 1 for ref in refs):
                pending.append({"seed_id": seed_id, "reason": "ambiguous_source_relation", "relation": relation})
                continue
            extra = list(dict.fromkeys(doc_id for ref in refs
                for doc_id in by_scope_ref[(key[0], key[1], ref)] if doc_id not in selected))
            chars = sum(len(str(by_id[doc_id].get("text_canonical") or "")) for doc_id in extra)
            if extra and (chars > remaining or char_budget == 0):
                pending.append({"seed_id": seed_id, "reason": "source_relation_budget",
                    "evidence_ids": extra, "chars": chars, "relation": relation})
                continue
            selected.extend(extra)
            added.extend(extra)
            relation_added.extend(extra)
            remaining -= chars
    return selected, {
        "method": "source_region_and_observed_relations_v2",
        "seed_ids": list(dict.fromkeys(seed_ids)),
        "added_ids": added,
        "relation_added_ids": relation_added,
        "added_chars": char_budget - remaining,
        "char_budget": char_budget,
        "deferred_groups": pending,
        "semantic_dependencies_complete": False,
    }
