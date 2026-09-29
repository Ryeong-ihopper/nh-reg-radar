"""A source-authored amount-cap alternative, using only cited advertisement text."""
from __future__ import annotations

import re
from decimal import Decimal

CAP_LABEL = re.compile(r'(?<![가-힣])대출\s*한도')
CAP_HEADING = re.compile(r'^\s*대출\s*한도\s*[:：|]?\s*')
NUMBER = r'(?:[0-9]+|[1-9][0-9]{0,2}(?:,[0-9]{3})+)(?:\.[0-9]+)?'
CAP_CONDITION = re.compile(
    r'(?:한도|대출\s*금액)[^\n]{0,48}(?:추가|별도|상향|증액|변경|선택|조건별|달라|상이|따라)'
    r'|(?:추가|별도|상향|증액|승인|조건별|담보별|신용별)[^\n]{0,48}(?:한도|대출\s*금액)'
    r'|(?:추가\s*담보|추가\s*대출|담보\s*조건|신용\s*조건)[^\n]{0,48}'
    + NUMBER + r'\s*(?:억원|천만원|만원|원)')
VARIANT_KEYS = ('amount_variant_id', 'loan_variant_id', 'product_variant_id')
ADVERTISEMENT_ROLES = (None, 'ADVERTISEMENT_CONTENT', 'PRODUCT_BODY',
                       'ADVERTISEMENT_TEXT', 'ADVERTISEMENT_REGION', 'ADVERTISEMENT_SCAN')


def amount_check(adapter, check, payload, item_id):
    unknown = {'status': 'UNDETERMINED', 'finding_basis': 'UNKNOWN',
               'evidence_ids': [], 'evidence_line_refs': [],
               'reason': '같은 광고·상품의 명시 대출한도와 원문 금액 기준을 확인해야 합니다.'}
    if adapter.get('kind') != 'LOAN_AMOUNT_CAP_WITHIN':
        return None
    try:
        threshold = Decimal(str(adapter['maximum_won']))
    except (KeyError, ValueError, ArithmeticError):
        return unknown
    if threshold < 0 or not threshold.is_finite():
        return unknown
    # Reuse provenance/reading guards, never the endpoint arithmetic or verdict.
    # Keep this dependency local because reading_quality imports review_program.
    from rag.judgment.loan_rate_evidence import _scope_lines

    bundle, error = _scope_lines(payload, item_id)
    if error:
        return unknown
    scope = payload['evidence_scope'][item_id]
    docs = [d for d in payload['documents'] if d.get('evidence_id') in bundle['scope_ids']]
    if any(d.get('source_role') not in ADVERTISEMENT_ROLES for d in docs):
        return unknown
    for key in VARIANT_KEYS:
        variants = [v[key] for v in [payload, scope, *docs] if v.get(key) is not None]
        if any(not isinstance(v, str) or not v for v in variants) or len(set(variants)) > 1:
            return unknown
    cited = check.get('evidence_line_refs')
    lines = bundle['lines']
    if (not isinstance(cited, list) or not cited
            or any(not isinstance(ref, str) or ref not in lines for ref in cited)):
        return unknown
    observations = [(ref, text) for ref, text in lines.items() if CAP_LABEL.search(text)]
    full_text = payload['full_ad_text']
    if (len(observations) != 1 or observations[0][0] not in cited
            or len(CAP_LABEL.findall(full_text)) != 1
            or CAP_CONDITION.search('\n'.join(lines.values())) or CAP_CONDITION.search(full_text)):
        return unknown
    ref, text = observations[0]
    heading = CAP_HEADING.match(text)
    if not heading or re.search(r'또는|선택|조건별|별도|반올림|절사|\[.*불명', text):
        return unknown
    body = text[heading.end():].strip()
    # A conflicting full-ad source value must not disappear through retrieval.
    full_claims = [s for s in full_text.splitlines() if CAP_LABEL.search(s)]
    if len(full_claims) != 1:
        return unknown
    full_heading = CAP_HEADING.match(full_claims[0])
    if (not full_heading or re.sub(r'\s+', '', full_claims[0][full_heading.end():])
            != re.sub(r'\s+', '', body)):
        return unknown
    amount = re.fullmatch(r'(?:최대\s*)?(' + NUMBER + r')\s*(억원|천만원|만원|원)'
                          r'(?:\s*(?:이하|이내|까지))?[.。]?\s*', body)
    if amount:
        raw = Decimal(amount[1].replace(',', ''))
        parts = raw.as_tuple()
        # Tuple scaling is exact and independent of Decimal's 28-digit context.
        value = Decimal((parts.sign, parts.digits,
                         parts.exponent + {'억원': 8, '천만원': 7, '만원': 4, '원': 0}[amount[2]]))
        satisfied = value <= threshold
        reason = f'한도 근거: "{text}". 검산: {format(value, "f")}원 ' + \
                 ('<=' if satisfied else '>') + f' {format(threshold, "f")}원.'
    elif re.fullmatch(r'(?:담보물?\s*가액|임차\s*보증금)(?:의)?\s*\d+(?:\.\d+)?\s*%\s*(?:이내|이하|까지)[.。]?\s*', body):
        satisfied = False
        reason = f'한도 근거: "{text}". 비율 설명만 있고 구체적인 대출한도 금액이 기재되지 않았습니다.'
    else:
        return unknown
    return {'status': 'SATISFIED' if satisfied else 'VIOLATED', 'finding_basis': 'OBSERVED',
            'evidence_ids': [bundle['owners'][ref]], 'evidence_line_refs': [ref], 'reason': reason}
