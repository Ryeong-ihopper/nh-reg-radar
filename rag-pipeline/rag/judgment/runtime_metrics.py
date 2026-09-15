"""Count physical model attempts including failed parents, not just final leaves."""


def judgment_call_metrics(rows):
    events = {}
    complete = True
    for row in rows:
        history = row.get("call_history")
        if history is None:
            complete = False
            history = [dict(row, attempt=1)]
        for event in history:
            key = (event["request_id"], event["attempt"])
            if key in events and events[key] != event:
                raise ValueError(f"conflicting model call audit: {key}")
            events[key] = event
    return {
        "physical_calls": len(events),
        "final_response_rows": len(rows),
        "valid_contract_calls": sum(not row.get("validation_errors") for row in events.values()),
        "failed_contract_calls": sum(bool(row.get("validation_errors")) for row in events.values()),
        "model_seconds_sum": round(sum(float(row.get("seconds") or 0) for row in events.values()), 3),
        "call_audit_complete": complete,
    }
