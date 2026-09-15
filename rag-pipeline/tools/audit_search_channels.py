"""Trace real BM25/dense/RRF/reranking without invoking the judgment model.

Only --prepare-current-index permits creation of a new content-addressed index.
The configured existing index and review results are never modified.
"""
from __future__ import annotations

import argparse
import collections
import copy
import json
import time
from pathlib import Path

import numpy as np

import hybrid_rule_retrieval as r
import run_operational_e2e as runner


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--fine", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--prepare-current-index", action="store_true")
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    source = Path(cfg["regulation_path"])
    r.v2_source.set_agent_path(source)
    previous, catalog = r.load_scope()
    current, _ = r.load_scope(include_layout=True)
    previous_ids = {row["id"] for row in previous}
    current_ids = {row["id"] for row in current}
    fine = r.read_jsonl(args.fine)
    groups = r.routing_scope(fine)["candidate_product_groups"]
    model = r.load_model()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    docs = r.rule_docs(current)

    def vectors(name, rows, key, path):
        return r.load_or_encode(rows, text_key=key, source=path, model=model, batch_size=4,
                                vectors_path=args.output_dir / f"{name}.npy",
                                meta_path=args.output_dir / f"{name}.meta.json", force=False)[0]

    rule_vectors = vectors("rules", docs, "search_text", source)
    fine_vectors = vectors("fine", fine, "text_search", args.fine)
    vector_by_id = dict(zip((row["doc_id"] for row in fine), fine_vectors))
    query_views, query_audit = runner.build_context_queries(fine)
    context_views = [row for row in query_views if row.get("_query_members")]
    if context_views:
        context_vectors = vectors("query-context", context_views, "text_search", args.fine)
        vector_by_id.update(zip((row["doc_id"] for row in context_views), context_vectors))
    rules = {row["item_id"]: row for row in runner.judgment_input.load_cd_rules(include_layout=True)}
    if set(rules) != current_ids:
        raise ValueError("search/judgment catalog ID mismatch")
    report = {
        "scope": "diagnostic search, mapped-rule exclusion disabled; not full E2E or recall evaluation",
        "source_sha256": r.sha256(source), "fine_sha256": r.sha256(args.fine),
        "source_count": len(catalog), "previous_count": len(previous), "current_count": len(current),
        "judgment_rule_definition_count": len(rules),
        "added_layout_ids": sorted(current_ids - previous_ids),
        "outside_product_scope_ids": sorted(set(catalog) - current_ids),
        "candidate_product_groups": groups, "runs": {},
        "query_context": query_audit,
    }
    indexes = [("previous", cfg["es_index"])]
    if args.prepare_current_index:
        index = r.versioned_rule_index(cfg["es_index"], docs, rule_vectors)
        report["index_preparation"] = r.ensure_rule_index(cfg["es_url"], index, docs, rule_vectors,
                                                        source_sha=r.sha256(source))
        indexes.append(("current", index))
    details = {}
    for label, index in indexes:
        indexed = r.request(cfg["es_url"], "POST", f"/{index}/_search", {"size": 1000, "query": {"match_all": {}}})
        r.validate_search_response(indexed)
        actual = {hit["_source"]["item_id"]: hit["_source"] for hit in indexed["hits"]["hits"]}
        expected = docs if label == "current" else r.rule_docs(previous)
        mismatches = [row["item_id"] for row in expected if
                      any(actual.get(row["item_id"], {}).get(key) != value
                          for key, value in row.items() if key != "doc_id")]
        started = time.perf_counter()
        channels = r.hybrid_hits_batch(cfg["es_url"], index, query_views, vector_by_id, groups,
                                      set(), 5, ("PRESENCE", "PROHIBIT", "STYLE"))
        channel_seconds = time.perf_counter() - started
        candidates = r.discover_prohibitions(query_views, vector_by_id, groups, base_url=cfg["es_url"],
                    index=index, per_chunk_k=5, rrf_k=60, deterministic_item_ids=set(),
                    categories=("PRESENCE", "PROHIBIT", "STYLE"))
        reranked = runner.rerank_prohibition_candidates(copy.deepcopy(candidates), rules=rules,
                        fine_documents={row["doc_id"]: row for row in fine}, rrf_k=60, candidate_pool=80)
        selected, budget_audit = runner.balanced_candidates(reranked, rules, 30)
        def ids(rows):
            return [row["item_id"] for row in rows]
        wrong_product = sorted({hit["_source"]["item_id"] for row in channels.values()
                                for hits in row.values() for hit in hits
                                if not set(hit["_source"]["product_groups"]) & {"전체", *groups}})
        counts = {channel: {"nonempty_queries": sum(bool(row[channel]) for row in channels.values()),
                           "unique_rule_hits": len({hit["_source"]["item_id"] for row in channels.values() for hit in row[channel]})}
                  for channel in ("bm25_nori", "bge_m3_exact_cosine")}
        report["runs"][label] = {"index": index, "document_count": len(actual),
            "bm25_and_dense_batch_seconds": round(channel_seconds, 3),
            "text_or_metadata_mismatch_ids": mismatches, "wrong_product_hit_ids": wrong_product,
            "queries": len(channels), "channels": counts, "rrf_candidate_count": len(candidates),
            "rrf_top10": ids(candidates[:10]), "reranked_top10": ids(reranked[:10]),
            "new_layout_retrieved": sorted(set(ids(candidates)) & (current_ids - previous_ids)),
            "top30_category_counts": dict(collections.Counter(rules[row["item_id"]]["category"] for row in reranked[:30])),
            "balanced30_category_counts": budget_audit["selected_by_category"],
            "balanced30_ids": ids(selected)}
        if label == "current":
            deltas = [float(np.max(np.abs(np.asarray(actual[row["item_id"]]["text_vector"]) - vector)))
                      for row, vector in zip(docs, rule_vectors)]
            report["runs"][label]["indexed_vector_max_abs_delta"] = max(deltas)
            eligible = [row for row in docs if set(row["product_groups"]) & {"전체", *groups}
                        and row["category"] in {"PRESENCE", "PROHIBIT", "STYLE"}]
            indexed_vectors = np.asarray([actual[row["item_id"]]["text_vector"] for row in eligible])
            indexed_vectors /= np.linalg.norm(indexed_vectors, axis=1, keepdims=True)
            eligible_positions = {row["item_id"]: i for i, row in enumerate(eligible)}
            below_exact_cutoff = 0
            for row in query_views:
                query_vector = vector_by_id[row["doc_id"]]
                scores = indexed_vectors @ (query_vector / np.linalg.norm(query_vector))
                for hit in channels[row["doc_id"]]["bge_m3_exact_cosine"]:
                    category = hit["_source"]["category"]
                    category_scores = scores[[i for i, doc in enumerate(eligible) if doc["category"] == category]]
                    cutoff = np.sort(category_scores)[-min(5, len(category_scores))]
                    if scores[eligible_positions[hit["_source"]["item_id"]]] < cutoff - 1e-6:
                        below_exact_cutoff += 1
            report["runs"][label]["dense_hits_below_exact_category_top5_cutoff"] = below_exact_cutoff
            report["runs"][label]["bm25_empty_inputs"] = [
                {"doc_id": row["doc_id"], "text": row["text_search"],
                 "tokens": [token["token"] for token in r.request(cfg["es_url"], "POST",
                            f"/{index}/_analyze", {"analyzer": "ko_nori", "text": row["text_search"]})["tokens"]]}
                for row in fine if not channels[row["doc_id"]]["bm25_nori"]]
        details[label] = {"channels": channels, "rrf": candidates, "reranked": reranked,
                          "candidate_budget": budget_audit}
    for name, value in (("metrics", report), ("channel-trace", details)):
        (args.output_dir / f"{name}.json").write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.output_dir / "metrics.json"),
                      "source_count": len(catalog), "previous_count": len(previous),
                      "current_count": len(current),
                      "runs": {key: {k: v for k, v in value.items() if k != "bm25_empty_inputs"}
                               for key, value in report["runs"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
