"""Explicit source clauses and unambiguous output contradictions, not ad answers."""
import re
from decimal import Decimal

from rag.judgment.grounding import cited_window_text, grounded_source_excerpt_present
from rag.judgment.reading_quality import claims_disclosure_absence
from rag.templates.catalog import required_observation_medium

QUOTED_REQUIRED = re.compile(r"[‘'\"]([^’'\"\n]{1,60})[’'\"]\s*(?:기재|표시)\s*필수")
AD_SCOPE = re.compile(r"[（(]([^()（）\n]*(?:없는|있는)\s*광고)\s*[)）]")

# Conservative markers for shared website chrome. These are generic UI
# elements, not advertisement-specific answers. A product breadcrumb that
# contains the actual product name does not match merely because it is near a
# page header.
PAGE_CHROME = re.compile(
    r'금융상품몰|계열사|관련사이트|보안센터|전자민원|개인정보처리|'
    r'금융소비자정보포털|상품공시실|전화상담|이메일상담|고객행복센터|'
    r'고객센터|상담시간|copyright|all\s+rights\s+reserved',
    re.IGNORECASE,
)
CHROME_FACT_RULE = re.compile(
    r'(?:금융회사|판매업자|금융상품판매업자|회사|은행|상호).{0,20}(?:명칭|이름)|'
    r'(?:명칭|이름).{0,20}(?:금융회사|판매업자|회사|은행)|'
    r'연락처|전화번호|이메일|홈페이지|웹사이트|사이트\s*주소|URL|링크|접속',
    re.IGNORECASE,
)


def rule_accepts_page_chrome(rule):
    """Whether shared page chrome can directly prove the fact being checked."""
    rule_text = ' '.join(str(rule.get(key) or '') for key in (
        'title', 'question', 'criterion', 'guide', 'standard_guidance'))
    return bool(CHROME_FACT_RULE.search(rule_text))


def evidence_rows_for_rule(rule, rows, *, keep_doc_ids=()):
    """Remove structurally identified page chrome before body-rule retrieval.

    Evidence already discovered as a trigger stays in the pool. Dropping it
    would leave the retrieved window disagreeing with the discovery record,
    which reads downstream as a missing source rather than as excluded chrome.
    """
    if rule_accepts_page_chrome(rule):
        return list(rows)
    keep = set(keep_doc_ids)
    return [row for row in rows
            if row.get('source_role') != 'PAGE_CHROME' or row.get('doc_id') in keep]

EXTERNAL_VERIFICATION_NOTE = re.compile(
    r'(?:상품설명서|원자료|외부\s*자료).{0,20}(?:대조|확인).{0,10}필요|'
    r'(?:대조|원자료\s*확인).{0,10}필요'
)
CERTAINTY_RULE = re.compile(r'불확실.{0,20}(?:단정|확정)|단정적\s*판단')
CERTAINTY_MARKER = re.compile(
    r'확실(?:히)?|틀림없이|반드시|무조건|(?<!비)보장|확정|변함없이|앞으로도\s*계속|'
    r'하면\s*됩니다|수익률\s*\d+(?:\.\d+)?\s*%'
)
NEGATED_GUARANTEE = re.compile(r'비보장|보장(?:되지|하지)\s*않\w*|보장할\s*수\s*없\w*')


def unresolved_applicability(result):
    """An explicit inability to decide applicability is not a negative finding."""
    reason = str(result.get('reason') or '')
    unsupported_condition = (
        any(check.get('status') == 'NOT_SATISFIED' for check in result.get('condition_checks') or [])
        and not any(result.get(field) for field in ('applicability_evidence_ids',
            'applicability_evidence_line_refs', 'applicability_metadata_fields'))
    )
    return result.get('verdict') == 'NOT_APPLICABLE' and bool(
        unsupported_condition
        or re.search(r'적용\s*여부.{0,24}(?:판단|확인).{0,12}(?:없|불가|어렵)', reason)
        or re.search(r'(?:여부|인지).{0,35}(?:판단|확인).{0,12}(?:없|불가|어렵)', reason)
        or re.search(r'(?:자료|근거|정보)(?:가|는)?\s*(?:없|부족|불충분).{0,45}(?:적용|해당|대상|제외|의무)', reason))


ARITHMETIC_WITNESS = re.compile(
    r'검산\s*[:：]\s*([+-]?\d+(?:\.\d+)?(?:\s*[+-]\s*\d+(?:\.\d+)?)+)\s*!=\s*(\d+(?:\.\d+)?)')
RANGE_WITNESS = re.compile(
    r'범위\s*검산\s*[:：]\s*([+-]?\d+(?:\.\d+)?(?:\s*[+-]\s*\d+(?:\.\d+)?)+)'
    r'\s*not in\s*\[(\d+(?:\.\d+)?),\s*(\d+(?:\.\d+)?)\]')


def has_arithmetic_mismatch_witness(reason, cited_text):
    """Verify an explicit sum/difference disproof; never infer source formulas.

    More complex or ambiguous calculations require human review. A syntactic
    inequality is insufficient: every operand and the advertised result must
    be cited, and the exact decimal calculation must actually disagree.
    """
    source_values = {Decimal(v) for v in re.findall(r'(?<![\d.])\d+(?:\.\d+)?(?![\d.])', cited_text)}
    source_ranges = {(Decimal(low), Decimal(high)) for low, high in re.findall(
        r'최저\s*(?:연\s*)?(\d+(?:\.\d+)?)\s*%\s*[~～∼–-]\s*'
        r'(?:최고|최대)\s*(?:연\s*)?(\d+(?:\.\d+)?)\s*%', cited_text)}
    for expression, low_text, high_text in RANGE_WITNESS.findall(reason):
        terms = [Decimal(v) for v in re.findall(r'[+-]?\d+(?:\.\d+)?', re.sub(r'\s+', '', expression))]
        low, high = Decimal(low_text), Decimal(high_text)
        if ((low, high) in source_ranges and low <= high
                and all(abs(v) in source_values for v in terms)
                and not low <= sum(terms) <= high):
            return True
    for expression, displayed in ARITHMETIC_WITNESS.findall(reason):
        terms = [Decimal(v) for v in re.findall(r'[+-]?\d+(?:\.\d+)?', re.sub(r'\s+', '', expression))]
        if (all(abs(v) in source_values for v in terms) and Decimal(displayed) in source_values
                and sum(terms) != Decimal(displayed)):
            return True
    return False


def requires_arithmetic_consistency(text):
    """A mention of a formula/combined duration is not a numerical assertion.

    Require an explicit numerical consistency obligation before demanding a
    mismatch witness. Disclosure and exemption rules can mention arithmetic
    without making every violation a calculation error.
    """
    return bool(re.search(r'산술|산식|합산|합계|계산', text) and re.search(
        r'정합|일치|일관|어긋|검산|정확(?:성|한|하)|오류|잘못', text))


def source_scope_clauses(question):
    return list(dict.fromkeys(match.group(1) for match in AD_SCOPE.finditer(question)))


def quoted_required_clauses(criterion):
    # Do not detach a quoted token from a conditional branch or exception.
    # Such paragraphs remain losslessly in O1 for source-scoped review.
    lines = [line for line in criterion.splitlines()
             if not re.search(r'이면|하면|으면|경우|때|생략|면제|또는|단\s*[,，]', line)]
    return list(dict.fromkeys(match.group(0) for line in lines for match in QUOTED_REQUIRED.finditer(line)))


def template_heading_only_citation(rule, check, documents):
    """A source label alone cannot establish the meaning of its body example.

    This narrow citation check never infers absence or a violation. It also
    accepts any substantive body wording, without requiring example equality.
    """
    if rule.get('source_sheet') != 'HWPX_TEMPLATE' or check.get('finding_basis') != 'OBSERVED':
        return False
    if check.get('status') not in {'SATISFIED', 'VIOLATED'}:
        return False
    fields = (rule.get('template_basis') or {}).get('fields') or {}
    label = str((fields.get('label') or {}).get('text') or rule.get('title') or '').strip()
    example = str(rule.get('example_text') or (fields.get('example') or {}).get('text') or '').strip()
    if not example:
        canonical_plan = (rule.get('canonical_execution_plan')
                          or (rule.get('template_basis') or {}).get('canonical_plan') or {})
        example = next((
            str(hint.get('text') or '').strip()
            for obligation in canonical_plan.get('obligations') or []
            for hint in obligation.get('interpretation_hints') or []
            if hint.get('role') == 'NON_BINDING_SOURCE_EXAMPLE'
            and str(hint.get('text') or '').strip()
        ), '')
    if not label or len(example) <= len(label):
        return False
    refs = check.get('evidence_line_refs') or []
    ids = set(check.get('evidence_ids') or [])
    text = (cited_window_text(refs, documents) if refs else
            '\n'.join(str(d.get('text') or '') for d in documents if d.get('evidence_id') in ids))
    lines = [line.strip(' •●■※:：[]') for line in text.splitlines() if line.strip()]
    criterion = str(rule.get('criterion') or '')
    normalized_example = re.sub(r'\s+', '', example)
    normalized_citation = re.sub(r'\s+', '', ''.join(lines))
    # When the source expressly defines compliance by semantic similarity to
    # a substantive example, a short noun fragment cannot prove the complete
    # meaning. This is length/role validation only; it neither requires exact
    # example wording nor turns the example into advertisement evidence.
    if (re.search(r'예시\s*문구와\s*유사(?:한\s*)?(?:의미|문구)', criterion)
            and len(normalized_example) >= 16
            and 0 < len(normalized_citation) < 12):
        return True
    if (re.search(r'예시\s*문구와\s*유사(?:한\s*)?(?:의미|문구)', criterion)
            and len(normalized_example) >= 16 and len(normalized_citation) >= 12):
        example_chars = re.sub(r'[^가-힣A-Za-z0-9]', '', example)
        citation_chars = re.sub(r'[^가-힣A-Za-z0-9]', '', ''.join(lines))
        example_trigrams = {example_chars[index:index + 3]
                            for index in range(max(0, len(example_chars) - 2))}
        citation_trigrams = {citation_chars[index:index + 3]
                             for index in range(max(0, len(citation_chars) - 2))}
        # Sentence endings are shared by unrelated Korean disclosures and are
        # not meaningful lexical anchors (for example, both may end in
        # "합니다").  Keep the veto conservative by ignoring only these
        # grammar-only spans.
        grammar_trigrams = {
            ending[index:index + 3]
            for ending in ('합니다', '됩니다', '있습니다', '없습니다', '바랍니다')
            for index in range(max(0, len(ending) - 2))
        }
        example_trigrams -= grammar_trigrams
        citation_trigrams -= grammar_trigrams
        # Zero lexical anchors is a conservative mismatch veto. A paraphrase
        # with any shared substantive three-character span proceeds to LLM
        # review; this check never declares compliance by itself.
        if example_trigrams and citation_trigrams and not example_trigrams & citation_trigrams:
            return True
    # Only a bare source label or short noun prefix plus that label qualifies.
    # Sentence endings, conditions, rates and other body text fail this match.
    heading = re.compile(r'(?:[가-힣A-Za-z]{1,8}\s+){0,2}' + re.escape(label))
    return bool(lines) and all(heading.fullmatch(line) for line in lines)


def page_chrome_only_citation(rule, check, documents):
    """Reject shared site chrome as proof of an unrelated body disclosure.

    Header, footer and navigation text can still prove the company identity,
    contact detail or link it directly states. It cannot prove product terms,
    fees, review procedure or other disclosure content merely by proximity.
    """
    if check.get('finding_basis') != 'OBSERVED':
        return False
    if check.get('status') not in {'SATISFIED', 'VIOLATED'}:
        return False
    if rule_accepts_page_chrome(rule):
        return False
    refs = check.get('evidence_line_refs') or []
    ids = set(check.get('evidence_ids') or [])
    cited_documents = [
        document for document in documents
        if document.get('evidence_id') in ids
        or set(document.get('line_refs') or []).intersection(refs)
    ]
    if cited_documents and all(
        document.get('source_role') == 'PAGE_CHROME'
        for document in cited_documents
    ):
        return True
    text = (cited_window_text(refs, documents) if refs else
            '\n'.join(str(d.get('text') or '') for d in documents
                      if d.get('evidence_id') in ids))
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return bool(lines) and all(
        len(line) <= 180 and PAGE_CHROME.search(line) for line in lines
    )


def observed_grounding_errors(payload, result):
    """Validate model-observed facts against their exact cited advertisement lines."""
    rule = next((r for r in payload.get('rules', [])
                 if r.get('item_id') == result.get('item_id')), {})
    documents = payload.get('documents') or []
    rule_text = ' '.join(str(rule.get(key) or '') for key in (
        'title', 'question', 'criterion', 'v2_note'))
    errors = []
    checks = result.get('requirement_checks') or []
    authored = {o.get('obligation_id'): o for o in (rule.get('condition_contract') or {}).get('obligation_checks') or []}
    for index, check in enumerate(checks):
        if (not isinstance(check, dict) or check.get('finding_basis') != 'OBSERVED'
                or check.get('status') not in {'SATISFIED', 'VIOLATED'}):
            continue
        refs = check.get('evidence_line_refs') or []
        text = cited_window_text(refs, documents)
        numeric = bool((authored.get(check.get('obligation_ref')) or {}).get('deterministic_adapter'))
        absence_claim = claims_disclosure_absence(check, str(result.get('reason') or '') if len(checks) == 1 else '')
        if (not numeric and absence_claim
                and check.get('finding_basis') != 'ABSENCE'):
            errors.append(
                f"{result.get('item_id')}: requirement_checks[{index}] 누락 주장은 "
                "OBSERVED가 아니라 ABSENCE 근거와 전체 판독을 사용해야 함"
            )
        if (refs and not absence_claim
                and not requires_arithmetic_consistency(rule.get('criterion', ''))
                and not grounded_source_excerpt_present(str(check.get('reason') or ''), text)):
            errors.append(
                f"{result.get('item_id')}: requirement_checks[{index}] 관찰 판정 사유에 "
                "인용한 원문 줄의 직접 인용이 없음; 실제 지지 문구를 따옴표로 "
                "제시하고 그 문구가 있는 줄만 인용해야 함"
            )
        if (check.get('status') == 'VIOLATED' and EXTERNAL_VERIFICATION_NOTE.search(
                str(rule.get('v2_note') or ''))):
            errors.append(
                f"{result.get('item_id')}: requirement_checks[{index}] 규칙이 요구하는 "
                "외부 자료 대조 없이 광고 원문만으로 위반을 확정할 수 없음"
            )
        if check.get('status') == 'VIOLATED' and CERTAINTY_RULE.search(rule_text):
            assertion_text = NEGATED_GUARANTEE.sub('', text)
            if not CERTAINTY_MARKER.search(assertion_text):
                errors.append(
                    f"{result.get('item_id')}: requirement_checks[{index}] 인용 원문에 "
                    "불확실한 사항을 확정하는 표현이 없어 단정적 판단 위반을 확정할 수 없음"
                )
    return errors


def source_claim_errors(payload, result):
    rule = next((r for r in payload.get('rules', []) if r.get('item_id') == result.get('item_id')), {})
    obligations = (rule.get('condition_contract') or {}).get('obligation_checks') or []
    documents = payload.get('documents') or []
    errors = ([f"{result.get('item_id')}: explanation says applicability cannot be determined; unknown is UNDETERMINED, not NOT_APPLICABLE"]
              if unresolved_applicability(result) else [])
    errors.extend(observed_grounding_errors(payload, result))
    for index, check in enumerate(result.get('requirement_checks') or []):
        if not isinstance(check, dict):
            continue
        if template_heading_only_citation(rule, check, documents):
            errors.append(f"{result.get('item_id')}: requirement_checks[{index}] template heading alone cannot establish the required body disclosure")
        if page_chrome_only_citation(rule, check, documents):
            errors.append(
                f"{result.get('item_id')}: requirement_checks[{index}] shared page chrome "
                "cannot establish an unrelated body disclosure"
            )
        obligation = next((o for o in obligations if o.get('obligation_id') == check.get('obligation_ref')), {})
        if obligation.get('required_terms') and check.get('status') == 'SATISFIED':
            window = cited_window_text(check.get('evidence_line_refs') or [], documents)
            for term in obligation['required_terms']:
                if not isinstance(term, str) or not term or term not in window:
                    errors.append(f"{result.get('item_id')}: source explicitly requires the quoted term; cited text cannot establish SATISFIED for {check.get('obligation_ref')}")
        match = QUOTED_REQUIRED.fullmatch(obligation.get('text', ''))
        if match and check.get('status') == 'SATISFIED':
            refs = check.get('evidence_line_refs') or []
            ids = set(check.get('evidence_ids') or [])
            text = (cited_window_text(refs, documents) if refs else
                    '\n'.join(str(d.get('text') or '') for d in documents if d.get('evidence_id') in ids))
            if re.sub(r'\s+', '', match.group(1)) not in re.sub(r'\s+', '', text):
                errors.append(f"{result.get('item_id')}: source explicitly requires the quoted term; cited text cannot establish SATISFIED for {check.get('obligation_ref')}")
        reason = str(check.get('reason') or '')
        if check.get('status') in {'VIOLATED', 'MISSING'}:
            program = (rule.get('condition_contract') or {}).get('review_program') or {}
            if (not program.get('line_structure_policy')
                    and required_observation_medium(str(rule.get('guide') or rule.get('criterion') or ''))[2] == '원문줄구조'):
                refs = list(dict.fromkeys(check.get('evidence_line_refs') or []))
                text = cited_window_text(refs, documents)
                marker_count = len(re.findall(r'(?:^|\s)(?:※|\*|•|●)\s*\S', text))
                sentence_count = len(re.findall(
                    r'(?:습니다|합니다|됩니다|있습니다|없습니다|바랍니다|않습니다|입니다)\s*[.!?]',
                    text,
                ))
                if len(refs) != 1 or max(marker_count, sentence_count) < 2:
                    errors.append(
                        f"{result.get('item_id')}: same-line notice violation needs one cited source line "
                        "containing at least two distinct notice statements; separate lines or one statement "
                        "cannot establish a violation"
                    )
            # Canonical atoms declare their numeric adapter explicitly. Prose
            # saying that additional arithmetic is *not* required must not
            # turn a semantic disclosure's absence into a calculation error.
            arithmetic_required = (
                (obligation.get('deterministic_adapter') or {}).get('kind')
                == 'ADVERTISED_ARITHMETIC_CONSISTENCY'
                if program else requires_arithmetic_consistency(
                    obligation.get('text') or rule.get('criterion', ''))
            )
            if arithmetic_required:
                text = cited_window_text(check.get('evidence_line_refs') or [], documents)
                if not has_arithmetic_mismatch_witness(reason, text):
                    errors.append(f"{result.get('item_id')}: arithmetic violation needs a reproducible cited mismatch: write '검산: a+b-c != d' for an asserted equality or '범위 검산: a+b-c not in [low,high]' for an advertised range, using actual source values. Equal results and values inside the range are not violations; unresolved formulas require UNDETERMINED. Do not invent an inequality or combine alternative conditions.")
            if re.search(r'(?:수정|재검토)\s*[:：][\s\S]*(?:COMPLIANT|SATISFIED)', reason):
                errors.append(f"{result.get('item_id')}: explanation corrects the conclusion to compliant but status still indicates a violation")
            if (arithmetic_required
                    and re.search(r'(?<!불)일치(?:합니다|함)\s*[.!]?\s*$', str(result.get('reason') or ''))):
                errors.append(f"{result.get('item_id')}: arithmetic violation contradicts the explanation of matching values; identify a source-grounded mismatch or correct the status")
    return errors
