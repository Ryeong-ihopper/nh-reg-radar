"""Deterministic reading-quality gates, independent of advertisement/rule IDs.

Uncertain observations cannot establish a fact or absence. This module never
repairs OCR text or invents an alternative citation. Original model outputs are
retained by the caller; guard records explain each conservative abstention.
"""
from __future__ import annotations

import copy
from typing import Any


VERSION = "reading-quality-gate-v1"


def needs_reading_review(value: dict[str, Any]) -> bool:
    texts = [value.get(key) for key in ('final_text', 'text_canonical', 'text', 'selected_text')]
    texts.extend((value.get('line_texts') or {}).values())
    # Only objective decoding damage is detected here. Plausible but wrong
    # OCR words still require parser uncertainty flags or a human inspection.
    if any(isinstance(text, str) and ('\ufffd' in text or '\x00' in text) for text in texts):
        return True
    selection = value.get("text_selection", {})
    if not isinstance(selection, dict):
        return True
    # A missing field in a legacy contract is not a new observation of failure.
    # A present malformed flag, however, must never silently become trusted.
    flag = selection.get("needs_review", False)
    return flag is not False or selection.get("selection_status") in {
        "judge_selected_vlm_requires_review", "judge_unresolved_parser_fallback",
        "unassigned_parser_text",
    }


def uncertain_ad_readings(ad: dict[str, Any]) -> list[dict[str, Any]]:
    findings = []
    for page in ad.get("pages") or []:
        for value in [*(page.get("regions") or []), *(page.get("unassigned_lines") or [])]:
            if needs_reading_review(value):
                findings.append({"page_no": page.get("page_no"),
                    "evidence_id": value.get("evidence_id"),
                    "line_refs": value.get("line_refs") or ([value["line_ref"]] if value.get("line_ref") else []),
                    "reason": (value.get("text_selection") or {}).get("reason")
                    if isinstance(value.get("text_selection"), dict) else "invalid text_selection"})
    return findings


def reading_issues(payload: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    """Find determinations which depend on explicitly uncertain source evidence."""
    documents = payload.get("documents") or []
    unsafe = [doc for doc in documents if needs_reading_review(doc)]
    unsafe_ids = {str(doc.get("evidence_id")) for doc in unsafe}
    unsafe_refs = {str(ref) for doc in unsafe for ref in doc.get("line_refs") or []}
    scope = (payload.get("evidence_scope") or {}).get(result.get("item_id")) or {}
    incomplete = (
        payload.get("parser_coverage") == "PARTIAL"
        or bool(payload.get("reading_quality", {}).get("requires_review"))
        or bool(unsafe)
        or scope.get("complete_ad_scan") is False
    )
    issues = []

    def check_refs(value: dict[str, Any], location: str, id_key="evidence_ids", ref_key="evidence_line_refs"):
        ids = value.get(id_key)
        refs = value.get(ref_key)
        touched_ids = sorted(set(map(str, ids if isinstance(ids, list) else [])) & unsafe_ids)
        touched_refs = sorted(set(map(str, refs if isinstance(refs, list) else [])) & unsafe_refs)
        if touched_ids or touched_refs:
            issues.append({"location": location, "code": "UNCERTAIN_READING_EVIDENCE",
                "evidence_ids": touched_ids, "line_refs": touched_refs})

    if result.get("applicability") in {"APPLICABLE", "NOT_APPLICABLE"}:
        check_refs(result, "applicability", "applicability_evidence_ids", "applicability_evidence_line_refs")
    for name in ("scope_check", "condition_checks", "review_condition_checks"):
        values = [result.get(name)] if name == "scope_check" else result.get(name)
        for index, value in enumerate(values if isinstance(values, list) else []):
            if isinstance(value, dict) and value.get("status") != "UNDETERMINED":
                check_refs(value, f"{name}:{index}")
    for index, check in enumerate(result.get("requirement_checks") or []):
        if not isinstance(check, dict) or check.get("status") not in {"SATISFIED", "MISSING", "VIOLATED"}:
            continue
        location = f"requirement_checks:{index}"
        if check.get("finding_basis") == "ABSENCE" and incomplete:
            issues.append({"location": location, "code": "INCOMPLETE_READING_ABSENCE"})
        elif check.get("finding_basis") == "OBSERVED":
            check_refs(check, location)
    return issues


def apply_reading_guard(payload: dict[str, Any], parsed: dict[str, Any]) -> list[dict[str, Any]]:
    """Abstain on unsafe claims instead of spending retries on unreadable input.

    Unaffected findings stay intact. Changed rows preserve their original value
    in the returned audit. Structural/ID errors remain subject to validation.
    """
    audit = []
    for result in parsed.get("results") or []:
        if not isinstance(result, dict):
            continue
        issues = reading_issues(payload, result)
        if not issues:
            continue
        before = copy.deepcopy(result)
        gate_issue = any(not issue["location"].startswith("requirement_checks:") for issue in issues)
        reason = "원문 판독 불확실성 또는 읽기 미완료로 자동 확정할 수 없습니다. 해당 원본을 사람이 확인해야 합니다."
        if gate_issue:
            result["applicability"] = "UNDETERMINED"
            result["applicability_basis"] = "UNDETERMINED"
            if isinstance(result.get("scope_check"), dict):
                result["scope_check"]["status"] = "UNDETERMINED"
            for name in ("condition_checks", "review_condition_checks"):
                for check in result.get(name) or []:
                    if isinstance(check, dict):
                        check["status"] = "UNDETERMINED"
            result["requirement_checks"] = []
        else:
            affected = {int(issue["location"].split(":")[1]) for issue in issues}
            for index in affected:
                check = result["requirement_checks"][index]
                check.update(status="UNDETERMINED", finding_basis="UNKNOWN", reason=reason)
        # An independent, still valid violating component remains actionable.
        # A partially supported compliance result can never stay COMPLIANT.
        has_independent_violation = not gate_issue and any(
            check.get("status") in {"VIOLATED", "MISSING"}
            for check in result.get("requirement_checks") or [] if isinstance(check, dict))
        result.update(verdict="VIOLATION" if has_independent_violation else "UNDETERMINED",
            needs_researcher_review=True, confidence="LOW")
        result["reason"] = (" / ".join(str(check.get("reason") or "")
            for check in result.get("requirement_checks") or []
            if check.get("status") in {"VIOLATED", "MISSING"}) + " / " + reason
            if has_independent_violation else reason)
        result["reading_quality_review"] = {"policy": VERSION, "issues": issues}
        audit.append({"item_id": result.get("item_id"), "policy": VERSION,
            "issues": issues, "original_result": before, "final_verdict": result["verdict"]})
    return audit
