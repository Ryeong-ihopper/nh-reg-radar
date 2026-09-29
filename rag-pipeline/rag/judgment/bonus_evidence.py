"""Read complete bonus-rate operands from cited text or observed table links."""
from __future__ import annotations

import json
import re
from decimal import Decimal

NUMBER = r'\d+(?:\.\d+)?'
RATE = re.compile(rf'연\s*({NUMBER})\s*(%p|%)(?![A-Za-z%])')
RESTRICTION = re.compile(r'중복.{0,12}(?:불가|불가능|제한|않)|택일|선택|절사|반올림|기본.{0,12}포함|우대.{0,12}제외')


def _scope_lines(payload, item_id):
    # reading_quality imports the dispatcher, so resolve this shared guard
    # only after the modules have loaded. A visited scope may still be unreadable.
    from .reading_quality import needs_reading_review, unresolved_scope_readings

    scopes = payload.get('evidence_scope') or {}
    reading = payload.get('reading_quality') or {}
    if not isinstance(scopes, dict) or not isinstance(reading, dict):
        return None
    scope = scopes.get(item_id) or {}
    if (not isinstance(scope, dict) or scope.get('complete_ad_scan') is not True
            or payload.get('parser_coverage') != 'READY'
            or reading.get('global_scan_incomplete', False) is not False
            or needs_reading_review({'text': payload.get('full_ad_text')})):
        return None
    allowed = scope.get('evidence_ids')
    documents = payload.get('documents') or []
    if (not isinstance(allowed, list) or not allowed
            or any(not isinstance(key, str) or not key for key in allowed)
            or len(allowed) != len(set(allowed)) or not isinstance(documents, list)
            or any(not isinstance(doc, dict) for doc in documents)):
        return None
    docs = [doc for doc in documents if doc.get('evidence_id') in allowed]
    if len(docs) != len(allowed) or len({doc['evidence_id'] for doc in docs}) != len(allowed):
        return None
    # Missing legacy identity fields remain bound by the frozen evidence scope;
    # explicit identities must agree. Multiple files of the same ad are allowed.
    for keys in (('ad_id',), ('product_id',), ('revision_id', 'advertisement_revision_id'),
                 ('rate_variant_id',)):
        values = [row[key] for row in [payload, scope, *docs] for key in keys
                  if row.get(key) is not None]
        if any(not isinstance(value, str) or not value for value in values) or len(set(values)) > 1:
            return None
    for doc in docs:
        refs, texts = doc.get('line_refs'), doc.get('line_texts')
        if (not isinstance(refs, list) or not refs
                or any(not isinstance(ref, str) or not ref for ref in refs)
                or len(refs) != len(set(refs)) or not isinstance(texts, dict)
                or set(refs) != set(texts)
                or any(not isinstance(text, str) for text in texts.values())):
            return None
    if unresolved_scope_readings(payload, item_id):
        return None
    # A clean view can supersede an uncertain fallback but the fallback itself
    # must never own a numeric citation or supply a table link.
    docs = [doc for doc in docs if not needs_reading_review(doc)]
    lines = {}
    owners = {}
    for doc in docs:
        for ref, text in doc['line_texts'].items():
            if ref in lines and lines[ref] != text:
                return None
            lines[ref] = text
            owners.setdefault(ref, doc['evidence_id'])
    return docs, lines, owners


def bonus_operands(payload, item_id, cited_refs):
    bundle = _scope_lines(payload, item_id)
    if bundle is None:
        return None
    docs, lines, owners = bundle
    if (not isinstance(cited_refs, list) or not cited_refs
            or any(not isinstance(ref, str) or ref not in lines for ref in cited_refs)):
        return None
    cited = list(dict.fromkeys(cited_refs))
    text = '\n'.join(lines[r] for r in cited)
    # Uncited restrictions cannot be ignored merely because a numeric leaf
    # selected only favorable lines. Full-ad text is scoped by the caller.
    if RESTRICTION.search('\n'.join([*lines.values(), str(payload.get('full_ad_text') or '')])):
        return None
    counts = re.findall(r'우대조건\s*(?:총\s*)?(\d+)\s*개', text)
    maxima = re.findall(rf'(?:최대\s*우대금리|우대금리\s*최대)\s*연\s*({NUMBER})\s*(%p|%)(?![A-Za-z%])', text)
    if len(counts) != 1 or int(counts[0]) < 1 or len(maxima) != 1:
        return None
    count, (maximum, unit) = int(counts[0]), maxima[0]
    components = re.findall(rf'우대조건\s*(\d+)\s*[:：]\s*연\s*({NUMBER})\s*(%p|%)(?![A-Za-z%])', text)
    values = None
    evidence = cited
    if components:
        if len(components) != count or len({c[0] for c in components}) != count or {c[2] for c in components} != {unit}:
            return None
        values = [Decimal(c[1]) for c in components]
    else:
        candidates, seen = [], set()
        for doc in docs:
            table = doc.get('table') or {}
            signature = json.dumps(table, sort_keys=True, ensure_ascii=False)
            if not table or signature in seen:
                continue
            seen.add(signature)
            cells = table.get('cells') or []
            by_id = {c.get('cell_id'): c for c in cells}
            if not cells or None in by_id or len(by_id) != len(cells):
                continue
            if any(c.get('status', table.get('status')) != 'observed' or c.get('row_span', 1) != 1
                   or c.get('col_span', 1) != 1 or not isinstance(c.get('row'), int)
                   or not isinstance(c.get('col'), int) for c in cells):
                continue

            def refs(cell):
                return cell.get('line_refs') or cell.get('line_ids') or []

            if any(not refs(c) or any(r not in lines for r in refs(c)) for c in cells):
                continue
            cell_refs = [r for c in cells for r in refs(c)]
            if len(cell_refs) != len(set(cell_refs)) or len({(c['row'], c['col']) for c in cells}) != len(cells):
                continue
            if not any(r in cited for c in cells for r in refs(c)):
                continue

            def body(cell):
                return ' '.join(lines[r] for r in refs(cell)).strip()

            rate_rows, used, invalid = {}, [], False
            for cell in cells:
                headers = [by_id[h] for h in cell.get('header_cell_ids') or [] if h in by_id]
                if len(headers) != len(cell.get('header_cell_ids') or []):
                    invalid = True
                    break
                header_text = ' '.join(body(h) for h in headers)
                if '우대금리' not in header_text:
                    continue
                units = re.findall(r'연[^\d%]{0,8}(%p|%)(?![A-Za-z%])', header_text)
                if not units or set(units) != {unit}:
                    invalid = True
                    break
                value = re.fullmatch(rf'(?:연\s*)?({NUMBER})\s*(%p|%)?', body(cell))
                if not value or (value[2] and value[2] != unit) or cell.get('row') in rate_rows:
                    invalid = True
                    break
                condition_cells = [c for c in cells if c.get('row') == cell.get('row') and c is not cell
                    and any(h in by_id and re.search(r'우대조건|우대항목', body(by_id[h]))
                            for h in c.get('header_cell_ids') or [])]
                if len(condition_cells) != 1 or not body(condition_cells[0]):
                    invalid = True
                    break
                condition_headers = [by_id[h] for h in condition_cells[0].get('header_cell_ids') or [] if h in by_id]
                notes = [r for c in [cell, condition_cells[0], *headers, *condition_headers] for r in c.get('footnote_line_ids') or []]
                # A footnote of unknown meaning blocks arithmetic. Only these
                # explicit unit/tax/cumulative statements require no branching.
                if any(r not in lines or not re.fullmatch(
                        r'[※*\s]*(?:모든 우대조건 중복 적용 가능|세전|연 이율)[.\s]*', lines[r]) for r in notes):
                    invalid = True
                    break
                rate_rows[cell.get('row')] = Decimal(value[1])
                used.extend([*refs(cell), *refs(condition_cells[0]), *(r for h in [*headers, *condition_headers] for r in refs(h)), *notes])
            if not invalid and len(rate_rows) == count:
                candidates.append((list(rate_rows.values()), used))
        if len(candidates) != 1:
            return None
        values, table_refs = candidates[0]
        evidence = list(dict.fromkeys([*cited, *table_refs]))
    return {'maximum': Decimal(maximum), 'sum': sum(values), 'unit': unit,
            'evidence_line_refs': evidence, 'evidence_ids': list(dict.fromkeys(owners[r] for r in evidence)),
            'quotes': '\n'.join(lines[r] for r in evidence)}
