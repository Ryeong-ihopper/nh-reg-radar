"""Current coordinate-only visibility scope, explicitly chosen by the user."""
import re
from rag.templates.catalog import required_observation_medium


_MEASURED_VISUAL_REQUIREMENT = re.compile(
    r'시인성|가독성|글자\s*크기|글씨\s*크기|폰트|글꼴|서체|색상|색채|명도|'
    r'배경색|명암|색\s*대비|근접\s*(?:표시|기재)|인접\s*(?:표시|기재)|'
    r'같은\s*(?:화면|줄)|동일\s*(?:화면|줄)|우상단|좌상단|배치|위치|'
    r'강조|동일한\s*수준|차별화|'
    r'첫\s*번째\s*(?:웹)?페이지|\d+단계\s*이상|분할\s*게시|'
    r'합리적\s*의사결정'
)


def has_text_decision_facet(rule):
    """Whether a mixed layout row has a complete text-only decision branch.

    Some v2 rows use ``필요매체=레이아웃`` because their question contains a
    broad phrase such as "쉽게 인식", while the approved decision criterion
    defines compliance solely by readable named fields.  Deferring the whole
    row discards that independently decidable text obligation.  A visual
    threshold in the criterion keeps the row in manual review.
    """
    if str(rule.get('category') or '') != 'PRESENCE':
        return False
    if str(rule.get('required_medium') or '').strip() != '레이아웃':
        return False
    criterion = str(rule.get('criterion') or rule.get('decision_criteria') or '').strip()
    # Any actual visual/placement branch keeps the whole source row manual.
    # A later space-limited-media landing-page alternative is not itself a
    # visual measurement, so a textual primary format can remain decidable.
    if not criterion or _MEASURED_VISUAL_REQUIREMENT.search(criterion):
        return False
    return bool(
        re.search(r'(?:표시|기재|명시|포함|확인).{0,30}(?:충족|적정)', criterion)
        and re.search(r'(?:번호|유효기간|명칭|문구|내용|사항|주체|금액|요율)', criterion)
    )


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
    canonical = rule.get('canonical_execution_plan') or {}
    if canonical:
        atoms = canonical.get('obligations') or []
        # The reviewed canonical plan owns the modality split. Legacy
        # category=STYLE must not turn a language/content obligation into a
        # color/placement review.
        automatic = any(not (atom.get('owners') or {}).get('human') for atom in atoms)
        if automatic:
            return False
        if atoms:
            return all((atom.get('owners') or {}).get('human') for atom in atoms)
    if (rule.get('source_sheet') == 'HWPX_TEMPLATE'
            and (rule.get('template_basis') or {}).get('text_facet_only') is True):
        return False  # The visual facet remains an explicit deferred obligation.
    if has_text_decision_facet(rule):
        return False
    # Exact source-line grouping is a parser structure contract.  It is
    # machine-checkable when the parser proves its projection and is handled
    # separately by automated_input_ready().
    if str(rule.get('required_medium') or '').strip() == '원문줄구조':
        return False
    # STYLE is a source taxonomy (format/procedure), not an observation
    # modality. Text-only language and format rules remain automatable.
    if rule.get('required_medium') == '레이아웃':
        return True
    text = ' '.join(str(rule.get(key) or '') for key in (
        'title', 'question', 'criterion', 'guide', 'standard_guidance', 'input_requirement'))
    return bool(_MEASURED_VISUAL_REQUIREMENT.search(text))


def deferred_input_reason(rule):
    if requires_visual_review(rule):
        return '시인성은 사람 검토 대상입니다. 좌표는 위치 확인용이며 색상·폰트·글자 크기·배치는 자동 판정하지 않습니다.'
    return '필요한 외부 자료 또는 원문 구조를 확인할 수 없어 사람 검토가 필요합니다.'


def partition_visual_review_candidates(item_ids, rules):
    """Keep visual rules visible while withholding an automated verdict.

    Candidate discovery and judgment capability are different decisions. A
    layout rule which has already entered the formal candidate set must not be
    discarded merely because its final decision belongs to a reviewer.
    """
    automated = []
    manual = []
    for item_id in item_ids:
        rule = rules[item_id]
        if not requires_visual_review(rule):
            automated.append(item_id)
            continue
        manual.append({
            'item_id': item_id,
            'title': rule.get('title', item_id),
            'question': rule.get('question', ''),
            'facet': 'VISUAL_OR_STRUCTURE',
            'required_medium': rule.get('required_medium'),
            'input_requirement': rule.get('input_requirement'),
            'reason': deferred_input_reason(rule),
        })
    return automated, manual


def attach_visual_retrieval_evidence(manual_rows, retrieved_rows):
    """Attach the retrieval regions that caused each visual review item."""
    retrieved_by_id = {row['item_id']: row for row in retrieved_rows}
    enriched = []
    for row in manual_rows:
        retrieved = retrieved_by_id.get(row['item_id'], {})
        enriched.append({
            **row,
            'trigger_evidence': retrieved.get('trigger_evidence') or [],
            'retrieval_score': retrieved.get('score'),
            'discovery_method': 'retrieved_visual_human_review',
        })
    return enriched
