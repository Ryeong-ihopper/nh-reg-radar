"""Runtime contract validation for the canonical operational pipeline.

JSON Schema files under ``schemas/`` are the external contract.  These small
validators enforce the cross-field invariants that JSON Schema cannot express
cleanly, such as unique line references and count consistency.
"""
from __future__ import annotations

import re
from typing import Any, Iterable


INTEGRATED_INPUT_VERSION = "nh-ad-review-integrated-input-v1"
SEARCH_DOCUMENT_VERSION = "ad-evidence-search-v1"
DISCOVERY_VERSION = "operational-discovery-v1"
FREEZE_VERSION = "operational-e2e-freeze-v1"
GEMMA_RESPONSE_VERSION = "gemma-exhaustive-response-v1"
OPERATIONAL_RESULT_VERSION = "operational-e2e-result-v1"
JOB_STATUS_VERSION = "operational-review-job-v1"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ContractError(ValueError):
    """Raised when a pipeline artifact violates its versioned contract."""


def _mapping(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{location} must be an object")
    return value


def _list(value: Any, location: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractError(f"{location} must be an array")
    return value


def _text(value: Any, location: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ContractError(f"{location} must be a non-empty string")
    return value


def _unique(values: Iterable[str], location: str) -> list[str]:
    rows = list(values)
    if len(rows) != len(set(rows)):
        raise ContractError(f"{location} contains duplicates")
    return rows


def validate_integrated_input(value: Any) -> dict[str, Any]:
    root = _mapping(value, "input")
    contract = _mapping(root.get("contract"), "contract")
    if contract.get("version") != INTEGRATED_INPUT_VERSION:
        raise ContractError(
            f"contract.version must be {INTEGRATED_INPUT_VERSION!r}"
        )
    sources = _mapping(contract.get("sources"), "contract.sources")
    if sources.get("p1_contract") != "nh-ad-review-evidence-v6":
        raise ContractError("contract.sources.p1_contract mismatch")
    if sources.get("p3_contract") != "nh-ad-review-region-input-v1":
        raise ContractError("contract.sources.p3_contract mismatch")
    for name in ("p1_sha256", "p3_sha256"):
        if not _SHA256.fullmatch(str(sources.get(name) or "")):
            raise ContractError(f"contract.sources.{name} must be sha256")

    document = _mapping(root.get("document"), "document")
    _text(document.get("ad_id"), "document.ad_id")
    _text(document.get("source_file"), "document.source_file")
    _mapping(document.get("routing_metadata"), "document.routing_metadata")

    evidence_ids: list[str] = []
    all_refs: list[str] = []
    pages = _list(root.get("pages"), "pages")
    if not pages:
        raise ContractError("pages must not be empty")
    page_numbers: list[int] = []
    region_count = 0
    for page_index, page_raw in enumerate(pages):
        page = _mapping(page_raw, f"pages[{page_index}]")
        page_no = page.get("page_no")
        if not isinstance(page_no, int) or page_no < 1:
            raise ContractError(f"pages[{page_index}].page_no must be >= 1")
        page_numbers.append(page_no)
        for region_index, region_raw in enumerate(_list(page.get("regions"), f"pages[{page_index}].regions")):
            region_count += 1
            location = f"pages[{page_index}].regions[{region_index}]"
            region = _mapping(region_raw, location)
            evidence_ids.append(_text(region.get("evidence_id"), f"{location}.evidence_id"))
            _text(region.get("region_id"), f"{location}.region_id")
            _text(region.get("final_text"), f"{location}.final_text", allow_empty=True)
            refs = _unique(
                (_text(ref, f"{location}.line_refs[]") for ref in _list(region.get("line_refs"), f"{location}.line_refs")),
                f"{location}.line_refs",
            )
            lines = _list(region.get("lines"), f"{location}.lines")
            line_refs = [
                _text(_mapping(line, f"{location}.lines[]").get("line_ref"), f"{location}.lines[].line_ref")
                for line in lines
            ]
            if refs != line_refs:
                raise ContractError(f"{location}.line_refs must exactly match lines order")
            all_refs.extend(refs)
        for line in _list(page.get("unassigned_lines"), f"pages[{page_index}].unassigned_lines"):
            all_refs.append(
                _text(_mapping(line, f"pages[{page_index}].unassigned_lines[]").get("line_ref"), "unassigned line_ref")
            )
    _unique((str(number) for number in page_numbers), "pages.page_no")
    _unique(evidence_ids, "regions.evidence_id")
    _unique(all_refs, "all line_refs")

    quality = _mapping(root.get("quality"), "quality")
    if quality.get("line_partition_exact") is not True:
        raise ContractError("quality.line_partition_exact must be true")
    if quality.get("line_count") != len(all_refs):
        raise ContractError("quality.line_count does not match input")
    if quality.get("region_count") != region_count:
        raise ContractError("quality.region_count does not match input")
    return root


def validate_search_document(value: Any) -> dict[str, Any]:
    row = _mapping(value, "search document")
    if row.get("schema_version") != SEARCH_DOCUMENT_VERSION:
        raise ContractError(
            f"schema_version must be {SEARCH_DOCUMENT_VERSION!r}"
        )
    for field in ("ad_id", "doc_id", "view_type", "text_canonical", "text_search"):
        _text(row.get(field), field)
    _list(row.get("line_refs"), "line_refs")
    _list(row.get("labels"), "labels")
    _mapping(row.get("routing_metadata"), "routing_metadata")
    return row


def validate_search_collections(
    inputs: Iterable[dict[str, Any]],
    coarse: Iterable[dict[str, Any]],
    fine: Iterable[dict[str, Any]],
) -> None:
    ads = {validate_integrated_input(value)["document"]["ad_id"] for value in inputs}
    coarse_rows = [validate_search_document(row) for row in coarse]
    fine_rows = [validate_search_document(row) for row in fine]
    coarse_ads = {row["ad_id"] for row in coarse_rows}
    fine_ads = {row["ad_id"] for row in fine_rows}
    if ads != coarse_ads or ads != fine_ads:
        raise ContractError(
            f"ad_id set mismatch input={sorted(ads)} coarse={sorted(coarse_ads)} fine={sorted(fine_ads)}"
        )
    coarse_ids = _unique((str(row["doc_id"]) for row in coarse_rows), "coarse.doc_id")
    _unique((str(row["doc_id"]) for row in fine_rows), "fine.doc_id")
    coarse_set = set(coarse_ids)
    missing_parents = sorted({
        str(row.get("parent_doc_id"))
        for row in fine_rows
        if str(row.get("parent_doc_id")) not in coarse_set
    })
    if missing_parents:
        raise ContractError(f"fine documents have missing coarse parents: {missing_parents[:5]}")


def validate_judgment(value: Any) -> dict[str, Any]:
    row = _mapping(value, "judgment")
    _text(row.get("item_id"), "judgment.item_id")
    if row.get("applicability") not in {"APPLICABLE", "NOT_APPLICABLE", "UNDETERMINED"}:
        raise ContractError("judgment.applicability enum mismatch")
    if row.get("verdict") not in {"COMPLIANT", "VIOLATION", "NOT_APPLICABLE", "UNDETERMINED"}:
        raise ContractError("judgment.verdict enum mismatch")
    _list(row.get("evidence_ids"), "judgment.evidence_ids")
    _list(row.get("evidence_line_refs"), "judgment.evidence_line_refs")
    _list(row.get("requirement_checks"), "judgment.requirement_checks")
    _text(row.get("reason"), "judgment.reason")
    if not isinstance(row.get("needs_researcher_review"), bool):
        raise ContractError("judgment.needs_researcher_review must be boolean")
    return row


def validate_job_status(value: Any) -> dict[str, Any]:
    row = _mapping(value, "job status")
    if row.get("schema_version") != JOB_STATUS_VERSION:
        raise ContractError(f"schema_version must be {JOB_STATUS_VERSION!r}")
    _text(row.get("job_id"), "job_id")
    if row.get("status") not in {
        "QUEUED",
        "RUNNING",
        "PLANNED",
        "COMPLETED",
        "COMPLETED_WITH_WARNINGS",
        "INPUT_REQUIRED",
        "FAILED",
        "INTERRUPTED",
    }:
        raise ContractError("job status enum mismatch")
    if not isinstance(row.get("attempt"), int) or row["attempt"] < 0:
        raise ContractError("job attempt must be a non-negative integer")
    _mapping(row.get("progress"), "job progress")
    _text(row.get("created_at"), "created_at")
    _text(row.get("updated_at"), "updated_at")
    return row


def validate_operational_result(value: Any) -> dict[str, Any]:
    root = _mapping(value, "operational result")
    if root.get("schema_version") != OPERATIONAL_RESULT_VERSION:
        raise ContractError(
            f"schema_version must be {OPERATIONAL_RESULT_VERSION!r}"
        )
    counts = _mapping(root.get("counts"), "counts")
    ads = _list(root.get("ads"), "ads")
    if counts.get("ads") != len(ads):
        raise ContractError("counts.ads does not match ads")
    pairs: list[tuple[str, str]] = []
    predicted = 0
    failures = 0
    for ad_raw in ads:
        ad = _mapping(ad_raw, "ads[]")
        ad_id = _text(ad.get("ad_id"), "ads[].ad_id")
        if "deferred_rules" in ad:
            deferred = _list(ad.get("deferred_rules"), "ads[].deferred_rules")
            _unique(
                (
                    _text(
                        _mapping(item, "ads[].deferred_rules[]").get("item_id"),
                        "ads[].deferred_rules[].item_id",
                    )
                    for item in deferred
                ),
                "ads[].deferred_rules.item_id",
            )
        for candidate_raw in _list(ad.get("candidates"), "ads[].candidates"):
            candidate = _mapping(candidate_raw, "candidate")
            item_id = _text(candidate.get("item_id"), "candidate.item_id")
            pairs.append((ad_id, item_id))
            if candidate.get("status") == "predicted":
                validate_judgment(candidate.get("judgment"))
                predicted += 1
            elif candidate.get("status") == "OUTPUT_FAILURE":
                if candidate.get("judgment") is not None:
                    raise ContractError("OUTPUT_FAILURE candidate must not have judgment")
                failures += 1
            else:
                raise ContractError("candidate.status enum mismatch")
    _unique((f"{ad_id}\0{item_id}" for ad_id, item_id in pairs), "candidate pairs")
    if counts.get("requested_pairs") != len(pairs):
        raise ContractError("counts.requested_pairs does not match candidates")
    if counts.get("predicted_pairs") != predicted:
        raise ContractError("counts.predicted_pairs does not match candidates")
    if counts.get("output_failures") != failures:
        raise ContractError("counts.output_failures does not match candidates")
    return root
