"""The offline repair may only publish complete saved metrics-failure results."""
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest

spec = importlib.util.spec_from_file_location('metrics_repair', Path(__file__).resolve().parents[1] / 'scripts/repair-operational-metrics.py')
repair = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repair)


def fixture(tmp_path):
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')
    state_path = tmp_path / 'execution/web-state.json'
    state = {'reviews':[{'review':{'review_id':'REV-SYN','advertisement_id':'ADV-SYN'},
                         'job':{'status':'FAILED'}}], 'links':{'REV-SYN':{'rag_job_id':'JOB-SYN'}}}
    write(state_path, state)
    job = tmp_path / 'execution/rag-jobs/JOB-SYN'
    write(job / 'status.json', {'attempt':1, 'status':'FAILED'})
    (job / 'attempt-1-pipeline.log').write_text(
        'judgment_call_metrics\nValueError: conflicting model call audit: synthetic', encoding='utf-8')
    result = {'ads':[{'ad_id':'ADV-SYN', 'candidates':[{'item_id':'SYN','status':'predicted'}]}],
              'counts':{'output_failures':0,'requested_pairs':1,'predicted_pairs':1}, 'output_failure_pairs':[]}
    write(job / 'attempt-1/04_operational_results.json', result)
    write(job / 'attempt-1/02_judgment_requests.jsonl', {'ad_id':'ADV-SYN','requested_item_ids':['SYN']})
    return state_path, state, job, result


def test_inspection_is_read_only_and_requires_matching_complete_pairs(tmp_path):
    state_path, state, job, result = fixture(tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    with patch.object(repair, 'validate_operational_result') as validate:
        repair.inspect_completed_metrics_failure(tmp_path, 'REV-SYN')
        validate.assert_called_once_with(result)
        result['ads'][0]['candidates'][0]['item_id'] = 'OTHER'
        (job / 'attempt-1/04_operational_results.json').write_text(json.dumps(result), encoding='utf-8')
        with pytest.raises(ValueError, match='incomplete'):
            repair.inspect_completed_metrics_failure(tmp_path, 'REV-SYN')
    assert state_path.read_bytes() == before[state_path]
    assert (job / 'status.json').read_bytes() == before[job / 'status.json']


def test_unrelated_failure_and_active_review_are_not_repaired(tmp_path):
    state_path, state, job, result = fixture(tmp_path)
    (job / 'attempt-1-pipeline.log').write_text('model connection failure', encoding='utf-8')
    with pytest.raises(ValueError, match='not the supported'):
        repair.inspect_completed_metrics_failure(tmp_path, 'REV-SYN')
    state['reviews'][0]['job']['status'] = 'RUNNING'
    state_path.write_text(json.dumps(state), encoding='utf-8')
    with pytest.raises(ValueError, match='Active'):
        repair.inspect_completed_metrics_failure(tmp_path, 'REV-SYN')
