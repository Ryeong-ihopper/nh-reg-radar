"""Additional source-parent queries; original fine queries remain intact."""
from __future__ import annotations

import hashlib
import json


def build_context_queries(rows, *, max_chars=700):
    if max_chars < 0:
        raise ValueError("query context budget must be non-negative")
    if len({row["doc_id"] for row in rows}) != len(rows):
        raise ValueError("duplicate query source doc_id")
    groups = {}
    for row in rows:
        key = tuple(row.get(field) for field in
                    ("ad_id", "product_id", "source_file", "page_no", "parent_doc_id"))
        if all(key[index] is not None and key[index] != "" for index in (0, 2, 3, 4)):
            groups.setdefault(key, []).append(row)
    queries, added, relation_added, deferred = list(rows), [], [], []
    used_ids = {row["doc_id"] for row in rows}
    def add_view(members, *, method):
        texts = [str(row.get("text_search") or row.get("text_canonical") or "") for row in members]
        ids = [row["doc_id"] for row in members]
        text = "\n".join(texts)
        if not all(part.strip() for part in texts) or len(text) > max_chars or max_chars == 0:
            deferred.append({"source_doc_ids": ids, "chars": len(text),
                             "reason": f"{method}_query_budget_or_empty_text"})
            return
        identity = hashlib.sha256(json.dumps([ids, text], ensure_ascii=False).encode()).hexdigest()
        query_id = "QUERY-CONTEXT-" + identity
        if query_id in used_ids:
            return
        used_ids.add(query_id)
        queries.append({**members[0], "doc_id": query_id, "text_search": text,
                        "_query_members": members, "_query_context_method": method})
        record = {"query_id": query_id, "source_doc_ids": ids, "chars": len(text)}
        (relation_added if method == "observed_relation" else added).append(record)

    for members in groups.values():
        if len(members) < 2:
            continue
        add_view(members, method="whole_parent")

    # Keep short label/value/footnote chunks citable on their own. Combine
    # them only as a retrieval view when the parser observed their relation.
    row_order = {row["doc_id"]: index for index, row in enumerate(rows)}
    by_scope_ref = {}
    for row in rows:
        scope = (row.get("ad_id"), row.get("product_id"), row.get("source_file"))
        for ref in row.get("line_refs") or []:
            by_scope_ref.setdefault((*scope, str(ref)), []).append(row)
    relation_keys = set()
    for row in rows:
        scope = (row.get("ad_id"), row.get("product_id"), row.get("source_file"))
        for relation in row.get("source_relations") or []:
            if (relation.get("status") != "observed"
                    or relation.get("type") not in {"header_for", "footnote_for", "continuation_of", "condition_context"}):
                continue
            refs = [*(relation.get("from_line_ids") or []), *(relation.get("to_line_ids") or [])]
            key = (*scope, relation.get("type"), tuple(refs))
            if key in relation_keys:
                continue
            relation_keys.add(key)
            members = list({candidate["doc_id"]: candidate for ref in refs
                            for candidate in by_scope_ref.get((*scope, str(ref)), [])}.values())
            members.sort(key=lambda candidate: row_order[candidate["doc_id"]])
            if len(members) >= 2:
                add_view(members, method="observed_relation")
    return queries, {"method": "source_parent_and_observed_relation_v2", "max_chars": max_chars,
                     "original_queries": len(rows), "added": added,
                     "relation_added": relation_added, "deferred": deferred,
                     "cross_region_relations_inferred": False}
