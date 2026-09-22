import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from rag.judgment.manual_review import (  # noqa: E402
    attach_visual_retrieval_evidence,
    deferred_input_reason,
    has_text_decision_facet,
    partition_visual_review_candidates,
    requires_visual_review,
    text_facet_claim_errors,
)
from rag.judgment.reading_quality import needs_reading_review, apply_reading_guard  # noqa: E402
from tools.run_operational_e2e import automated_input_ready  # noqa: E402


class ManualReviewScopeTests(unittest.TestCase):
    def test_canonical_text_obligation_is_not_demoted_by_legacy_style_category(self):
        rule = {
            'category': 'STYLE', 'required_medium': '레이아웃',
            'canonical_execution_plan': {'obligations': [{
                'owners': {'rule': False, 'llm': True, 'external_input': False, 'human': False},
            }]},
        }
        self.assertFalse(requires_visual_review(rule))

    def test_visual_review_keeps_trigger_regions_for_reviewer(self):
        manual = [{'item_id': 'V-1', 'reason': 'human'}]
        trigger = [{
            'item_id': 'V-1',
            'score': 0.9,
            'trigger_evidence': [{'trigger': {'doc_id': 'line-7'}}],
        }]
        enriched = attach_visual_retrieval_evidence(manual, trigger)
        self.assertEqual(
            enriched[0]['trigger_evidence'][0]['trigger']['doc_id'],
            'line-7',
        )
        self.assertEqual(enriched[0]['retrieval_score'], 0.9)

    def test_text_facet_rejects_visual_conclusions_but_preserves_text_and_abstention(self):
        rule = {'item_id': 'SYNTHETIC', 'source_sheet': 'HWPX_TEMPLATE',
                'template_basis': {'text_facet_only': True}}
        for requirement, status, rejected in [
            ('한 줄에 두 문구 배치 불가', 'VIOLATED', False),
            ('문구의 글자 크기를 확인', 'SATISFIED', True),
            ('안내 로고 필수', 'SATISFIED', True),
            ('같은 줄 배치 여부', 'UNDETERMINED', False),
            ('중도해지 우대금리 제외 안내', 'VIOLATED', False),
            ('부대비용과 전년 대비 차이 안내', 'SATISFIED', False),
        ]:
            result = {'item_id': 'SYNTHETIC', 'requirement_checks': [
                {'requirement': requirement, 'status': status}]}
            with self.subTest(requirement=requirement):
                self.assertEqual(bool(text_facet_claim_errors({'rules': [rule]}, result)), rejected)
                self.assertEqual(text_facet_claim_errors({'rules': []}, result), [])

    def test_visual_rules_always_manual_even_when_measurements_arrive(self):
        ad = {'pages':[{'regions':[{'bbox':[0,0,100,100], 'visibility':{'contrast_ratio':7},
            'lines':[{'style':{'size_pt':12},'bbox':[0,0,20,10]}]}]}]}
        for rule in [{'required_medium':'레이아웃'},
                      {'category':'PRESENCE','criterion':'글자크기와 색상을 확인한다'},
                      {'category':'PROHIBIT','criterion':'눈에 띄는 폰트로 표시한다'}]:
            with self.subTest(rule=rule):
                self.assertFalse(automated_input_ready(rule, ad))
                self.assertTrue(deferred_input_reason(rule).startswith('시인성은 사람 검토'))

    def test_text_style_taxonomy_does_not_force_visual_review(self):
        rule = {
            'category': 'STYLE',
            'required_medium': '텍스트',
            'criterion': '표시문구를 본문과 동일한 언어로 표시한다.',
        }
        self.assertFalse(requires_visual_review(rule))
        self.assertTrue(automated_input_ready(rule))

    def test_discovered_visual_rule_is_preserved_for_human_review(self):
        rules = {
            'TEXT': {'item_id': 'TEXT', 'title': '문구', 'category': 'PRESENCE',
                     'required_medium': '텍스트'},
            'VISUAL': {'item_id': 'VISUAL', 'title': '배경 대비', 'question': '배경과 구별되는가?',
                       'category': 'STYLE', 'required_medium': '레이아웃'},
        }
        automated, manual = partition_visual_review_candidates(
            ['TEXT', 'VISUAL'], rules
        )
        self.assertEqual(automated, ['TEXT'])
        self.assertEqual([row['item_id'] for row in manual], ['VISUAL'])
        self.assertEqual(manual[0]['facet'], 'VISUAL_OR_STRUCTURE')
        self.assertIn('사람 검토', manual[0]['reason'])

    def test_layout_row_with_complete_text_decision_branch_is_judged_as_text(self):
        rule = {
            'category': 'PRESENCE',
            'required_medium': '레이아웃',
            'input_requirement': '광고물+랜딩캡처',
            'question': '심의주체·번호·유효기간을 쉽게 인식할 수 있도록 표시하였는가?',
            'criterion': (
                "'○○사 준법감시인 심의필 제○○호(유효기간)' 형식으로 "
                '심의주체·번호·유효기간이 모두 표시되면 충족.'
            ),
        }
        ad = {'document': {'routing_metadata': {'media_type': {
            'value': 'WEB_PRODUCT_PAGE', 'status': 'provided'}}}, 'pages': []}
        self.assertTrue(has_text_decision_facet(rule))
        self.assertFalse(requires_visual_review(rule))
        self.assertTrue(automated_input_ready(rule, ad))

        visual = {**rule, 'criterion': '심의번호를 본문보다 큰 글자 크기로 표시하면 충족.'}
        self.assertFalse(has_text_decision_facet(visual))
        self.assertTrue(requires_visual_review(visual))

        conditional_visual = {**rule, 'criterion': (
            "필수 경고문구가 표시되면 충족. 여신금융회사 광고는 "
            '본문과 구별되는 차별화표기로 표시되어야 충족.')}
        self.assertFalse(has_text_decision_facet(conditional_visual))
        self.assertTrue(requires_visual_review(conditional_visual))

        first_landing = {**rule, 'criterion': (
            '생략된 의무표시사항이 연결되는 첫 번째 웹페이지에 모두 기재되면 충족.')}
        self.assertFalse(has_text_decision_facet(first_landing))
        self.assertTrue(requires_visual_review(first_landing))

    def test_text_comparison_is_not_color_contrast(self):
        rule={'category':'PROHIBIT','required_medium':'텍스트','criterion':'기존 금리 대비 우대를 설명한다'}
        self.assertFalse(requires_visual_review(rule))
        self.assertTrue(automated_input_ready(rule))

    def test_decode_damage_and_parser_flags_require_review(self):
        for value in [{'text':'가입 \ufffd 기간'}, {'final_text':'안내\x00문'},
                      {'text_selection':{'needs_review':True}}]:
            self.assertTrue(needs_reading_review(value))
        self.assertFalse(needs_reading_review({'text':'가입 기간은 12개월입니다.'}))

    def test_broken_evidence_does_not_cancel_independent_observation(self):
        payload={'documents':[{'evidence_id':'bad','line_refs':['bad-line'],'text':'\ufffd'},
            {'evidence_id':'good','line_refs':['good-line'],'text':'정상 문구'}],
            'evidence_scope':{'R':{'evidence_ids':['bad','good'],'complete_ad_scan':False}}}
        result={'item_id':'R','applicability':'APPLICABLE','applicability_evidence_ids':['good'],
            'applicability_evidence_line_refs':['good-line'],'verdict':'VIOLATION',
            'requirement_checks':[
                {'status':'VIOLATED','finding_basis':'OBSERVED','evidence_ids':['good'], 'evidence_line_refs':['good-line'],'reason':'독립 위반'},
                {'status':'SATISFIED','finding_basis':'OBSERVED','evidence_ids':['bad'],'evidence_line_refs':['bad-line'],'reason':'원문 확인'}]}
        value={'results':[copy.deepcopy(result)]}
        audit=apply_reading_guard(payload,value)
        self.assertEqual(len(audit),1)
        self.assertEqual(value['results'][0]['verdict'],'VIOLATION')
        self.assertEqual(value['results'][0]['requirement_checks'][1]['status'],'UNDETERMINED')
        self.assertTrue(value['results'][0]['needs_researcher_review'])


if __name__ == '__main__':
    unittest.main()
