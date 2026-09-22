import json
import tempfile
import unittest
from pathlib import Path

from rag.templates.structured_methodology import (
    SOURCE_TYPE_ASSOCIATION_GUIDANCE,
    compile_extracted_methodologies,
)


class StructuredMethodologyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        specs = (
            ("01_대출성상품-상품명노출", "1. 대출성상품-상품명 노출(심의방법) (1).xlsx", 23),
            ("02_예금성상품-입출식", "12. 예금성상품-입출식 심의방법.xlsx", 4),
            ("03_투자성상품-심의사례", "8. 투자성상품-퇴직연금 심의방법.xlsx", 4),
            ("03_투자성상품-심의사례", "10. 투자성상품-ETF 심의방법.xlsx", 4),
            ("03_투자성상품-심의사례", "11. 투자성상품-ELB 심의방법.xlsx", 4),
        )
        manifest = []
        for group, name, excel_row in specs:
            path = self.root / group / name.replace(".xlsx", ".json")
            path.parent.mkdir(parents=True, exist_ok=True)
            original_hash = f"{excel_row:064x}"
            row = {
                "excel_row": excel_row,
                "구분": "유의사항" if excel_row == 23 else "회사명",
                "예 시 문 구": "표시 예시",
                "적정 판단": "표시된 경우 적정",
                "부적정 / 부적정 판단": (
                    "누락 시 부적정, 한줄에 2개 이상의 대출 유의사항이 줄바꿈없이 나열되는 경우 부적정"
                    if excel_row == 23 else "누락 시 부적정"
                ),
                "부적정 / 안내문구": (
                    "줄바꿈 없이 나열되면 안됩니다(은행연합회 지도사항)."
                    if excel_row == 23 else "기재 바랍니다."
                ),
                "확인필요 / 확인필요 판단": "",
                "확인필요 / 안내문구": "",
            }
            payload = {
                "meta": {"group": group, "name": name, "sha256": original_hash},
                "kind": "xlsx",
                "sheets": [{"title": "Sheet2", "structured": {"records": [row]}}],
            }
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            manifest.append({"group": group, "name": name, "sha256": original_hash})
        (self.root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
        )
        answer = self.root / "03_투자성상품-심의사례" / "8. 투자성상품-퇴직연금(심의정답).md"
        answer.write_text(
            """### p.1
```text
금융투자상품이 언급된 경우 퇴직연금 유의사항에 상품 유의사항을 더합니다.
로고 병기 의무는 없습니다.
펀드 단독 광고용 템플릿을 별도로 제작합니다.
```
### p.2
```text
사례 판단과 정답은 절대로 읽으면 안 됩니다.
```
""",
            encoding="utf-8",
        )

    def test_compiler_keeps_answer_rows_out_and_builds_scope_policy(self):
        document = compile_extracted_methodologies(self.root)
        self.assertEqual(document["counts"]["methodology_rules"], 5)
        self.assertFalse(document["policy"]["case_answer_judgments_loaded"])
        scope = document["scope_policies"][0]
        self.assertEqual(scope["composition"]["logic"], "ALL_APPLICABLE")
        self.assertFalse(scope["deposit_protection_logo"]["required"])
        self.assertFalse(scope["source"]["case_answer_rows_loaded"])
        self.assertNotIn("사례 판단", json.dumps(document, ensure_ascii=False))

    def test_association_guidance_is_one_shared_line_rule(self):
        document = compile_extracted_methodologies(self.root)
        loan = next(row for row in document["rules"] if row["rule_id"] == "MTH-LOAN-NAMED-R23")
        self.assertIn(SOURCE_TYPE_ASSOCIATION_GUIDANCE, loan["source_types"])
        self.assertEqual(loan["decision_route"], "RULE_LINE_STRUCTURE_AND_LLM_MEANING")
        shared = document["shared_rules"][0]
        self.assertEqual(shared["member_rule_ids"], [loan["rule_id"]])
        self.assertEqual(shared["required_input"], "VERIFIED_RENDERED_LINE_STRUCTURE")

    def test_example_is_search_hint_but_never_condition_or_ad_evidence(self):
        document = compile_extracted_methodologies(self.root)
        rule = document["rules"][0]
        self.assertEqual(
            rule["example_policy"],
            "SEMANTIC_RETRIEVAL_HINT_NOT_AN_EXACT_MATCH_OR_EVIDENCE",
        )
        self.assertNotIn(rule["display_example"], rule["applicability"]["criteria"])
        examples = rule["retrieval"]["query_groups"]["positive_semantic_examples"]
        self.assertEqual(examples[0]["text"], rule["display_example"])
        self.assertFalse(examples[0]["exact_match_required"])
        self.assertFalse(examples[0]["can_serve_as_advertisement_evidence"])
        self.assertFalse(rule["retrieval"]["template_text_is_evidence"])
        self.assertTrue(rule["retrieval"]["outcome_requires_advertisement_evidence"])

    def test_cross_product_wording_is_not_silently_activated(self):
        deposit_path = (
            self.root / "02_예금성상품-입출식" / "12. 예금성상품-입출식 심의방법.json"
        )
        data = json.loads(deposit_path.read_text(encoding="utf-8"))
        row = data["sheets"][0]["structured"]["records"][0]
        row["부적정 / 안내문구"] = "대출 유의사항은 한 줄에 함께 쓰지 않습니다(은행연합회 지도사항)."
        deposit_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        document = compile_extracted_methodologies(self.root)
        deposit = next(
            rule for rule in document["rules"] if rule["rule_id"] == "MTH-DEPOSIT-DEMAND-R04"
        )
        self.assertEqual(deposit["issues"], ["SOURCE_SCOPE_TERM_CONFLICT"])
        self.assertEqual(deposit["activation_status"], "SOURCE_REVIEW_REQUIRED")

    def test_leading_guidance_condition_is_an_explicit_trigger(self):
        deposit_path = (
            self.root / "02_예금성상품-입출식" / "12. 예금성상품-입출식 심의방법.json"
        )
        data = json.loads(deposit_path.read_text(encoding="utf-8"))
        row = data["sheets"][0]["structured"]["records"][0]
        row["확인필요 / 확인필요 판단"] = "안내문구 언급 없는 경우"
        row["확인필요 / 안내문구"] = (
            "생성형 AI를 활용한 경우, 생성형 AI 활용 안내를 기재하시기 바랍니다."
        )
        deposit_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        document = compile_extracted_methodologies(self.root)
        deposit = next(
            rule for rule in document["rules"] if rule["rule_id"] == "MTH-DEPOSIT-DEMAND-R04"
        )
        self.assertEqual(
            ["생성형 AI를 활용한 경우"],
            [row["predicate_text"] for row in deposit["applicability"]["triggers"]],
        )
        self.assertNotIn(
            "안내문구 언급 없는 경우",
            [row["predicate_text"] for row in deposit["applicability"]["triggers"]],
        )
        self.assertEqual(
            "EVALUATE_TRIGGERS_BEFORE_OBLIGATIONS", deposit["applicability"]["default"]
        )


if __name__ == "__main__":
    unittest.main()
