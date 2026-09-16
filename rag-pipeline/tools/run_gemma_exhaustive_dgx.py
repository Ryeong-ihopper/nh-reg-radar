# -*- coding: utf-8 -*-
"""GPU Gemma API로 규칙 배치를 판정한다; 파일명은 DGX 보고 경로와 호환된다."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag.judgment.grounding import grounding_errors  # noqa: E402
from rag.judgment.evidence_projection import pack_documents  # noqa: E402
from rag.parsing.source_structure import compact_source_structure  # noqa: E402
from rag.judgment.reading_quality import apply_reading_guard, needs_reading_review, reading_issues  # noqa: E402
from rag.judgment.temporal import basis_date_observations, temporal_claim_errors  # noqa: E402
from rag.judgment.manual_review import text_facet_claim_errors  # noqa: E402
from rag.judgment.source_checks import source_claim_errors  # noqa: E402
from rag.judgment.arithmetic import calculate_loan_rates, METHOD as ARITHMETIC_METHOD  # noqa: E402
from rag.judgment.output_contract import response_format, response_mode  # noqa: E402


DEFAULT_HOST = os.environ.get("DGX_HOST")
DEFAULT_KEY = Path(os.environ["DGX_SSH_KEY"]) if os.environ.get("DGX_SSH_KEY") else None
DEFAULT_MODEL = os.environ.get(
    "NH_GPU_GEMMA_MODEL",
    os.environ.get("DGX_GEMMA_MODEL", "gemma-4-26b-NVFP4-MTP"),
)
ENDPOINT = "http://127.0.0.1:8102/v1/chat/completions"


# Keep the wire contract short. Canonical IDs and duplicated applicability
# fields are restored deterministically after this response is validated.
COMPACT_OUTPUT_SYSTEM = """
Return exactly one JSON object and no prose. Produce one result for every input
rule_ref, in the same order. Never output ad_id, item_id, applicability,
applicability_basis, top-level evidence, or needs_researcher_review; the runner
derives those fields from the gates below.
Never return an empty result object. If evidence is insufficient, still return
the rule_ref, gate checks, UNDETERMINED verdict, reason and confidence; follow
the gate rules below for whether obligation checks are required.

{
  "results": [{
    "rule_ref": "R1",
    "scope_check": {
      "scope_ref": "SCOPE",
      "status": "MATCHED|NOT_MATCHED|UNDETERMINED",
      "evidence_refs": ["E1", "L1"],
      "metadata_fields": ["product_group"]
    },
    "condition_checks": [],
    "review_condition_checks": [],
    "verdict": "COMPLIANT|VIOLATION|UNDETERMINED",
    "requirement_checks": [{
      "obligation_ref": "O1",
      "requirement": "checked obligation",
      "status": "SATISFIED|MISSING|VIOLATED|UNDETERMINED",
      "finding_basis": "OBSERVED|ABSENCE|UNKNOWN",
      "evidence_refs": ["E1", "L1"],
      "reason": "direct reason"
    }],
    "reason": "one or two sentences",
    "confidence": "LOW|MEDIUM|HIGH"
  }]
}

Evaluate gates strictly in SCOPE -> A -> U -> obligation order. SCOPE must match
every person, product, situation, medium, and procedure qualifier in the complete
scope_text for the same advertisement context. If the rule's triggering expression
or situation is absent, use NOT_MATCHED, not MATCHED. Return every A/U reference
exactly once and in source order; use [] when the contract has none.
Each rule's output_check_refs is the complete allowed A/U checklist. If an array
is empty, return [] for that array: never copy A1/U1 from this format example or
invent a new condition ID from natural-language qualifiers. Such qualifiers
still belong to SCOPE. evidence_scope lists allowed E and L aliases per rule;
an alias allowed for another rule is not available to this rule. Q aliases are
reading metadata, never citation IDs. The full transcript is context, not an
additional citable source. Never borrow a nearby line to cite a transcript claim.
For v2 contracts, requirement_checks must return every listed obligation_ref
exactly once, in source order, after gates pass. Do not merge multiple O checks
into a generic "all mandatory disclosures present" check. Each O check needs its
own supporting references or an explicit MISSING/UNDETERMINED outcome. Source
notes narrow the criterion; an umbrella rule is not a substitute for all other
rules. Preserve source exceptions and ANY_OF choices. Never split examples into
mandatory items. If the applicable set of elements cannot be established, use
UNDETERMINED rather than asserting complete compliance.
Search facets are retrieval hints, not additional obligations or proof of absence.
Resolve each O against its source conditions, exceptions and alternatives before
assigning its status. A definitive VIOLATED obligation remains an overall VIOLATION
even when another obligation is UNDETERMINED; do not hide a confirmed independent
violation behind uncertainty elsewhere. Do not mark an O VIOLATED while its own
applicability or exception remains unresolved.
MATCHED SCOPE requires a supporting allowed evidence reference or a confirmed
metadata field. Do not leave both empty when claiming a match. Before returning
each rule, check every cited alias against that rule's allowlist. If the supplied
citable evidence cannot support the assertion, report UNDETERMINED rather than
substituting a different line or fabricating applicability support.

사용자에게 보이는 reason·requirement 설명은 한국어로 작성한다. 규칙·근거 ID와
enum 값은 지정된 영문을 그대로 유지하고, 원문 고유명사·수치는 번역하거나 바꾸지 않는다.

Document lines maps L aliases to exact source text; line_bboxes maps the same
aliases to coordinates. These are source lines, not new or independent evidence.
For every SATISFIED/VIOLATED OBSERVED check, cite the specific supporting L aliases
when exact lines are supplied. An E region alone is insufficient: select the
actual source sentence, not all lines in the region. Uncertain source readings
are retained as context but have no citable aliases; use readable evidence.
When claiming a name or phrase is present, quote the observed wording in the
reason and cite the L line that actually contains it. The first line of a
region cannot stand in for a different sentence elsewhere in that region.
source_relations and table cells describe parser structure between canonical L
lines. They do not prove legal applicability. Missing structure is not a missing
disclosure. A table cell with status other than observed is navigation context,
not proof of a row/column association. Use canonical text or UNDETERMINED instead.
asset_ref separates source files; never mix rates from different
products, variants, dates or conditions into one arithmetic comparison. First
establish the same scope from readable source evidence. Cell text outside the
canonical lines is not supplied as evidence. Unknown unit, date, rate basis or
visual measurement requires UNDETERMINED for the dependent obligation.
An arithmetic VIOLATED check must include a reproducible source-based witness
in its Korean reason: "검산: a+b-c != d", replacing variables with actual cited
numbers. The sum/difference must really differ from the advertised result.
Equal values are not violations. Complex or unresolved formulas need human
review; do not invent a mismatch or sum alternative benefit conditions together.
Verify the arithmetic relationships actually asserted in the source. Separate
the stated base example from conditional adjustments. An adjustment without a
separately advertised total creates no extra equality to verify: do not demand
an unstated variant total or treat the adjustment as part of a different base
example. Explain each computable base sum/difference and benefit alternative
before identifying any genuinely unresolved advertised calculation.
Resolve each document's text_selection_ref in reading_contexts: it describes
OCR/VLM reading uncertainty, not legal review. A shared Q entry does not mean
the documents are independent readings or share a source location.
If needs_review is true, do not establish a definitive observed fact from that
document alone; use independently readable evidence or UNDETERMINED.
span_status=region_level_selected_text means the refs cover a source region,
not an exact alignment of selected text. Cite an individual line only when its
provided text directly supports the claim. Unknown precision is not line-exact.

If SCOPE is NOT_MATCHED or any A is NOT_SATISFIED, set requirement_checks=[]. If
any gate is UNDETERMINED or a U condition is TRIGGERED, use verdict=UNDETERMINED
and requirement_checks=[]. Do not judge the obligation before those gates pass.
If every gate passes but the obligation itself cannot be determined, keep SCOPE
MATCHED, use verdict=UNDETERMINED, and return the listed obligation checks with
unresolved ones marked UNDETERMINED/UNKNOWN. Never omit a required O check.

Use only E/L aliases present in that rule's evidence_scope and only confirmed
metadata field names. OBSERVED requires direct E/L evidence. ABSENCE/MISSING is
allowed only when complete_ad_scan=true. An incomplete scan blocks absence and
whole-ad completeness claims, not a directly observed required phrase. After
gates pass, readable allowed evidence that establishes every required element
of a presence obligation supports SATISFIED+OBSERVED even if parser_coverage is
PARTIAL. Do not demand an entire-ad scan to confirm that such a phrase exists.
If that obligation depends on unread text, missing layout or external input,
use UNKNOWN and UNDETERMINED. Empty arrays must be [], never
null. For an applicable prohibition with no prohibited content in a complete scan,
return COMPLIANT with one SATISFIED+ABSENCE requirement check; never omit the check.
For a required presence rule, SATISFIED+ABSENCE is impossible: if its triggering
scope does not apply use SCOPE=NOT_MATCHED; if it applies and the required content
is absent from a complete scan use MISSING+ABSENCE and verdict=VIOLATION. A
MISSING+ABSENCE finding proves absence with complete_ad_scan and therefore must not
invent an L line reference. Only OBSERVED/VIOLATED findings require a direct L ref.
When complete_ad_scan=true for a text-only rule, do not claim that the scan is
incomplete. Decide the source scope first; if it matches, absence of the required
text is MISSING, while an absent triggering situation is SCOPE=NOT_MATCHED.
SATISFIED+UNKNOWN is invalid. Examples are aids, not exact phrases or new rules.
""".strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # The web bridge, Explorer/OneDrive, and concurrent jobs can all observe a
    # checkpoint on Windows.  A shared ``.tmp`` name both races and is easily
    # held briefly by an indexer, so use an invocation-local name and retry the
    # replacement only for a transient file lock.
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        for attempt in range(6):
            try:
                temporary.replace(path)
                return
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.05 * (2 ** attempt))
    finally:
        temporary.unlink(missing_ok=True)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def parse_content(content: str) -> dict[str, Any]:
    text = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.S | re.I)
    if fenced:
        text = fenced.group(1).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        # Some OpenAI-compatible servers append harmless whitespace or a short
        # explanation despite json_object mode.  Accept one complete leading
        # object, but never attempt to repair a truncated object.
        value, end = json.JSONDecoder().raw_decode(text)
        if text[end:].strip() and not text[end:].strip().startswith("```"):
            raise
    if not isinstance(value, dict):
        raise ValueError("응답이 JSON 객체가 아님")
    return value


def _compact_model_request(row: dict[str, Any]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Replace repeated canonical identifiers with short, reversible aliases."""
    payload = json.loads(row["messages"][1]["content"])
    item_ids = list(row.get("requested_item_ids") or [])
    item_to_ref = {item_id: f"R{index}" for index, item_id in enumerate(item_ids, 1)}
    ref_to_item = {value: key for key, value in item_to_ref.items()}

    evidence_to_ref: dict[str, str] = {}
    ref_to_evidence: dict[str, str] = {}
    line_to_ref: dict[str, str] = {}
    ref_to_line: dict[str, str] = {}
    compact_documents = []
    needs_spatial_evidence = row.get("category") == "STYLE" or any(
        str(rule.get("required_medium") or "") == "레이아웃"
        or "원본형식" in str(rule.get("input_requirement") or "")
        for rule in (payload.get("rules") or [])
        if isinstance(rule, dict)
    )
    # Preserve the frozen candidates, including uncertain readings, but never
    # offer revoked observations as citable aliases. This uses existing parser
    # uncertainty; it neither reclassifies labels nor repairs source text.
    source_documents = [document for document in payload.get("documents") or []
                        if not needs_reading_review(document)]
    line_citable_ids = {str(doc['evidence_id']) for doc in source_documents
                        if doc.get('line_texts') and doc.get('span_status') != 'region_level_selected_text'}
    uncertain_documents = [document for document in payload.get("documents") or []
                           if needs_reading_review(document)]
    for evidence_index, document in enumerate(source_documents, 1):
        evidence_id = str(document["evidence_id"])
        evidence_ref = f"E{evidence_index}"
        evidence_to_ref[evidence_id] = evidence_ref
        ref_to_evidence[evidence_ref] = evidence_id
        compact_line_refs = []
        for line_ref in document.get("line_refs") or []:
            line_ref = str(line_ref)
            alias = line_to_ref.get(line_ref)
            if alias is None:
                alias = f"L{len(line_to_ref) + 1}"
                line_to_ref[line_ref] = alias
                ref_to_line[alias] = line_ref
            compact_line_refs.append(alias)
        compact_document = {
            "evidence_ref": evidence_ref,
            "page_no": document.get("page_no"),
            "labels": [
                label.get("label")
                for label in (document.get("labels") or [])
                if isinstance(label, dict) and label.get("label")
            ],
            "line_refs": compact_line_refs,
            "text": document.get("text") or "",
            "span_status": document.get("span_status") or "unknown",
            "text_selection": document.get("text_selection") or {},
        }
        if needs_spatial_evidence:
            compact_document["bbox"] = document.get("bbox")
            compact_document["line_bboxes"] = [
                {
                    "line_ref": line_to_ref[str(line_ref)],
                    "bbox": bbox,
                }
                for line_ref, bbox in (document.get("line_bboxes") or {}).items()
                if str(line_ref) in line_to_ref
            ]
        # A list of line IDs next to aggregate text does not identify which
        # words each ID denotes. Carry exact source lines; never zip inferred
        # text splits with IDs (tables and wrapped lines are not one-to-one).
        line_texts = document.get("line_texts") or {}
        source_lines = [
            {"line_ref": line_to_ref[str(ref)], "text": line_texts[str(ref)]}
            for ref in document.get("line_refs") or []
            if str(ref) in line_texts
        ]
        if source_lines:
            compact_document["lines"] = source_lines
            same_text = "".join(str(part["text"]) for part in source_lines).split()
            if "".join(same_text) == "".join(compact_document["text"].split()):
                compact_document.pop("text")  # Avoid sending identical text twice.
        compact_documents.append(compact_document)

    # Resolve cross-document endpoints only after every canonical line has an
    # alias. Asset aliases preserve variant boundaries without treating names
    # as classification evidence. Table OCR cannot become extra citable text.
    asset_aliases = {}
    for source, target in zip(source_documents, compact_documents):
        asset = source.get("asset_id") or source.get("source_file")
        if asset:
            target["asset_ref"] = asset_aliases.setdefault(str(asset), f"F{len(asset_aliases) + 1}")
            target["source_page_no"] = source.get("source_page_no")
        target.update(compact_source_structure(source, line_to_ref))

    def compact_scope(scope: dict[str, Any]) -> dict[str, Any]:
        allowed_evidence = set(map(str, scope.get("evidence_ids") or []))
        allowed_lines = list(dict.fromkeys(
            line_to_ref[str(ref)] for document in source_documents
            if str(document['evidence_id']) in allowed_evidence
            for ref in document.get('line_refs') or []))
        return {
            "evidence_refs": [
                evidence_to_ref[value]
                for value in map(str, scope.get("evidence_ids") or [])
                if value in evidence_to_ref and value not in line_citable_ids
            ] + allowed_lines,
            "line_refs": allowed_lines,
            "complete_ad_scan": scope.get("complete_ad_scan") is True and not uncertain_documents,
        }

    rules = []
    for rule in payload.get("rules") or []:
        item_id = str(rule.get("item_id") or "")
        compact_rule = {key: value for key, value in rule.items() if key != "item_id"}
        contract = compact_rule.get("condition_contract")
        if isinstance(contract, dict):
            # The compiled contract retains authoritative conditions and
            # explicit bound guide obligations. Raw auxiliary guidance is
            # retained in the frozen request, not a second competing rule.
            for field in ('standard_guidance', 'standard_examples', 'guide', 'rule_summaries'):
                compact_rule.pop(field, None)
            basis = compact_rule.get('template_basis')
            if isinstance(basis, dict):
                compact_rule['template_basis'] = {key: value for key, value in basis.items()
                    if key not in {'fields', 'manual_guidance', 'alternative_members'}}
            contract = copy.deepcopy(contract)
            compact_rule["condition_contract"] = contract
            compact_rule["output_check_refs"] = {
                "condition_checks": [value["condition_id"] for value in contract.get("applicability_conditions") or []],
                "review_condition_checks": [value["condition_id"] for value in contract.get("review_conditions") or []],
                **({"requirement_checks": [value["obligation_id"] for value in contract["obligation_checks"]]}
                   if "obligation_checks" in contract else {}),
            }
            if "obligation_checks" in contract:
                contract.pop("obligation", None)
                contract.pop("source_note", None)  # Already in complete scope_text.
            # The source-bound contract already carries the full question,
            # criterion/obligation and product scope.  Do not send the same
            # text a second time under legacy projection fields.
            for duplicate in (
                "question", "criterion", "product_groups", "product_subtype",
                "rule_summaries", "example_policy", "decision_guide_policy",
            ):
                compact_rule.pop(duplicate, None)
            if "obligation_checks" in contract:
                compact_rule.pop("v2_note", None)
        compact_rule["rule_ref"] = item_to_ref[item_id]
        rules.append(compact_rule)
    evidence_scope = payload.get("evidence_scope") or {}
    compact_facts = copy.deepcopy(payload.get("deterministic_facts") or {})
    for page in (compact_facts.get("parser_visibility") or {}).get("pages") or []:
        for region in page.get("regions") or []:
            parent_id = str(region.pop("evidence_id", ""))
            region["evidence_refs"] = [evidence_to_ref[str(doc["evidence_id"])]
                for doc in source_documents
                if str(doc.get("parent_evidence_id") or doc["evidence_id"]) == parent_id]
            region["measurement_scope"] = "source_region_not_individual_chunk"
            region["line_styles"] = [
                {**line, "line_ref": line_to_ref[str(line["line_ref"])]}
                for line in region.get("line_styles") or []
                if str(line.get("line_ref")) in line_to_ref]
    compact_documents, reading_contexts = pack_documents(compact_documents)
    compact_payload = {
        "basis_date_observations": [
            {"basis_date": value['basis_date'], "review_date": value['review_date'],
             "elapsed_days": value['elapsed_days'], "evidence_ref": evidence_to_ref[value['evidence_id']],
             "line_refs": [line_to_ref[ref] for ref in value['line_refs'] if ref in line_to_ref]}
            for value in basis_date_observations(source_documents,
                (payload.get('review_context') or {}).get('review_date'))
        ],
        "review_context": payload.get("review_context"),
        "routing": payload.get("routing") or {},
        "parser_coverage": payload.get("parser_coverage"),
        "reading_quality": payload.get("reading_quality") or {},
        "observed_ad_text": payload.get("full_ad_text"),
        "uncertain_context": [{"text": doc.get("text") or "",
                               "page_no": doc.get("page_no"),
                               "span_status": doc.get("span_status") or "unknown",
                               "text_selection": doc.get("text_selection") or {},
                               "citable": False} for doc in uncertain_documents],
        "documents": compact_documents,
        "reading_contexts": reading_contexts,
        "evidence_scope": {
            item_to_ref[item_id]: compact_scope(evidence_scope.get(item_id) or {})
            for item_id in item_ids
        },
        "deterministic_facts": compact_facts,
        "applicability_screen": {
            item_to_ref[item_id]: value
            for item_id, value in (payload.get("applicability_screen") or {}).items()
            if item_id in item_to_ref
        },
        "external_input_assessment": {
            item_to_ref[item_id]: value
            for item_id, value in (payload.get("external_input_assessment") or {}).items()
            if item_id in item_to_ref
        },
        "rules": rules,
    }
    system = row["messages"][0]["content"].strip() + "\n\n" + COMPACT_OUTPUT_SYSTEM
    for field, statuses in (
        ("condition_checks", "SATISFIED|NOT_SATISFIED|UNDETERMINED"),
        ("review_condition_checks", "TRIGGERED|NOT_TRIGGERED|UNDETERMINED"),
    ):
        if any((rule.get("output_check_refs") or {}).get(field) for rule in rules):
            system += (f"\nFor nonempty output_check_refs.{field}, return one entry per listed ID: "
                       '{"condition_ref":"<listed ID>","status":"' + statuses
                       + '","evidence_refs":[],"metadata_fields":[]}. '
                       "Use the actual evidence/confirmed metadata supporting each check.")
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(compact_payload, ensure_ascii=False, separators=(",", ":"))},
    ]
    messages.extend(copy.deepcopy(row["messages"][2:]))
    return messages, {
        "ref_to_item": ref_to_item,
        "ref_to_evidence": ref_to_evidence,
        "ref_to_line": ref_to_line,
        "ref_to_asset": {alias: source for source, alias in asset_aliases.items()},
    }


def _expand_model_response(
    row: dict[str, Any], parsed: dict[str, Any], aliases: dict[str, Any]
) -> dict[str, Any]:
    """Restore the canonical stored judgment without trusting echoed identifiers."""
    results = parsed.get("results")
    if not isinstance(results, list):
        return {"ad_id": row["ad_id"], "results": results}

    def expand_refs(values: Any) -> tuple[list[str], list[str]]:
        if not isinstance(values, list):
            return values, values
        evidence_ids, line_refs = [], []
        for raw_value in map(str, values):
            # Older prompt examples visually combined an evidence and line alias
            # as ``E1|L1``.  Treat that spelling exactly like ["E1", "L1"];
            # unknown components are still preserved so validation rejects them.
            parts = raw_value.split("|") if "|" in raw_value else [raw_value]
            for value in parts:
                value = value.strip()
                if value in aliases["ref_to_evidence"]:
                    evidence_ids.append(aliases["ref_to_evidence"][value])
                elif value in aliases["ref_to_line"]:
                    line_refs.append(aliases["ref_to_line"][value])
                else:
                    # Preserve an unknown alias so canonical validation rejects it.
                    evidence_ids.append(value)
        return evidence_ids, line_refs

    expanded = []
    expected_item_ids = list(row.get("requested_item_ids") or [])
    for result_index, model_result in enumerate(results):
        if not isinstance(model_result, dict):
            expanded.append(model_result)
            continue
        item_id = aliases["ref_to_item"].get(str(model_result.get("rule_ref") or ""))
        if item_id is None and len(results) == len(expected_item_ids) == 1:
            # A singleton cannot be reordered. Recover a missing/malformed
            # short alias without trusting any model-echoed canonical ID.
            item_id = expected_item_ids[0]
        raw_scope = model_result.get("scope_check")
        scope_check = raw_scope
        gate_ids: list[str] = []
        gate_lines: list[str] = []
        gate_metadata: list[str] = []
        if isinstance(raw_scope, dict):
            scope_ids, scope_lines = expand_refs(raw_scope.get("evidence_refs"))
            if isinstance(scope_ids, list):
                gate_ids.extend(scope_ids)
            if isinstance(scope_lines, list):
                gate_lines.extend(scope_lines)
            if isinstance(raw_scope.get("metadata_fields"), list):
                gate_metadata.extend(map(str, raw_scope["metadata_fields"]))
            scope_check = {
                "scope_ref": raw_scope.get("scope_ref"),
                "status": raw_scope.get("status"),
            }

        def expand_condition_checks(values: Any) -> Any:
            if not isinstance(values, list):
                return values
            output = []
            for value in values:
                if not isinstance(value, dict):
                    output.append(value)
                    continue
                expanded_check = {
                    "condition_ref": value.get("condition_ref"),
                    "status": value.get("status"),
                }
                condition_ids, condition_lines = expand_refs(value.get("evidence_refs"))
                if isinstance(condition_ids, list):
                    gate_ids.extend(condition_ids)
                if isinstance(condition_lines, list):
                    gate_lines.extend(condition_lines)
                if isinstance(value.get("metadata_fields"), list):
                    gate_metadata.extend(map(str, value["metadata_fields"]))
                output.append(expanded_check)
            return output

        condition_checks = expand_condition_checks(model_result.get("condition_checks"))
        review_condition_checks = expand_condition_checks(
            model_result.get("review_condition_checks")
        )

        checks = []
        for check in model_result.get("requirement_checks") or []:
            if not isinstance(check, dict):
                checks.append(check)
                continue
            check_ids, check_lines = expand_refs(check.get("evidence_refs"))
            checks.append({
                **({"obligation_ref": check["obligation_ref"]} if "obligation_ref" in check else {}),
                "requirement": check.get("requirement"),
                "status": check.get("status"),
                "finding_basis": check.get("finding_basis"),
                "evidence_ids": check_ids,
                "evidence_line_refs": check_lines,
                "reason": check.get("reason"),
            })

        scope_status = scope_check.get("status") if isinstance(scope_check, dict) else None
        condition_statuses = [
            check.get("status") for check in condition_checks
            if isinstance(check, dict)
        ] if isinstance(condition_checks, list) else []
        review_statuses = [
            check.get("status") for check in review_condition_checks
            if isinstance(check, dict)
        ] if isinstance(review_condition_checks, list) else []
        if scope_status == "NOT_MATCHED" or "NOT_SATISFIED" in condition_statuses:
            applicability = "NOT_APPLICABLE"
        elif (
            scope_status == "UNDETERMINED"
            or "UNDETERMINED" in condition_statuses
            or any(status in {"TRIGGERED", "UNDETERMINED"} for status in review_statuses)
        ):
            applicability = "UNDETERMINED"
        elif scope_status == "MATCHED" and all(
            status == "SATISFIED" for status in condition_statuses
        ) and all(status == "NOT_TRIGGERED" for status in review_statuses):
            applicability = "APPLICABLE"
        else:
            # Preserve malformed legacy output so validation rejects it rather
            # than silently inventing a gate result.
            applicability = model_result.get("applicability")

        old_app_ids, old_app_lines = expand_refs(
            model_result.get("applicability_evidence_refs")
        )
        if isinstance(old_app_ids, list):
            gate_ids.extend(old_app_ids)
        if isinstance(old_app_lines, list):
            gate_lines.extend(old_app_lines)
        old_metadata = model_result.get("applicability_metadata_fields")
        if isinstance(old_metadata, list):
            gate_metadata.extend(map(str, old_metadata))
        gate_ids = list(dict.fromkeys(gate_ids))
        gate_lines = list(dict.fromkeys(gate_lines))
        gate_metadata = list(dict.fromkeys(gate_metadata))

        if applicability == "NOT_APPLICABLE":
            applicability_basis = "NOT_APPLICABLE"
            verdict = "NOT_APPLICABLE"
            checks = []
            app_ids, app_lines, metadata_fields = [], [], []
        elif applicability == "UNDETERMINED":
            applicability_basis = "UNDETERMINED"
            verdict = "UNDETERMINED"
            checks = []
            app_ids, app_lines, metadata_fields = [], [], gate_metadata
        else:
            app_ids, app_lines, metadata_fields = gate_ids, gate_lines, gate_metadata
            if app_ids or app_lines:
                applicability_basis = "ADVERTISEMENT_EVIDENCE"
            elif metadata_fields:
                applicability_basis = "CONFIRMED_METADATA"
            else:
                applicability_basis = model_result.get("applicability_basis")
            verdict = model_result.get("verdict")

        old_evidence_ids, old_evidence_lines = expand_refs(model_result.get("evidence_refs"))
        evidence_ids = list(dict.fromkeys([
            *(old_evidence_ids if isinstance(old_evidence_ids, list) else []),
            *(str(value) for check in checks if isinstance(check, dict)
              for value in (check.get("evidence_ids") or [])),
        ]))
        evidence_lines = list(dict.fromkeys([
            *(old_evidence_lines if isinstance(old_evidence_lines, list) else []),
            *(str(value) for check in checks if isinstance(check, dict)
              for value in (check.get("evidence_line_refs") or [])),
        ]))
        expanded.append({
            "item_id": item_id,
            "scope_check": scope_check,
            "condition_checks": condition_checks,
            "review_condition_checks": review_condition_checks,
            "applicability": applicability,
            "applicability_basis": applicability_basis,
            "applicability_evidence_ids": app_ids,
            "applicability_evidence_line_refs": app_lines,
            "applicability_metadata_fields": metadata_fields,
            "verdict": verdict,
            "evidence_ids": evidence_ids,
            "evidence_line_refs": evidence_lines,
            "requirement_checks": checks,
            "reason": model_result.get("reason"),
            "confidence": model_result.get("confidence"),
            "needs_researcher_review": verdict in {"VIOLATION", "UNDETERMINED"},
        })
    return {"ad_id": row["ad_id"], "results": expanded}


def validate_condition_contract_result(
    *,
    item_id: str,
    rule: dict[str, Any],
    result: dict[str, Any],
    allowed_ids: set[str],
    allowed_refs: set[str],
    routing: dict[str, Any],
) -> list[str]:
    """Reject a judgment which skipped source scope or an explicit condition."""
    contract = rule.get("condition_contract")
    if not isinstance(contract, dict):
        return []  # Backward compatibility for frozen requests made before v1.
    errors: list[str] = []
    scope = result.get("scope_check")
    if not isinstance(scope, dict):
        return [f"{item_id}: source scope 확인 누락"]
    if scope.get("scope_ref") != contract.get("scope_ref"):
        errors.append(f"{item_id}: scope_ref 불일치")
    scope_status = scope.get("status")
    if scope_status not in {"MATCHED", "NOT_MATCHED", "UNDETERMINED"}:
        errors.append(f"{item_id}: scope status enum")

    expected_conditions = [
        str(value.get("condition_id"))
        for value in (contract.get("applicability_conditions") or [])
        if isinstance(value, dict)
    ]
    checks = result.get("condition_checks")
    if not isinstance(checks, list):
        errors.append(f"{item_id}: condition_checks 배열 아님")
        checks = []
    actual_conditions = [
        str(value.get("condition_ref")) if isinstance(value, dict) else ""
        for value in checks
    ]
    if actual_conditions != expected_conditions:
        errors.append(
            f"{item_id}: condition_checks 누락/순서 불일치 "
            f"expected={expected_conditions} actual={actual_conditions}"
        )
    condition_statuses = []
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            errors.append(f"{item_id}: condition_checks[{index}] 객체 아님")
            continue
        status = check.get("status")
        condition_statuses.append(status)
        if status not in {"SATISFIED", "NOT_SATISFIED", "UNDETERMINED"}:
            errors.append(f"{item_id}: condition_checks[{index}] status enum")

    expected_review = [
        str(value.get("condition_id"))
        for value in (contract.get("review_conditions") or [])
        if isinstance(value, dict)
    ]
    review_checks = result.get("review_condition_checks")
    if not isinstance(review_checks, list):
        errors.append(f"{item_id}: review_condition_checks 배열 아님")
        review_checks = []
    actual_review = [
        str(value.get("condition_ref")) if isinstance(value, dict) else ""
        for value in review_checks
    ]
    if actual_review != expected_review:
        errors.append(
            f"{item_id}: review_condition_checks 누락/순서 불일치 "
            f"expected={expected_review} actual={actual_review}"
        )
    review_statuses = []
    for index, check in enumerate(review_checks):
        if not isinstance(check, dict):
            errors.append(f"{item_id}: review_condition_checks[{index}] 객체 아님")
            continue
        status = check.get("status")
        review_statuses.append(status)
        if status not in {"TRIGGERED", "NOT_TRIGGERED", "UNDETERMINED"}:
            errors.append(f"{item_id}: review_condition_checks[{index}] status enum")

    applicability = result.get("applicability")
    obligations = contract.get("obligation_checks")
    if applicability == "APPLICABLE" and isinstance(obligations, list):
        expected_obligations = [value["obligation_id"] for value in obligations]
        requirement_checks = result.get("requirement_checks")
        actual_obligations = [value.get("obligation_ref") if isinstance(value, dict) else None
            for value in requirement_checks] if isinstance(requirement_checks, list) else []
        if actual_obligations != expected_obligations:
            errors.append(f"{item_id}: obligation_checks 누락/중복/순서 불일치 expected={expected_obligations} actual={actual_obligations}")
    if applicability == "APPLICABLE" and (
        scope_status != "MATCHED"
        or any(status != "SATISFIED" for status in condition_statuses)
        or any(status == "TRIGGERED" for status in review_statuses)
    ):
        errors.append(f"{item_id}: 미확정/불충족 조건에서 APPLICABLE 금지")
    if applicability == "NOT_APPLICABLE" and not (
        scope_status == "NOT_MATCHED"
        or "NOT_SATISFIED" in condition_statuses
    ):
        errors.append(f"{item_id}: 불충족 조건 없는 NOT_APPLICABLE 금지")
    if "TRIGGERED" in review_statuses and result.get("verdict") != "UNDETERMINED":
        errors.append(f"{item_id}: 사람 확인 조건에서 확정 verdict 금지")
    for gate in [scope, *checks, *review_checks]:
        if not isinstance(gate, dict):
            continue
        ids, refs = gate.get("evidence_ids") or [], gate.get("evidence_line_refs") or []
        if not isinstance(ids, list) or set(map(str, ids)) - allowed_ids:
            errors.append(f"{item_id}: 조건 게이트 evidence_scope 밖 evidence_id")
        if not isinstance(refs, list) or set(map(str, refs)) - allowed_refs:
            errors.append(f"{item_id}: 조건 게이트 evidence_scope 밖 line_ref")
    return errors


def validate(request_row: dict[str, Any], parsed: dict[str, Any], *, check_reading: bool = True) -> list[str]:
    payload = json.loads(request_row["messages"][1]["content"])
    expected = request_row["requested_item_ids"]
    results = parsed.get("results")
    errors = []
    if parsed.get("ad_id") != request_row["ad_id"]:
        errors.append("ad_id 불일치")
    if not isinstance(results, list):
        return errors + ["results가 배열이 아님"]
    actual = [row.get("item_id") for row in results if isinstance(row, dict)]
    if len(actual) != len(results):
        errors.append("results에 객체가 아닌 원소가 있음")
    if len(actual) != len(expected):
        errors.append(f"result 개수 불일치 expected={len(expected)} actual={len(actual)}")
    if len(actual) != len(set(actual)):
        errors.append(f"item_id 중복 actual={actual}")
    if actual != expected:
        errors.append(f"item_id 순서/값 불일치 expected={expected} actual={actual}")
    allowed_ids = {doc["evidence_id"] for doc in payload["documents"]}
    allowed_refs = {ref for doc in payload["documents"] for ref in doc["line_refs"]}
    rules_by_id = {rule["item_id"]: rule for rule in payload.get("rules", [])}
    evidence_scope = payload.get("evidence_scope") or {}
    deterministic_facts = payload.get("deterministic_facts") or {}
    document_by_id = {
        str(document["evidence_id"]): document for document in payload["documents"]
    }
    for result_index, row in enumerate(results):
        if not isinstance(row, dict):
            errors.append(f"results[{result_index}]가 객체가 아님: {type(row).__name__}")
            continue
        item_id = row.get("item_id")
        errors.extend(temporal_claim_errors(payload, row))
        errors.extend(text_facet_claim_errors(payload, row))
        errors.extend(source_claim_errors(payload, row))
        if check_reading:
            errors.extend(f"{item_id}: reading_quality:{issue['code']}:{issue['location']}"
                          for issue in reading_issues(payload, row))
        applicability = row.get("applicability")
        applicability_basis = row.get("applicability_basis")
        verdict = row.get("verdict")
        assessment = (payload.get("external_input_assessment") or {}).get(item_id) or {}
        if verdict == "COMPLIANT" and assessment.get("input_mode") == "PARTIAL":
            errors.append(f"{item_id}: 외부입력 미확인 구성요소가 남은 PARTIAL 규칙의 전체 COMPLIANT 금지")
        if applicability not in {"APPLICABLE", "NOT_APPLICABLE", "UNDETERMINED"}:
            errors.append(f"{item_id}: applicability enum")
        if verdict not in {"COMPLIANT", "VIOLATION", "NOT_APPLICABLE", "UNDETERMINED"}:
            errors.append(f"{item_id}: verdict enum")
        if applicability == "NOT_APPLICABLE" and verdict != "NOT_APPLICABLE":
            errors.append(f"{item_id}: NOT_APPLICABLE 정합성")
        if applicability == "APPLICABLE" and verdict == "NOT_APPLICABLE":
            errors.append(f"{item_id}: APPLICABLE 정합성")
        if applicability == "UNDETERMINED" and verdict != "UNDETERMINED":
            errors.append(f"{item_id}: applicability UNDETERMINED 정합성")
        if applicability_basis not in {
            "ADVERTISEMENT_EVIDENCE", "CONFIRMED_METADATA", "NOT_APPLICABLE", "UNDETERMINED",
        }:
            errors.append(f"{item_id}: applicability_basis enum")
        app_ids = row.get("applicability_evidence_ids")
        app_refs = row.get("applicability_evidence_line_refs")
        metadata_fields = row.get("applicability_metadata_fields")
        if not isinstance(app_ids, list) or set(map(str, app_ids)) - allowed_ids:
            errors.append(f"{item_id}: 제공 밖 applicability evidence_id")
        if not isinstance(app_refs, list) or set(map(str, app_refs)) - allowed_refs:
            errors.append(f"{item_id}: 제공 밖 applicability line_ref")
        if not isinstance(metadata_fields, list) or not all(
            isinstance(value, str) for value in metadata_fields
        ):
            errors.append(f"{item_id}: applicability_metadata_fields 배열 아님")
            metadata_fields = []
        if applicability == "APPLICABLE" and applicability_basis not in {
            "ADVERTISEMENT_EVIDENCE", "CONFIRMED_METADATA",
        }:
            errors.append(f"{item_id}: APPLICABLE 근거 없음")
        if applicability == "NOT_APPLICABLE" and applicability_basis != "NOT_APPLICABLE":
            errors.append(f"{item_id}: NOT_APPLICABLE basis 불일치")
        if applicability == "UNDETERMINED" and applicability_basis != "UNDETERMINED":
            errors.append(f"{item_id}: UNDETERMINED basis 불일치")
        if applicability_basis == "ADVERTISEMENT_EVIDENCE" and not (app_ids or app_refs):
            errors.append(f"{item_id}: 광고 근거 없는 ADVERTISEMENT_EVIDENCE")
        rule = rules_by_id.get(item_id) or {}
        scoped = evidence_scope.get(item_id) if isinstance(evidence_scope, dict) else None
        gate_ids = set(map(str, scoped.get("evidence_ids") or [])) if isinstance(scoped, dict) else allowed_ids
        gate_refs = {str(ref) for evidence_id in gate_ids
                     for ref in document_by_id.get(evidence_id, {}).get("line_refs") or []}
        if isinstance(app_ids, list) and set(map(str, app_ids)) - gate_ids:
            errors.append(f"{item_id}: 적용성 evidence_scope 밖 evidence_id")
        if isinstance(app_refs, list) and set(map(str, app_refs)) - gate_refs:
            errors.append(f"{item_id}: 적용성 evidence_scope 밖 line_ref")
        errors.extend(validate_condition_contract_result(
            item_id=str(item_id or ""),
            rule=rule,
            result=row,
            allowed_ids=gate_ids,
            allowed_refs=gate_refs,
            routing=payload.get("routing") or {},
        ))
        item_scope = (
            evidence_scope.get(item_id)
            if isinstance(evidence_scope, dict)
            else None
        )
        routing = payload.get("routing") or {}
        confirmed_statuses = {"confirmed", "verified", "provided"}
        if applicability_basis == "CONFIRMED_METADATA":
            if not metadata_fields:
                errors.append(f"{item_id}: 확인 메타데이터 필드 없음")
            for field in metadata_fields:
                value = routing.get(field)
                if field == "product_group":
                    if not isinstance(value, dict) or value.get("routing_provisional", True):
                        errors.append(f"{item_id}: 미확정 product_group 메타데이터")
                elif not isinstance(value, dict) or value.get("status") not in confirmed_statuses:
                    errors.append(f"{item_id}: 미확정 {field} 메타데이터")
        if rule.get("source_sheet") == "신규규칙후보" and applicability == "APPLICABLE":
            template = routing.get("template_id") or {}
            if (
                applicability_basis != "CONFIRMED_METADATA"
                or "template_id" not in metadata_fields
                or not isinstance(template, dict)
                or template.get("status") not in confirmed_statuses
                or not template.get("value")
                or template.get("value") != rule.get("product_subtype")
            ):
                errors.append(f"{item_id}: 확정 템플릿 없는 T 규칙 APPLICABLE")
        if row.get("confidence") not in {"LOW", "MEDIUM", "HIGH"}:
            errors.append(f"{item_id}: confidence enum")
        if not isinstance(row.get("needs_researcher_review"), bool):
            errors.append(f"{item_id}: needs_researcher_review boolean 아님")
        evidence_ids = row.get("evidence_ids")
        evidence_refs = row.get("evidence_line_refs")
        evidence_id_values = {str(value) for value in evidence_ids} if isinstance(evidence_ids, list) else set()
        invalid_evidence_ids = {
            value for value in evidence_id_values
            if value not in allowed_ids
            and value not in allowed_refs
            and not ("/L" in value and value.rsplit("/L", 1)[0] in allowed_ids)
        }
        if not isinstance(evidence_ids, list) or invalid_evidence_ids:
            errors.append(f"{item_id}: 제공 밖 evidence_id")
        if not isinstance(evidence_refs, list) or set(evidence_refs) - allowed_refs:
            errors.append(f"{item_id}: 제공 밖 line_ref")
        preliminary_checks = row.get("requirement_checks")
        absence_only_violation = (
            verdict == "VIOLATION"
            and isinstance(item_scope, dict)
            and (not check_reading or item_scope.get("complete_ad_scan") is True)
            and isinstance(preliminary_checks, list)
            and any(
                isinstance(check, dict)
                and check.get("status") == "MISSING"
                and check.get("finding_basis") == "ABSENCE"
                for check in preliminary_checks
            )
            and not any(
                isinstance(check, dict) and check.get("status") == "VIOLATED"
                for check in preliminary_checks
            )
        )
        if verdict == "VIOLATION" and not evidence_refs and not absence_only_violation:
            errors.append(f"{item_id}: 위반에는 원본 줄 근거가 필요")
        if isinstance(item_scope, dict):
            scoped_ids = set(map(str, item_scope.get("evidence_ids") or []))
            scoped_refs = {
                str(ref)
                for evidence_id in scoped_ids
                for ref in document_by_id.get(evidence_id, {}).get("line_refs") or []
            }
            if evidence_id_values - scoped_ids:
                errors.append(f"{item_id}: 규칙별 evidence_scope 밖 evidence_id")
            if isinstance(evidence_refs, list) and set(map(str, evidence_refs)) - scoped_refs:
                errors.append(f"{item_id}: 규칙별 evidence_scope 밖 line_ref")
        if not str(row.get("reason") or "").strip():
            errors.append(f"{item_id}: reason 없음")
        if verdict == "VIOLATION":
            errors.extend(grounding_errors(
                item_id=str(item_id or ""),
                location="판정 근거",
                reason=str(row.get("reason") or ""),
                line_refs=evidence_refs if isinstance(evidence_refs, list) else [],
                documents=payload["documents"],
            ))
        reason_text = " ".join([
            str(row.get("reason") or ""),
            *(str(check.get("reason") or "") for check in (row.get("requirement_checks") or [])
              if isinstance(check, dict)),
        ]).lower()
        claims_incomplete_scan = any(token in reason_text for token in (
            "scan is incomplete",
            "scan or required layout/external input is incomplete",
            "incomplete scan",
            "전체 스캔 미완료",
            "전체 스캔이 완료되지",
        ))
        if (
            verdict == "UNDETERMINED"
            and isinstance(item_scope, dict)
            and item_scope.get("complete_ad_scan") is True
            and str(rule.get("required_medium") or "").strip() in {"텍스트", "TEXT"}
            and assessment.get("input_mode") not in {"PARTIAL", "EXTERNAL"}
            and claims_incomplete_scan
        ):
            errors.append(f"{item_id}: 완료된 텍스트 전체 스캔을 미완료로 판단함")
        checks = row.get("requirement_checks")
        if not isinstance(checks, list) or not checks:
            if applicability in {"NOT_APPLICABLE", "UNDETERMINED"} and verdict == applicability:
                # The source scope/condition gate stopped this rule before O1.
                # Requiring a fabricated obligation check here would contradict
                # the condition-before-obligation contract.
                continue
            errors.append(f"{item_id}: requirement_checks 없음")
            continue
        check_statuses = []
        for check_index, check in enumerate(checks):
            if not isinstance(check, dict):
                errors.append(f"{item_id}: requirement_checks[{check_index}] 객체 아님")
                continue
            if not str(check.get("requirement") or "").strip():
                errors.append(f"{item_id}: requirement_checks[{check_index}] requirement 없음")
            check_status = check.get("status")
            finding_basis = check.get("finding_basis")
            if check_status not in {
                "SATISFIED", "MISSING", "VIOLATED", "NOT_APPLICABLE", "UNDETERMINED",
            }:
                errors.append(f"{item_id}: requirement_checks[{check_index}] status enum")
            else:
                check_statuses.append(check_status)
            if finding_basis not in {"OBSERVED", "ABSENCE", "UNKNOWN"}:
                errors.append(f"{item_id}: requirement_checks[{check_index}] finding_basis enum")
            if check_status == "MISSING" and finding_basis != "ABSENCE":
                errors.append(f"{item_id}: MISSING finding_basis는 ABSENCE여야 함")
            if check_status == "VIOLATED" and finding_basis != "OBSERVED":
                errors.append(f"{item_id}: VIOLATED finding_basis는 OBSERVED여야 함")
            if check_status == "UNDETERMINED" and finding_basis != "UNKNOWN":
                errors.append(f"{item_id}: UNDETERMINED finding_basis는 UNKNOWN이어야 함")
            if check_status == "SATISFIED" and finding_basis == "UNKNOWN":
                errors.append(f"{item_id}: SATISFIED finding_basis는 UNKNOWN일 수 없음")
            if (
                check_status == "SATISFIED"
                and finding_basis == "ABSENCE"
                and request_row.get("category") != "PROHIBIT"
            ):
                errors.append(f"{item_id}: 금지 규칙 외 SATISFIED+ABSENCE 금지")
            check_ids = check.get("evidence_ids")
            check_refs = check.get("evidence_line_refs")
            if not isinstance(check_ids, list) or set(map(str, check_ids)) - allowed_ids:
                errors.append(f"{item_id}: requirement_checks[{check_index}] 제공 밖 evidence_id")
            if not isinstance(check_refs, list) or set(map(str, check_refs)) - allowed_refs:
                errors.append(f"{item_id}: requirement_checks[{check_index}] 제공 밖 line_ref")
            if check_status == "VIOLATED" and not (check_ids or check_refs):
                errors.append(f"{item_id}: 관찰 근거 없는 VIOLATED")
            if check_status == "VIOLATED" and not check_refs:
                errors.append(f"{item_id}: VIOLATED에는 원본 줄 근거가 필요")
            if finding_basis == "OBSERVED" and not (check_ids or check_refs):
                errors.append(
                    f"{item_id}: OBSERVED에는 직접 광고 근거가 필요"
                )
            if (finding_basis == "OBSERVED" and check_status in {"SATISFIED", "VIOLATED"}
                    and not check_refs and isinstance(check_ids, list)
                    and any(document_by_id.get(str(ref), {}).get("line_texts")
                            and document_by_id[str(ref)].get("span_status") != "region_level_selected_text"
                            for ref in check_ids)):
                errors.append(f"{item_id}: OBSERVED 확정에는 제공된 원본 줄을 직접 인용해야 함")
            if (
                check_reading and finding_basis == "ABSENCE"
                and isinstance(item_scope, dict)
                and item_scope.get("complete_ad_scan") is not True
            ):
                errors.append(f"{item_id}: 축소 근거 창으로 ABSENCE 확정")
            if not str(check.get("reason") or "").strip():
                errors.append(f"{item_id}: requirement_checks[{check_index}] reason 없음")
            if check_status in {"VIOLATED", "SATISFIED"} and finding_basis == "OBSERVED":
                errors.extend(grounding_errors(
                    item_id=str(item_id or ""),
                    location=f"requirement_checks[{check_index}]",
                    reason=str(check.get("reason") or ""),
                    line_refs=check_refs if isinstance(check_refs, list) else [],
                    documents=payload["documents"],
                ))
        if verdict == "COMPLIANT" and any(
            status in {"MISSING", "VIOLATED", "NOT_APPLICABLE", "UNDETERMINED"}
            for status in check_statuses
        ):
            errors.append(f"{item_id}: 구성요소 미충족/불명확인데 COMPLIANT")
        if verdict == "VIOLATION" and not any(
            status in {"MISSING", "VIOLATED"} for status in check_statuses
        ):
            errors.append(f"{item_id}: 위반 구성요소 없이 VIOLATION")
        obligation_failure = "VIOLATED" in check_statuses or (
            request_row.get("category") == "PRESENCE"
            and
            isinstance(item_scope, dict)
            and item_scope.get("complete_ad_scan") is True
            and "MISSING" in check_statuses
        )
        if (
            applicability == "APPLICABLE"
            and obligation_failure
            and verdict != "VIOLATION"
        ):
            errors.append(
                f"{item_id}: 필수요건 누락·위반과 전체 verdict 불일치"
            )
        if (
            check_reading and isinstance(item_scope, dict)
            and item_scope.get("complete_ad_scan") is not True
            and "MISSING" in check_statuses
        ):
            errors.append(f"{item_id}: 축소 근거 창으로 광고 전체 부재 확정")
        rule_text = " ".join(
            str(rule.get(name) or "")
            for name in ("title", "question", "criterion")
        )
        if (
            deterministic_facts.get("review_number_present") is True
            and ("심의필" in rule_text or "심사필" in rule_text)
            and "MISSING" in check_statuses
        ):
            errors.append(f"{item_id}: 심의필 번호 관측값과 MISSING 충돌")
        placeholder_only_violation = (
            verdict == "VIOLATION"
            and any(status in {"MISSING", "VIOLATED"} for status in check_statuses)
            and all(
                status not in {"MISSING", "VIOLATED"}
                or any(token in str(check.get("reason") or "") for token in (
                    "자리표시", "00.00", "0000", "실제 날짜가 아닌", "형식이 아닌",
                ))
                for check, status in zip(checks, check_statuses)
            )
        )
        media = (payload.get("routing") or {}).get("media_type") or {}
        media_value = media.get("value") if isinstance(media, dict) else None
        media_status = str(media.get("status") or "").lower() if isinstance(media, dict) else ""
        electronic_delivery = {"PUSH", "SMS", "ALIMTALK", "EMAIL", "MMS", "LMS"}
        electronic_rule = any(token in rule_text for token in (
            "전자적 전송매체", "영리목적 광고성 정보", "수신거부", "전송자 명칭",
        ))
        if (
            electronic_rule
            and media_status in {"provided", "confirmed", "verified"}
            and isinstance(media_value, str)
            and media_value not in electronic_delivery
            and applicability != "NOT_APPLICABLE"
        ):
            errors.append(
                f"{item_id}: 확정 매체 {media_value}에 전송형 광고 규칙을 적용함"
            )
        if (
            placeholder_only_violation
            and deterministic_facts.get("review_number_placeholder_present") is True
            and ("심의필" in rule_text or "심사필" in rule_text or "심의번호" in rule_text)
        ):
            errors.append(f"{item_id}: 인정된 심의번호 자리표시자만으로 형식 위반 판정")
        if (
            placeholder_only_violation
            and deterministic_facts.get("review_validity_placeholder_range_present") is True
            and "유효기간" in rule_text
        ):
            errors.append(f"{item_id}: 인정된 유효기간 자리표시자만으로 형식 위반 판정")
        if (
            int(deterministic_facts.get("bullet_marker_count") or 0) > 0
            and ("구분기호" in rule_text or "말머리기호" in rule_text)
            and "MISSING" in check_statuses
        ):
            errors.append(f"{item_id}: 불릿 관측값과 MISSING 충돌")
    return errors


def call_once(row: dict[str, Any], host: str | None, key: Path | None, model: str, max_tokens: int) -> dict[str, Any]:
    model_messages, aliases = _compact_model_request(row)
    payload = {
        "model": model,
        "messages": model_messages,
        "temperature": 0,
        "max_tokens": max_tokens,
        "response_format": response_format(json.loads(model_messages[1]["content"])),
    }
    from dgx_openai_client import post_json

    started = time.perf_counter()
    response = post_json(payload, host=host, key=key, timeout=900)
    seconds = time.perf_counter() - started
    choice = response["choices"][0]
    model_parsed = parse_content(choice["message"]["content"])
    parsed = _expand_model_response(row, model_parsed, aliases)
    contract_normalizations = normalize_contract_sentinels(parsed, row)
    # A valid model answer can still rely on unreadable evidence. Route that
    # semantic uncertainty to review once, not into JSON-format retry loops.
    structural_errors = validate(row, parsed, check_reading=False)
    reading_quality_guards = [] if structural_errors else apply_reading_guard(
        json.loads(row["messages"][1]["content"]), parsed)
    return {
        "request_id": row["request_id"],
        "ad_id": row["ad_id"],
        "category": row["category"],
        "seconds": round(seconds, 3),
        "model_returned": response.get("model"),
        "finish_reason": choice.get("finish_reason"),
        "usage": response.get("usage"),
        "model_parsed": model_parsed,
        "response_format": payload["response_format"]["type"],
        "parsed": parsed,
        "contract_projection": "gate-derived-v1",
        "contract_normalizations": contract_normalizations,
        "reading_quality_guards": reading_quality_guards,
        "validation_errors": validate(row, parsed),
    }


def normalize_contract_sentinels(
    parsed: Any, request_row: dict[str, Any] | None = None
) -> list[dict[str, str]]:
    """Canonicalize non-semantic basis sentinels while retaining an audit record."""
    if not isinstance(parsed, dict) or not isinstance(parsed.get("results"), list):
        return []
    normalizations: list[dict[str, str]] = []
    rules_by_id: dict[str, Any] = {}
    if request_row is not None:
        try:
            payload = json.loads(request_row["messages"][1]["content"])
            rules_by_id = {
                str(rule.get("item_id")): rule
                for rule in (payload.get("rules") or [])
                if isinstance(rule, dict) and rule.get("item_id")
            }
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            rules_by_id = {}
    for result in parsed["results"]:
        if not isinstance(result, dict):
            continue
        # Condition checks are a keyed set semantically.  Gemma often returns
        # every required condition exactly once but changes only their array
        # order.  Reorder that losslessly from the frozen source contract and
        # keep malformed, missing or duplicate sets untouched for validation.
        rule = rules_by_id.get(str(result.get("item_id") or "")) or {}
        contract = rule.get("condition_contract") or {}
        for field, contract_field, id_field, ref_field in (
            ("condition_checks", "applicability_conditions", "condition_id", "condition_ref"),
            ("review_condition_checks", "review_conditions", "condition_id", "condition_ref"),
            ("requirement_checks", "obligation_checks", "obligation_id", "obligation_ref"),
        ):
            checks_to_order = result.get(field)
            expected_refs = [
                str(value.get(id_field))
                for value in (contract.get(contract_field) or [])
                if isinstance(value, dict) and value.get(id_field)
            ]
            if not isinstance(checks_to_order, list) or not expected_refs:
                continue
            by_ref = {
                str(value.get(ref_field)): value
                for value in checks_to_order
                if isinstance(value, dict) and value.get(ref_field)
            }
            actual_refs = [
                str(value.get(ref_field))
                for value in checks_to_order
                if isinstance(value, dict) and value.get(ref_field)
            ]
            if (
                len(by_ref) == len(checks_to_order) == len(expected_refs)
                and set(by_ref) == set(expected_refs)
                and actual_refs != expected_refs
            ):
                result[field] = [by_ref[ref] for ref in expected_refs]
                normalizations.append({
                    "item_id": str(result.get("item_id") or ""),
                    "field": field,
                    "from": ",".join(actual_refs),
                    "to": ",".join(expected_refs),
                })
        # The model sometimes puts an observed line only on the individual
        # requirement check.  Copying that same canonical reference to the
        # result-level audit field is structural normalization, not a semantic
        # verdict change, and prevents a truthful bbox from being discarded.
        result_lines = result.get("evidence_line_refs")
        if isinstance(result_lines, list) and not result_lines:
            check_lines = list(dict.fromkeys(
                str(line_ref)
                for check in (result.get("requirement_checks") or [])
                if isinstance(check, dict)
                for line_ref in (check.get("evidence_line_refs") or [])
            ))
            if check_lines:
                result["evidence_line_refs"] = check_lines
                normalizations.append({
                    "item_id": str(result.get("item_id") or ""),
                    "field": "evidence_line_refs",
                    "from": "[]",
                    "to": "requirement_checks.evidence_line_refs",
                })
        # Passing gates followed by an unknown obligation is semantically
        # different from an unknown gate. Gemma occasionally preserves the
        # former verdict but omits its required audit row. Restore only that
        # structural row from the frozen rule obligation; do not change the
        # applicability or verdict.
        checks = result.get("requirement_checks")
        if (
            result.get("applicability") == "APPLICABLE"
            and result.get("verdict") == "UNDETERMINED"
            and isinstance(checks, list)
            and not checks
        ):
            obligation = (rule.get("condition_contract") or {}).get("obligation") or {}
            obligation_text = str(obligation.get("text") or rule.get("criterion") or rule.get("question") or "").strip()
            source_obligations = contract.get("obligation_checks") or ([{"text": obligation_text}] if obligation_text else [])
            if source_obligations:
                result["requirement_checks"] = [{
                    **({"obligation_ref": source_obligation["obligation_id"]} if "obligation_id" in source_obligation else {}),
                    "requirement": source_obligation["text"],
                    "status": "UNDETERMINED",
                    "finding_basis": "UNKNOWN",
                    "evidence_ids": [],
                    "evidence_line_refs": [],
                    "reason": str(result.get("reason") or "의무 충족 여부를 확인할 근거가 부족함"),
                } for source_obligation in source_obligations]
                normalizations.append({
                    "item_id": str(result.get("item_id") or ""),
                    "field": "requirement_checks",
                    "from": "[]",
                    "to": "source obligation as UNDETERMINED",
                })
        applicability = result.get("applicability")
        verdict = result.get("verdict")
        expected_basis = None
        if applicability == verdict == "NOT_APPLICABLE":
            expected_basis = "NOT_APPLICABLE"
        elif applicability == verdict == "UNDETERMINED":
            expected_basis = "UNDETERMINED"
        old_basis = result.get("applicability_basis")
        if expected_basis is None or old_basis == expected_basis:
            continue
        result["applicability_basis"] = expected_basis
        normalizations.append({
            "item_id": str(result.get("item_id") or ""),
            "field": "applicability_basis",
            "from": str(old_basis or ""),
            "to": expected_basis,
        })
    return normalizations


def contract_attempt_limit(row: dict[str, Any]) -> int:
    item_count = len(row.get("requested_item_ids") or [])
    if item_count > 6:
        return 1
    if item_count > 1:
        return 2
    return 3


def retry_contract_instruction(
    row: dict[str, Any], validation_errors: list[str]
) -> str:
    """Build a generic repair instruction from the frozen request contract."""
    requested_item_ids = list(row.get("requested_item_ids") or [])
    errors = "\n".join(f"- {error}" for error in validation_errors)
    repair_hints = []
    joined_errors = "\n".join(validation_errors)
    if "requirement_checks 없음" in joined_errors:
        repair_hints.append(
            "게이트가 모두 통과했지만 의무가 불명확하면 requirement_checks에 "
            "UNDETERMINED+UNKNOWN 1건을 반드시 넣어라."
        )
    if "위반에는 원본 줄 근거가 필요" in joined_errors:
        repair_hints.append(
            "관찰 위반(VIOLATED)은 직접 L 근거를 넣고, 완전 스캔에서의 미기재 "
            "위반(MISSING+ABSENCE)은 존재하지 않는 L 근거를 만들지 말라."
        )
    if "SATISFIED+ABSENCE" in joined_errors:
        repair_hints.append(
            "표시의무에서 내용이 없으면 범위 미적용은 SCOPE=NOT_MATCHED, "
            "범위 적용 후 누락은 MISSING+ABSENCE/VIOLATION으로 구분하라."
        )
    if "완료된 텍스트 전체 스캔을 미완료로 판단함" in joined_errors:
        repair_hints.append(
            "complete_ad_scan=true인 텍스트 규칙이다. 스캔 미완료를 이유로 판단불가 처리하지 "
            "말고, 선행 상황이 없으면 SCOPE=NOT_MATCHED, 적용 후 필수 문구가 없으면 "
            "MISSING+ABSENCE/VIOLATION으로 판정하라."
        )
    if "인용한 근거 줄에 없는 수치" in joined_errors:
        repair_hints.append(
            "이유문에 쓴 금리·비율 수치는 네가 인용한 L 근거 안에 실제로 있어야 한다. "
            "그 수치가 있는 L 근거를 함께 인용하거나, 광고에서 확인되지 않는 수치라면 "
            "그 수치를 근거로 쓰지 말고 UNDETERMINED로 판정하라."
        )
    if "서로 다른 광고 파일의 수치" in joined_errors:
        repair_hints.append(
            "서로 다른 파일의 수치는 같은 표·같은 상품의 값이라는 보장이 없다. "
            "산술 비교는 한 파일 안에서 확인되는 수치로만 하고, 파일을 넘겨야 판단되면 "
            "UNDETERMINED로 판정하라."
        )
    hints = ("\n수정 지침:\n- " + "\n- ".join(repair_hints)) if repair_hints else ""
    return (
        "이전 응답의 계약 오류만 고쳐 전체 JSON을 다시 출력하라. "
        "입력의 rule_ref 순서와 E/L 참조를 그대로 사용하고 없는 참조를 만들지 말라. "
        f"원본 규칙={requested_item_ids}\n검증 오류:\n{errors}{hints}"
    )


def call_with_retry(row: dict[str, Any], host: str | None, key: Path | None, model: str, max_tokens: int) -> dict[str, Any]:
    attempts = []
    call_history = []
    current = row
    # Large invalid responses are more reliably and cheaply recovered by the
    # existing recursive splitter than by asking the model to repeat the same
    # oversized JSON object a second time.
    max_attempts = contract_attempt_limit(row)
    for attempt in range(1, max_attempts + 1):
        attempt_started = time.perf_counter()
        try:
            result = call_once(current, host, key, model, max_tokens)
        except Exception as exc:
            result = {
                "request_id": row["request_id"],
                "ad_id": row["ad_id"],
                "category": row["category"],
                "fatal_error": str(exc),
                "validation_errors": [f"호출/JSON 파싱 실패: {exc}"],
            }
        attempts.append(result["validation_errors"])
        event = {
            "request_id": row["request_id"], "attempt": attempt,
            "seconds": round(time.perf_counter() - attempt_started, 3),
            "validation_errors": copy.deepcopy(result["validation_errors"]),
            "finish_reason": result.get("finish_reason"), "usage": result.get("usage"),
            "response_format": result.get("response_format"),
        }
        # Do not discard the failed parent's cause/usage when splitting later.
        # These local audit records are never added to future model prompts.
        if result["validation_errors"]:
            for field in ("fatal_error", "model_parsed"):
                if field in result:
                    event[field] = copy.deepcopy(result[field])
        call_history.append(event)
        result["call_history"] = call_history
        if not result["validation_errors"]:
            result["contract_attempts"] = attempt
            result["attempted_validation_errors"] = attempts
            return result
        if attempt < max_attempts:
            current = copy.deepcopy(row)
            if isinstance(result.get("model_parsed"), dict):
                current["messages"].append({
                    "role": "assistant",
                    "content": json.dumps(result["model_parsed"], ensure_ascii=False),
                })
            current["messages"].append({
                "role": "user",
                "content": retry_contract_instruction(row, result["validation_errors"]),
            })
    result["contract_attempts"] = max_attempts
    result["attempted_validation_errors"] = attempts
    return result


def split_request_row(row: dict[str, Any], *, cpu_items: set[str] | None = None) -> list[dict[str, Any]]:
    """Split a failed request and isolate every child to its rule evidence."""
    expected = list(row.get("requested_item_ids") or [])
    if len(expected) < 2:
        return [row]
    payload = json.loads(row["messages"][1]["content"])
    rules = payload.get("rules")
    if not isinstance(rules, list) or [rule.get("item_id") for rule in rules] != expected:
        raise ValueError("요청 rules와 requested_item_ids 순서가 다름")
    midpoint = len(rules) // 2
    groups = (("a", rules[:midpoint]), ("b", rules[midpoint:])) if cpu_items is None else (
        ("cpu", [rule for rule in rules if rule['item_id'] in cpu_items]),
        ("model", [rule for rule in rules if rule['item_id'] not in cpu_items]))
    children = []
    for label, child_rules in groups:
        child = copy.deepcopy(row)
        child_id = f"{row['request_id']}~split-{label}"
        child_payload = copy.deepcopy(payload)
        child_payload["request_id"] = child_id
        child_payload["rules"] = child_rules
        child_item_ids = [rule["item_id"] for rule in child_rules]
        evidence_scope = payload.get("evidence_scope")
        if isinstance(evidence_scope, dict):
            child_scope = {
                item_id: copy.deepcopy(evidence_scope[item_id])
                for item_id in child_item_ids
                if item_id in evidence_scope
            }
            child_payload["evidence_scope"] = child_scope
            if len(child_scope) == len(child_item_ids):
                allowed_ids = {
                    str(evidence_id)
                    for scope in child_scope.values()
                    for evidence_id in (scope.get("evidence_ids") or [])
                }
                child_payload["documents"] = [
                    document
                    for document in (payload.get("documents") or [])
                    if str(document.get("evidence_id")) in allowed_ids
                ]
        child["request_id"] = child_id
        child["requested_item_ids"] = child_item_ids
        child["messages"][1]["content"] = json.dumps(child_payload, ensure_ascii=False)
        child["logical_request_id"] = row.get("logical_request_id", row["request_id"])
        children.append(child)
    return children


def call_with_retry_and_split(
    row: dict[str, Any],
    host: str | None,
    key: Path | None,
    model: str,
    max_tokens: int,
    *,
    depth: int = 0,
    max_split_depth: int = 8,
) -> list[dict[str, Any]]:
    """Retry contract failures and recursively isolate oversized bad batches."""
    payload = json.loads(row['messages'][1]['content'])
    computed = [calculate_loan_rates(payload, rule) for rule in payload.get('rules', [])]
    if computed and all(computed):
        parsed = {'ad_id': row['ad_id'], 'results': computed}
        errors = validate(row, parsed)
        if not errors:
            return [{'request_id': row['request_id'], 'ad_id': row['ad_id'],
                     'category': row['category'], 'parsed': parsed, 'validation_errors': [],
                     'decision_source': ARITHMETIC_METHOD, 'model_returned': None,
                     'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0},
                     'seconds': 0, 'call_history': [], 'attempts': 0,
                     'logical_request_id': row.get('logical_request_id', row['request_id']),
                     'split_depth': depth}]
    elif any(computed) and len(row.get('requested_item_ids', [])) > 1:
        # Separate CPU-certifiable items before sending any request to the GPU.
        return [response for child in split_request_row(row, cpu_items={r['item_id'] for r in computed if r})
                for response in call_with_retry_and_split(child, host, key, model, max_tokens,
                    depth=depth + 1, max_split_depth=max_split_depth)]
    result = call_with_retry(row, host, key, model, max_tokens)
    result["logical_request_id"] = row.get("logical_request_id", row["request_id"])
    result["split_depth"] = depth
    if not result["validation_errors"]:
        return [focus_unresolved_source_checks(row, result, host, key, model, max_tokens)]
    if len(row.get("requested_item_ids") or []) < 2 or depth >= max_split_depth:
        return [result]
    output: list[dict[str, Any]] = []
    for child in split_request_row(row):
        output.extend(call_with_retry_and_split(
            child, host, key, model, max_tokens,
            depth=depth + 1, max_split_depth=max_split_depth,
        ))
    if output:
        # Retain each discarded ancestor exactly once, not once per leaf.
        output[0]["call_history"] = result.get("call_history", []) + output[0].get("call_history", [])
    return output


def focus_unresolved_source_checks(
    row: dict[str, Any], result: dict[str, Any], host: str | None,
    key: Path | None, model: str, max_tokens: int,
) -> dict[str, Any]:
    """One isolated source check for a presence/arithmetic abstention.

    Never re-read parser labels, waive uncertainty, supply a target verdict or
    retry a reading guard. Valid neighboring judgments stay byte-for-byte equal.
    If the isolated answer is invalid or still unknown, the original survives.
    """
    if not row.get('requested_item_ids'):
        return result
    payload = json.loads(row['messages'][1]['content'])
    rules = {r['item_id']: r for r in payload.get('rules') or []}
    documents = {d['evidence_id']: d for d in payload.get('documents') or []}
    targets = []
    for judgment in (result.get('parsed') or {}).get('results') or []:
        item = judgment.get('item_id')
        contract = (rules.get(item) or {}).get('condition_contract') or {}
        arithmetic = bool(re.search(r'산술|산식|합산', ' '.join(
            str(check.get('text') or '') for check in contract.get('obligation_checks') or [])))
        assessment = (payload.get('external_input_assessment') or {}).get(item) or {}
        scoped = (payload.get('evidence_scope') or {}).get(item) or {}
        if ((row.get('category') == 'PRESENCE' or arithmetic)
                and judgment.get('verdict') == 'UNDETERMINED'
                and judgment.get('applicability') == 'APPLICABLE'
                and not judgment.get('reading_quality_review')
                and contract.get('applicability_mode') in {'UNCONDITIONAL', 'SOURCE_SCOPED'}
                and not contract.get('applicability_conditions') and not contract.get('review_conditions')
                and assessment.get('input_mode') not in {'PARTIAL', 'EXTERNAL'}
                and any(not needs_reading_review(documents[eid]) and documents[eid].get('line_texts')
                        for eid in scoped.get('evidence_ids') or [] if eid in documents)):
            targets.append(item)
    if not targets:
        return result
    focused = copy.deepcopy(result)
    focused['source_focus_attempts'] = []
    focused['source_focus_applied'] = []
    for item in targets:
        isolated = copy.deepcopy(row)
        while len(isolated['requested_item_ids']) > 1:
            isolated = next(child for child in split_request_row(isolated)
                            if item in child['requested_item_ids'])
        isolated_payload = json.loads(isolated['messages'][1]['content'])
        isolated_payload.pop('full_ad_text', None)
        for document in isolated_payload.get('documents') or []:
            document.pop('labels', None)
        isolated['messages'][1]['content'] = json.dumps(isolated_payload, ensure_ascii=False)
        isolated['messages'].append({'role': 'user', 'content': (
            '이 단일 항목의 허용 documents.lines를 줄마다 확인하십시오. 긍정 존재 판정은 '
            '읽을 수 있는 해당 문구와 그 줄 ID를 함께 찾아야 합니다. PARTIAL은 전체 부재 '
            '확정을 제한하지만 읽힌 문구의 존재 확인까지 금지하지 않습니다. 예시 답안의 '
            '첫 줄 ID를 복사하지 마십시오. 충족 여부는 원문과 규칙으로 판단하고 근거가 '
            '부족하면 판단불가를 유지하십시오. 완전히 읽힌 범위에서는 원문이 명시적으로 '
            '요구하는 필수 문구의 부재도 확인하십시오. 산술 요건이면 원문이 같은 조건으로 '
            '주장한 합·차를 직접 검산하고 수치와 설명을 제시하십시오. 별도 최종 결과값이 '
            '없는 조건부 가산에 새 합계 기재 의무를 만들지 마십시오.'
        )})
        # No parent answer, expected status, or parser relabeling is sent.
        started = time.perf_counter()
        try:
            retry = call_with_retry(isolated, host, key, model, max_tokens)
        except Exception as exc:
            retry = {'validation_errors': [str(exc)]}
        original = next(j for j in focused['parsed']['results'] if j['item_id'] == item)
        focused['source_focus_attempts'].append({'item_id': item, 'request': copy.deepcopy(isolated),
                                                'original_result': copy.deepcopy(original),
                                                'response': retry})
        history = retry.get('call_history') or [{
            'request_id': isolated['request_id'], 'attempt': 1,
            'purpose': 'isolated_source_judgment',
            'seconds': round(time.perf_counter() - started, 3),
            'validation_errors': copy.deepcopy(retry.get('validation_errors', [])),
            'finish_reason': retry.get('finish_reason'), 'usage': retry.get('usage'),
            'response_format': retry.get('response_format'),
        }]
        focused.setdefault('call_history', []).extend([
            {**event, 'purpose': 'isolated_source_judgment'} for event in history
        ])
        replacements = (retry.get('parsed') or {}).get('results') or []
        if not retry.get('validation_errors') and len(replacements) == 1:
            replacement = replacements[0]
            if replacement.get('item_id') == item and replacement.get('verdict') in {'COMPLIANT', 'VIOLATION'}:
                candidate = copy.deepcopy(focused['parsed'])
                candidate['results'] = [replacement if j['item_id'] == item else j for j in candidate['results']]
                if not validate(row, candidate):
                    focused['parsed'] = candidate
                    focused['source_focus_applied'].append(item)
    if focused['source_focus_applied']:
        focused['contract_projection'] = 'gate-derived-v1+isolated-source-v1'
    return focused


def completed_item_ids(result_rows: list[dict[str, Any]]) -> list[str]:
    item_ids = []
    for batch in result_rows:
        if batch.get("validation_errors"):
            continue
        parsed = batch.get("parsed") or {}
        for result in parsed.get("results") or []:
            if isinstance(result, dict) and result.get("item_id"):
                item_ids.append(str(result["item_id"]))
    return item_ids


def logical_request_complete(
    request_row: dict[str, Any], result_rows: list[dict[str, Any]]
) -> bool:
    actual = completed_item_ids(result_rows)
    expected = list(request_row.get("requested_item_ids") or [])
    return len(actual) == len(set(actual)) and actual == expected


def checkpoint_payload(
    *,
    input_path: Path,
    host: str | None,
    model: str,
    rows_by_id: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    return {
        "schema_version": "gemma-exhaustive-checkpoint-v1",
        "source_input": str(input_path.resolve()),
        "source_input_sha256": sha256(input_path),
        "host": host,
        "model": model,
        "runner_sha256": sha256(Path(__file__).resolve()),
        "evidence_projection_sha256": sha256(ROOT / "rag/judgment/evidence_projection.py"),
        "reading_quality_sha256": sha256(ROOT / "rag/judgment/reading_quality.py"),
        "grounding_sha256": sha256(ROOT / "rag/judgment/grounding.py"),
        "output_contract_sha256": sha256(ROOT / "rag/judgment/output_contract.py"),
        "response_format": response_mode(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "completed_logical_requests": len(rows_by_id),
        "rows_by_logical_request": rows_by_id,
    }


def load_checkpoint(
    path: Path,
    *,
    input_path: Path,
    host: str | None,
    model: str,
) -> dict[str, list[dict[str, Any]]]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "source_input_sha256": sha256(input_path),
        "host": host,
        "model": model,
        "runner_sha256": sha256(Path(__file__).resolve()),
        "evidence_projection_sha256": sha256(ROOT / "rag/judgment/evidence_projection.py"),
        "reading_quality_sha256": sha256(ROOT / "rag/judgment/reading_quality.py"),
        "grounding_sha256": sha256(ROOT / "rag/judgment/grounding.py"),
        "output_contract_sha256": sha256(ROOT / "rag/judgment/output_contract.py"),
        "response_format": response_mode(),
    }
    mismatches = {
        key: {"expected": value, "actual": payload.get(key)}
        for key, value in expected.items()
        if payload.get(key) != value
    }
    if mismatches:
        raise RuntimeError(f"체크포인트 실행 계약 불일치: {mismatches}")
    rows = payload.get("rows_by_logical_request")
    if not isinstance(rows, dict):
        raise RuntimeError("체크포인트 rows_by_logical_request가 객체가 아님")
    return {
        str(request_id): result_rows
        for request_id, result_rows in rows.items()
        if isinstance(result_rows, list)
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    # No historical dataset is a default.  Each run must name both prediction
    # input and output explicitly; this prevents an old labelled workset from
    # being reused by accident.
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--key", type=Path, default=DEFAULT_KEY)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-tokens", type=int, default=12288)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--request-id",
        action="append",
        default=[],
        help="Run only the named logical request. Repeat to select multiple requests.",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        help="중간 저장 경로. 생략 시 output 파일 옆 *.checkpoint.json",
    )
    args = parser.parse_args()

    requests = read_jsonl(args.input)
    if args.request_id:
        requested = set(args.request_id)
        available = {str(row.get("request_id")) for row in requests}
        missing = sorted(requested - available)
        if missing:
            raise SystemExit(f"Unknown --request-id values: {missing}")
        requests = [row for row in requests if str(row.get("request_id")) in requested]
    if not requests:
        raise SystemExit("요청이 0건")
    checkpoint_path = args.checkpoint or args.output.with_name(
        args.output.name + ".checkpoint.json"
    )
    loaded = load_checkpoint(
        checkpoint_path,
        input_path=args.input,
        host=args.host,
        model=args.model,
    )
    request_by_id = {row["request_id"]: row for row in requests}
    unknown_checkpoint_ids = set(loaded) - set(request_by_id)
    if unknown_checkpoint_ids:
        raise RuntimeError(
            f"현재 입력에 없는 체크포인트 request_id: {sorted(unknown_checkpoint_ids)}"
        )
    rows_by_id: dict[str, list[dict[str, Any]]] = {}
    for request_id, result_rows in loaded.items():
        if logical_request_complete(request_by_id[request_id], result_rows):
            rows_by_id[request_id] = result_rows
    pending = [row for row in requests if row["request_id"] not in rows_by_id]
    if rows_by_id:
        print(
            f"[resume] completed={len(rows_by_id)} pending={len(pending)} "
            f"checkpoint={checkpoint_path}",
            flush=True,
        )
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                call_with_retry_and_split,
                row, args.host, args.key, args.model, args.max_tokens,
            ): row
            for row in pending
        }
        done = len(rows_by_id)
        for future in as_completed(futures):
            source = futures[future]
            try:
                result_rows = future.result()
            except Exception as exc:
                result_rows = [{
                    "request_id": source["request_id"],
                    "logical_request_id": source["request_id"],
                    "ad_id": source["ad_id"],
                    "category": source["category"],
                    "fatal_error": str(exc),
                    "validation_errors": ["호출 실패"],
                    "split_depth": 0,
                }]
            rows_by_id[source["request_id"]] = result_rows
            done += 1
            write_json_atomic(
                checkpoint_path,
                checkpoint_payload(
                    input_path=args.input,
                    host=args.host,
                    model=args.model,
                    rows_by_id=rows_by_id,
                ),
            )
            unresolved = sum(bool(row["validation_errors"]) for row in result_rows)
            print(
                f"[{done}/{len(requests)}] {source['request_id']} "
                f"physical={len(result_rows)} unresolved={unresolved}",
                flush=True,
            )

    rows = [
        result
        for request_row in requests
        for result in rows_by_id[request_row["request_id"]]
    ]
    payload = {
        "schema_version": "gemma-exhaustive-response-v1",
        "status": "silver_model_pass_not_final_gold",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_requests": str(args.input),
        "execution": {
            "host": args.host,
            "endpoint_on_host": ENDPOINT,
            "model": args.model,
            "temperature": 0,
            "response_format": response_mode(),
            "workers": args.workers,
            "selected_request_ids": list(args.request_id) or None,
        },
        "counts": {
            "requests": len(requests),
            "logical_requests": len(requests),
            "physical_results": len(rows),
            "auto_split_results": sum(row.get("split_depth", 0) > 0 for row in rows),
            "valid_contract": sum(not row["validation_errors"] for row in rows),
            "invalid_contract": sum(bool(row["validation_errors"]) for row in rows),
            "fatal_errors": sum("fatal_error" in row for row in rows),
            "call_audit_complete": all("call_history" in row for row in rows),
            "recorded_judge_attempts": sum(len(row.get("call_history", [])) for row in rows),
        },
        "rows": rows,
    }
    write_json_atomic(args.output, payload)
    print(json.dumps({"output": str(args.output), **payload["counts"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
