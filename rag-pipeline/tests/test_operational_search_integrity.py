"""Source scope, immutable index identity and partial-search protection."""
import unittest
from unittest.mock import patch

import numpy as np
import hybrid_rule_retrieval as retrieval
import run_operational_e2e as runner


class SearchIntegrityTests(unittest.TestCase):
    def test_search_and_judgment_loaders_keep_identical_layout_scope(self):
        from collections import defaultdict
        item = defaultdict(str, {"id": "layout", "category": "STYLE", "적용상품": ["전체"],
                                 "판정유형": "레이아웃필요"})
        with patch.object(retrieval.v2_source, "build", return_value=([item], [])):
            search, _ = retrieval.load_scope(include_layout=True)
            judgment = runner.judgment_input.load_cd_rules(include_layout=True)
        self.assertEqual({row["id"] for row in search}, {row["item_id"] for row in judgment})
        self.assertEqual(judgment[0]["judgment_type"], "레이아웃필요")

    def test_existing_index_with_missing_documents_is_rejected(self):
        vectors = np.eye(1, 1024, dtype="float32")
        docs = [{"doc_id": "a", "item_id": "a", "search_text": "generic"}]
        with patch.object(retrieval, "index_exists", return_value=False), patch.object(
            retrieval, "request", side_effect=[{}, {"errors": False}, {"count": 1}]
        ) as request:
            retrieval.ensure_rule_index("url", "idx", docs, vectors, source_sha="sha")
        mapping = request.call_args_list[0].args[3]
        with patch.object(retrieval, "index_exists", return_value=True), patch.object(
            retrieval, "request", side_effect=[{"idx": mapping}, {"count": 0}]
        ):
            with self.assertRaises(RuntimeError):
                retrieval.ensure_rule_index("url", "idx", docs, vectors, source_sha="sha")

    def test_rrf_keeps_candidates_from_either_channel_and_source_refs(self):
        fine = {"doc_id": "e1", "text_search": "generic text", "text_canonical": "generic text",
                "parent_chunk_id": "p1", "page_no": 1, "region_id": "r1", "line_refs": ["l1"]}

        def hit(item, score):
            return {"_score": score, "_source": {"item_id": item, "title": item, "product_groups": ["전체"]}}

        channels = {"e1": {"bm25_nori": [hit("A", 8), hit("B", 2)],
                           "bge_m3_exact_cosine": [hit("C", 0.9), hit("A", 0.8)]}}
        with patch.object(retrieval, "hybrid_hits_batch", return_value=channels):
            rows = retrieval.discover_prohibitions([fine], {}, "예금성", base_url="url", index="idx",
                    per_chunk_k=2, rrf_k=60, deterministic_item_ids=set())
        self.assertEqual({row["item_id"] for row in rows}, {"A", "B", "C"})
        self.assertEqual(rows[0]["item_id"], "A")
        self.assertAlmostEqual(rows[0]["score"], 1 / 61 + 1 / 62, places=7)
        self.assertEqual(rows[0]["trigger_evidence"][0]["trigger"]["line_refs"], ["l1"])

    def test_layout_is_searchable_but_missing_observations_defer_judgment(self):
        rows = [
            {"id": "common", "적용상품": ["전체"], "판정유형": "레이아웃필요"},
            {"id": "loan", "적용상품": ["대출성"], "판정유형": "확정"},
            {"id": "investment", "적용상품": ["투자성"], "판정유형": "확정"},
        ]
        with patch.object(retrieval.v2_source, "build", return_value=(rows, [])):
            selected, catalog = retrieval.load_scope(include_layout=True)
        self.assertEqual([row["id"] for row in selected], ["common", "loan"])
        self.assertEqual(len(catalog), 3)
        rule = {"required_medium": "레이아웃", "title": "글자 크기"}
        self.assertFalse(runner.automated_input_ready(rule, {"pages": []}))
        self.assertFalse(runner.automated_input_ready(rule, {"pages": [
            {"regions": [{"bbox": [0, 0, 10, 10], "lines": []}]}]}))

    def test_index_identity_changes_with_text_routing_or_vectors(self):
        vectors = np.eye(1, 1024, dtype="float32")
        docs = [{"item_id": "generic", "search_text": "original", "product_groups": ["전체"]}]
        name = retrieval.versioned_rule_index("base", docs, vectors)
        self.assertEqual(name, retrieval.versioned_rule_index("base", docs, vectors.copy()))
        for change in ({"search_text": "changed"}, {"product_groups": ["대출성"]}):
            self.assertNotEqual(name, retrieval.versioned_rule_index("base", [{**docs[0], **change}], vectors))
        self.assertNotEqual(name, retrieval.versioned_rule_index("base", docs, np.roll(vectors, 1)))

    def test_partial_search_results_are_not_success_or_empty_hits(self):
        for response in ({"timed_out": True}, {"_shards": {"failed": 1}}, {"error": "bad query"}):
            with self.assertRaises(RuntimeError):
                retrieval.validate_search_response(response)
        retrieval.validate_search_response({"timed_out": False, "_shards": {"failed": 0}})

    def test_msearch_uses_identical_scope_for_both_channels(self):
        fine = [{"doc_id": "e1", "text_search": "generic text"}]
        import json
        response = {"hits": {"hits": []}, "_shards": {"failed": 0}}
        with patch.object(retrieval, "request", return_value={"responses": [response] * 4}) as request:
            retrieval.hybrid_hits_batch("url", "idx", fine, {"e1": np.eye(1, 1024)[0]},
                                        "예금성", {"mapped"}, 5, ["STYLE", "PROHIBIT"])
        payload = [json.loads(line) for line in request.call_args.args[3].decode().splitlines()]
        bm25 = payload[1]["query"]["bool"]
        dense = payload[3]["query"]["script_score"]["query"]["bool"]
        self.assertEqual(bm25["filter"], dense["filter"])
        self.assertEqual(bm25["must_not"], dense["must_not"])
        self.assertNotIn("knn", payload[3])
        self.assertEqual(payload[3]["sort"][-1], {"item_id": "asc"})
        self.assertEqual(len(payload), 8)
        self.assertEqual(payload[1]["query"]["bool"]["filter"][0]["terms"]["category"], ["STYLE"])
        self.assertEqual(payload[5]["query"]["bool"]["filter"][0]["terms"]["category"], ["PROHIBIT"])

    def test_duplicate_queries_share_search_but_preserve_both_source_ids(self):
        response = {"hits": {"hits": []}}
        fine = [{"doc_id": key, "text_search": "identical"} for key in ("a", "b")]
        with patch.object(retrieval, "request", return_value={"responses": [response] * 2}) as request:
            result = retrieval.hybrid_hits_batch("url", "idx", fine,
                        {key: np.eye(1, 1024)[0] for key in ("a", "b")}, "예금성", set(), 5)
        self.assertEqual(set(result), {"a", "b"})
        self.assertEqual(len(request.call_args.args[3].decode().splitlines()), 4)

    def test_category_floors_preserve_minority_and_redistribute_without_invention(self):
        from rag.retrieval.candidates import balanced_candidates
        rules = {str(i): {"category": category} for i, category in
                 enumerate(["PRESENCE"] * 30 + ["PROHIBIT"] * 15 + ["STYLE"] * 2)}
        rows = [{"item_id": key} for key in rules]
        chosen, audit = balanced_candidates(rows, rules, 30)
        self.assertEqual(len(chosen), 30)
        self.assertEqual(audit["selected_by_category"], {"PRESENCE": 18, "PROHIBIT": 10, "STYLE": 2})
        self.assertEqual(len(audit["deferred_ids"]), 17)
        self.assertEqual(balanced_candidates(rows, rules, 0)[0], [])
        self.assertEqual(balanced_candidates(rows, rules, 100)[0], rows)

    def test_judgment_candidates_have_no_thirty_or_eighty_item_cutoff(self):
        from rag.retrieval.candidates import all_judgment_candidates
        rules = {str(i): {'category': ['PRESENCE', 'PROHIBIT', 'STYLE'][i % 3]} for i in range(121)}
        rows = [{'item_id': key} for key in rules]
        selected, audit = all_judgment_candidates(rows, rules)
        self.assertEqual(selected, rows)
        self.assertEqual(audit['deferred_ids'], [])
        self.assertIsNone(audit['limit'])

    def test_context_queries_preserve_originals_and_never_cross_source_scope(self):
        from rag.retrieval.queries import build_context_queries
        base = {"ad_id": "ad", "product_id": "p", "source_file": "f", "page_no": 1,
                "parent_doc_id": "region"}
        rows = [{**base, "doc_id": "a", "text_search": "조건을 충족하면"},
                {**base, "doc_id": "b", "text_search": "우대금리 적용"}]
        views, audit = build_context_queries(rows)
        self.assertEqual(views[:2], rows)
        self.assertEqual(len(views), 3)
        self.assertEqual(views[-1]["text_search"], "조건을 충족하면\n우대금리 적용")
        self.assertEqual(audit["added"][0]["source_doc_ids"], ["a", "b"])
        for field in ("ad_id", "product_id", "source_file", "page_no", "parent_doc_id"):
            changed = [rows[0], {**rows[1], field: "different"}]
            self.assertEqual(len(build_context_queries(changed)[0]), 2)
        limited, audit = build_context_queries(rows, max_chars=2)
        self.assertEqual(limited, rows)
        self.assertEqual(len(audit["deferred"]), 1)

    def test_context_query_returns_only_original_evidence_to_reranker(self):
        from rag.retrieval.queries import build_context_queries
        base = {"ad_id": "ad", "product_id": "p", "source_file": "f", "page_no": 1,
                "region_id": "r", "parent_doc_id": "parent", "parent_chunk_id": "parent"}
        fine = [{**base, "doc_id": key, "text_search": text, "text_canonical": text, "line_refs": [key]}
                for key, text in (("a", "조건"), ("b", "의무"))]
        views, _ = build_context_queries(fine)
        hit = {"_score": 1, "_source": {"item_id": "rule", "title": "generic", "product_groups": ["전체"]}}
        channels = {row["doc_id"]: {"bm25_nori": [], "bge_m3_exact_cosine": []} for row in views}
        channels[views[-1]["doc_id"]]["bm25_nori"] = [hit]
        # An earlier standalone hit must not erase a later context-query link.
        channels["a"]["bm25_nori"] = [hit]
        with patch.object(retrieval, "hybrid_hits_batch", return_value=channels):
            result = retrieval.discover_prohibitions(views, {}, "예금성", base_url="url", index="idx",
                        per_chunk_k=5, rrf_k=60, deterministic_item_ids=set())
        self.assertEqual({row["trigger"]["doc_id"] for row in result[0]["trigger_evidence"]}, {"a", "b"})
        with patch.object(runner, "dgx_rerank", return_value=np.asarray([0.5])) as rerank:
            runner.rerank_prohibition_candidates(result, rules={"rule": {"category": "PROHIBIT"}},
                fine_documents={row["doc_id"]: row for row in fine}, rrf_k=60, candidate_pool=80)
        self.assertEqual(rerank.call_args.args[0][0][0], "조건\n의무")
