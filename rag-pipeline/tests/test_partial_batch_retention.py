"""Synthetic partial failures retain validated neighbors and every call audit."""
import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tools')]
import run_gemma_exhaustive_dgx as gemma  # noqa: E402
from test_operational_rag_contracts import request_row, result  # noqa: E402
from rag.judgment.runtime_metrics import judgment_call_metrics  # noqa: E402


def response(row, values):
    parsed = {'ad_id': row['ad_id'], 'results': values}
    return {'request_id': row['request_id'], 'ad_id': row['ad_id'], 'category': row['category'],
            'parsed': parsed, 'validation_errors': gemma.validate(row, parsed)}


def test_valid_neighbors_are_not_recalled_and_checkpoint_order_is_preserved():
    row = request_row(['X-A', 'X-B', 'X-C'])
    values = [result(item) for item in row['requested_item_ids']]
    values[1]['requirement_checks'][0]['evidence_line_refs'] = ['UNKNOWN']
    before = copy.deepcopy(values)

    def call(current, *args):
        ids = current['requested_item_ids']
        return response(current, copy.deepcopy(values) if len(ids) == 3 else [result('X-B')])

    with patch.object(gemma, 'call_once', side_effect=call) as model, patch.object(
        gemma, 'focus_unresolved_source_checks', wraps=gemma.focus_unresolved_source_checks
    ) as focus:
        rows = gemma.call_with_retry_and_split(row, None, None, 'mock', 100)
    assert [call.args[0]['requested_item_ids'] for call in model.call_args_list] == [
        ['X-A', 'X-B', 'X-C'], ['X-B']]
    assert gemma.logical_request_complete(row, rows)
    final = [value for batch in rows for value in batch['parsed']['results']]
    assert final[0] == before[0] and final[2] == before[2]
    assert judgment_call_metrics(rows)['physical_calls'] == 2
    assert judgment_call_metrics(rows)['failed_contract_calls'] == 1
    assert [call.args[0]['requested_item_ids'] for call in focus.call_args_list] == [
        ['X-A', 'X-C'], ['X-B']]


def test_global_identity_errors_are_not_salvaged():
    row = request_row(['X-A', 'X-B'])
    good = response(row, [result('X-A'), result('X-B')])
    variants = []
    for ids in (['X-A', 'X-A'], ['X-B', 'X-A'], ['X-A'], ['X-A', 'UNKNOWN']):
        variants.append(response(row, [result(item) for item in ids]))
    wrong_ad = copy.deepcopy(good)
    wrong_ad['parsed']['ad_id'] = 'OTHER'
    variants.append(wrong_ad)
    for value in variants:
        assert gemma.validated_batch_items(row, value) == []


def test_rule_evidence_scope_is_not_widened_by_partial_validation():
    row = request_row(['X-A', 'X-B'])
    payload = json.loads(row['messages'][1]['content'])
    payload['documents'].append({'evidence_id': 'E-2', 'line_refs': ['L-2'], 'text': 'other'})
    payload['evidence_scope'] = {
        'X-A': {'evidence_ids': ['E-1'], 'complete_ad_scan': True},
        'X-B': {'evidence_ids': ['E-2'], 'complete_ad_scan': True},
    }
    payload['full_ad_text'] = 'full text of both assets'
    row['messages'][1]['content'] = json.dumps(payload)
    batch = response(row, [result('X-A'), result('X-B')])
    assert gemma.validated_batch_items(row, batch) == ['X-A']
    child = gemma.select_request_items(row, ['X-B'], 'pending')
    narrowed = json.loads(child['messages'][1]['content'])
    assert narrowed['full_ad_text'] == payload['full_ad_text']
    assert [doc['evidence_id'] for doc in narrowed['documents']] == ['E-2']


def test_unresolved_item_is_not_lost_or_reported_complete():
    row = request_row(['X-A', 'X-B'])

    def call(current, *args):
        values = [result(item) for item in current['requested_item_ids']]
        next(value for value in values if value['item_id'] == 'X-B')['applicability'] = 'BROKEN'
        return response(current, values)

    with patch.object(gemma, 'call_once', side_effect=call):
        rows = gemma.call_with_retry_and_split(row, None, None, 'mock', 100)
    assert not gemma.logical_request_complete(row, rows)
    assert gemma.completed_item_ids(rows) == ['X-A']
    assert any(batch['validation_errors'] for batch in rows)
    assert judgment_call_metrics(rows)['physical_calls'] == 4


def test_cpu_partition_preserves_order_without_recalling_model():
    row = request_row(['X-A', 'X-B', 'X-C'])
    with patch.object(gemma, 'calculate_loan_rates', side_effect=lambda payload, rule:
        result('X-B') if rule['item_id'] == 'X-B' else None), patch.object(
        gemma, 'call_once', side_effect=lambda current, *args:
            response(current, [result(item) for item in current['requested_item_ids']])
    ) as model:
        rows = gemma.call_with_retry_and_split(row, None, None, 'mock', 100)
    assert gemma.logical_request_complete(row, rows)
    assert model.call_count == 1
    assert model.call_args.args[0]['requested_item_ids'] == ['X-A', 'X-C']
    assert judgment_call_metrics(rows)['physical_calls'] == 1
