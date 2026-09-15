"""Lossless wire-only packing; never select, merge or reinterpret evidence."""

from __future__ import annotations

import copy
import json
from typing import Any


def pack_documents(documents: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict]:
    """Keep ownership local; share only identical reading metadata per request.

    Line tables remain inside each evidence document. Sharing text across an
    advertisement/product boundary, dropping uncertainty or matching by text
    similarity are deliberately outside this function's remit.
    """
    packed = copy.deepcopy(documents)
    contexts: dict[str, Any] = {}
    context_refs: dict[str, str] = {}
    for document in packed:
        if "text_selection" in document:
            selection = document.pop("text_selection")
            key = json.dumps(selection, ensure_ascii=False, sort_keys=True)
            if key not in context_refs:
                context_refs[key] = f"Q{len(context_refs) + 1}"
                contexts[context_refs[key]] = selection
            document["text_selection_ref"] = context_refs[key]
        for field, value_key in (("lines", "text"), ("line_bboxes", "bbox")):
            if field not in document:
                continue
            table = {}
            for entry in document[field]:
                ref = entry["line_ref"]
                if ref in table:
                    raise ValueError(f"duplicate line reference in {field}")
                if set(entry) != {"line_ref", value_key}:
                    raise ValueError(f"unexpected source fields in {field}")
                table[ref] = entry[value_key]
            document[field] = table
    return packed, contexts


def unpack_documents(documents: list[dict[str, Any]], contexts: dict) -> list[dict[str, Any]]:
    """Reconstruct pre-packing documents for audits/tests, without model output."""
    unpacked = copy.deepcopy(documents)
    for document in unpacked:
        if "text_selection_ref" in document:
            ref = document.pop("text_selection_ref")
            document["text_selection"] = copy.deepcopy(contexts[ref])
        for field, value_key in (("lines", "text"), ("line_bboxes", "bbox")):
            if field in document:
                document[field] = [
                    {"line_ref": ref, value_key: value} for ref, value in document[field].items()
                ]
    return unpacked
