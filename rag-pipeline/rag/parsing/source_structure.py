"""Preserve explicit parser structure without promoting cell OCR to source text."""
from __future__ import annotations

import copy

LINE_ARRAYS = {'line_refs', 'line_ids', 'from_line_ids', 'to_line_ids', 'footnote_line_ids'}
ID_ARRAYS = {'header_cell_ids'}
ID_FIELDS = {'line_ref', 'line_id', 'cell_id', 'table_id', 'relation_id'}
RELATION_TYPES = {'header_for', 'footnote_for', 'continuation_of', 'condition_context'}


def namespace_structure(value, asset_id):
    """Rewrite explicit reference fields only; never alter source text or bbox."""
    if isinstance(value, list):
        return [namespace_structure(item, asset_id) for item in value]
    if not isinstance(value, dict):
        return copy.deepcopy(value)
    result = {}
    for key, item in value.items():
        if key in LINE_ARRAYS | ID_ARRAYS and isinstance(item, list):
            result[key] = [f'{asset_id}::{ref}' if isinstance(ref, str) else ref for ref in item]
        elif key in ID_FIELDS and isinstance(item, str):
            result[key] = f'{asset_id}::{item}'
        else:
            result[key] = namespace_structure(item, asset_id)
    return result


def table_relations(table):
    """Translate explicit cell links, never infer headers from row position.

    Unknown/inferred status is retained so retrieval can audit and defer it.
    A parser must mark the structural observation before automatic expansion.
    """
    if not isinstance(table, dict) or not isinstance(table.get('cells'), list):
        return []
    cells = [cell for cell in table['cells'] if isinstance(cell, dict)]
    by_id = {}
    for cell in cells:
        if cell.get('cell_id'):
            by_id.setdefault(cell['cell_id'], []).append(cell)
    output = []
    for cell in cells:
        targets = cell.get('line_ids') or cell.get('line_refs')
        if not isinstance(targets, list) or not targets:
            continue
        status = cell.get('status') or table.get('status') or 'unknown'
        notes = cell.get('footnote_line_ids')
        if isinstance(notes, list) and notes:
            output.append(dict(type='footnote_for', status=status,
                from_line_ids=list(notes), to_line_ids=list(targets)))
        for header_id in cell.get('header_cell_ids') or []:
            headers = by_id.get(header_id, [])
            if len(headers) != 1:
                continue
            header = headers[0]
            refs = header.get('line_ids') or header.get('line_refs')
            if isinstance(refs, list) and refs:
                header_status = header.get('status') or table.get('status') or 'unknown'
                output.append(dict(type='header_for', status=status if header_status == 'observed' else header_status,
                    from_line_ids=list(refs), to_line_ids=list(targets)))
    return output


def compact_source_structure(document, line_aliases):
    """Only cite supplied lines. Unanchored cell OCR is never model evidence.

    Canonical documents retain full structures for audit. Model structures
    contain only validated references and coordinates, not duplicate cell text.
    Missing endpoints are counted explicitly, never silently fabricated.
    """
    output = {}
    deferred = 0
    relations = []
    for relation in document.get('source_relations') or []:
        if not isinstance(relation, dict):
            deferred += 1
            continue
        left, right = relation.get('from_line_ids'), relation.get('to_line_ids')
        if (relation.get('status') != 'observed' or relation.get('type') not in RELATION_TYPES
                or not isinstance(left, list) or not left or not isinstance(right, list) or not right
                or any(not isinstance(ref, str) or ref not in line_aliases for ref in [*left, *right])):
            deferred += 1
            continue
        value = {'type': relation['type'], 'status': 'observed',
                 'from_line_ids': [line_aliases[ref] for ref in left],
                 'to_line_ids': [line_aliases[ref] for ref in right]}
        if value not in relations:
            relations.append(value)
    if relations:
        output['source_relations'] = relations
    table = document.get('table')
    if isinstance(table, dict):
        cells = []
        for cell in table.get('cells') or []:
            refs = cell.get('line_ids') or cell.get('line_refs') if isinstance(cell, dict) else None
            if not isinstance(refs, list) or not refs or any(
                    not isinstance(ref, str) or ref not in line_aliases for ref in refs):
                deferred += 1
                continue
            projected = {key: copy.deepcopy(cell[key]) for key in
                         ('cell_id', 'row', 'col', 'row_span', 'col_span', 'bbox') if key in cell}
            projected['status'] = cell.get('status') or table.get('status') or 'unknown'
            projected['line_ids'] = [line_aliases[ref] for ref in refs]
            cells.append(projected)
        if cells:
            by_cell = {cell.get('cell_id'): cell for cell in cells if cell.get('cell_id')}
            for original in table.get('cells') or []:
                if not isinstance(original, dict) or original.get('cell_id') not in by_cell:
                    continue
                target = by_cell[original['cell_id']]
                for key, aliases in [('header_cell_ids', {key: key for key in by_cell}),
                                     ('footnote_line_ids', line_aliases)]:
                    refs = original.get(key) or []
                    if (refs and target['status'] == 'observed' and isinstance(refs, list)
                            and all(isinstance(ref, str) and ref in aliases for ref in refs)
                            and (key != 'header_cell_ids' or all(by_cell[ref]['status'] == 'observed' for ref in refs))):
                        target[key] = [aliases[ref] for ref in refs]
                    elif refs:
                        deferred += 1
            output['table'] = {'cells': cells, 'text_policy': 'canonical_lines_only'}
    if deferred:
        output['structure_unavailable_count'] = deferred
    return output
