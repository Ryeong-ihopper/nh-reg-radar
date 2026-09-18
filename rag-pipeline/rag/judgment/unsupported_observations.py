"""Quarantine unsupported observations after bounded model contract repair."""
import copy
import re


def quarantine_unsupported_observations(request, response, validate):
    errors = response.get("validation_errors") or []
    if not errors or not response.get("parsed"):
        return response
    affected = {}
    for error in errors:
        match = re.fullmatch(r"([^:]+): requirement_checks\[(\d+)\] template heading alone cannot establish the required body disclosure", error)
        if match:
            affected.setdefault(match[1], set()).add(int(match[2]))
            continue
        match = re.fullmatch(r"([^:]+): requirement_checks\[(\d+)\] 원문에 있다고 설명한 인용 문구가 선택한 줄에 없음; 해당 문구의 실제 원본 줄을 인용해야 함", error)
        if match:
            affected.setdefault(match[1], set()).add(int(match[2]))
            continue
        match = re.fullmatch(r"([^:]+): OBSERVED에는 직접 광고 근거가 필요", error)
        if not match:
            return response  # Never turn execution/schema/unknown-ID failures into judgments.
        for result in response["parsed"].get("results", []):
            if result.get("item_id") == match[1]:
                affected.setdefault(match[1], set()).update(
                    i for i, check in enumerate(result.get("requirement_checks", []))
                    if check.get("finding_basis") == "OBSERVED"
                    and not (check.get("evidence_ids") or check.get("evidence_line_refs")))
    guarded = copy.deepcopy(response)
    reason = "모델이 제시한 관찰 내용과 인용한 원문 줄을 검증하지 못했습니다. 해당 요건은 사람이 원본을 확인해야 합니다."
    for result in guarded["parsed"].get("results", []):
        indexes = affected.get(result.get("item_id"))
        if not indexes:
            continue
        checks = result.get("requirement_checks", [])
        if any(i >= len(checks) for i in indexes):
            return response
        for i in indexes:
            checks[i].update(status="UNDETERMINED", finding_basis="UNKNOWN", reason=reason,
                             evidence_ids=[], evidence_line_refs=[])
        retained = [c for i, c in enumerate(checks) if i not in indexes and c.get("finding_basis") == "OBSERVED"]
        for field in ("evidence_ids", "evidence_line_refs"):
            result[field] = list(dict.fromkeys(ref for c in retained for ref in c.get(field, [])))
        violations = [c for i,c in enumerate(checks) if i not in indexes and c.get("status") in {"VIOLATED", "MISSING"}]
        result.update(verdict="VIOLATION" if violations else "UNDETERMINED", confidence="LOW",
                      needs_researcher_review=True,
                      reason=" / ".join([c.get("reason", "") for c in violations]+[reason]))
    if validate(request, guarded["parsed"]):
        return response
    guarded["unsupported_observation_review"] = {
        "policy": "unsupported-observation-review-v1", "validation_errors": errors,
        "original_result": copy.deepcopy(response["parsed"]),
    }
    guarded["validation_errors"] = []
    return guarded
