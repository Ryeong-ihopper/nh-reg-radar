# -*- coding: utf-8 -*-
"""Read batched judgment requests and model responses without policy logic.

This module deliberately contains no advertisement- or rule-specific mapping.
It is safe for both evaluation tooling and the service-shaped runtime to use.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def load_requests(
    request_path: Path,
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    rule_by_pair: dict[tuple[str, str], dict[str, Any]] = {}
    docs_by_ad: dict[str, list[dict[str, Any]]] = {}
    for line in request_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        request = json.loads(line)
        payload = json.loads(request["messages"][1]["content"])
        ad_id = str(request["ad_id"])
        docs_by_ad.setdefault(ad_id, payload["documents"])
        for rule in payload["rules"]:
            rule_by_pair[(ad_id, str(rule["item_id"]))] = rule
    return rule_by_pair, docs_by_ad


def load_results(
    response_paths: Iterable[Path],
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[tuple[str, str], str]]:
    results: dict[tuple[str, str], dict[str, Any]] = {}
    sources: dict[tuple[str, str], str] = {}
    for path in response_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for batch in payload["rows"]:
            # Contract-invalid model output is not a prediction.  Keeping even
            # a partially parseable row would silently mix malformed evidence
            # or inconsistent enums into the workpaper.
            if batch.get("validation_errors"):
                continue
            parsed = batch.get("parsed") or {}
            ad_id = str(parsed.get("ad_id") or batch.get("ad_id"))
            for result in parsed.get("results") or []:
                if not isinstance(result, dict) or not result.get("item_id"):
                    continue
                pair = (ad_id, str(result["item_id"]))
                results[pair] = result
                sources[pair] = path.name
    return results, sources
