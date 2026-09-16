"""Fail closed if any selected physical template row loses its disposition."""


def audit_template_coverage(catalog, section, rules, requested_ids, deferred):
    selection = catalog.select(section, status='provided')
    if selection['status'] != 'SELECTED':
        raise ValueError('selected template has no authoritative source rows')
    source_ids = {row['item_id'] for row in selection['entries']}
    selected = [rule for rule in rules if rule.get('product_subtype') == section]
    represented = []
    for rule in selected:
        members = (rule.get('template_basis') or {}).get('alternative_members') or []
        represented.extend([member['item_id'] for member in members] if members else [rule['item_id']])
    if set(represented) != source_ids or len(represented) != len(set(represented)):
        raise ValueError('selected template source rows are missing, duplicated, or unexpected')
    deferred_ids = {row['item_id'] for row in deferred}
    expected = {rule['item_id'] for rule in selected}
    missing = expected - set(requested_ids) - deferred_ids
    if missing:
        raise ValueError('selected template rules have no disposition: ' + ', '.join(sorted(missing)))
    return {
        'policy': 'selected-template-coverage-v1', 'template_section': section,
        'source_row_count': len(source_ids), 'rule_count': len(expected),
        'requested_count': len(expected & set(requested_ids)),
        'manual_review_count': len(expected & deferred_ids), 'missing_count': 0,
        'items': [{'item_id': rule['item_id'], 'title': rule['title'],
                   'requested': rule['item_id'] in requested_ids,
                   'manual_review_required': rule['item_id'] in deferred_ids,
                   'source_item_ids': [m['item_id'] for m in
                       (rule.get('template_basis') or {}).get('alternative_members', [])] or [rule['item_id']]}
                  for rule in selected],
    }
