from __future__ import annotations

import unittest

from rag.judgment.canonical_arithmetic import calculate_explicit_arithmetic


def payload(text: str):
    return {
        "parser_coverage": "READY", "reading_quality": {},
        "evidence_scope": {"D-163": {"evidence_ids": ["E1"], "complete_ad_scan": True}},
        "documents": [{"evidence_id": "E1", "line_refs": ["L1"],
                       "line_texts": {"L1": text}, "text_selection": {}}],
    }


RULE = {
    "item_id": "D-163",
    "condition_contract": {
        "scope_ref": "SCOPE",
        "applicability_conditions": [
            {"condition_id": "A1"}, {"condition_id": "A2"},
        ],
        "obligation_checks": [{
            "obligation_id": "O1", "text": "같은 기준의 계산이 일치하는가",
            "deterministic_adapter": {"kind": "ADVERTISED_ARITHMETIC_CONSISTENCY"},
        }],
    },
}


class CanonicalArithmeticTests(unittest.TestCase):
    def test_explicit_equation_is_calculated(self):
        result = calculate_explicit_arithmetic(payload("기본 2.5% + 우대 1.5% - 할인 0.5% = 최종 3.5%"), RULE)
        self.assertEqual("COMPLIANT", result["verdict"])
        self.assertEqual(["L1"], result["evidence_line_refs"])

    def test_mismatch_is_violation_with_reproducible_witness(self):
        result = calculate_explicit_arithmetic(payload("2.5%+1.5%-0.5%=4.0%"), RULE)
        self.assertEqual("VIOLATION", result["verdict"])
        self.assertIn("2.5+1.5-0.5 != 4.0", result["reason"])

    def test_unrelated_numbers_do_not_activate_arithmetic(self):
        result = calculate_explicit_arithmetic(payload("최고 2%, 기본 0.1%, 1인당 1억원"), RULE)
        self.assertEqual("NOT_APPLICABLE", result["verdict"])
        self.assertEqual("NOT_MATCHED", result["scope_check"]["status"])

    def test_visible_but_unparseable_calculation_is_reviewed_without_llm_guess(self):
        result = calculate_explicit_arithmetic(payload("우대금리 합계 1.5% 최대 우대금리 2.0%"), RULE)
        self.assertEqual("UNDETERMINED", result["verdict"])
        self.assertEqual(["L1"], result["evidence_line_refs"])
        self.assertTrue(result["needs_researcher_review"])

    def test_incomplete_scan_is_deterministically_undetermined(self):
        value = payload("2%+1%=3%")
        value["parser_coverage"] = "PARTIAL"
        result = calculate_explicit_arithmetic(value, RULE)
        self.assertEqual("UNDETERMINED", result["verdict"])


if __name__ == "__main__":
    unittest.main()
