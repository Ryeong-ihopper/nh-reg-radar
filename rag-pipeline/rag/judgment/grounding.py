# -*- coding: utf-8 -*-
"""위반·충족 관찰 판정의 수치가 인용 근거에 접지돼 있는지 검사한다.

두 가지만 본다.

1. 수치 접지: 이유문의 비율·소수 수치는 인용한 줄에 실재해야 한다.
   줄 텍스트가 없는 옛 계약에만 소유 문서 폴백을 사용한다. 산술 검산 규칙은 합계를 제시하는
   것이 정상이므로, 이유문이 계산 결과라고 밝힌 값(등호나 '합계' 뒤에 오는 값)이
   인용 창의 다른 수치들의 합과 맞으면 접지된 것으로 본다. 계산 결과라고 밝히지
   않은 값은 우연히 합과 맞아떨어져도 접지로 보지 않는다.
2. 상품 경계: 서로 다른 상품의 수치를 묶지 않는다. 동일 광고/상품의 여러 파일은
   함께 검토할 수 있으며 파일 경계만으로 유효한 근거를 거부하지 않는다.

규칙 ID·사례별 예외는 두지 않는다. 의미 정확도 전체를 검증하는 모듈은 아니다.
"""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Iterable


# 법령·항목 인용의 번호를 수치로 오인하지 않도록 먼저 지운다.
_CITATION = re.compile(r"제\s*\d+\s*(?:조|항|호|목|절|장)(?:\s*의\s*\d+)?|[A-Z]-\d+|R-\d+")

# 비율 계열만 본다. 금리·우대폭·환급률의 산술 오류가 이 범위에 들어오고,
# 날짜·전화번호·조문 번호처럼 계산 대상이 아닌 숫자는 들어오지 않는다.
_RATIO = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*(?:%p|%|퍼센트|프로)|(?<![\d.])(\d+\.\d+)(?![\d.])")

# A positive verbatim-source claim must occur on the cited line, not merely
# somewhere else in its region. Rule quotations and descriptions of absence
# are not assertions that the quoted wording occurs in the advertisement.
_POSITIVE_QUOTE = re.compile(
    r"[‘'\"“]([^’'\"”\n]{2,100})[’'\"”]([^.!?\n]{0,100})")


def ungrounded_source_quotes(reason: str, window: str) -> list[str]:
    normalized = re.sub(r'\s+', '', window)
    missing = []
    for match in _POSITIVE_QUOTE.finditer(reason):
        quote, tail = match.groups()
        prefix = reason[max(0, match.start()-30):match.start()]
        # An observed quote may start the sentence or follow any field name.
        # Do not let "'<name>' is shown" evade checking without an "ad" prefix.
        if re.search(r'(?:규정|기준|예시|요건)(?:은|는|에|의|에서)\s*$', prefix):
            continue
        if not re.search(r'표시|기재|명시|확인|포함|존재', tail):
            continue
        if re.search(r'없|않|미기재|누락|불명|불가|필요|요구|필수', tail):
            continue
        # An explicit ellipsis can omit text, never invent or reorder it.
        parts = [part for part in re.split(r'\.{3,}|…+', re.sub(r'\s+', '', quote)) if part]
        cursor, matched = 0, True
        for part in parts:
            index = normalized.find(part, cursor)
            if index < 0:
                matched = False
                break
            cursor = index + len(part)
        if not matched:
            missing.append(quote)
    return missing

def ratio_values(text: str) -> list[str]:
    """이유문에서 비율·소수 수치를 원문 표기 그대로 뽑는다."""
    cleaned = _CITATION.sub(" ", str(text or "")).replace(",", "")
    values: list[str] = []
    for percent_value, decimal_value in _RATIO.findall(cleaned):
        picked = percent_value or decimal_value
        if picked:
            values.append(picked)
    return list(dict.fromkeys(values))


def cited_window_text(line_refs: Iterable[Any], documents: Iterable[dict[str, Any]]) -> str:
    """Use exact cited line text where provided; retain legacy document fallback.

    A number elsewhere in the same chunk must not validate a wrong line citation.
    Missing keys in an explicit line map are not evidence of that line's text.
    """
    wanted = {str(ref) for ref in line_refs or []}
    if not wanted:
        return ""
    parts: list[str] = []
    for document in documents or []:
        refs = {str(ref) for ref in document.get("line_refs") or []}
        if refs & wanted:
            line_texts = document.get("line_texts")
            if isinstance(line_texts, dict) and line_texts:
                parts.extend(str(line_texts[ref]) for ref in sorted(refs & wanted) if ref in line_texts)
            else:
                parts.append(str(document.get("text") or ""))
    return "\n".join(parts)


def _ungrounded_values(reason: str, window_text: str) -> list[str]:
    values = ratio_values(reason)
    if not values:
        return []
    normalized_window = str(window_text or "").replace(",", "")
    # Numeric tokens, not substrings: 2.0 must not match 12.0, while
    # equivalent representations such as 2 and 2.00 must match.
    window_values = {Decimal(value) for value in re.findall(r"(?<![\d.])\d+(?:\.\d+)?(?![\d.])", normalized_window)}
    grounded = [value for value in values if Decimal(value) in window_values]
    ungrounded = [value for value in values if value not in grounded]
    return [
        value for value in ungrounded
        if not _explicit_sum_matches(reason, value, window_values)
    ]


_ADDITION = re.compile(
    r"(?<![\d.])(\d+(?:\.\d+)?(?:\s*[+-]\s*\d+(?:\.\d+)?)+)"
    r"\s*(?:=|합계(?:는|은|가)?|총합(?:는|은)?)\s*(\d+(?:\.\d+)?)"
)


def _explicit_sum_matches(reason: str, value: str, window_values: set[Decimal]) -> bool:
    for expression, result in _ADDITION.findall(reason):
        terms = [Decimal(term) for term in re.findall(r'[+-]?\d+(?:\.\d+)?', re.sub(r'\s+', '', expression))]
        if (Decimal(result) == Decimal(value) == sum(terms)
                and all(abs(term) in window_values for term in terms)):
            return True
    return False


def grounding_errors(
    *,
    item_id: str,
    location: str,
    reason: str,
    line_refs: Iterable[Any],
    documents: Iterable[dict[str, Any]],
) -> list[str]:
    """위반 근거 한 건의 수치 접지와 자산 경계를 확인한다."""
    documents = list(documents or [])
    refs = [str(ref) for ref in line_refs or []]
    if not refs:
        return []
    errors: list[str] = []
    window = cited_window_text(refs, documents)
    if ungrounded_source_quotes(reason, window):
        errors.append(f"{item_id}: {location} 원문에 있다고 설명한 인용 문구가 선택한 줄에 없음; 해당 문구의 실제 원본 줄을 인용해야 함")
    ungrounded = _ungrounded_values(reason, window)
    if ungrounded:
        errors.append(
            f"{item_id}: {location} 인용한 근거 줄에 없는 수치로 위반 판정 "
            f"({', '.join(ungrounded)})"
        )
    for expression, result in _ADDITION.findall(reason):
        terms = [Decimal(term) for term in re.findall(r'[+-]?\d+(?:\.\d+)?', re.sub(r'\s+', '', expression))]
        if sum(terms) != Decimal(result):
            errors.append(f"{item_id}: {location} 이유문의 합·차 계산이 일치하지 않음")
    products = {
        str(doc["product_id"]) for doc in documents
        if doc.get("product_id") and set(refs).intersection(doc.get("line_refs") or [])
    }
    if len(products) > 1 and len(ratio_values(reason)) > 1:
        errors.append(
            f"{item_id}: {location} 서로 다른 상품의 수치를 한 산술 근거로 묶음 "
            f"({', '.join(sorted(products))})"
        )
    return errors
