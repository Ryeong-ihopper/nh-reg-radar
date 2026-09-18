"""Explicit source clauses and unambiguous output contradictions, not ad answers."""
import re
from decimal import Decimal

from rag.judgment.grounding import cited_window_text

QUOTED_REQUIRED = re.compile(r"[‘'\"]([^’'\"\n]{1,60})[’'\"]\s*(?:기재|표시)\s*필수")
AD_SCOPE = re.compile(r"[（(]([^()（）\n]*(?:없는|있는)\s*광고)\s*[)）]")


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
        or re.search(r'(?:자료|근거|정보)(?:가|는)?\s*(?:없|부족|불충분).{0,45}(?:적용|해당|대상|제외|의무)', reason))


ARITHMETIC_WITNESS = re.compile(
    r'검산\s*[:：]\s*([+-]?\d+(?:\.\d+)?(?:\s*[+-]\s*\d+(?:\.\d+)?)+)\s*!=\s*(\d+(?:\.\d+)?)')


def has_arithmetic_mismatch_witness(reason, cited_text):
    """Verify an explicit sum/difference disproof; never infer source formulas.

    More complex or ambiguous calculations require human review. A syntactic
    inequality is insufficient: every operand and the advertised result must
    be cited, and the exact decimal calculation must actually disagree.
    """
    source_values = {Decimal(v) for v in re.findall(r'(?<![\d.])\d+(?:\.\d+)?(?![\d.])', cited_text)}
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
    if not label or len(example) <= len(label):
        return False
    refs = check.get('evidence_line_refs') or []
    ids = set(check.get('evidence_ids') or [])
    text = (cited_window_text(refs, documents) if refs else
            '\n'.join(str(d.get('text') or '') for d in documents if d.get('evidence_id') in ids))
    lines = [line.strip(' •●■※:：[]') for line in text.splitlines() if line.strip()]
    # Only a bare source label or short noun prefix plus that label qualifies.
    # Sentence endings, conditions, rates and other body text fail this match.
    heading = re.compile(r'(?:[가-힣A-Za-z]{1,8}\s+){0,2}' + re.escape(label))
    return bool(lines) and all(heading.fullmatch(line) for line in lines)


def source_claim_errors(payload, result):
    rule = next((r for r in payload.get('rules', []) if r.get('item_id') == result.get('item_id')), {})
    obligations = (rule.get('condition_contract') or {}).get('obligation_checks') or []
    documents = payload.get('documents') or []
    errors = ([f"{result.get('item_id')}: explanation says applicability cannot be determined; unknown is UNDETERMINED, not NOT_APPLICABLE"]
              if unresolved_applicability(result) else [])
    for index, check in enumerate(result.get('requirement_checks') or []):
        if not isinstance(check, dict):
            continue
        if template_heading_only_citation(rule, check, documents):
            errors.append(f"{result.get('item_id')}: requirement_checks[{index}] template heading alone cannot establish the required body disclosure")
        obligation = next((o for o in obligations if o.get('obligation_id') == check.get('obligation_ref')), {})
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
            arithmetic_required = requires_arithmetic_consistency(
                obligation.get('text') or rule.get('criterion', ''))
            if arithmetic_required:
                text = cited_window_text(check.get('evidence_line_refs') or [], documents)
                if not has_arithmetic_mismatch_witness(reason, text):
                    errors.append(f"{result.get('item_id')}: arithmetic violation needs a reproducible cited mismatch: write '검산: a+b-c != d' using actual source values. Equal results are not violations; unresolved formulas require UNDETERMINED. Do not invent an inequality or combine alternative conditions.")
            if re.search(r'(?:수정|재검토)\s*[:：][\s\S]*(?:COMPLIANT|SATISFIED)', reason):
                errors.append(f"{result.get('item_id')}: explanation corrects the conclusion to compliant but status still indicates a violation")
            if (arithmetic_required
                    and re.search(r'(?<!불)일치(?:합니다|함)\s*[.!]?\s*$', str(result.get('reason') or ''))):
                errors.append(f"{result.get('item_id')}: arithmetic violation contradicts the explanation of matching values; identify a source-grounded mismatch or correct the status")
    return errors
