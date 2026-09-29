"""Build the 271-record current-scope plans and family prompt batches."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from rag.judgment.canonical_execution_plans import compile_current_scope
from rag.judgment.family_prompts import make_batches
from rag.judgment.review_program import apply_programs, load_policies


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--routing", type=Path, required=True)
    parser.add_argument("--methodologies", type=Path, required=True)
    parser.add_argument("--methodology-review", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--review-program-policies", type=Path,
                        default=Path(__file__).resolve().parents[1] / "config/review-program-policies-v1.json")
    parser.add_argument("--max-items", type=int, default=4)
    parser.add_argument("--max-complexity", type=int, default=12)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("output directory already exists")
    routing = json.loads(args.routing.read_text(encoding="utf-8"))
    methodologies = json.loads(args.methodologies.read_text(encoding="utf-8"))
    methodology_review = json.loads(args.methodology_review.read_text(encoding="utf-8"))
    document = compile_current_scope(routing, methodologies, methodology_review)
    document = apply_programs(document, load_policies(args.review_program_policies))
    batches = make_batches(document["plans"], max_items=args.max_items,
                           max_complexity=args.max_complexity)
    args.output_dir.mkdir(parents=True)
    (args.output_dir / "canonical-execution-plans.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    batch_document = {
        "schema_version": "family-prompt-batches-v1",
        "source_binding_sha256": document["source_binding_sha256"],
        "policies": {"role_preserving": True, "examples_in_prompt": False,
                     "overall_verdict_owner": "CODE", "runtime_execution_verified": False},
        "counts": {"batches": len(batches),
                   "families": dict(sorted(Counter(b["family"] for b in batches).items())),
                   "plans": sum(len(b["plans"]) for b in batches),
                   "oversized_singletons": sum(b["complexity"] > args.max_complexity for b in batches)},
        "batches": batches,
    }
    (args.output_dir / "family-prompt-batches.json").write_text(
        json.dumps(batch_document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        **{key: value for key, value in document["counts"].items() if key != "families"},
        "plan_families": document["counts"]["families"],
        "batches": batch_document["counts"]["batches"],
        "batch_families": batch_document["counts"]["families"],
        "oversized_singletons": batch_document["counts"]["oversized_singletons"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
