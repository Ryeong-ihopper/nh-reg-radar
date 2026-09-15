"""Source-bound evidence retrieval; lexical matches are never verdicts."""
from __future__ import annotations

import math
import re

STOPWORDS = {'광고', '광고물', '표시', '기재', '여부', '경우', '관련', '대한',
             '않았는가', '있는가', '확인', '점검', '규정', '위반', '항목'}


def search_terms(text):
    # Preserve two-syllable Korean nouns, numbers and units. No ad-specific
    # dictionary, stemming guesses or answer IDs participate in selection.
    return set(re.findall(r'[가-힣A-Za-z0-9]{2,}', str(text).lower())) - STOPWORDS


def source_facets(rule):
    """Separate source fields/sentences for SEARCH, not mandatory sub-rules.

    The complete source contract remains the only judgment obligation. A
    sentence boundary never certifies an exception or alternative as a duty.
    """
    contract = rule.get('condition_contract') or {}
    fields = [('SCOPE', contract.get('scope_text'))]
    for key, id_key in [('applicability_conditions', 'condition_id'),
                        ('review_conditions', 'condition_id'), ('obligation_checks', 'obligation_id')]:
        fields.extend((row[id_key], row.get('text')) for row in contract.get(key) or [])
    fields.extend((key, rule.get(key)) for key in ('question', 'criterion', 'guide', 'standard_guidance', 'v2_note'))
    facets, seen = [], set()
    for ref, text in fields:
        if not text:
            continue
        for part in re.split(r'\n+|(?<=[.!?])\s+', str(text)):
            part = part.strip()
            if not part or part in seen:
                continue
            seen.add(part)
            facets.append({'source_ref': ref, 'query': part})
    return facets


def supplement_evidence(seed_ids, rows, rule, *, char_budget):
    """One lexical candidate per source facet under a shared addition budget.

    Seeds cannot be displaced. Missing matches and oversized whole chunks are
    audited, not interpreted as missing advertising requirements.
    """
    if char_budget < 0:
        raise ValueError('evidence char budget must be non-negative')
    by_id = {row['doc_id']: row for row in rows}
    if len(by_id) != len(rows) or any(key not in by_id for key in seed_ids):
        raise ValueError('invalid evidence identifiers')
    scopes = {(by_id[key].get('ad_id'), by_id[key].get('product_id')) for key in seed_ids}
    if len(scopes) > 1:
        raise ValueError('evidence seeds cross advertisement/product scope')
    eligible = [row for row in rows if not scopes or (row.get('ad_id'), row.get('product_id')) in scopes]
    texts = {row['doc_id']: str(row.get('text_canonical') or row.get('text_search') or '').lower() for row in eligible}
    selected = list(dict.fromkeys(seed_ids))
    added, audit = [], []
    remaining = char_budget
    for facet in source_facets(rule):
        terms = search_terms(facet['query'])
        weights = {term: math.log(1 + len(texts) / (1 + sum(term in text for text in texts.values()))) for term in terms}
        scores = {key: sum(weight for term, weight in weights.items() if term in text) for key, text in texts.items()}
        ranked = sorted((key for key in texts if scores[key] > 0), key=lambda key: (-scores[key], key))
        event = {**facet, 'evidence_ids': [], 'status': 'NO_LEXICAL_MATCH'}
        if ranked:
            best = ranked[0]
            event['evidence_ids'] = [best]
            if best in selected:
                event['status'] = 'ALREADY_SELECTED'
            elif len(texts[best]) <= remaining and char_budget > 0:
                selected.append(best)
                added.append(best)
                remaining -= len(texts[best])
                event['status'] = 'ADDED'
            else:
                event['status'] = 'BUDGET_DEFERRED'
        audit.append(event)
    return selected, {'method': 'source_facets_v1', 'facets': audit, 'added_ids': added,
                      'added_chars': char_budget - remaining, 'char_budget': char_budget,
                      'semantic_dependencies_complete': False}
