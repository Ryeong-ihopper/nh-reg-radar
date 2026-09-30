"""Source-reviewed composition and evidence policies, independent of case answers."""
from __future__ import annotations

import copy
import re


def extend_policies(document, policies):
    result = copy.deepcopy(policies)
    if result.get('review_extension_version') == 'composition-evidence-and-line-v1':
        return _separate_rate_prerequisites(document, result)
    plans = {p['plan_id']: p for p in document['plans']}
    for policy in result['plans']:
        plan = plans[policy['plan_id']]
        fields = (policy.get('source_revision') or {}).get('source_fields') or plan['source']['source_fields']
        program = policy['program']
        program['evidence_policy'] = {
            'mode': 'LABEL_LEXICAL' if program['kinds'] == ['PRESENCE'] else 'LEXICAL',
            'mandatory_selection': 'CONFIRMED_TEMPLATE_ENUMERATION',
            'label_is_proof': False,
            'retrieval_miss_is_absence': False,
            'absence_requires_complete_readable_scope': True,
            'dense_status': 'PENDING_ITEM_LEVEL_COMPARISON',
        }
        # These two source rows explicitly separate the text from a logo and
        # authorize a retirement context exemption for the logo only.
        if (plan['source'].get('product_template') in {'투자성상품-ETF', '투자성상품-ELB'}
                and fields.get('label') == '유의사항'
                and '퇴직연금 내 운용상품' in str(fields.get('satisfied'))
                and '로고 병기 생략 가능' in str(fields.get('satisfied'))):
            policy['applicability_inputs'] = [copy.deepcopy(plan['applicability_inputs'][0]), {
                'fact_id': 'B1', 'name': '퇴직연금 내 운용상품으로 소개되는가',
                'owner': 'RULE', 'type': 'CONFIRMED_METADATA', 'purpose': 'DECISION_BRANCH',
                'metadata_key': 'product_context', 'equals': 'RETIREMENT',
                'unknown_policy': 'UNDETERMINED'}]
            policy['applicability_logic'] = {'all': [{'fact': 'A1'}]}
            policy['obligations'] = [
                _atom('O1', '광고에 해당 운용상품이 예금자보호 대상이 아니라는 의미가 기재되어 있는가', 'LLM'),
                _atom('O2', '예금자 비보호 로고가 병기되어 있는가. 퇴직연금 운용상품에서는 로고만 생략할 수 있다.', 'HUMAN')]
            policy['obligation_logic'] = {'if': [{'fact': 'B1'}, {'ref': 'O1'},
                                               {'all': [{'ref': 'O1'}, {'ref': 'O2'}]}]}
            program['kinds'] = ['SEMANTIC', 'CONDITIONAL', 'VISUAL']
            program['visual_exemption'] = {'metadata_key': 'product_context', 'equals': 'RETIREMENT'}
        violation = str(fields.get('violated') or '')
        if re.search(r'한\s*줄에\s*2개\s*이상의', violation):
            # Only two explicitly reviewed source shapes are supported here.
            clauses = re.findall(r'한\s*줄에\s*2개\s*이상의[^\n]*(?:부적정|불가능)(?:\(은행연합회 지도사항\))?', violation)
            if len(clauses) != 1:
                raise ValueError('line-structure source wording needs review')
            clause = clauses[0]
            atoms = copy.deepcopy(policy.get('obligations', plan['obligations']))
            if not atoms:
                continue
            for atom in atoms:
                atom['text'] = atom['text'].replace(clause, '').rstrip(', -\n')
                atom['retrieval_queries'] = [q.replace(clause, '').rstrip(', -\n') for q in atom.get('retrieval_queries', [])]
            ref = 'O' + str(max(int(a['obligation_id'][1:]) for a in atoms) + 1)
            atoms.append(_atom(ref, clause + '. 실제 줄 경계와 서로 다른 유의사항의 의미 경계를 원문에서 확인한다. 문장 수나 bbox만으로 개수를 추정하지 않는다.', 'HUMAN'))
            policy['obligations'] = atoms
            policy['obligation_logic'] = {'all': [copy.deepcopy(policy.get('obligation_logic', plan['obligation_logic'])), {'ref': ref}]}
            program['kinds'] = list(dict.fromkeys([*program['kinds'], 'VISUAL']))
            program['line_structure_policy'] = 'SEPARATE_HUMAN_CHECK_UNTIL_WARNING_UNITS_AND_RENDERED_LINES_VERIFIED'
            if '예금성' in str(plan['source'].get('product_template')) and '대출 유의사항' in clause:
                program['line_scope_conflict'] = 'DEPOSIT_SOURCE_NAMES_LOAN_WARNING; DO_NOT_REINTERPRET'
    result['review_extension_version'] = 'composition-evidence-and-line-v1'
    return _separate_rate_prerequisites(document, result)


def _separate_rate_prerequisites(document, policies):
    """Keep shared rate validity as a prerequisite, not another bonus breach.

    The source's amount-limit row refers to the three rate display methods.
    Failure of their common date/tax/year prerequisites cannot independently
    establish that the bonus amount-limit disclosure itself is missing.
    """
    if policies.get('rate_prerequisite_version') == 'shared-rate-prerequisites-v1':
        return policies
    plans = {p['plan_id']: p for p in document['plans']}
    for policy in policies['plans']:
        if policy['plan_id'] != 'MTH-DEPOSIT-DEMAND-R11':
            continue
        plan = plans[policy['plan_id']]
        source = plan['source']['source_fields']['satisfied']
        if 'c8셀의 방식 2 또는 c9셀의 방식 3' not in source or '어느금액까지' not in source:
            raise ValueError('bonus amount source revision requires review')
        logic = policy.get('obligation_logic', plan['obligation_logic'])
        nodes = logic.get('all') or []
        common = [{'ref': ref} for ref in ('O7', 'O8', 'O9')]
        if nodes[:3] != common or len(nodes) != 4:
            raise ValueError('unexpected shared rate prerequisite formula')
        policy['obligation_logic'] = {'if': [
            {'all': common}, copy.deepcopy(nodes[3]),
            {'unknown': 'SHARED_RATE_REQUIREMENTS_NOT_CONFIRMED'}]}
        policy['program']['prerequisite_obligations'] = ['O7', 'O8', 'O9']
        policy['program']['prerequisite_group_id'] = 'MTH-DEPOSIT-DEMAND-R07'
    policies['rate_prerequisite_version'] = 'shared-rate-prerequisites-v1'
    return policies


def _atom(ref, text, owner):
    return {'obligation_id': ref, 'text': text,
            'owners': {'rule': False, 'llm': owner == 'LLM', 'external_input': False, 'human': owner == 'HUMAN'},
            'evidence': {'advertisement_direct_quote_required': owner == 'LLM', 'absence_requires_complete_scan': True,
                         'same_advertisement_product_revision_scope': True, 'rule_or_example_text_is_advertisement_evidence': False},
            'interpretation_hints': [], 'retrieval_queries': [text]}
