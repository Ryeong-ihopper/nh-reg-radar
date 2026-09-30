# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from rag.judgment.grounding import (  # noqa: E402
    grounded_source_excerpt_present,
    grounding_errors,
    ratio_values,
    ungrounded_source_quotes,
)


ASSET_A = "FILE-AAAA"
ASSET_B = "FILE-BBBB"


def ref(asset, line):
    return f"{asset}::p1/p1_r004/L{line:03d}"


def document(asset, lines, text):
    return {
        "evidence_id": f"{asset}:p1:p1_r004~s001",
        "line_refs": [ref(asset, line) for line in lines],
        "text": text,
    }


class RatioValueTests(unittest.TestCase):
    def test_percent_and_decimal_values_are_extracted(self):
        self.assertEqual(
            ratio_values("우대금리 합계 3.0%p, 최고 연 2.0%"), ["3.0", "2.0"]
        )

    def test_legal_citation_numbers_are_not_values(self):
        self.assertEqual(
            ratio_values("금융소비자 보호에 관한 법률 제22조 제2항 위반"), []
        )

    def test_item_identifiers_are_not_values(self):
        self.assertEqual(ratio_values("D-163 규칙과 R-1745 근거"), [])

    def test_dates_and_counts_are_not_ratio_values(self):
        self.assertEqual(ratio_values("2026.06.18. 심의, 36개월, 1천원"), [])


class NumericGroundingTests(unittest.TestCase):
    """인용한 줄에 없는 수치로 위반을 만들 수 없다."""

    def test_positive_source_quote_must_be_on_the_cited_line_not_its_neighbor(self):
        docs = [{'evidence_id': 'region', 'line_refs': ['first', 'second'],
                 'text': '이벤트 안내\n가상은행 영업점 문의',
                 'line_texts': {'first': '이벤트 안내', 'second': '가상은행 영업점 문의'}}]
        reason = "광고물에 '가상은행'이라는 금융회사 명칭이 표시되어 있습니다."
        self.assertTrue(grounding_errors(item_id='SYNTHETIC', location='O1', reason=reason,
                                        line_refs=['first'], documents=docs))
        self.assertEqual(grounding_errors(item_id='SYNTHETIC', location='O1', reason=reason,
                                         line_refs=['second'], documents=docs), [])

    def test_observed_finding_requires_a_verbatim_excerpt_from_the_cited_line(self):
        docs = [{'evidence_id': 'region', 'line_refs': ['footer', 'review'],
                 'line_texts': {
                     'footer': '계열사/관련사이트',
                     'review': '준법감시인심의번호 2026-4847(2026.09.01 ~2027.08.31.)',
                 }, 'text': '계열사/관련사이트\n준법감시인심의번호 2026-4847(2026.09.01 ~2027.08.31.)'}]
        reason = '준법감시인 심의번호와 유효기간이 표시되어 있습니다.'
        errors = grounding_errors(
            item_id='SYNTHETIC', location='O1', reason=reason,
            line_refs=['footer'], documents=docs, require_source_excerpt=True,
        )
        self.assertTrue(any('직접 인용이 없음' in error for error in errors))
        quoted = "'준법감시인심의번호 2026-4847'이 표시되어 있습니다."
        self.assertEqual(grounding_errors(
            item_id='SYNTHETIC', location='O1', reason=quoted,
            line_refs=['review'], documents=docs, require_source_excerpt=True,
        ), [])
        self.assertTrue(grounded_source_excerpt_present(quoted, docs[0]['line_texts']['review']))

    def test_rule_quote_absence_and_whitespace_are_not_false_source_claims(self):
        for reason, source in [("광고에 '가상 은행'이 기재되어 있습니다.", '가상은행'),
                               ("광고에 '필수 문구'가 기재되어 있지 않습니다.", '다른 문장'),
                               ("규정은 '필수 문구' 표시를 요구합니다.", '다른 문장')]:
            self.assertEqual(ungrounded_source_quotes(reason, source), [])

    def test_observed_quote_does_not_need_an_advertisement_prefix(self):
        for reason in ["'가상은행' 문구가 확인됩니다.", "회사명 '가상은행'이 명시되어 있습니다.",
                       "'표본상품'이라는 이름이 기재되어 있습니다."]:
            self.assertEqual(len(ungrounded_source_quotes(reason, '심의필번호 안내')), 1)
        self.assertEqual(ungrounded_source_quotes("예시에 '가상은행'이 기재되어 있습니다.", '다른 문장'), [])

    def test_each_observed_quote_must_appear_in_the_cited_lines(self):
        reason = "광고에 '표본상품' 및 '표본은행' 명칭이 확인됩니다."
        self.assertEqual(ungrounded_source_quotes(reason, "표본상품"), ["표본은행"])
        self.assertEqual(ungrounded_source_quotes(reason, "표본상품 표본은행"), [])

    def test_explicit_ellipsis_preserves_only_source_ordered_fragments(self):
        source = '상품 가입 전에 설명서와 약관을 읽고 문의하시기 바랍니다.'
        for quote in ['상품 가입 전에...', '상품 가입 전에…문의하시기 바랍니다.', '…약관을 읽고']:
            self.assertEqual(ungrounded_source_quotes(f"예시와 동등한 '{quote}' 문구가 확인됩니다.", source), [])
        for quote in ['다른은행...', '문의하시기...상품 가입', '가입..문구']:
            self.assertEqual(ungrounded_source_quotes(f"'{quote}' 문구가 확인됩니다.", source), [quote])

    def setUp(self):
        self.documents = [
            document(ASSET_A, range(15, 21), "가입금액\n1천원 이상~50만원 이하\n상품과목\n자유로우대적금"),
            document(ASSET_A, range(21, 37), "우대금리\n·최대연3.0%p\n1.0\n0.7\n0.3\n0.3\n0.2\n0.5"),
            document(ASSET_B, range(20, 24), "최저 연 0.5%~최고 연 2.0%"),
        ]

    def test_value_absent_from_cited_lines_is_rejected(self):
        errors = grounding_errors(
            item_id="D-163",
            location="판정 근거",
            reason="우대금리 합계는 3.0%p이나 최고 연 2.0%와 정합하지 않음",
            line_refs=[ref(ASSET_A, 15), ref(ASSET_A, 20)],
            documents=self.documents,
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("2.0", errors[0])
        self.assertIn("3.0", errors[0])

    def test_correctly_cited_values_pass(self):
        self.assertEqual(
            grounding_errors(
                item_id="D-163",
                location="판정 근거",
                reason="우대항목 합계 3.0%p가 최대 연 3.0%p와 일치",
                line_refs=[ref(ASSET_A, 22), ref(ASSET_A, 26)],
                documents=self.documents,
            ),
            [],
        )

    def test_sum_of_cited_values_is_treated_as_grounded(self):
        """산술 검산 규칙은 합계를 계산해 제시하는 것이 정상 동작이다."""
        self.assertEqual(
            grounding_errors(
                item_id="D-163",
                location="판정 근거",
                reason="항목별 1.0+0.7+0.3+0.3+0.2+0.5 합계는 3.0%p로 표기와 다름",
                line_refs=[ref(ASSET_A, 22)],
                documents=self.documents,
            ),
            [],
        )

    def test_coincidental_sum_does_not_ground_an_uncited_value(self):
        """광고에 없는 수치가 우연히 다른 수치들의 합과 같아도 접지가 아니다."""
        errors = grounding_errors(
            item_id="D-163",
            location="판정 근거",
            reason=(
                "우대금리 항목의 합계(1.0 + 0.7 + 0.3 + 0.3 + 0.2 + 0.5 = 3.0%p)는 "
                "표기된 최대 우대금리 3.0%p와 일치하나, 상단 요약 금리(최고 연 2.0%)와 "
                "정합하지 않음"
            ),
            line_refs=[ref(ASSET_A, 22), ref(ASSET_A, 26)],
            documents=self.documents,
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("2.0", errors[0])
        self.assertNotIn("3.0", errors[0])

    def test_missing_line_refs_do_not_trigger_grounding(self):
        """부재(ABSENCE) 위반은 인용 줄이 없을 수 있어 이 검사의 대상이 아니다."""
        self.assertEqual(
            grounding_errors(
                item_id="D-100",
                location="판정 근거",
                reason="광고 전체에 최고 연 2.0% 표기가 없음",
                line_refs=[],
                documents=self.documents,
            ),
            [],
        )

    def test_reason_without_ratio_values_is_not_flagged(self):
        self.assertEqual(
            grounding_errors(
                item_id="C-058",
                location="판정 근거",
                reason="수수료 항목이 기재되지 않음",
                line_refs=[ref(ASSET_A, 15)],
                documents=self.documents,
            ),
            [],
        )


class AssetBoundaryTests(unittest.TestCase):
    """파일 묶음은 함께 검토하고 상품 소유권 경계는 지킨다."""

    def setUp(self):
        self.documents = [
            document(ASSET_A, [22], "·최대연3.0%p"),
            document(ASSET_B, [22], "최저 연 0.5%~최고 연 2.0%"),
        ]

    def test_different_product_numeric_comparison_is_rejected(self):
        self.documents[0]["product_id"] = "P1"
        self.documents[1]["product_id"] = "P2"
        errors = grounding_errors(
            item_id="D-163",
            location="판정 근거",
            reason="우대금리 3.0%p와 최고 연 2.0%가 불일치",
            line_refs=[ref(ASSET_A, 22), ref(ASSET_B, 22)],
            documents=self.documents,
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("P1", errors[0])
        self.assertIn("P2", errors[0])

    def test_same_product_across_files_is_allowed(self):
        self.assertEqual(grounding_errors(
            item_id="RULE", location="basis", reason="3.0%와 2.0% 불일치",
            line_refs=[ref(ASSET_A, 22), ref(ASSET_B, 22)], documents=self.documents,
        ), [])

    def test_numeric_substring_does_not_count_as_observed(self):
        self.assertTrue(grounding_errors(
            item_id="RULE", location="basis", reason="2.0% 오류",
            line_refs=[ref(ASSET_A, 1)], documents=[document(ASSET_A, [1], "12.0%")],
        ))

    def test_equivalent_decimal_representation_is_allowed(self):
        self.assertEqual(grounding_errors(
            item_id="RULE", location="basis", reason="2.00% 오류",
            line_refs=[ref(ASSET_A, 1)], documents=[document(ASSET_A, [1], "2%")],
        ), [])

    def test_incorrect_sum_cannot_use_an_arbitrary_subset(self):
        self.assertTrue(grounding_errors(
            item_id="RULE", location="basis", reason="1.0+0.7+0.3+0.3+0.2+0.5 합계는 2.7%",
            line_refs=[ref(ASSET_A, 1)], documents=[document(ASSET_A, [1], "1.0 0.7 0.3 0.3 0.2 0.5")],
        ))

    def test_single_asset_numeric_comparison_is_allowed(self):
        self.assertEqual(
            grounding_errors(
                item_id="D-163",
                location="판정 근거",
                reason="최저 연 0.5%~최고 연 2.0% 범위가 어긋남",
                line_refs=[ref(ASSET_B, 22)],
                documents=self.documents,
            ),
            [],
        )

    def test_cross_asset_without_numeric_claim_is_allowed(self):
        self.assertEqual(
            grounding_errors(
                item_id="C-058",
                location="판정 근거",
                reason="필수 안내문구가 두 파일 모두에서 누락됨",
                line_refs=[ref(ASSET_A, 22), ref(ASSET_B, 22)],
                documents=self.documents,
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
