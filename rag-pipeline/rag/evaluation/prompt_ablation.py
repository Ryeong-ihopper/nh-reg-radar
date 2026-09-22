"""Evaluation protocol for structured prompt changes without answer leakage."""
from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any


def build_protocol(plans: dict[str, Any], batches: dict[str, Any],
                   legacy_dev_score: dict[str, Any] | None = None) -> dict[str, Any]:
    if plans["source_binding_sha256"] != batches["source_binding_sha256"]:
        raise ValueError("plans and prompt batches use different source snapshots")
    plan_rows = plans["plans"]
    batch_rows = batches["batches"]
    prompt_hashes = sorted({hashlib.sha256(row["prompt"].encode("utf-8")).hexdigest()
                            for row in batch_rows})
    unresolved = [{"plan_id": row["plan_id"], "issues": row["unresolved"]}
                  for row in plan_rows if row["unresolved"]]
    held_facets = [{"plan_id": row["plan_id"], "facets": row.get("held_facets") or []}
                   for row in plan_rows if row.get("held_facets")]
    return {
        "schema_version": "structured-prompt-ablation-v1",
        "source_binding_sha256": plans["source_binding_sha256"],
        "change_under_test": [
            "role-preserving obligation projection with non-binding source-example hints",
            "family-specific short instructions",
            "family-isolated complexity-capped batches",
            "code-owned applicability and overall aggregation",
        ],
        "splits": {
            "dev_regression": {
                "name": "ISA six advertisements / template labels",
                "advertisements": 6, "labeled_template_pairs": 66,
                "purpose": "known-error regression only",
                "legacy_score": legacy_dev_score,
            },
            "holdout": {
                "name": None, "advertisements": 0, "labeled_pairs": 0,
                "status": "MISSING_INDEPENDENT_HOLDOUT",
            },
        },
        "required_metrics": [
            "applicability_macro_f1", "compliance_macro_f1", "violation_recall",
            "undetermined_rate", "unsupported_citation_rate", "rule_family_breakdown",
        ],
        "ablation_arms": [
            {"id": "A0", "prompt": "legacy operational prompt", "batching": "fixed-size"},
            {"id": "A1", "prompt": "role-preserving base", "batching": "fixed-size"},
            {"id": "A2", "prompt": "role-preserving + family instruction", "batching": "fixed-size"},
            {"id": "A3", "prompt": "role-preserving + family instruction",
             "batching": "family-isolated complexity cap"},
        ],
        "structural_checks": {
            "candidate_plans": len(plan_rows),
            "obligation_atoms": sum(len(row["obligations"]) for row in plan_rows),
            "prompt_families": dict(sorted(Counter(row["prompt_family"] for row in plan_rows).items())),
            "prompt_hashes": prompt_hashes,
            "batches": len(batch_rows),
            "examples_projected_as_advertisement_evidence": False,
            "examples_projected_as_non_binding_hints": True,
            "overall_verdict_owner": "CODE",
            "unresolved_source_interpretations": unresolved,
            "held_source_conflict_facets": held_facets,
        },
        "execution_state": {
            "requests_generated": False,
            "new_predictions_generated": False,
            "dev_compared": False,
            "holdout_compared": False,
            "reason": "No new model outputs and no independent labeled holdout",
        },
        "reporting_policy": {
            "may_claim_structural_contract_coverage": True,
            "may_claim_dev_improvement": False,
            "may_claim_generalization": False,
        },
    }


def compare_predictions(protocol: dict[str, Any], arms: dict[str, list[dict[str, Any]]],
                        gold: list[dict[str, Any]], *, split: str,
                        require_all_arms: bool = False) -> dict[str, Any]:
    if split not in {"dev_regression", "holdout"}:
        raise ValueError("unknown split")
    if split == "holdout" and protocol["splits"]["holdout"]["labeled_pairs"] == 0:
        raise ValueError("independent holdout is absent; comparison would invent evidence")
    keys = [(row["ad_id"], row["item_id"]) for row in gold]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate gold key")
    gold_by_key = {key: row for key, row in zip(keys, gold, strict=True)}
    expected_arms = {row["id"] for row in protocol["ablation_arms"]}
    if require_all_arms and set(arms) != expected_arms:
        raise ValueError("all A0-A3 ablation arms are required")
    output = {}
    for arm, rows in arms.items():
        predicted = {(row["ad_id"], row["item_id"]): row for row in rows}
        if set(predicted) != set(gold_by_key):
            raise ValueError(f"{arm} prediction/gold key mismatch")
        exact = sum(predicted[key].get("verdict") == gold_by_key[key].get("verdict")
                    for key in gold_by_key)
        output[arm] = {
            "pairs": len(gold_by_key), "exact_verdict": exact,
            "exact_verdict_rate": exact / len(gold_by_key) if gold_by_key else None,
            **_decision_metrics(predicted, gold_by_key),
        }
    return {"split": split, "arms": output,
            "generalization_claim_allowed": split == "holdout"}


def _decision_metrics(predicted: dict[tuple[str, str], dict[str, Any]],
                      gold: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    labels = ("COMPLIANT", "VIOLATION", "UNDETERMINED", "NOT_APPLICABLE")
    confusion = {actual: {guess: 0 for guess in labels} for actual in labels}
    for key, expected in gold.items():
        actual = expected.get("verdict")
        guess = predicted[key].get("verdict")
        if actual not in labels or guess not in labels:
            raise ValueError("unknown verdict label")
        confusion[actual][guess] += 1
    compliance_labels = labels[:3]
    scored_labels = [label for label in compliance_labels if sum(confusion[label].values())]
    f1_values = [_f1(confusion, label) for label in scored_labels]
    applicable_confusion = _binary_applicability_confusion(predicted, gold)
    unsupported = sum(row.get("citation_supported") is False for row in predicted.values())
    undetermined = sum(row.get("verdict") == "UNDETERMINED" for row in predicted.values())
    violation_total = sum(confusion["VIOLATION"].values())
    return {
        "applicability_macro_f1": _binary_macro_f1(applicable_confusion),
        "compliance_macro_f1": (sum(f1_values) / len(f1_values) if f1_values else None),
        "violation_recall": (confusion["VIOLATION"]["VIOLATION"] / violation_total
                             if violation_total else None),
        "undetermined_rate": undetermined / len(predicted) if predicted else None,
        "unsupported_citation_rate": unsupported / len(predicted) if predicted else None,
        "confusion": confusion,
        "rule_family_breakdown": _family_breakdown(predicted, gold),
    }


def _f1(confusion: dict[str, dict[str, int]], label: str) -> float:
    true_positive = confusion[label][label]
    false_positive = sum(confusion[actual][label] for actual in confusion if actual != label)
    false_negative = sum(value for guess, value in confusion[label].items() if guess != label)
    denominator = 2 * true_positive + false_positive + false_negative
    return 2 * true_positive / denominator if denominator else 0.0


def _binary_applicability_confusion(predicted: dict, gold: dict) -> dict[str, dict[str, int]]:
    output = {"APPLICABLE": {"APPLICABLE": 0, "NOT_APPLICABLE": 0},
              "NOT_APPLICABLE": {"APPLICABLE": 0, "NOT_APPLICABLE": 0}}
    for key, expected in gold.items():
        actual = "NOT_APPLICABLE" if expected["verdict"] == "NOT_APPLICABLE" else "APPLICABLE"
        guess = ("NOT_APPLICABLE" if predicted[key]["verdict"] == "NOT_APPLICABLE"
                 else "APPLICABLE")
        output[actual][guess] += 1
    return output


def _binary_macro_f1(confusion: dict[str, dict[str, int]]) -> float:
    values = []
    for label in confusion:
        true_positive = confusion[label][label]
        other = next(value for value in confusion if value != label)
        false_positive = confusion[other][label]
        false_negative = confusion[label][other]
        denominator = 2 * true_positive + false_positive + false_negative
        values.append(2 * true_positive / denominator if denominator else 0.0)
    return sum(values) / len(values)


def _family_breakdown(predicted: dict, gold: dict) -> dict[str, dict[str, int]]:
    output: dict[str, dict[str, int]] = {}
    for key, expected in gold.items():
        family = str(expected.get("rule_family") or "UNSPECIFIED")
        bucket = output.setdefault(family, {"pairs": 0, "exact": 0})
        bucket["pairs"] += 1
        bucket["exact"] += predicted[key]["verdict"] == expected["verdict"]
    return dict(sorted(output.items()))
