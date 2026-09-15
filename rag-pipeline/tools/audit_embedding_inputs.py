"""Audit actual runtime embedding inputs without judgment, gold or ES mutation."""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
import time

import numpy as np

import hybrid_rule_retrieval as retrieval
from dgx_bge_client import health
from run_operational_e2e import TemplateCatalog, template_rule_doc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--fine", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    regulation = Path(config["regulation_path"])
    template = Path(config["template_source_path"])
    retrieval.v2_source.set_agent_path(regulation)
    items, all_items = retrieval.load_scope(include_layout=True)
    fine = retrieval.read_jsonl(args.fine)
    template_rows = [template_rule_doc(rule) for rule in
                     TemplateCatalog.from_hwpx(template).operational_rules()]
    groups = (
        ("advertisement", fine, "text_search", args.fine),
        ("v2", retrieval.rule_docs(items), "search_text", regulation),
        ("template", template_rows, "search_text", template),
    )
    report = {
        "scope": "embedding integrity, not retrieval recall or judgment accuracy",
        "service": health(),
        "v2_source_items": len(all_items),
        "v2_active_search_items": len(items),
        "fine_source_file_values": sorted({row["source_file"] for row in fine}),
        "groups": {},
    }
    model = retrieval.load_model()
    started = time.perf_counter()
    for name, rows, key, source in groups:
        options = dict(text_key=key, source=source, model=model, batch_size=4,
                       vectors_path=args.output_dir / f"{name}.npy",
                       meta_path=args.output_dir / f"{name}.meta.json", force=False)
        matrix, first_hit, seconds = retrieval.load_or_encode(rows, **options)
        cached, second_hit, _ = retrieval.load_or_encode(rows, **options)
        np.testing.assert_array_equal(matrix, cached)
        lengths = [len(row[key]) for row in rows]
        counts = collections.Counter(row[key] for row in rows)
        report["groups"][name] = {
            "source": str(source.resolve()), "source_sha256": retrieval.sha256(source),
            "rows": len(rows), "dimension": matrix.shape[1],
            "norm_range": [float(value) for value in
                           (np.linalg.norm(matrix, axis=1).min(), np.linalg.norm(matrix, axis=1).max())],
            "max_input_chars_not_tokens": max(lengths),
            "duplicate_text_excess": sum(count - 1 for count in counts.values()),
            "first_cache_hit": first_hit, "second_cache_hit": second_hit,
            "first_cached_array_equal": True, "encode_seconds": round(seconds, 3),
            "input_truncation_verified": False,
        }
    report["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    target = args.output_dir / "metrics.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
