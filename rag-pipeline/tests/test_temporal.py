import unittest
from rag.judgment.temporal import basis_date_observations, temporal_claim_errors
from rag.judgment.condition_contracts import compile_condition_contract


class TemporalTests(unittest.TestCase):
    def payload(self, printed='2026.04.01.기준'):
        rule={'item_id':'SYNTHETIC','question':'기준일 표시','criterion':'금리와 세전 표시. 기준일자 : 검토시점 14일 이내'}
        rule['condition_contract']=compile_condition_contract(rule)
        return {'rules':[rule], 'review_context':{'review_date':'2026-04-15'},
                'documents':[{'evidence_id':'E-A','line_refs':['L-A'],
                    'line_texts':{'L-A':printed},'text':printed}]}

    def result(self):
        return {'item_id':'SYNTHETIC','requirement_checks':[{'obligation_ref':'O2','status':'SATISFIED',
                'evidence_ids':['E-A'],'evidence_line_refs':['L-A']}]}

    def test_source_window_is_a_separate_required_check(self):
        checks=self.payload()['rules'][0]['condition_contract']['obligation_checks']
        self.assertEqual([x['obligation_id'] for x in checks],['O1','O2'])
        self.assertEqual(checks[1]['text'],'기준일자 : 검토시점 14일 이내')

    def test_window_boundary_positive_negative_future_and_no_date(self):
        for printed,valid in [('2026.04.02.기준',True),('2026.04.01.기준',True),
                              ('2026.03.31.기준',False),('2026.04.16.기준',False),
                              ('2026.02.30.기준',False),('검토등록 2026.04.15',False)]:
            with self.subTest(printed=printed):
                self.assertEqual(not temporal_claim_errors(self.payload(printed),self.result()),valid)

    def test_uncertain_wrong_citation_and_missing_review_date_cannot_establish_compliance(self):
        payload=self.payload()
        payload['documents'][0]['text_selection']={'needs_review':True}
        self.assertTrue(temporal_claim_errors(payload,self.result()))
        payload=self.payload()
        payload['review_context']={}
        self.assertTrue(temporal_claim_errors(payload,self.result()))
        result=self.result()
        result['requirement_checks'][0]['evidence_line_refs']=['unrelated']
        self.assertTrue(temporal_claim_errors(self.payload(),result))

    def test_short_year_and_registration_date_are_not_confused(self):
        payload=self.payload("기본금리 1%('26.04.01.기준), 등록일 2026.04.15")
        observations=basis_date_observations(payload['documents'],'2026-04-15')
        self.assertEqual([(x['basis_date'],x['elapsed_days']) for x in observations],[('2026-04-01',14)])
        payload=self.payload('금리 (2026.04.01. 당행 기준금리 1%)')
        self.assertEqual(len(basis_date_observations(payload['documents'],'2026-04-15')),1)

    def test_known_calendar_outcome_cannot_be_replaced_by_abstention(self):
        result = self.result()
        result['applicability'] = 'APPLICABLE'
        result['requirement_checks'][0]['status'] = 'UNDETERMINED'
        self.assertTrue(temporal_claim_errors(self.payload('2026.03.31.기준'), result))
        self.assertTrue(temporal_claim_errors(self.payload('2026.04.01.기준'), result))
        self.assertEqual(temporal_claim_errors(self.payload('날짜 미확인'), result), [])

    def test_dropping_date_citation_cannot_evade_known_scoped_window(self):
        result = self.result()
        result['applicability'] = 'APPLICABLE'
        check = result['requirement_checks'][0]
        check.update(status='UNDETERMINED', evidence_ids=[], evidence_line_refs=[])
        payload = self.payload('2026.03.31.기준')
        self.assertTrue(temporal_claim_errors(payload, result))
        payload['evidence_scope'] = {'SYNTHETIC': {'evidence_ids': ['other']}}
        self.assertEqual(temporal_claim_errors(payload, result), [])
        payload.pop('evidence_scope')
        payload['documents'].append({'evidence_id': 'E-B', 'line_refs': ['L-B'],
                                    'line_texts': {'L-B': '2026.04.01.기준'}})
        self.assertEqual(temporal_claim_errors(payload, result), [])
