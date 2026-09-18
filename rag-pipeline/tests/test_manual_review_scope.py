import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
from rag.judgment.manual_review import requires_visual_review, deferred_input_reason, text_facet_claim_errors  # noqa: E402
from rag.judgment.reading_quality import needs_reading_review, apply_reading_guard  # noqa: E402
from tools.run_operational_e2e import automated_input_ready  # noqa: E402


class ManualReviewScopeTests(unittest.TestCase):
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
        for rule in [{'category':'STYLE'}, {'required_medium':'레이아웃'},
                     {'category':'PRESENCE','criterion':'글자크기와 색상을 확인한다'},
                     {'category':'PROHIBIT','criterion':'눈에 띄는 폰트로 표시한다'}]:
            with self.subTest(rule=rule):
                self.assertFalse(automated_input_ready(rule, ad))
                self.assertTrue(deferred_input_reason(rule).startswith('시인성은 사람 검토'))

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
