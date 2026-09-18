"""Count physical model attempts including failed parents, not just final leaves."""

import json
import warnings


def judgment_call_metrics(rows):
    events = {}
    conflicts = []
    complete = True
    for row in rows:
        history = row.get("call_history")
        if history is None:
            complete = False
            history = [dict(row, attempt=1)]
        for event in history:
            # A focused source judgment may revisit the same split leaf. Its
            # attempt counter starts at one, but it is a separate physical call.
            key = ("call_id", event["call_id"]) if event.get("call_id") else (
                event["request_id"], event["attempt"], event.get("purpose", "judgment"))
            variants = events.setdefault(key, [])
            if event in variants:
                continue  # A copied split ancestor is still one physical call.
            if variants:
                complete = False
                conflicts.append({"identity": list(key), "code": "CONFLICTING_MODEL_CALL_AUDIT"})
            variants.append(event)
    # Conflicting legacy records cannot establish an exact physical-call count.
    # Preserve every variant, flag the uncertainty, and leave judgments intact.
    calls = [event for variants in events.values() for event in variants]
    return {
        "physical_calls": len(calls) if not conflicts else None,
        "distinct_audit_records": len(calls),
        "final_response_rows": len(rows),
        "valid_contract_calls": sum(not row.get("validation_errors") for row in calls) if not conflicts else None,
        "failed_contract_calls": sum(bool(row.get("validation_errors")) for row in calls) if not conflicts else None,
        "model_seconds_sum": round(sum(float(row.get("seconds") or 0) for row in calls), 3) if not conflicts else None,
        "call_audit_complete": complete,
        "call_audit_conflicts": conflicts,
    }


def save_completed_runtime_metrics(path, base, rows, wall_seconds):
    """Noncritical telemetry after the validated judgment result was saved."""
    try:
        judgment = judgment_call_metrics(rows)
    except Exception as exc:
        judgment = {"call_audit_complete": False, "physical_calls": None,
                    "call_audit_error": type(exc).__name__}
        warnings.warn(f"Judgments saved; call metrics unavailable: {type(exc).__name__}")
    document = {**base, "phase": "complete",
                "judgment": {"wall_seconds": wall_seconds, **judgment}}
    try:
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        warnings.warn(f"Judgments saved; runtime metrics write failed: {type(exc).__name__}")
    return document
