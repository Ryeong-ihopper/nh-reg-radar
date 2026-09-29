"""Apply reviewed policy extensions to an already source-bound canonical snapshot."""
from __future__ import annotations

import argparse
import copy
import json
from collections import Counter
from pathlib import Path

from rag.judgment.family_prompts import make_batches
from rag.judgment.obligation_logic import validate_expression
from rag.judgment.review_program import KINDS, digest, execution_digest
from rag.judgment.review_program_extensions import extend_policies


def revise(document, old_policies, reviewed_policies=None):
    result = copy.deepcopy(document)
    old = {p['plan_id']: p for p in old_policies['plans']}
    template_ids = {p['plan_id'] for p in document['plans'] if p['source']['source_kind'] == 'TEMPLATE'}
    binding = document.get('review_program_source_binding') or {}
    if (len(old) != len(old_policies['plans']) or set(old) != template_ids
            or binding.get('policies_sha256') != digest(old_policies)
            or document.get('source_binding_sha256') != digest(binding)):
        raise ValueError('current source/policy binding needs review')
    for plan in result['plans']:
        if plan['source']['source_kind'] != 'TEMPLATE':
            continue
        program = plan['review_program']
        if (plan['source_sha256'] != digest(plan['source'])
                or program['execution_sha256'] != execution_digest(plan)
                or program['program_sha256'] != digest({'policy': old[plan['plan_id']], 'source': plan['source_sha256']})):
            raise ValueError('current source/program hash needs review')
    policies = extend_policies(document, reviewed_policies if reviewed_policies is not None else old_policies)
    revised_ids = [p['plan_id'] for p in policies['plans']]
    if (policies.get('schema_version') != old_policies.get('schema_version')
            or len(revised_ids) != len(set(revised_ids)) or set(revised_ids) != template_ids):
        raise ValueError('reviewed policies must preserve the canonical template set')
    for policy in policies['plans']:
        plan = next(p for p in result['plans'] if p['plan_id'] == policy['plan_id'])
        if policy.get('base_source_sha256') != old[plan['plan_id']].get('base_source_sha256'):
            raise ValueError('reviewed policy must preserve its original source binding')
        revision = policy.get('source_revision') or {}
        if set(revision) - {'source_fields', 'source_provenance'}:
            raise ValueError('source revision cannot change rule identity or product scope')
        if revision:
            plan['source'].update(copy.deepcopy(revision))
            plan['source_sha256'] = digest(plan['source'])
        for key in ('applicability_inputs', 'applicability_logic', 'obligations', 'obligation_logic'):
            if key in policy:
                plan[key] = copy.deepcopy(policy[key])
        program = copy.deepcopy(policy['program'])
        if not program['kinds'] or set(program['kinds']) - KINDS:
            raise ValueError('unknown reviewed program kind')
        if program['mode'] == 'REVIEW_ONLY' and (plan['obligations'] or program['allowed_outcomes'] != ['UNDETERMINED']):
            raise ValueError('review-only item must not acquire automatic duties')
        validate_expression(plan['obligation_logic'], [a['obligation_id'] for a in plan['obligations']],
                            [f['fact_id'] for f in plan['applicability_inputs']])
        program.update(schema_version='review-program-v1', source_sha256=plan['source_sha256'],
                       program_sha256=digest({'policy': policy, 'source': plan['source_sha256']}),
                       execution_sha256=execution_digest(plan))
        plan['review_program'] = program
        if any(a['owners']['human'] for a in plan['obligations']) and any(a['owners']['llm'] for a in plan['obligations']):
            plan['prompt_family'] = 'HYBRID_VISUAL'
        plan['complexity'] = len(plan['applicability_inputs']) + sum(1 + int(a['owners'].get('human', False)) + int(a['owners'].get('external_input', False)) for a in plan['obligations'])
    result['counts']['obligation_atoms'] = sum(len(p['obligations']) for p in result['plans'])
    result['counts']['application_inputs'] = sum(len(p['applicability_inputs']) for p in result['plans'])
    result['counts']['families'] = dict(Counter(p['prompt_family'] for p in result['plans']))
    result['review_program_source_binding']['policies_sha256'] = digest(policies)
    result['source_binding_sha256'] = digest(result['review_program_source_binding'])
    return result, policies


def revise_migration(document, migration, revised):
    current = {p['plan_id']: p for p in document['plans']}
    updated = {p['plan_id']: p for p in revised['plans']}
    rows = migration['rows']
    ids = [row['plan_id'] for row in rows]
    if len(ids) != len(set(ids)) or set(ids) != set(current) or set(updated) != set(current):
        raise ValueError('migration must preserve the canonical plan set')
    if any(row['source_sha256'] != current[row['plan_id']]['source_sha256'] for row in rows):
        raise ValueError('current migration source binding needs review')
    result = copy.deepcopy(migration)
    for row in result['rows']:
        row['source_sha256'] = updated[row['plan_id']]['source_sha256']
    return result


def revise_worklist(document, worklist, revised):
    if (worklist.get('schema_version') != 'review-worklist-v1'
            or worklist.get('operationally_connected') is not False
            or worklist.get('canonical_source_binding_sha256') != document['source_binding_sha256']):
        raise ValueError('current design worklist source binding needs review')
    plans = {p['plan_id']: p for p in revised['plans'] if p['source']['source_kind'] == 'TEMPLATE'}
    rows = worklist['rows']
    ids = [row['id'] for row in rows]
    template_ids = {row['id'] for row in rows if row['kind'] == 'TEMPLATE'}
    if len(ids) != len(set(ids)) or template_ids != set(plans):
        raise ValueError('design worklist must preserve the canonical template set')
    result = copy.deepcopy(worklist)
    for row in result['rows']:
        if row['kind'] != 'TEMPLATE':
            continue
        plan = plans[row['id']]
        for key in ('source', 'source_sha256', 'review_program', 'applicability_inputs',
                    'applicability_logic', 'obligations', 'obligation_logic'):
            row[key] = copy.deepcopy(plan[key])
    result['canonical_source_binding_sha256'] = revised['source_binding_sha256']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'config')
    parser.add_argument('--reviewed-policies', type=Path,
                        help='Reviewed replacements; the current policy snapshot is checked before applying them')
    args = parser.parse_args()
    folder = args.config_dir
    def read(name):
        return json.loads((folder / name).read_text(encoding='utf-8'))
    def write(name, value):
        (folder / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    replacements = json.loads(args.reviewed_policies.read_text(encoding='utf-8')) if args.reviewed_policies else None
    current = read('canonical-execution-plans-v2.json')
    document, policies = revise(current, read('review-program-policies-v1.json'), replacements)
    migration = revise_migration(current, read('operational-catalog-migration-v1.json'), document)
    worklist = (revise_worklist(current, read('review-worklist-v1.json'), document)
                if (folder / 'review-worklist-v1.json').is_file() else None)
    dispositions = read('operational-rule-dispositions-v1.json')
    dispositions['canonical_source_binding_sha256'] = document['source_binding_sha256']
    batches = read('family-prompt-batches-v1.json')
    batches['source_binding_sha256'] = document['source_binding_sha256']
    batches['batches'] = make_batches(document['plans'])
    batches['counts'].update(batches=len(batches['batches']), families=dict(Counter(b['family'] for b in batches['batches'])),
                            plans=sum(len(b['plans']) for b in batches['batches']),
                            oversized_singletons=sum(b['complexity'] > 12 for b in batches['batches']))
    write('canonical-execution-plans-v2.json', document)
    write('review-program-policies-v1.json', policies)
    write('operational-catalog-migration-v1.json', migration)
    write('operational-rule-dispositions-v1.json', dispositions)
    write('family-prompt-batches-v1.json', batches)
    if worklist is not None:
        write('review-worklist-v1.json', worklist)
    print(json.dumps(document['counts'], ensure_ascii=False))


if __name__ == '__main__':
    main()
