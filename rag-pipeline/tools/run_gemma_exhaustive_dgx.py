# -*- coding: utf-8 -*-
"""DGX Spark Gemma로 전수 규칙 배치를 판정하고 출력 계약을 검증한다."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_HOST = os.environ.get("DGX_HOST")
DEFAULT_KEY = Path(os.environ["DGX_SSH_KEY"]) if os.environ.get("DGX_SSH_KEY") else None
DEFAULT_MODEL = os.environ.get("DGX_GEMMA_MODEL", "gemma-4-26b-NVFP4-MTP")
ENDPOINT = "http://127.0.0.1:8102/v1/chat/completions"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def parse_content(content: str) -> dict[str, Any]:
    text = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.S | re.I)
    if fenced:
        text = fenced.group(1).strip()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("응답이 JSON 객체가 아님")
    return value


def validate(request_row: dict[str, Any], parsed: dict[str, Any]) -> list[str]:
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
    for result_index, row in enumerate(results):
        if not isinstance(row, dict):
            errors.append(f"results[{result_index}]가 객체가 아님: {type(row).__name__}")
            continue
        item_id = row.get("item_id")
        applicability = row.get("applicability")
        applicability_basis = row.get("applicability_basis")
        verdict = row.get("verdict")
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
        if not str(row.get("reason") or "").strip():
            errors.append(f"{item_id}: reason 없음")
        checks = row.get("requirement_checks")
        if not isinstance(checks, list) or not checks:
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
            if check_status not in {
                "SATISFIED", "MISSING", "VIOLATED", "NOT_APPLICABLE", "UNDETERMINED",
            }:
                errors.append(f"{item_id}: requirement_checks[{check_index}] status enum")
            else:
                check_statuses.append(check_status)
            check_ids = check.get("evidence_ids")
            check_refs = check.get("evidence_line_refs")
            if not isinstance(check_ids, list) or set(map(str, check_ids)) - allowed_ids:
                errors.append(f"{item_id}: requirement_checks[{check_index}] 제공 밖 evidence_id")
            if not isinstance(check_refs, list) or set(map(str, check_refs)) - allowed_refs:
                errors.append(f"{item_id}: requirement_checks[{check_index}] 제공 밖 line_ref")
            if not str(check.get("reason") or "").strip():
                errors.append(f"{item_id}: requirement_checks[{check_index}] reason 없음")
        if verdict == "COMPLIANT" and any(
            status in {"MISSING", "VIOLATED", "UNDETERMINED"}
            for status in check_statuses
        ):
            errors.append(f"{item_id}: 구성요소 미충족/불명확인데 COMPLIANT")
        if verdict == "VIOLATION" and not any(
            status in {"MISSING", "VIOLATED"} for status in check_statuses
        ):
            errors.append(f"{item_id}: 위반 구성요소 없이 VIOLATION")
    return errors


def call_once(row: dict[str, Any], host: str | None, key: Path | None, model: str, max_tokens: int) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": row["messages"],
        "temperature": 0,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    from dgx_openai_client import post_json

    started = time.perf_counter()
    response = post_json(payload, host=host, key=key, timeout=900)
    seconds = time.perf_counter() - started
    choice = response["choices"][0]
    parsed = parse_content(choice["message"]["content"])
    return {
        "request_id": row["request_id"],
        "ad_id": row["ad_id"],
        "category": row["category"],
        "seconds": round(seconds, 3),
        "model_returned": response.get("model"),
        "finish_reason": choice.get("finish_reason"),
        "usage": response.get("usage"),
        "parsed": parsed,
        "validation_errors": validate(row, parsed),
    }


def contract_attempt_limit(row: dict[str, Any]) -> int:
    return 1 if len(row.get("requested_item_ids") or []) > 6 else 2


def call_with_retry(row: dict[str, Any], host: str | None, key: Path | None, model: str, max_tokens: int) -> dict[str, Any]:
    attempts = []
    current = row
    # Large invalid responses are more reliably and cheaply recovered by the
    # existing recursive splitter than by asking the model to repeat the same
    # oversized JSON object a second time.
    max_attempts = contract_attempt_limit(row)
    for attempt in range(1, max_attempts + 1):
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
        if not result["validation_errors"]:
            result["contract_attempts"] = attempt
            result["attempted_validation_errors"] = attempts
            return result
        if attempt < max_attempts:
            current = {**row, "messages": [dict(message) for message in row["messages"]]}
            current["messages"][0]["content"] += (
                "\n\n이전 응답은 출력 계약을 위반했다. 이번에는 입력 rule 순서와 개수를 정확히 유지하고, "
                "각 enum·근거 ID·line_ref를 제공된 값으로만 작성하라."
            )
    result["contract_attempts"] = max_attempts
    result["attempted_validation_errors"] = attempts
    return result


def split_request_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Split a failed multi-rule request without changing its evidence input."""
    expected = list(row.get("requested_item_ids") or [])
    if len(expected) < 2:
        return [row]
    payload = json.loads(row["messages"][1]["content"])
    rules = payload.get("rules")
    if not isinstance(rules, list) or [rule.get("item_id") for rule in rules] != expected:
        raise ValueError("요청 rules와 requested_item_ids 순서가 다름")
    midpoint = len(rules) // 2
    children = []
    for label, child_rules in (("a", rules[:midpoint]), ("b", rules[midpoint:])):
        child = copy.deepcopy(row)
        child_id = f"{row['request_id']}~split-{label}"
        child_payload = copy.deepcopy(payload)
        child_payload["request_id"] = child_id
        child_payload["rules"] = child_rules
        child["request_id"] = child_id
        child["requested_item_ids"] = [rule["item_id"] for rule in child_rules]
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
    result = call_with_retry(row, host, key, model, max_tokens)
    result["logical_request_id"] = row.get("logical_request_id", row["request_id"])
    result["split_depth"] = depth
    if not result["validation_errors"]:
        return [result]
    if len(row.get("requested_item_ids") or []) < 2 or depth >= max_split_depth:
        return [result]
    output: list[dict[str, Any]] = []
    for child in split_request_row(row):
        output.extend(call_with_retry_and_split(
            child, host, key, model, max_tokens,
            depth=depth + 1, max_split_depth=max_split_depth,
        ))
    return output


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
        "--checkpoint",
        type=Path,
        help="중간 저장 경로. 생략 시 output 파일 옆 *.checkpoint.json",
    )
    args = parser.parse_args()

    requests = read_jsonl(args.input)
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
            "workers": args.workers,
        },
        "counts": {
            "requests": len(requests),
            "logical_requests": len(requests),
            "physical_results": len(rows),
            "auto_split_results": sum(row.get("split_depth", 0) > 0 for row in rows),
            "valid_contract": sum(not row["validation_errors"] for row in rows),
            "invalid_contract": sum(bool(row["validation_errors"]) for row in rows),
            "fatal_errors": sum("fatal_error" in row for row in rows),
        },
        "rows": rows,
    }
    write_json_atomic(args.output, payload)
    print(json.dumps({"output": str(args.output), **payload["counts"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
