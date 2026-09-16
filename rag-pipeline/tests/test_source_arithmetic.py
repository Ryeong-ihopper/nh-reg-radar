"""Synthetic positive/negative/boundary cases; no advertisement answer fixture."""
import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from rag.judgment.arithmetic import calculate_loan_rates, METHOD
from run_gemma_exhaustive_dgx import call_with_retry_and_split, validate


def fixture():
    criterion = '금리 산식 및 우대조건별 합계 일치, 계산 예시 정합 확인'
    rule = {'item_id': 'SYN-MATH', 'category': 'PROHIBIT', 'question': '산술 관계가 일치하는가?',
            'criterion': criterion, 'condition_contract': {
                'schema_version': 'rule-applicability-contract-v2',
                'scope_ref': 'SCOPE', 'applicability_mode': 'SOURCE_SCOPED',
                'applicability_conditions': [], 'review_conditions': [],
                'obligation_checks': [{'obligation_id': 'O1', 'text': criterion}]}}
    lines = {'ASSET::p1/r/L1': '대출금리 | 최저 연 5.9% ~ 최대 연 6.5% (2026.01.02. 기준금리(6개월변동) 연 4.1%, 가산금리 2.4%, 우대금리 0.6%p 적용시)',
             'ASSET::p1/r/L2': '우대금리 | 최대 0.6%p (2026.01.02.현재, 급여이체 0.1%p, 적금 매월 40만원 0.3%p(15만원이하는 0.2%p), 앱 이용 0.2%p)'}
    payload = {'ad_id': 'SYN', 'rules': [rule], 'parser_coverage': 'READY',
               'evidence_scope': {'SYN-MATH': {'evidence_ids': ['E'], 'complete_ad_scan': True}},
               'documents': [{'evidence_id': 'E', 'asset_id': 'ASSET', 'product_id': 'P',
                   'line_refs': list(lines), 'line_texts': lines, 'text': '\n'.join(lines.values()),
                   'span_status': 'parser_line_exact', 'text_selection': {'needs_review': False}}]}
    return payload, rule


def edit(payload, before, after):
    doc = payload['documents'][0]
    doc['line_texts'] = {ref: text.replace(before, after) for ref, text in doc['line_texts'].items()}
    doc['text'] = '\n'.join(doc['line_texts'].values())


def request(payload):
    return {'request_id': 'SYN:PROHIBIT:1', 'ad_id': 'SYN', 'category': 'PROHIBIT',
            'requested_item_ids': [r['item_id'] for r in payload['rules']],
            'messages': [{'role': 'system', 'content': ''},
                         {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}]}


def test_decimal_sum_alternative_tier_and_exact_source_refs():
    payload, rule = fixture()
    before = copy.deepcopy(payload)
    result = calculate_loan_rates(payload, rule)
    assert result['verdict'] == 'COMPLIANT'
    assert '0.1+0.3+0.2 = 0.6' in result['reason']
    assert result['evidence_line_refs'] == list(payload['documents'][0]['line_texts'])
    assert payload == before
    assert validate(request(payload), {'ad_id': 'SYN', 'results': [result]}) == []


@pytest.mark.parametrize(('before', 'after'), [('5.9%', '5.8%'), ('6.5%', '6.6%'),
    ('급여이체 0.1%p', '급여이체 0.15%p'), ('최대 0.6%p', '최대 0.7%p')])
def test_actual_mismatch_is_violation_with_a_source_witness(before, after):
    payload, rule = fixture()
    edit(payload, before, after)
    result = calculate_loan_rates(payload, rule)
    assert result['verdict'] == 'VIOLATION'
    assert '!=' in result['reason']
    assert validate(request(payload), {'ad_id': 'SYN', 'results': [result]}) == []


@pytest.mark.parametrize(('before', 'after'), [
    ('15만원이하는', '45만원이하는'), ('15만원이하는 0.2', '15만원이하는 0.4'),
    ('15만원이하는', '추가우대'), ('앱 이용', '다른 항목과 중복 불가 앱 이용'),
    ('급여이체 0.1%p', '택일 급여이체 0.1%p'), ('현재', '현재, 별도 혜택'),
    ('최대 0.6%p', '최대 0.6%p 또는 0.8%p'), ('우대금리 0.6%p 적용시', '우대금리 확인 필요'),
    ('앱 이용 0.2%p', '앱 이용 0.2%p ※ 예시 수취이자 500원'),
    ('앱 이용 0.2%p', '앱 이용 0.2%p, 2026.01.03.'),
])
def test_unsupported_or_conflicting_conditions_abstain(before, after):
    payload, rule = fixture()
    edit(payload, before, after)
    assert calculate_loan_rates(payload, rule) is None


@pytest.mark.parametrize('boundary', ['partial', 'uncertain', 'scope', 'external', 'compound', 'different_asset', 'different_product', 'corruption'])
def test_safety_boundaries(boundary):
    payload, rule = fixture()
    if boundary == 'partial':
        payload['parser_coverage'] = 'PARTIAL'
    elif boundary == 'uncertain':
        payload['documents'][0]['text_selection']['needs_review'] = True
    elif boundary == 'scope':
        payload['evidence_scope']['SYN-MATH']['complete_ad_scan'] = False
    elif boundary == 'external':
        rule['condition_contract']['review_conditions'] = [{'condition_id': 'U1'}]
    elif boundary == 'compound':
        rule['condition_contract']['obligation_checks'].append({'obligation_id': 'O2', 'text': '기준일 30일 이내'})
    elif boundary == 'corruption':
        edit(payload, '앱 이용', '\ufffd')
    else:
        doc = copy.deepcopy(payload['documents'][0])
        doc['evidence_id'] = 'E2'
        doc['asset_id' if boundary == 'different_asset' else 'product_id'] = 'OTHER'
        payload['documents'].append(doc)
        payload['evidence_scope']['SYN-MATH']['evidence_ids'].append('E2')
    assert calculate_loan_rates(payload, rule) is None


def test_cpu_completes_without_any_model_call():
    payload, _ = fixture()
    with patch('run_gemma_exhaustive_dgx.call_with_retry', side_effect=AssertionError('GPU called')):
        result = call_with_retry_and_split(request(payload), None, None, 'unused', 1)[0]
    assert result['decision_source'] == METHOD
    assert result['usage']['total_tokens'] == 0
    assert result['parsed']['results'][0]['verdict'] == 'COMPLIANT'


def test_conditional_surcharge_without_displayed_total_is_not_a_missing_formula():
    payload, rule = fixture()
    edit(payload, '적용시)', '적용시) ※ 한도대출의 경우 0.7%p 가산됨')
    assert calculate_loan_rates(payload, rule)['verdict'] == 'COMPLIANT'
    edit(payload, '가산됨', '가산됨, 최저금리 6.6%')
    assert calculate_loan_rates(payload, rule) is None


def test_mixed_batch_keeps_non_arithmetic_rules_in_one_model_request():
    payload, _ = fixture()
    for index in range(3):
        rule = copy.deepcopy(payload['rules'][0])
        rule['item_id'] = f'SYN-OTHER-{index}'
        rule['question'] = '다른 요건'
        payload['rules'].append(rule)
        payload['evidence_scope'][rule['item_id']] = copy.deepcopy(payload['evidence_scope']['SYN-MATH'])
    response = {'validation_errors': [], 'parsed': {'ad_id': 'SYN', 'results': []}}
    with patch('run_gemma_exhaustive_dgx.call_with_retry', return_value=response) as model:
        outputs = call_with_retry_and_split(request(payload), None, None, 'unused', 1)
    assert model.call_count == 1
    assert model.call_args.args[0]['requested_item_ids'] == [f'SYN-OTHER-{i}' for i in range(3)]
    assert outputs[0]['decision_source'] == METHOD


def test_saved_projection_replaces_abstention_and_keeps_original_immutable():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
    from operational_locations import saved_workspace
    payload, _ = fixture()
    raw = {'ads': [{'ad_id': 'SYN', 'candidates': [{'item_id': 'SYN-MATH', 'judgment': {
        'verdict': 'UNDETERMINED', 'reason': '계산 확인 필요', 'evidence_line_refs': []}}]}]}
    before = copy.deepcopy(raw)
    result = saved_workspace(raw, [payload], {'pages': []}, 'SYN')['rows'][0]
    assert result['verdict'] == '충족'
    assert result['decision_trace']['decision_source'] == METHOD
    assert len(result['evidence_line_refs']) == 2
    assert result['evidence_locations'] == []  # HWP text does not invent geometry.
    assert raw == before


def test_response_loading_preserves_cpu_provenance(tmp_path):
    from model_result_io import load_results
    from run_operational_e2e import decision_trace
    payload, _ = fixture()
    rows = call_with_retry_and_split(request(payload), None, None, 'unused', 1)
    path = tmp_path / 'responses.json'
    path.write_text(json.dumps({'rows': rows}), encoding='utf-8')
    results, sources = load_results([path])
    pair = ('SYN', 'SYN-MATH')
    assert decision_trace(results[pair], sources[pair])['decision_source'] == METHOD


def test_inconsistent_or_unsupported_cost_share_blocks_whole_item_pass():
    payload, rule = fixture()
    doc = payload['documents'][0]
    ref = 'ASSET::p1/r/L3'
    doc['line_refs'].append(ref)
    doc['line_texts'][ref] = '인지세 고객 부담 40%: 10만원(고객부담 4만원)'
    assert calculate_loan_rates(payload, rule)['verdict'] == 'COMPLIANT'
    doc['line_texts'][ref] = '인지세 고객 부담 40%: 10만원(고객부담 5만원)'
    assert calculate_loan_rates(payload, rule) is None
    doc['line_texts'][ref] = '인지세 고객 부담 40%: 10만원(고객부담 4만원), 추가 고객 부담 1만원'
    assert calculate_loan_rates(payload, rule) is None
