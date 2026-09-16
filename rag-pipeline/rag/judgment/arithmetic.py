"""Bounded, source-only loan-rate arithmetic. Unsupported syntax abstains.

No model output, advertisement identifiers, labels or expected answers are inputs.
Decimal operands are extracted together with their roles and canonical source lines.
"""
import re
from decimal import Decimal

from rag.judgment.reading_quality import needs_reading_review

METHOD = "DETERMINISTIC_SOURCE_ARITHMETIC"
NUMBER = r"(\d+(?:\.\d+)?)"
PERCENT = re.compile(NUMBER + r"\s*%[pP]?")


def _one(pattern, text):
    found = re.findall(pattern, text)
    return Decimal(found[0]) if len(found) == 1 else None


def _flat(text):
    """Remove balanced parentheticals, retaining all outer text."""
    depth, output = 0, []
    for char in text:
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth < 0:
                return None
        elif not depth:
            output.append(char)
    return ''.join(output) if depth == 0 else None


def _parts(text):
    depth, start, parts = 0, 0, []
    for index, char in enumerate(text):
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
        elif char == ',' and not depth:
            parts.append(text[start:index])
            start = index + 1
        if depth < 0:
            return []
    return parts + [text[start:]] if depth == 0 else []


def _won(text):
    """Exact Korean small monetary amounts; unknown units never become zero."""
    match = re.fullmatch(r'(?:(\d+)만)?(?:(\d+)천)?(\d+)?원', text.strip())
    if not match or not any(match.groups()):
        return None
    return sum(int(value or 0) * unit for value, unit in zip(match.groups(), (10000, 1000, 1)))


def _verified_cost_shares(text):
    """A loan ad's stamp-cost examples must not contradict a rate-only pass.

    This guard certifies only explicit common customer-share percentages with
    amount(parenthesized customer amount) pairs. Unknown/mismatched money
    relations defer the *whole* item to the general review path.
    """
    if not re.search(r'고객\s*부담\s*\d', text):
        return True
    shares = re.findall(r'고객\s*부담\s*' + NUMBER + r'\s*%', text)
    pairs = re.findall(r'([\d만천]+원)\s*\(\s*고객\s*부담\s*([\d만천]+원)\s*\)', text)
    if len(shares) != 1 or not pairs:
        return False
    occurrences = re.findall(r'고객\s*부담\s*\d', text)
    if len(occurrences) != len(pairs) + 1:
        return False
    for total, part in pairs:
        total, part = _won(total), _won(part)
        if total is None or part is None or Decimal(total) * Decimal(shares[0]) / 100 != part:
            return False
    return True


def _benefits(text):
    head, _, tail = text.partition('※')
    if re.search(r'중복|택\s*\d|택일|선택|둘\s*중|하나만|동시|제외|한도|한정', text):
        return None
    # One explicit maximum followed by one comma-separated parenthesized list.
    match = re.fullmatch(r'우대금리\s*\|\s*최대\s*' + NUMBER
                         + r'\s*%[pP]\s*\((.*)\)\s*', head.strip())
    if not match or PERCENT.search(tail):
        return None
    maximum, body = Decimal(match[1]), match[2]
    parts = _parts(body)
    values = []
    for index, part in enumerate(parts):
        flat = _flat(part)
        if flat is None:
            return None
        rates = PERCENT.findall(flat)
        if not rates and index == 0 and re.fullmatch(r'\s*\d{4}[./-]\d{1,2}[./-]\d{1,2}\.?\s*(?:현재)?\s*', flat):
            continue
        if len(rates) != 1 or not re.search(r'%[pP]', flat):
            return None
        value = Decimal(rates[0])
        nested = re.findall(r'\(([^()]*)\)', part)
        alternatives = [fragment for fragment in nested if PERCENT.search(fragment)]
        if alternatives:
            # Only a lower monetary tier within this very same component is
            # certified as an alternative. Other parentheses are NOT dropped.
            if len(alternatives) != 1:
                return None
            lower = re.fullmatch(r'\s*' + NUMBER + r'\s*만원\s*이하(?:는)?\s*'
                                 + NUMBER + r'\s*%[pP]\s*', alternatives[0])
            upper = re.search(NUMBER + r'\s*만원\s*(?:이상)?\s*' + NUMBER + r'\s*%[pP]', flat)
            if (not lower or not upper or Decimal(lower[1]) >= Decimal(upper[1])
                    or Decimal(lower[2]) > value):
                return None
        if len(PERCENT.findall(part)) != 1 + len(alternatives):
            return None
        values.append(value)
    return (maximum, values) if len(values) >= 2 else None


def calculate_loan_rates(payload, rule):
    """Return a fully grounded judgment or None; never guess an unknown relation."""
    contract = rule.get('condition_contract') or {}
    obligations = contract.get('obligation_checks') or []
    criterion = rule.get('criterion', '')
    # This adapter covers the source's arithmetic-only prohibition, not a
    # compound template interest-rate obligation (dates/disclosures included).
    if (rule.get('category') != 'PROHIBIT' or '산술' not in rule.get('question', '')
            or not all(term in criterion for term in ('금리 산식', '우대조건별', '계산 예시'))
            or len(obligations) != 1 or obligations[0].get('text') != criterion
            or contract.get('applicability_mode') not in {'SOURCE_SCOPED', 'UNCONDITIONAL'}
            or contract.get('applicability_conditions') or contract.get('review_conditions')
            or payload.get('parser_coverage') != 'READY'
            or (payload.get('reading_quality') or {}).get('requires_review')):
        return None
    scope = (payload.get('evidence_scope') or {}).get(rule['item_id']) or {}
    assessment = (payload.get('external_input_assessment') or {}).get(rule['item_id']) or {}
    if not scope.get('complete_ad_scan') or assessment.get('input_mode') in {'PARTIAL', 'EXTERNAL'}:
        return None
    docs = [doc for doc in payload.get('documents', []) if doc.get('evidence_id') in scope.get('evidence_ids', [])]
    if (not docs or len({doc['evidence_id'] for doc in docs}) != len(set(scope.get('evidence_ids', [])))
            or any(needs_reading_review(doc) or not doc.get('line_texts') for doc in docs)
            or len({(doc.get('asset_id'), doc.get('product_id')) for doc in docs}) != 1
            or any(not doc.get('asset_id') or not doc.get('product_id') for doc in docs)):
        return None
    lines, sources = {}, {}
    for doc in docs:
        for ref, text in doc['line_texts'].items():
            if ref not in doc.get('line_refs', []) or (ref in lines and lines[ref] != text):
                return None
            lines[ref], sources[ref] = text, doc['evidence_id']
    rates = [(ref, text) for ref, text in lines.items() if re.match(r'^\s*대출금리\s*\|', text)]
    benefits = [(ref, text) for ref, text in lines.items() if re.match(r'^\s*우대금리\s*\|', text)]
    if len(rates) != 1 or len(benefits) != 1:
        return None
    if any(re.search(r'중복\s*(?:불가|불가능|적용\s*불가)|택일|동시\s*적용\s*불가|반올림|절사', text)
           for text in lines.values()):
        return None
    if any(not _verified_cost_shares(text) for text in lines.values()):
        return None
    # Calculated receipts/refunds need a separate day-count/tax adapter.
    if any(re.search(r'예시|수취이자|환급액|총\s*이자|이자\s*합계', text) and re.search(r'\d', text)
           for text in lines.values()):
        return None
    rate_ref, rate_text = rates[0]
    benefit_ref, benefit_text = benefits[0]
    dates = set(re.findall(r'\d{4}[./-]\d{1,2}[./-]\d{1,2}', rate_text + benefit_text))
    if len(dates) > 1:
        return None
    head = rate_text.split('※')[0]
    values = [_one(pattern, head) for pattern in (
        r'최저\s*(?:연\s*)?' + NUMBER + r'\s*%',
        r'(?:최대|최고)\s*(?:연\s*)?' + NUMBER + r'\s*%',
        r'기준금리\s*(?:\([^()]*\))?\s*(?:연\s*)?' + NUMBER + r'\s*%',
        r'가산금리\s*(?:연\s*)?' + NUMBER + r'\s*%',
        r'우대금리\s*' + NUMBER + r'\s*%[pP]\s*적용\s*시',
    )]
    benefit = _benefits(benefit_text)
    if any(value is None for value in values) or len(PERCENT.findall(head)) != 5 or not benefit:
        return None
    if re.search(r'또는|중복|택일|선택|고정.*변동|변동.*고정', head):
        return None
    low, high, base, spread, discount = values
    maximum, components = benefit
    # A conditional surcharge with no displayed final total is not itself an
    # arithmetic claim. Additional stated totals/formulas are unsupported.
    for note in rate_text.split('※')[1:]:
        if PERCENT.search(note) and not re.fullmatch(
                r'\s*한도대출의\s*경우\s*' + NUMBER + r'\s*%[pP]\s*가산됨\s*', note):
            return None
    checks = [(f'{base}+{spread}', base + spread, high),
              (f'{high}-{discount}', high - discount, low),
              ('+'.join(map(str, components)), sum(components, Decimal(0)), maximum)]
    if discount != maximum:
        checks.append(('+'.join(map(str, components)), sum(components, Decimal(0)), discount))
    mismatch = any(actual != advertised for _, actual, advertised in checks)
    formulas = '; '.join(f'검산: {expr} {"!=" if actual != advertised else "="} {advertised}'
                         for expr, actual, advertised in checks)
    reason = '원문 수치의 규칙 기반 검산: ' + formulas + ('. 불일치가 확인됩니다.' if mismatch else '. 표시된 금리 산식과 우대 합계가 일치합니다.')
    refs = [rate_ref, benefit_ref]
    ids = list(dict.fromkeys(sources[ref] for ref in refs))
    return {'item_id': rule['item_id'], 'scope_check': {'scope_ref': 'SCOPE', 'status': 'MATCHED'},
            'condition_checks': [], 'review_condition_checks': [], 'applicability': 'APPLICABLE',
            'applicability_basis': 'ADVERTISEMENT_EVIDENCE', 'applicability_evidence_ids': ids,
            'applicability_evidence_line_refs': refs, 'applicability_metadata_fields': [],
            'verdict': 'VIOLATION' if mismatch else 'COMPLIANT', 'evidence_ids': ids,
            'evidence_line_refs': refs, 'requirement_checks': [{
                'obligation_ref': obligations[0]['obligation_id'], 'requirement': criterion,
                'status': 'VIOLATED' if mismatch else 'SATISFIED', 'finding_basis': 'OBSERVED',
                'evidence_ids': ids, 'evidence_line_refs': refs, 'reason': reason}],
            'reason': reason, 'confidence': 'HIGH', 'needs_researcher_review': mismatch}
