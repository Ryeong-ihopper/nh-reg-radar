"""Deterministic reading-quality gates, independent of advertisement/rule IDs.

Uncertain observations cannot establish a fact or absence. This module never
repairs OCR text or invents an alternative citation. Original model outputs are
retained by the caller; guard records explain each conservative abstention.
"""
from __future__ import annotations

import copy
import re
from typing import Any


VERSION = "reading-quality-gate-v3"


def claims_disclosure_absence(check: dict[str, Any], result_reason: str = "") -> bool:
    """An explicit missing-disclosure explanation cannot become an observation.

    This only abstains when reading is incomplete; it never supplies a missing
    obligation, infers a violation, or treats an observed numerical error as
    absence. The aggregate reason is supplied only for a single obligation.
    """
    if check.get("status") == "MISSING":
        return True
    if check.get("status") != "VIOLATED":
        return False
    reason = str(check.get("reason") or "") + "\n" + result_reason
    # Negated absence claims and quoted source phrases are not missing facts.
    reason = re.sub(r"[‘'\"“][^’'\"”\n]*[’'\"”]", "", reason)
    reason = re.sub(r"누락(?:된\s*(?:문구|항목))?\s*(?:없이|없음|없다|없습니다)|누락되지\s*않\S*", "", reason)
    return bool(re.search(
        r"누락(?:되|됐|된|으로|이라고|입니다|[.!]?(?:\n|$))|미(?:기재|표시|표기|고지)"
        r"|(?:문구|안내|설명|고지|기재|표시|표기)(?:가|는|이|도)?\s*(?:없|존재하지)"
        r"|(?:문구|안내|설명|고지|기재|표시|표기|내용|조건|항목)(?:가|는|이|도)?\s*(?:확인|발견|관찰)되지\s*않"
        r"|(?:기재|표시|표기|명시|고지|안내)(?:되어)?\s*(?:있지|되지|하지)\s*않",
        reason))


def project_reading_citations(result: dict[str, Any]) -> dict[str, Any]:
    """Exclude revoked claims from active citations, including saved v1 results.

    This is a projection, not a new judgment or a semantic relevance check.
    The caller's saved result and the guard's original_result remain untouched.
    An unrelated UNDETERMINED result is not grounds to suppress its citations.
    """
    issues = (result.get("reading_quality_review") or {}).get("issues") or []
    if not issues:
        return result
    projected = copy.deepcopy(result)
    gate_issue = any(not issue["location"].startswith("requirement_checks:") for issue in issues)
    if gate_issue:
        projected["applicability_evidence_ids"] = []
        projected["applicability_evidence_line_refs"] = []
        checks = [projected.get("scope_check"),
                  *(projected.get("condition_checks") or []),
                  *(projected.get("review_condition_checks") or []),
                  *(projected.get("requirement_checks") or [])]
    else:
        affected = {int(issue["location"].split(":")[1]) for issue in issues}
        checks = [check for index, check in enumerate(projected.get("requirement_checks") or [])
                  if index in affected]
    for check in checks:
        if isinstance(check, dict):
            check["evidence_ids"], check["evidence_line_refs"] = [], []
    retained = [] if gate_issue else [
        check for index, check in enumerate(projected.get("requirement_checks") or [])
        if index not in affected and check.get("finding_basis") == "OBSERVED"
        and check.get("status") in {"SATISFIED", "VIOLATED"}
    ]
    for field in ("evidence_ids", "evidence_line_refs"):
        projected[field] = list(dict.fromkeys(ref for check in retained for ref in check.get(field, [])))
    return projected


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
    checks = result.get("requirement_checks") or []
    for index, check in enumerate(checks):
        if not isinstance(check, dict) or check.get("status") not in {"SATISFIED", "MISSING", "VIOLATED"}:
            continue
        location = f"requirement_checks:{index}"
        absence = check.get("finding_basis") == "ABSENCE" or claims_disclosure_absence(
            check, str(result.get("reason") or "") if len(checks) == 1 else "")
        if absence and incomplete:
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
        result.update(project_reading_citations(result))
        audit.append({"item_id": result.get("item_id"), "policy": VERSION,
            "issues": issues, "original_result": before, "final_verdict": result["verdict"]})
    return audit
