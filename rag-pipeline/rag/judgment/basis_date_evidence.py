"""Compare explicit role-bound dates inside one frozen advertisement scope."""
from __future__ import annotations

import re
from collections import Counter
from datetime import date


KIND = 'SOURCE_SCOPED_BASIS_DATE_EQUALITY'
ROLE_LABELS = {
    'loan_rate_basis_date': r'대출\s*(?:금리|이율)',
    'bonus_rate_basis_date': r'우대\s*(?:금리|이율)',
    'deposit_rate_basis_date': r'(?:예금\s*(?:기본\s*)?(?:금리|이율)|기본\s*(?:금리|이율))',
    'expected_interest_basis_date': r'(?:예상|예시)\s*(?:수취|수령)\s*이자',
}
ROLE_PAIRS = {
    frozenset(('loan_rate_basis_date', 'bonus_rate_basis_date')),
    frozenset(('deposit_rate_basis_date', 'expected_interest_basis_date')),
}
DATE_TEXT = r'(?<!\d)(\d{4})(?:[.\-/]\s*(\d{1,2})[.\-/]\s*(\d{1,2})\.?|년\s*(\d{1,2})월\s*(\d{1,2})일)(?!\d)'
DATE = re.compile(DATE_TEXT)
BASIS = re.compile(r'기준(?:일자|일)?(?!\s*(?:금리|이율))|산출\s*일자')
ADVERTISEMENT_ROLES = (None, 'ADVERTISEMENT_CONTENT', 'PRODUCT_BODY',
                       'ADVERTISEMENT_TEXT', 'ADVERTISEMENT_REGION', 'ADVERTISEMENT_SCAN')


def _unknown(reason):
    return {'status': 'UNDETERMINED', 'finding_basis': 'UNKNOWN',
            'evidence_ids': [], 'evidence_line_refs': [], 'reason': reason}


def _scope_lines(payload, item_id):
    # Share frozen provenance, not the loan endpoint arithmetic or verdict.
    from rag.judgment.loan_rate_evidence import _scope_lines as frozen_scope_lines
    from rag.judgment.reading_quality import needs_reading_review

    bundle, error = frozen_scope_lines(payload, item_id)
    if error:
        return None
    docs = [d for d in payload['documents'] if d.get('evidence_id') in bundle['scope_ids']]
    if any(d.get('source_role') not in ADVERTISEMENT_ROLES for d in docs):
        return None
    # Preserve the original adapter's conservative partial-revision behavior.
    revisions = [d.get('revision_id') for d in docs]
    if any(revisions) and (not all(revisions) or len(set(revisions)) != 1):
        return None
    lines, owners = bundle['lines'], bundle['owners']
    scope = payload['evidence_scope'][item_id]
    if 'line_refs' in scope and set(scope['line_refs']) != set(lines):
        return None
    aligned = [d for d in docs if not needs_reading_review(d)
               and d.get('span_status') != 'region_level_selected_text']
    return lines, owners, aligned


def _calendar_date(match):
    values = match.groups()
    return date(int(values[0]), int(values[1] or values[3]), int(values[2] or values[4]))


def _inline_dates(text, role, roles):
    """A label must bind the date directly or head an explicit basis-date row."""
    label = ROLE_LABELS[role]
    direct = re.compile(r'(?:' + label + r')\s*(?:의\s*)?(?:산출\s*)?'
                        r'(?:기준일자|기준일|기준|산출일자)?\s*[:：=|（(]*\s*' + DATE_TEXT)
    found = []
    for match in direct.finditer(text):
        # A bare date adjacent to a rate label is not necessarily its basis date.
        suffix = text[match.end():match.end() + 12]
        if re.match(r'\s*(?:[~～–—-]|부터|내지)\s*\d', suffix):
            raise ValueError('a date range is not one basis date')
        if not BASIS.search(match.group(0)) and not re.match(r'\s*(?:일)?\s*기준', suffix):
            continue
        tail = text[match.end():]
        next_role = re.search('|'.join('(?:' + ROLE_LABELS[r] + ')' for r in roles), tail)
        if DATE.search(tail[:next_role.start()] if next_role else tail):
            raise ValueError('multiple dates within one role binding')
        found.append((_calendar_date(match), (match.start(), match.end())))
    if found:
        return found
    declared = re.search(r'(?:' + label + r')\s*(?:의\s*)?(?:산출\s*)?'
                         r'(?:기준일자|기준일|산출일자)', text)
    heading = re.match(r'\s*(?:' + label + r')\s*[:：|（(]', text)
    if declared or (heading and BASIS.search(text)):
        matches = list(DATE.finditer(text))
        if not matches and re.fullmatch(r'\s*(?:' + label + r')\s*(?:의\s*)?(?:산출\s*)?'
                                       r'(?:기준일자|기준일|산출일자)\s*[:：]?\s*', text):
            return []  # An observed table can bind this exact header to its value.
        if len(matches) != 1:
            raise ValueError('non-unique or unreadable role basis date')
        return [(_calendar_date(matches[0]), (matches[0].start(), matches[0].end()))]
    return []


def _table_dates(docs, lines, roles):
    """Use observed value/header links, quoting their original line references."""
    found = []
    seen = {}
    for doc in docs:
        table = doc.get('table') or {}
        cells = table.get('cells') or []
        if not cells:
            continue
        by_id = {c.get('cell_id'): c for c in cells}

        def refs(cell):
            return cell.get('line_refs') or cell.get('line_ids') or []

        def body(cell):
            return ' '.join(lines[r] for r in refs(cell))

        for cell in cells:
            value_refs = refs(cell)
            if not value_refs or any(r not in lines for r in value_refs):
                continue
            values = list(DATE.finditer(body(cell)))
            headers = cell.get('header_cell_ids') or []
            if not values or not headers:
                continue
            if any(h not in by_id for h in headers):
                raise ValueError('missing observed date header')
            header_cells = [by_id[h] for h in headers]
            if any(not refs(h) or any(r not in lines for r in refs(h)) for h in header_cells):
                raise ValueError('unreadable date header')
            header_text = ' '.join(body(h) for h in header_cells)
            bound_roles = [role for role in roles if re.search(ROLE_LABELS[role], header_text)]
            if not bound_roles:
                continue
            relevant = [cell, *header_cells]
            if (len(by_id) != len(cells) or None in by_id
                    or any(c.get('status', table.get('status')) != 'observed'
                           or c.get('row_span', 1) != 1 or c.get('col_span', 1) != 1
                           or type(c.get('row')) is not int or type(c.get('col')) is not int
                           or c.get('footnote_line_ids') for c in relevant)
                    or len(bound_roles) != 1 or len(values) != 1
                    or not BASIS.search(header_text + ' ' + body(cell))):
                raise ValueError('ambiguous date table binding')
            all_refs = list(dict.fromkeys([*value_refs, *(r for h in header_cells for r in refs(h))]))
            if len({(c['row'], c['col']) for c in relevant}) != len(relevant):
                raise ValueError('duplicate table position')
            key = tuple(value_refs)
            binding = (bound_roles[0], tuple(all_refs), tuple((c['row'], c['col']) for c in relevant))
            if key in seen:
                if seen[key] != binding:
                    raise ValueError('conflicting observed date header links')
                continue
            seen[key] = binding
            found.append((bound_roles[0], _calendar_date(values[0]), tuple(value_refs), all_refs))
    return found


def date_equality_check(adapter, check, payload, item_id):
    """Return computed_check shape; no model date or inferred operand is accepted.

    adapter uses left_role/right_role and unit=DATE (default DATE). The two
    permitted role pairs are source-authored deposit and loan date comparisons.
    Dates must be uniquely bound in the complete allowed source, and both date
    operands must have been cited. Observed table headers may expand citations.
    """
    if adapter.get('kind') != KIND:
        return None
    unresolved = _unknown('같은 광고·상품 범위에서 역할별 단일 기준일의 명시 원문과 판독 상태를 확인해야 합니다.')
    roles = (adapter.get('left_role'), adapter.get('right_role'))
    if (any(not isinstance(role, str) or role not in ROLE_LABELS for role in roles)
            or frozenset(roles) not in ROLE_PAIRS or adapter.get('unit', 'DATE') != 'DATE'):
        return unresolved
    try:
        scoped = _scope_lines(payload, item_id)
    except (TypeError, ValueError, AttributeError):
        return unresolved
    if scoped is None:
        return unresolved
    lines, owners, docs = scoped
    full_text = payload['full_ad_text']
    scoped_text = '\n'.join(lines.values())
    try:
        # Completeness must agree with the readable source: retrieval cannot
        # hide another role/date or substitute a different full-ad date value.
        if (any(len(re.findall(ROLE_LABELS[role], full_text))
                != len(re.findall(ROLE_LABELS[role], scoped_text)) for role in roles)
                or Counter(_calendar_date(m) for m in DATE.finditer(full_text))
                != Counter(_calendar_date(m) for m in DATE.finditer(scoped_text))):
            return unresolved
    except ValueError:
        return unresolved
    cited = check.get('evidence_line_refs') or []
    if (not isinstance(cited, list) or not cited
            or any(not isinstance(r, str) or r not in lines for r in cited)):
        return unresolved
    candidates = {role: {} for role in roles}
    try:
        for ref, text in lines.items():
            for role in roles:
                for value, span in _inline_dates(text, role, roles):
                    candidates[role][(ref, span)] = (value, [ref], [ref])
        for role, value, value_refs, all_refs in _table_dates(docs, lines, roles):
            # A table must not duplicate an already explicit date on that line.
            matching = [key for key in candidates[role] if key[0] in value_refs]
            if matching:
                if len(matching) != 1 or candidates[role][matching[0]][0] != value:
                    return unresolved
            else:
                candidates[role][('table', value_refs)] = (value, list(value_refs), all_refs)
    except (TypeError, ValueError, KeyError):
        return unresolved
    if any(len(candidates[role]) != 1 for role in roles):
        return unresolved
    operands = [next(iter(candidates[role].values())) for role in roles]
    try:
        for role, (value, _, _) in zip(roles, operands):
            full_bindings = [d for line in full_text.splitlines()
                             for d, _ in _inline_dates(line, role, roles)]
            if full_bindings and (len(full_bindings) != 1 or full_bindings[0] != value):
                return unresolved
    except ValueError:
        return unresolved
    if any(not set(value_refs).intersection(cited) for _, value_refs, _ in operands):
        return unresolved
    evidence = list(dict.fromkeys(ref for _, _, refs in operands for ref in refs))
    satisfied = operands[0][0] == operands[1][0]
    quotes = ' / '.join('"' + lines[r] + '"' for r in evidence)
    return {'status': 'SATISFIED' if satisfied else 'VIOLATED', 'finding_basis': 'OBSERVED',
            'evidence_ids': list(dict.fromkeys(owners[r] for r in evidence)),
            'evidence_line_refs': evidence,
            'reason': '기준일 비교 근거: ' + quotes + '. 역할별 기준일 ' +
                      operands[0][0].isoformat() + ' / ' + operands[1][0].isoformat() +
                      ('이 일치합니다.' if satisfied else '이 일치하지 않습니다.')}
