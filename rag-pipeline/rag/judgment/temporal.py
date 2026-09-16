"""Source-stated date windows and source-bound calendar arithmetic, never ad rules."""
import re
from datetime import date

from rag.judgment.reading_quality import needs_reading_review

WINDOW = re.compile(r'기준일(?:자)?\s*[:：]?\s*(?:심의시점|검토시점|심의일|검토일)\s*(\d+)\s*일\s*이내')
DATE = re.compile(r"(?<!\d)(\d{4}|\d{2})\s*[./-]\s*(\d{1,2})\s*[./-]\s*(\d{1,2})(?!\d)")


def date_window_clauses(text):
    return list(dict.fromkeys(match.group(0) for match in WINDOW.finditer(text)))


def basis_date_observations(documents, review_date):
    if not review_date:
        return []
    reviewed = date.fromisoformat(review_date)
    observations = []
    for doc in documents:
        if needs_reading_review(doc):
            continue
        lines = doc.get('line_texts') or {None: doc.get('text', '')}
        for ref, text in lines.items():
            for match in DATE.finditer(str(text)):
                # Date must be adjacent to an explicit basis marker. Approval
                # periods and registration dates are not rate basis dates.
                after = str(text)[match.end():match.end()+24]
                before = str(text)[max(0,match.start()-12):match.start()]
                if not (re.match(r'^[.\s,，)\]]*(?:당행\s*)?(?:금리\s*)?기준', after)
                        or re.search(r'기준일(?:자)?\s*[:：]?\s*$', before)):
                    continue
                year, month, day = map(int, match.groups())
                if len(match.group(1)) == 2:
                    year = min((century+year for century in
                                (reviewed.year//100*100-100, reviewed.year//100*100, reviewed.year//100*100+100)),
                               key=lambda candidate: abs(candidate-reviewed.year))
                try:
                    basis = date(year,month,day)
                except ValueError:
                    continue
                observations.append({'basis_date':basis.isoformat(), 'review_date':review_date,
                    'elapsed_days':(reviewed-basis).days,'evidence_id':doc['evidence_id'],
                    'line_refs':[ref] if ref else list(doc.get('line_refs') or [])})
    return observations


def temporal_claim_errors(payload, result):
    rule = next((r for r in payload.get('rules',[]) if r['item_id']==result.get('item_id')), {})
    obligations = (rule.get('condition_contract') or {}).get('obligation_checks',[])
    observations = basis_date_observations(payload.get('documents',[]),
                                          (payload.get('review_context') or {}).get('review_date'))
    errors = []
    for check in result.get('requirement_checks') or []:
        if not isinstance(check, dict):
            continue
        obligation = next((o for o in obligations if o['obligation_id']==check.get('obligation_ref')), {})
        # Dedicated source excerpt only, not the compound O1/ANY_OF paragraph.
        match = WINDOW.fullmatch(obligation.get('text',''))
        if not match:
            continue
        ids, refs = set(check.get('evidence_ids') or []), set(check.get('evidence_line_refs') or [])
        cited = [o for o in observations if (set(o['line_refs']) & refs if refs else o['evidence_id'] in ids)]
        # Abstention must not evade a known calendar comparison by dropping
        # its citation. Only an unambiguous date inside this rule's existing
        # evidence scope qualifies; do not choose between conflicting dates.
        if not ids and not refs and check.get('status') == 'UNDETERMINED':
            scope = (payload.get('evidence_scope') or {}).get(result.get('item_id'))
            allowed = set(scope.get('evidence_ids') or []) if isinstance(scope, dict) else None
            available = [o for o in observations if allowed is None or o['evidence_id'] in allowed]
            if len({o['basis_date'] for o in available}) == 1:
                cited = available
        outcomes = {0 <= o['elapsed_days'] <= int(match.group(1)) for o in cited}
        if check.get('status') == 'SATISFIED' and outcomes != {True}:
            errors.append(f"{result.get('item_id')}:{check.get('obligation_ref')}: basis-date window cannot be SATISFIED; verify cited date arithmetic or abstain")
        if (result.get('applicability') == 'APPLICABLE' and len(outcomes) == 1
                and check.get('status') == 'UNDETERMINED'):
            expected = 'SATISFIED' if True in outcomes else 'VIOLATED'
            errors.append(f"{result.get('item_id')}:{check.get('obligation_ref')}: cited trusted basis date and review date resolve this source window as {expected}; do not abstain from known calendar arithmetic")
    return errors
