"""Measure saved operational requests without reading gold or calling models.

Print sizes/counts, never customer text. Character counts are NOT token counts.
"""

from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import json
from pathlib import Path

from run_gemma_exhaustive_dgx import _compact_model_request
from rag.judgment.evidence_projection import pack_documents, unpack_documents


def dump(value, *, compact=False):
    return json.dumps(value, ensure_ascii=False, **({"separators": (",", ":")} if compact else {}))


def audit_requests(rows):
    before_chars = after_chars = before_bytes = after_bytes = 0
    before_fields, after_fields = collections.Counter(), collections.Counter()
    checked_documents = checked_lines = 0
    for row in rows:
        source = json.loads(row["messages"][1]["content"])
        messages, aliases = _compact_model_request(row)
        wire = json.loads(messages[1]["content"])
        original_documents = unpack_documents(wire["documents"], wire["reading_contexts"])
        repacked, contexts = pack_documents(original_documents)
        assert repacked == wire["documents"] and contexts == wire["reading_contexts"]
        assert len(original_documents) == len(source["documents"])
        for original, compact in zip(source["documents"], original_documents):
            assert aliases["ref_to_evidence"][compact["evidence_ref"]] == original["evidence_id"]
            assert [aliases["ref_to_line"][ref] for ref in compact["line_refs"]] == original[
                "line_refs"
            ]
            assert compact["text_selection"] == (original.get("text_selection") or {})
            assert compact["span_status"] == (original.get("span_status") or "unknown")
            assert compact["page_no"] == original.get("page_no")
            expected_lines = [
                {"line_ref": ref, "text": original["line_texts"][ref]}
                for ref in original["line_refs"]
                if ref in (original.get("line_texts") or {})
            ]
            actual_lines = [
                {"line_ref": aliases["ref_to_line"][line["line_ref"]], "text": line["text"]}
                for line in compact.get("lines", [])
            ]
            assert actual_lines == expected_lines
            restored_text = compact.get(
                "text", "".join(str(line["text"]) for line in compact.get("lines", []))
            )
            assert "".join(restored_text.split()) == "".join(
                str(original.get("text") or "").split()
            )
            if "line_bboxes" in compact:
                assert {
                    aliases["ref_to_line"][line["line_ref"]]: line["bbox"]
                    for line in compact["line_bboxes"]
                } == (original.get("line_bboxes") or {})
                assert compact["bbox"] == original.get("bbox")
            checked_documents += 1
            checked_lines += len(actual_lines)
        # Only packing and JSON whitespace are reversed; this is a representation
        # size comparison, not an earlier model run or a semantic accuracy test.
        before = copy.deepcopy(wire)
        before["documents"] = original_documents
        before.pop("reading_contexts")
        before_text, after_text = dump(before), messages[1]["content"]
        before_chars += len(before_text)
        after_chars += len(after_text)
        before_bytes += len(before_text.encode("utf-8"))
        after_bytes += len(after_text.encode("utf-8"))
        before_fields.update({key: len(dump(value)) for key, value in before.items()})
        after_fields.update({key: len(dump(value, compact=True)) for key, value in wire.items()})
    return {
        "measurement": "user_message_json_only_not_model_tokens",
        "requests": len(rows),
        "verified_document_exposures": checked_documents,
        "verified_line_text_exposures": checked_lines,
        "before_chars": before_chars,
        "after_chars": after_chars,
        "reduction_percent": round(100 * (1 - after_chars / before_chars), 2)
        if before_chars
        else 0,
        "before_utf8_bytes": before_bytes,
        "after_utf8_bytes": after_bytes,
        "before_field_chars": dict(before_fields),
        "after_field_chars": dict(after_fields),
        "source_and_reference_checks": "PASS",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=Path, required=True)
    parser.add_argument("--fine", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--integrated", type=Path, help="Optional source for a controlled evidence-only replay"
    )
    parser.add_argument(
        "--replay-output", type=Path, help="New request file; preserves frozen rule/seed selection"
    )
    args = parser.parse_args()
    raw = args.requests.read_bytes()
    rows = [json.loads(line) for line in raw.decode("utf-8-sig").splitlines() if line.strip()]
    if args.integrated or args.replay_output:
        if not (args.integrated and args.replay_output):
            parser.error("--integrated and --replay-output must be provided together")
        if args.replay_output.exists():
            parser.error("replay output exists; preserve the previous execution")
        from rag.parsing.prepare_inputs import search_docs
        from rag.retrieval.context import expand_source_context
        from run_operational_e2e import (
            evidence_documents,
            deterministic_facts,
            model_deterministic_facts,
        )

        integrated = json.loads(args.integrated.read_text(encoding="utf-8-sig"))
        _, fine_rows = search_docs(integrated)
        fine_by_id = {doc["evidence_id"]: doc for doc in evidence_documents(fine_rows)}
        facts = deterministic_facts(fine_rows, ad=integrated)
        for row in rows:
            if row["ad_id"] != integrated["document"]["ad_id"]:
                parser.error("replay supports one exact scoped advertisement at a time")
            payload = json.loads(row["messages"][1]["content"])
            context_audit = {}
            for item_id, scope in payload["evidence_scope"].items():
                scope["evidence_ids"], context_audit[item_id] = expand_source_context(
                    scope["evidence_ids"], fine_rows
                )
            selected = list(
                dict.fromkeys(
                    ref
                    for scope in payload["evidence_scope"].values()
                    for ref in scope["evidence_ids"]
                )
            )
            payload["documents"] = [fine_by_id[ref] for ref in selected]
            payload["deterministic_facts"] = model_deterministic_facts(facts, payload["documents"])
            row["evidence_context_audit"] = context_audit
            row["messages"][1]["content"] = dump(payload)
        args.replay_output.parent.mkdir(parents=True, exist_ok=True)
        args.replay_output.write_text("".join(dump(row) + "\n" for row in rows), encoding="utf-8")
    result = {"source_requests_sha256": hashlib.sha256(raw).hexdigest(), **audit_requests(rows)}
    if args.fine:
        fine = [
            json.loads(line)
            for line in args.fine.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
        assert all(
            "".join(row["text_search"].split()) == "".join(row["text_canonical"].split())
            for row in fine
        )
        result["fine"] = {
            "count": len(fine),
            "body_chars": sum(len(row["text_canonical"]) for row in fine),
            "under_40_chars": sum(len(row["text_canonical"]) < 40 for row in fine),
            "search_text_is_whitespace_normalized_body": True,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(dump(result) + "\n", encoding="utf-8")
    print(dump({key: value for key, value in result.items() if not key.endswith("field_chars")}))


if __name__ == "__main__":
    main()
