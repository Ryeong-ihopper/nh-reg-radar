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
    queries, added, deferred = list(rows), [], []
    used_ids = {row["doc_id"] for row in rows}
    for members in groups.values():
        if len(members) < 2:
            continue
        texts = [str(row.get("text_search") or row.get("text_canonical") or "") for row in members]
        ids = [row["doc_id"] for row in members]
        text = "\n".join(texts)
        if not all(part.strip() for part in texts) or len(text) > max_chars or max_chars == 0:
            deferred.append({"source_doc_ids": ids, "chars": len(text), "reason": "whole_parent_query_budget_or_empty_text"})
            continue
        identity = hashlib.sha256(json.dumps([ids, text], ensure_ascii=False).encode()).hexdigest()
        query_id = "QUERY-CONTEXT-" + identity
        if query_id in used_ids:
            raise ValueError("context query ID collision")
        used_ids.add(query_id)
        # These are retrieval-only views, never new citable evidence documents.
        queries.append({**members[0], "doc_id": query_id, "text_search": text,
                        "_query_members": members})
        added.append({"query_id": query_id, "source_doc_ids": ids, "chars": len(text)})
    return queries, {"method": "whole_source_parent_v1", "max_chars": max_chars,
                     "original_queries": len(rows), "added": added, "deferred": deferred,
                     "cross_region_relations_inferred": False}
