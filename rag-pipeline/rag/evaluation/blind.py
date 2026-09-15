"""Leakage-resistant evaluation artifacts for operational RAG predictions.

The workflow is deliberately one-way:

1. freeze an operational prediction;
2. generate a review packet with every model field removed;
3. seal human decisions;
4. join the two immutable snapshots for scoring.

Runtime prediction code never imports or reads this module.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


VERDICTS = frozenset({"VIOLATION", "COMPLIANT", "NOT_APPLICABLE", "UNDETERMINED"})
SPLITS = frozenset({"DEV_REGRESSION", "BLIND_HOLDOUT"})
FORBIDDEN_BLIND_KEYS = frozenset(
    {
        "judgment",
        "prediction",
        "predicted_verdict",
        "model_result",
        "decision_trace",
        "confidence",
        "reason",
    }
)


class BlindEvaluationError(ValueError):
    """Raised when an evaluation artifact would violate the blind protocol."""


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def content_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def pair_key(row: dict[str, Any]) -> str:
    parts = (
        row.get("ad_id"),
        row.get("scope_id"),
        row.get("product_id"),
        row.get("item_id"),
    )
    if any(value is None or not str(value).strip() for value in parts):
        raise BlindEvaluationError(f"evaluation pair identity is incomplete: {parts}")
    return "\u241f".join(map(str, parts))


def _prediction_pairs(prediction: dict[str, Any]) -> list[dict[str, Any]]:
    if prediction.get("schema_version") != "operational-e2e-result-v1":
        raise BlindEvaluationError("prediction must be operational-e2e-result-v1")
    output_failures = {
        pair_key(row): row for row in prediction.get("output_failure_pairs", [])
    }
    pairs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ad in prediction.get("ads", []):
        identity = {
            "ad_id": ad.get("ad_id"),
            "scope_id": ad.get("scope_id"),
            "product_id": ad.get("product_id"),
        }
        for bucket in ("candidates", "excluded_candidates"):
            for candidate in ad.get(bucket, []):
                row = {**identity, "item_id": candidate.get("item_id")}
                key = pair_key(row)
                if key in seen:
                    raise BlindEvaluationError(f"duplicate prediction pair: {key}")
                seen.add(key)
                judgment = candidate.get("judgment")
                verdict = judgment.get("verdict") if isinstance(judgment, dict) else None
                if verdict not in VERDICTS:
                    raise BlindEvaluationError(f"invalid or missing prediction verdict: {key}")
                pairs.append(
                    {
                        **row,
                        "pair_key": key,
                        "prediction_status": "VALID",
                        "predicted_verdict": verdict,
                        "evidence_ids": list(judgment.get("evidence_ids") or []),
                        "evidence_line_refs": list(
                            judgment.get("evidence_line_refs") or []
                        ),
                    }
                )
    for key, row in output_failures.items():
        if key in seen:
            continue
        seen.add(key)
        pairs.append(
            {
                **{name: row.get(name) for name in ("ad_id", "scope_id", "product_id", "item_id")},
                "pair_key": key,
                "prediction_status": "OUTPUT_CONTRACT_FAILURE",
                "predicted_verdict": None,
                "evidence_ids": [],
                "evidence_line_refs": [],
            }
        )
    expected = prediction.get("counts", {}).get("requested_pairs")
    if expected is not None and int(expected) != len(pairs):
        raise BlindEvaluationError(
            f"prediction pair count differs: counts.requested_pairs={expected}, extracted={len(pairs)}"
        )
    return sorted(pairs, key=lambda row: row["pair_key"])


def freeze_prediction(
    prediction: dict[str, Any],
    *,
    prediction_sha256: str,
    dataset_id: str,
    split: str,
    unseen_confirmed_by: str | None = None,
    unseen_confirmed_at: str | None = None,
) -> dict[str, Any]:
    if split not in SPLITS:
        raise BlindEvaluationError(f"unsupported evaluation split: {split}")
    if split == "BLIND_HOLDOUT" and not (
        str(unseen_confirmed_by or "").strip() and str(unseen_confirmed_at or "").strip()
    ):
        raise BlindEvaluationError(
            "BLIND_HOLDOUT requires an unseen-data declaration and timestamp"
        )
    pairs = _prediction_pairs(prediction)
    if not pairs:
        raise BlindEvaluationError("prediction contains no rule pairs")
    return {
        "schema_version": "blind-prediction-freeze-v1",
        "dataset_id": dataset_id,
        "split": split,
        "created_at": _now(),
        "prediction_sha256": prediction_sha256,
        "prediction_schema_version": prediction["schema_version"],
        "prediction_audit": copy.deepcopy(prediction.get("audit") or {}),
        "unseen_declaration": (
            {
                "confirmed_by": unseen_confirmed_by,
                "confirmed_at": unseen_confirmed_at,
                "statement": "ads were not used to develop, tune, or repeatedly inspect this pipeline",
            }
            if split == "BLIND_HOLDOUT"
            else None
        ),
        "pair_count": len(pairs),
        "pairs": pairs,
    }


def _review_source(candidate: dict[str, Any], identity: dict[str, Any]) -> dict[str, Any]:
    basis = copy.deepcopy(candidate.get("rule_basis") or {})
    contract = copy.deepcopy(candidate.get("condition_contract") or {})
    return {
        **identity,
        "item_id": candidate.get("item_id"),
        "rule_basis": basis,
        "condition_contract": contract,
        "reviewer_decisions": [],
        "final_decision": None,
    }


def _find_forbidden_keys(value: Any, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key in FORBIDDEN_BLIND_KEYS:
                found.append(child_path)
            found.extend(_find_forbidden_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_find_forbidden_keys(child, f"{path}[{index}]"))
    return found


def create_review_packet(
    prediction: dict[str, Any], freeze: dict[str, Any]
) -> dict[str, Any]:
    actual_hash = content_sha256(prediction)
    # A file hash is normally used. Tests and API callers can freeze canonical JSON,
    # so accept it only when the freeze explicitly contains that same canonical hash.
    if freeze.get("prediction_sha256") != actual_hash:
        raise BlindEvaluationError("prediction content does not match the freeze")
    expected = {row["pair_key"] for row in freeze.get("pairs", [])}
    rows: list[dict[str, Any]] = []
    for ad in prediction.get("ads", []):
        identity = {
            "ad_id": ad.get("ad_id"),
            "scope_id": ad.get("scope_id"),
            "product_id": ad.get("product_id"),
        }
        for bucket in ("candidates", "excluded_candidates"):
            for candidate in ad.get(bucket, []):
                row = _review_source(candidate, identity)
                if pair_key(row) in expected:
                    rows.append(row)
    actual = {pair_key(row) for row in rows}
    if actual != expected:
        missing = sorted(expected - actual)
        raise BlindEvaluationError(
            f"blind packet cannot represent all frozen pairs; missing={missing}"
        )
    packet = {
        "schema_version": "blind-review-packet-v1",
        "dataset_id": freeze.get("dataset_id"),
        "split": freeze.get("split"),
        "created_at": _now(),
        "prediction_sha256": freeze.get("prediction_sha256"),
        "blind_policy": {
            "model_fields_omitted": sorted(FORBIDDEN_BLIND_KEYS),
            "reviewers_must_not_open_prediction_artifact": True,
        },
        "rows": sorted(rows, key=pair_key),
    }
    forbidden = _find_forbidden_keys(packet)
    if forbidden:
        raise BlindEvaluationError(f"model fields leaked into review packet: {forbidden}")
    return packet


def _validate_timestamp(value: Any, label: str) -> None:
    try:
        datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise BlindEvaluationError(f"{label} must be an ISO-8601 timestamp") from exc


def _validate_decision(value: Any, label: str) -> None:
    if not isinstance(value, dict):
        raise BlindEvaluationError(f"{label} must be an object")
    if value.get("verdict") not in VERDICTS:
        raise BlindEvaluationError(f"{label}.verdict is invalid")
    if not str(value.get("reason") or "").strip():
        raise BlindEvaluationError(f"{label}.reason is required")
    _validate_timestamp(value.get("reviewed_at") or value.get("decided_at"), label)


def seal_human_labels(
    packet: dict[str, Any], *, minimum_reviewers: int = 2
) -> dict[str, Any]:
    if minimum_reviewers < 1:
        raise BlindEvaluationError("minimum_reviewers must be at least 1")
    if packet.get("schema_version") != "blind-review-packet-v1":
        raise BlindEvaluationError("review packet version is invalid")
    forbidden = _find_forbidden_keys(
        {key: value for key, value in packet.items() if key != "rows"}
    )
    # Decisions legitimately contain reason/confidence-like prose; source rows may not.
    if forbidden:
        raise BlindEvaluationError(f"model fields leaked into review packet header: {forbidden}")
    sealed_rows: list[dict[str, Any]] = []
    pending = 0
    under_reviewed = 0
    seen_pairs: set[str] = set()
    for index, row in enumerate(packet.get("rows") or []):
        key = pair_key(row)
        if key in seen_pairs:
            raise BlindEvaluationError(f"duplicate review pair: {key}")
        seen_pairs.add(key)
        source_only = {
            name: value
            for name, value in row.items()
            if name not in {"reviewer_decisions", "final_decision"}
        }
        leaked = _find_forbidden_keys(source_only)
        if leaked:
            raise BlindEvaluationError(f"model fields leaked into review row: {leaked}")
        decisions = row.get("reviewer_decisions") or []
        reviewer_ids: set[str] = set()
        for decision_index, decision in enumerate(decisions):
            _validate_decision(decision, f"rows[{index}].reviewer_decisions[{decision_index}]")
            reviewer_id = str(decision.get("reviewer_id") or "").strip()
            if not reviewer_id or reviewer_id in reviewer_ids:
                raise BlindEvaluationError(f"row {key} has missing/duplicate reviewer_id")
            reviewer_ids.add(reviewer_id)
        final = row.get("final_decision")
        if len(reviewer_ids) < minimum_reviewers:
            under_reviewed += 1
        if final is None:
            pending += 1
        else:
            _validate_decision(final, f"rows[{index}].final_decision")
            if not str(final.get("decided_by") or "").strip():
                raise BlindEvaluationError(f"row {key} final_decision.decided_by is required")
            resolution = final.get("resolution")
            verdicts = {decision["verdict"] for decision in decisions}
            if resolution == "CONSENSUS":
                if len(verdicts) != 1 or final["verdict"] not in verdicts:
                    raise BlindEvaluationError(f"row {key} is not a valid consensus")
            elif resolution != "ADJUDICATION":
                raise BlindEvaluationError(
                    f"row {key} final_decision.resolution must be CONSENSUS or ADJUDICATION"
                )
        sealed_rows.append(
            {
                **{name: row.get(name) for name in ("ad_id", "scope_id", "product_id", "item_id")},
                "reviewer_decisions": copy.deepcopy(decisions),
                "final_decision": copy.deepcopy(final),
            }
        )
    status = (
        "GOLD_READY"
        if sealed_rows and pending == 0 and under_reviewed == 0
        else "HUMAN_REVIEW_IN_PROGRESS"
    )
    snapshot = {
        "schema_version": "human-judgment-snapshot-v1",
        "dataset_id": packet.get("dataset_id"),
        "split": packet.get("split"),
        "prediction_sha256": packet.get("prediction_sha256"),
        "sealed_at": _now(),
        "status": status,
        "minimum_reviewers": minimum_reviewers,
        "counts": {
            "pairs": len(sealed_rows),
            "finalized": len(sealed_rows) - pending,
            "pending": pending,
            "below_minimum_reviewers": under_reviewed,
        },
        "rows": sorted(sealed_rows, key=pair_key),
    }
    snapshot["snapshot_sha256"] = content_sha256(snapshot)
    return snapshot


def _error_type(predicted: str | None, expected: str) -> str:
    if predicted is None:
        return "OUTPUT_CONTRACT_FAILURE"
    if predicted == expected:
        return "MATCH"
    if expected == "NOT_APPLICABLE":
        return "OVER_APPLIED_RULE"
    if predicted == "NOT_APPLICABLE":
        return "MISSED_APPLICABLE_RULE"
    if expected == "UNDETERMINED":
        return "OVERCONFIDENT_DECISION"
    if predicted == "UNDETERMINED":
        return "UNRESOLVED_DECISION"
    return "VERDICT_ERROR"


def evaluate_frozen_prediction(
    freeze: dict[str, Any], labels: dict[str, Any]
) -> dict[str, Any]:
    if labels.get("status") != "GOLD_READY":
        raise BlindEvaluationError("human labels are not GOLD_READY")
    if labels.get("prediction_sha256") != freeze.get("prediction_sha256"):
        raise BlindEvaluationError("human labels are bound to a different prediction")
    expected = {pair_key(row): row for row in labels.get("rows", [])}
    predicted = {row["pair_key"]: row for row in freeze.get("pairs", [])}
    if set(expected) != set(predicted):
        raise BlindEvaluationError("prediction and human-label pair sets differ")
    rows = []
    errors: Counter[str] = Counter()
    agreement = 0
    for key in sorted(predicted):
        prediction = predicted[key]
        final = expected[key]["final_decision"]
        error_type = _error_type(prediction.get("predicted_verdict"), final["verdict"])
        errors[error_type] += 1
        agreement += error_type == "MATCH"
        rows.append(
            {
                "pair_key": key,
                "ad_id": prediction["ad_id"],
                "item_id": prediction["item_id"],
                "predicted_verdict": prediction.get("predicted_verdict"),
                "expected_verdict": final["verdict"],
                "error_type": error_type,
            }
        )
    total = len(rows)
    return {
        "schema_version": "blind-evaluation-result-v1",
        "dataset_id": freeze.get("dataset_id"),
        "split": freeze.get("split"),
        "evaluated_at": _now(),
        "prediction_sha256": freeze.get("prediction_sha256"),
        "human_snapshot_sha256": labels.get("snapshot_sha256"),
        "counts": {
            "pairs": total,
            "exact_agreement": agreement,
            "errors": total - agreement,
        },
        "exact_agreement_rate": agreement / total if total else None,
        "error_types": dict(sorted(errors.items())),
        "rows": rows,
    }


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BlindEvaluationError(f"JSON object required: {path}")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
