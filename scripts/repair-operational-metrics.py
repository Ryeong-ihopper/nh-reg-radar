"""Restore a completed review failed ONLY by legacy call metrics; no AI calls.

Stop the local web server first. The default is read-only inspection; --apply
backs up state and restores the already saved result, without changing verdicts.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'rag-pipeline'), str(ROOT / 'scripts')]
from rag.contracts.validation import validate_operational_result  # noqa: E402


def inspect_completed_metrics_failure(state_dir, review_id):
    state_path = state_dir / 'execution/web-state.json'
    state = json.loads(state_path.read_text(encoding='utf-8'))
    if any(r['job']['status'] in {'PENDING', 'RUNNING', 'RETRY_PENDING', 'STALE'} for r in state['reviews']):
        raise ValueError('Active web jobs exist; wait for completion first')
    bundle = next(r for r in state['reviews'] if r['review']['review_id'] == review_id)
    if bundle['job']['status'] not in {'FAILED', 'FAILED_FINAL'}:
        raise ValueError('Only a failed review can be repaired')
    link = state['links'][review_id]
    job_dir = state_dir / 'execution/rag-jobs' / link['rag_job_id']
    status = json.loads((job_dir / 'status.json').read_text(encoding='utf-8'))
    attempt = int(status['attempt'])
    log = (job_dir / f'attempt-{attempt}-pipeline.log').read_text(encoding='utf-8')
    if 'judgment_call_metrics' not in log or 'ValueError: conflicting model call audit:' not in log:
        raise ValueError('Failure is not the supported legacy call-metrics conflict')
    run = job_dir / f'attempt-{attempt}'
    final = run / '04_operational_results.json'
    result = json.loads(final.read_text(encoding='utf-8'))
    validate_operational_result(result)
    requests = [json.loads(line) for line in (run / '02_judgment_requests.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    expected = {(r['ad_id'], item) for r in requests for item in r['requested_item_ids']}
    actual = [(a.get('scope_id') or a['ad_id'], c['item_id']) for a in result['ads']
              for field in ('candidates', 'review_candidates', 'excluded_candidates')
              for c in a.get(field, []) if c.get('status') == 'predicted']
    ad_id = bundle['review']['advertisement_id']
    if ({a['ad_id'] for a in result['ads']} != {ad_id} or not expected
            or len(actual) != len(set(actual)) or set(actual) != expected
            or result['counts']['output_failures'] or result.get('output_failure_pairs')
            or result['counts']['requested_pairs'] != len(expected)
            or result['counts']['predicted_pairs'] != len(actual)):
        raise ValueError('Saved judgment is incomplete or belongs to a different review')
    return state_path, job_dir, run, final, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=ROOT / 'temp/operational-server')
    parser.add_argument('--config', type=Path, default=ROOT / 'temp/operational-config.local.json')
    parser.add_argument('--review-id', required=True)
    parser.add_argument('--port', type=int, default=5180)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    state_dir = args.state_dir.resolve()
    state_path, job_dir, run, final, result = inspect_completed_metrics_failure(state_dir, args.review_id)
    if not args.apply:
        print(json.dumps({'repairable': True, 'review_id': args.review_id, 'counts': result['counts'], 'model_calls': 0}))
        return
    # Hold the web port during the offline write, preventing a concurrent local
    # web process from persisting an older in-memory snapshot over the repair.
    with socket.socket() as guard:
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            guard.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        guard.bind(('127.0.0.1', args.port))
        for path in (state_dir / 'execution/rag-jobs').glob('*/status.json'):
            if json.loads(path.read_text(encoding='utf-8')).get('status') in {'RUNNING', 'QUEUED'}:
                raise ValueError('Active RAG jobs exist')
        stamp = datetime.now(UTC).strftime('%Y%m%dT%H%M%S%f')
        for path in (state_path, job_dir / 'status.json'):
            path.with_name(path.name + '.before-metrics-repair-' + stamp).write_bytes(path.read_bytes())
        spec = importlib.util.spec_from_file_location('operational_repair_server', ROOT / 'scripts/serve-operational-review.py')
        server = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(server)
        from operational_web_bridge import ExecutionBridge
        services = server.build_services(server.Settings(app_env='test', private_storage_path=state_dir / 'private'))
        bridge = ExecutionBridge(services, state_dir, args.config, server.project_results)
        try:
            bundle = services.reviews.repository.get(args.review_id)
            ad = services.repository.get_advertisement(bundle.review.advertisement_id)
            link = bridge.links[args.review_id]
            link['result_file'] = str(final)
            located = bridge.rebuild_result_projection(args.review_id)
            candidates = [c for a in result['ads'] for c in a.get('candidates', []) if c.get('status') == 'predicted']
            pending = any(a.get('review_candidates') or a.get('deferred_rules') for a in result['ads'])
            risk = 'HIGH' if any(c['judgment']['verdict'] == 'VIOLATION' for c in candidates) else 'CHECK_REQUIRED' if pending or any(c['judgment']['verdict'] == 'UNDETERMINED' for c in candidates) else 'LOW'
            now = datetime.now(UTC)
            bundle.review.status, bundle.job.status = 'REVIEW_COMPLETED', 'COMPLETED'
            bundle.review.completed_at = bundle.job.updated_at = now
            bundle.review.standard_version_ids = ('STDVER-V2',)
            bundle.job.progress_rate, bundle.job.is_retryable = 100, False
            bundle.job.failed_reason = bundle.job.failed_reason_code = None
            bundle.job.current_step = 'RESULT_GENERATION'
            bundle.review.overall_risk_level = risk
            if ad.latest_review_id == args.review_id:
                ad.overall_risk_level = risk
                ad.review_status = 'REVIEW_COMPLETED'
            for step in bundle.steps:
                step.status, step.failed_reason_code = 'COMPLETED', None
            link.update(completed_at=now.isoformat(), predicted_count=len(candidates),
                        located_annotation_count=located, output_failure_count=0,
                        partial_result_warning=None, metrics_only_repair=True)
            from rag.judgment.runtime_metrics import save_completed_runtime_metrics
            response = json.loads((run / '03_judgment_responses.json').read_text(encoding='utf-8'))
            save_completed_runtime_metrics(run / 'metrics-repaired.json', {}, response['rows'], None)
            bridge.rag.store.update(link['rag_job_id'], status='COMPLETED', error=None,
                completed_at=now.isoformat(), result_file=str(final.relative_to(job_dir)), progress={'stage': 'complete'})
            bridge.persist()
            print(json.dumps({'review_id': args.review_id, 'status': 'COMPLETED', 'counts': result['counts'], 'model_calls': 0}))
        finally:
            bridge.pool.shutdown()
            bridge.rag.executor.shutdown()


if __name__ == '__main__':
    main()
