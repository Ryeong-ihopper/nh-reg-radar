from __future__ import annotations

import unittest

from rag.parsing.chunking_audit import bm25_fine_coverage, summarize_fine_documents


class ChunkingAuditTests(unittest.TestCase):
    def test_summary_keeps_thresholds_and_source_groups_separate(self):
        rows = [
            {"doc_id": "A", "source_file": "one.png", "text_canonical": "12345",
             "span_status": "parser_line_exact", "line_refs": ["L1"], "table": None},
            {"doc_id": "B", "source_file": "one.png", "text_canonical": "x" * 20,
             "span_status": "selected_text_line_aligned", "line_refs": ["L2"], "table": {}},
            {"doc_id": "C", "source_file": "two.pdf", "text_canonical": "y" * 701,
             "span_status": "parser_line_exact", "line_refs": ["L3"], "table": {"rows": []}},
        ]
        result = summarize_fine_documents(rows)
        self.assertEqual(3, result["overall"]["fine_documents"])
        self.assertEqual(2, result["overall"]["thresholds"]["at_most_20"])
        self.assertEqual(1, result["overall"]["thresholds"]["over_700"])
        self.assertEqual(701, result["overall"]["characters"]["maximum"])
        self.assertEqual(2, result["by_source_file"]["one.png"]["fine_documents"])
        self.assertEqual("C", result["over_700_documents"][0]["doc_id"])

    def test_bm25_coverage_only_counts_fine_documents(self):
        rows = [{"doc_id": "A"}, {"doc_id": "B"}]
        channels = {
            "A": {"bm25_nori": [{"_id": "R1"}]},
            "B": {"bm25_nori": []},
            "QUERY-CONTEXT-1": {"bm25_nori": []},
        }
        result = bm25_fine_coverage(rows, channels)
        self.assertEqual(2, result["fine_documents"])
        self.assertEqual(1, result["bm25_empty"])
        self.assertEqual(0.5, result["bm25_empty_rate"])
        self.assertEqual(["B"], result["bm25_empty_doc_ids"])

    def test_bm25_coverage_rejects_missing_fine_rows(self):
        with self.assertRaisesRegex(ValueError, "missing fine document ids"):
            bm25_fine_coverage([{"doc_id": "A", "text_search": "정상 질의"}], {})

    def test_bm25_coverage_records_one_character_rows_as_unsearchable(self):
        result = bm25_fine_coverage([{"doc_id": "A", "text_search": "금"}], {})
        self.assertEqual(1, result["bm25_empty"])
        self.assertEqual(1, result["bm25_unsearchable_too_short"])
        self.assertEqual(["A"], result["bm25_unsearchable_too_short_doc_ids"])


if __name__ == "__main__":
    unittest.main()
