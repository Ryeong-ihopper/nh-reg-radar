"""Current coordinate-only visibility scope, explicitly chosen by the user."""
import re
from rag.templates.catalog import required_observation_medium


def text_facet_claim_errors(payload, result):
    """Reject automatic visual conclusions in an explicitly text-only facet."""
    rule = next((r for r in payload.get('rules', [])
                 if r.get('item_id') == result.get('item_id')), {})
    if not (rule.get('source_sheet') == 'HWPX_TEMPLATE'
            and (rule.get('template_basis') or {}).get('text_facet_only') is True):
        return []
    return [f"{result.get('item_id')}: text-only obligation cannot conclude a visual requirement; "
            "check the source text example, leave visual guidance for human review"
            for check in result.get('requirement_checks') or []
            if isinstance(check, dict) and check.get('status') in {'SATISFIED', 'VIOLATED'}
            and required_observation_medium(' '.join(str(check.get(key) or '')
                for key in ('requirement', 'reason')))[2] == '레이아웃']


def requires_visual_review(rule):
    if (rule.get('source_sheet') == 'HWPX_TEMPLATE'
            and (rule.get('template_basis') or {}).get('text_facet_only') is True):
        return False  # The visual facet remains an explicit deferred obligation.
    if rule.get('category') == 'STYLE' or rule.get('required_medium') == '레이아웃':
        return True
    text = ' '.join(str(rule.get(key) or '') for key in (
        'title', 'question', 'criterion', 'guide', 'standard_guidance', 'input_requirement'))
    return bool(re.search(r'시인성|가독성|글자\s*크기|글씨\s*크기|폰트|글꼴|서체|색상|색채|명도|배경색|명암|색\s*대비', text))


def deferred_input_reason(rule):
    if requires_visual_review(rule):
        return '시인성은 사람 검토 대상입니다. 좌표는 위치 확인용이며 색상·폰트·글자 크기·배치는 자동 판정하지 않습니다.'
    return '필요한 외부 자료 또는 원문 구조를 확인할 수 없어 사람 검토가 필요합니다.'
