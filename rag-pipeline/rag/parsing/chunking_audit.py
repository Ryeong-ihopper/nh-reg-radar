"""Deterministic measurements for advertisement fine search documents."""
from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from typing import Any, Iterable


LENGTH_BUCKETS = (
    ("at_most_5", 0, 5),
    ("6_to_20", 6, 20),
    ("21_to_50", 21, 50),
    ("51_to_100", 51, 100),
    ("101_to_300", 101, 300),
    ("301_to_700", 301, 700),
    ("over_700", 701, None),
)


def _nearest_rank(values: list[int], percentile: float) -> int:
    """Return an observed length using the nearest-rank definition."""
    if not values:
        return 0
    rank = max(1, math.ceil(percentile * len(values)))
    return sorted(values)[rank - 1]


def _length_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    lengths = [len(str(row.get("text_canonical") or "")) for row in rows]
    buckets = {
        name: sum(lower <= length and (upper is None or length <= upper) for length in lengths)
        for name, lower, upper in LENGTH_BUCKETS
    }
    count = len(lengths)
    return {
        "fine_documents": count,
        "characters": {
            "minimum": min(lengths, default=0),
            "p25_nearest_rank": _nearest_rank(lengths, 0.25),
            "median": statistics.median(lengths) if lengths else 0,
            "p75_nearest_rank": _nearest_rank(lengths, 0.75),
            "p90_nearest_rank": _nearest_rank(lengths, 0.90),
            "p95_nearest_rank": _nearest_rank(lengths, 0.95),
            "maximum": max(lengths, default=0),
            "mean": round(statistics.fmean(lengths), 3) if lengths else 0,
        },
        "thresholds": {
            "at_most_5": sum(length <= 5 for length in lengths),
            "at_most_5_rate": round(sum(length <= 5 for length in lengths) / count, 6)
            if count else 0,
            "at_most_20": sum(length <= 20 for length in lengths),
            "at_most_20_rate": round(sum(length <= 20 for length in lengths) / count, 6)
            if count else 0,
            "over_700": sum(length > 700 for length in lengths),
            "over_700_rate": round(sum(length > 700 for length in lengths) / count, 6)
            if count else 0,
        },
        "length_buckets": buckets,
        "span_status_counts": dict(sorted(Counter(
            str(row.get("span_status") or "UNKNOWN") for row in rows
        ).items())),
        "table_documents": sum(bool(row.get("table")) for row in rows),
    }


def summarize_fine_documents(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Summarize current fine chunks without changing or re-chunking them."""
    fine = list(rows)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in fine:
        grouped[str(row.get("source_file") or "UNKNOWN")].append(row)
    long_rows = sorted(
        (
            {
                "doc_id": str(row.get("doc_id") or ""),
                "source_file": str(row.get("source_file") or ""),
                "characters": len(str(row.get("text_canonical") or "")),
                "line_ref_count": len(row.get("line_refs") or []),
                "span_status": str(row.get("span_status") or "UNKNOWN"),
                "table": bool(row.get("table")),
            }
            for row in fine
            if len(str(row.get("text_canonical") or "")) > 700
        ),
        key=lambda row: (-row["characters"], row["doc_id"]),
    )
    return {
        "scope": "fine search document length baseline; no chunk mutation",
        "overall": _length_metrics(fine),
        "by_source_file": {
            name: _length_metrics(source_rows)
            for name, source_rows in sorted(grouped.items())
        },
        "over_700_documents": long_rows,
    }


def bm25_fine_coverage(
    fine_rows: Iterable[dict[str, Any]], channels: dict[str, dict[str, list[Any]]]
) -> dict[str, Any]:
    """Measure rule-index BM25 hits for fine documents, excluding context views."""
    fine = list(fine_rows)
    missing_channel_rows = [row for row in fine if row.get("doc_id") not in channels]
    invalid_missing = [
        str(row.get("doc_id") or "")
        for row in missing_channel_rows
        if len(str(row.get("text_search") or row.get("text_canonical") or "").strip()) >= 2
    ]
    if invalid_missing:
        raise ValueError("BM25 channel output is missing fine document ids")
    too_short = [str(row.get("doc_id") or "") for row in missing_channel_rows]
    empty = [
        *too_short,
        *(str(row["doc_id"]) for row in fine
          if row.get("doc_id") in channels and not channels[str(row["doc_id"])]["bm25_nori"]),
    ]
    count = len(fine)
    return {
        "fine_documents": count,
        "bm25_nonempty": count - len(empty),
        "bm25_empty": len(empty),
        "bm25_empty_rate": round(len(empty) / count, 6) if count else 0,
        "bm25_empty_doc_ids": empty,
        "bm25_unsearchable_too_short": len(too_short),
        "bm25_unsearchable_too_short_doc_ids": too_short,
    }
