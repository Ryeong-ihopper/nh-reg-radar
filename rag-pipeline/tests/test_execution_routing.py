import unittest

from rag.judgment.execution_routing import (
    compile_special_policy,
    compile_supplemental_item,
    compile_template_item,
)


class ExecutionRoutingTests(unittest.TestCase):
    def test_template_conditions_and_exceptions_are_never_silently_dropped(self):
        row = {
            "번호": "1", "상품유형": "예금", "구분": "금리", "예시문구": "연 3%",
            "적정판단 / 필수여부": "우대금리가 있는 경우 합계를 표시",
            "부적정판단 / 기재요령": "단, 제한 없는 경우 생략 가능",
            "부적정 안내문구": "조건을 확인하세요", "확인필요 판단": "자료가 없는 경우",
            "확인필요 안내문구": "상품 정본 필요", "근거(법령)": "법 제1조",
            "근거(협회 규정)": "협회 기준",
        }
        rule = compile_template_item(row)
        self.assertTrue(rule["applicability"]["triggers"])
        self.assertTrue(rule["applicability"]["exceptions"])
        self.assertEqual(rule["applicability"]["triggers"][0]["allowed_states"], ["TRUE", "FALSE", "UNKNOWN"])
        self.assertEqual(rule["applicability"]["unknown_policy"], "UNDETERMINED_NOT_INAPPLICABLE")
        self.assertFalse(rule["evidence_contract"]["rule_text_is_evidence"])
        self.assertEqual(rule["source_fields"]["example"], "연 3%")
        self.assertTrue(rule["clause_coverage"]["all_nonempty_fields_preserved"])

    def test_example_case_word_is_not_promoted_to_applicability(self):
        row = {
            "번호": "3", "상품유형": "대출", "구분": "유의사항",
            "예시문구": "연체될 경우 모든 원리금을 갚아야 할 수 있습니다.",
            "적정판단 / 필수여부": "필수(O)", "부적정판단 / 기재요령": "누락 시 부적정",
            "부적정 안내문구": "", "확인필요 판단": "", "확인필요 안내문구": "",
            "근거(법령)": "", "근거(협회 규정)": "협회 기준",
        }
        rule = compile_template_item(row)
        self.assertEqual(rule["applicability"]["triggers"], [])
        self.assertEqual(rule["decision"]["route"], "LLM_WITH_RULE_GATES")

    def test_calculation_and_meaning_are_hybrid(self):
        row = {
            "번호": "2", "상품유형": "대출", "구분": "우대금리", "예시문구": "최대 1%",
            "적정판단 / 필수여부": "최대 우대금리 ≤ 조건별 합계이며 설명이 일치",
            "부적정판단 / 기재요령": "계산이 다르면 부적정",
            "부적정 안내문구": "", "확인필요 판단": "", "확인필요 안내문구": "",
            "근거(법령)": "", "근거(협회 규정)": "협회 기준",
        }
        rule = compile_template_item(row)
        self.assertEqual(rule["decision"]["route"], "HYBRID_RULE_LLM")
        self.assertIn("RULE_DETERMINISTIC_CHECK", rule["decision"]["owners"])
        self.assertIn("LLM_SEMANTIC_JUDGMENT", rule["decision"]["owners"])

    def test_supplemental_requires_all_slots_and_atomic_approval(self):
        row = {
            "규칙ID": "C-X", "약칭": "비교", "업권 재검토 상태": "대상 템플릿 관련 후보 유지",
            "코드 담당(설계)": "날짜 비교", "LLM 담당(설계)": "동일 기준 확인",
            "분리할 자료 슬롯": "광고;원자료", "예외·사람검토·보류": "원자료 없으면 보류",
            "발동조건 초안": "비교광고인 경우", "출처": "R-X", "원문 전체 보존": "같은 기준으로 비교",
        }
        rule = compile_supplemental_item(row)
        self.assertEqual(rule["required_input_slots"], ["광고", "원자료"])
        self.assertEqual(rule["obligation"]["logic"], "SOURCE_TEXT_PENDING_ATOMIC_APPROVAL")
        self.assertEqual(rule["release_state"], "STRUCTURED_NOT_OPERATIONALLY_CONNECTED")

    def test_visual_special_rule_is_kept_for_human_review(self):
        rule = compile_special_policy({
            "item_id": "D-240", "execution_tier": "HUMAN_VISUAL_REVIEW",
            "source_fragment": "배경색과 구별", "evidence_trigger_any": [],
        })
        self.assertEqual(rule["decision"]["route"], "HUMAN_VISUAL_REVIEW")
        self.assertIn("HUMAN_VISUAL_REVIEW", rule["decision"]["owners"])


if __name__ == "__main__":
    unittest.main()
