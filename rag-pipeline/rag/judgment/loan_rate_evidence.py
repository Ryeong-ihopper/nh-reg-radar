"""Exact endpoint arithmetic from one readable, frozen advertisement scope.

The reviewed policy selects this adapter and its MAX/MIN source predicate.
Neither source filenames nor template versions select arithmetic here. Values
come only from original line text; example values and model arithmetic are not
inputs. Unsupported role/variant/reading associations remain undetermined.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any

KIND = "LOAN_RATE_ENDPOINT_EQUALITY"
NUMBER = r"[+-]?[0-9]+(?:\.[0-9]+)?"
ROLE_LABELS = {
    "MAX": r"(?<![가-힣])최고\s*(?:대출\s*)?(?:금리)?",
    "MIN": r"(?<![가-힣])최저\s*(?:대출\s*)?(?:금리)?",
    "base_rate": r"(?<![가-힣])기준\s*금리",
    "spread_rate": r"(?<![가-힣])가산\s*금리",
    "bonus_rate": r"(?<![가-힣])우대\s*금리",
    "subsidy_rate": r"(?<![가-힣])이차\s*보전(?:\s*(?:금리|율))?",
}
LABELS = {role: re.compile(label) for role, label in ROLE_LABELS.items()}
VALUES = {role: re.compile(
    label + rf"\s*[:：=]?\s*(?P<period>연|월|일)?\s*(?P<value>{NUMBER})"
    r"\s*(?P<unit>[%％][pP]?)(?![A-Za-z%％0-9])"
) for role, label in ROLE_LABELS.items()}
SINGLE_RATE = re.compile(
    rf"(?<![가-힣])대출\s*금리\s*[:：|]?\s*(?P<period>연|월|일)\s*"
    rf"(?P<value>{NUMBER})\s*(?P<unit>[%％][pP]?)(?![A-Za-z%％0-9])"
)
RESTRICTION = re.compile(
    r"반올림|절사|버림|사사오입|조건부|택일|선택\s*(?:적용|조건|가능|시)"
    r"|중복[^\n]{0,16}(?:불가|불가능|제한|않)"
    r"|(?:금리|우대|이차보전|상환방식|등급|대출기간|조건)[^\n]{0,24}(?:선택|별로|상이|달라)"
    r"|(?:상환\s*방식|(?:신용\s*)?등급|대출\s*기간|거치\s*기간|금리\s*유형)[^\n]{0,40}(?:또는|택일|각각|별로|상이|선택)"
    r"|[%％][pP]?\s*(?:또는|택일|중\s*선택)"
    r"|고정\s*금리[^\n]{0,40}변동\s*금리|변동\s*금리[^\n]{0,40}고정\s*금리"
)
REVISION_KEYS = ("revision_id", "advertisement_revision_id")
# These are ambiguity guards, not aliases from which a value is extracted.
# An unsupported discount/subsidy reference must not look like non-mention.
OPTIONAL_ROLE_AMBIGUITY = {
    "bonus_rate": re.compile(r"우대|감면|할인"),
    "subsidy_rate": re.compile(r"보전|보조|이차\s*지원|(?:이자|금리)\s*지원"
                              r"|(?:지원|보조)[^\n]{0,16}[0-9][^\n]{0,8}[%％]"
                              r"|[%％][pP]?\s*(?:지원|보조)"),
}
UNBOUND_OPTIONAL_PERCENT = {
    role: re.compile(rf"(?:{words})[^\n]{{0,32}}[0-9][^\n]{{0,8}}[%％]"
                     rf"|[%％][pP]?[^\n]{{0,8}}(?:{words})")
    for role, words in {"bonus_rate": "우대|감면|할인", "subsidy_rate": "보전|보조|지원"}.items()
}


def _unknown(endpoint: Any, code: str) -> dict[str, Any]:
    return {
        "status": "UNDETERMINED", "finding_basis": "UNKNOWN",
        "evidence_ids": [], "evidence_line_refs": [],
        "reason": "같은 대출금리 범위의 판독·수치 역할·연 단위·조건을 확인해야 합니다.",
        "calculation_trace": {"adapter": KIND, "endpoint": endpoint,
                              "state": "UNDETERMINED", "reason_code": code},
    }


def _scope_lines(payload: dict[str, Any], item_id: str):
    # The guard itself imports review_program. Keep this dependency local so
    # the computed-check dispatcher can import this adapter without a cycle.
    from .reading_quality import needs_reading_review, unresolved_scope_readings

    scopes = payload.get("evidence_scope") or {}
    reading = payload.get("reading_quality") or {}
    if not isinstance(scopes, dict) or not isinstance(reading, dict):
        return None, "INVALID_SCOPE_METADATA"
    scope = scopes.get(item_id) or {}
    if not isinstance(scope, dict):
        return None, "INVALID_SCOPE_METADATA"
    if (payload.get("parser_coverage") != "READY"
            or scope.get("complete_ad_scan") is not True
            or reading.get("global_scan_incomplete", False) is not False
            or not isinstance(payload.get("full_ad_text"), str)
            or not payload["full_ad_text"].strip()):
        return None, "INCOMPLETE_SCOPE"
    if needs_reading_review({"text": payload["full_ad_text"]}):
        return None, "UNREADABLE_FULL_TEXT"
    ids = scope.get("evidence_ids")
    if (not isinstance(ids, list) or not ids or any(not isinstance(x, str) or not x for x in ids)
            or len(ids) != len(set(ids))):
        return None, "INVALID_SCOPE_IDENTIFIERS"
    documents = payload.get("documents") or []
    if not isinstance(documents, list) or any(not isinstance(d, dict) for d in documents):
        return None, "INVALID_DOCUMENTS"
    docs = [d for d in documents if d.get("evidence_id") in ids]
    if len(docs) != len(ids) or len({d["evidence_id"] for d in docs}) != len(ids):
        return None, "MISSING_OR_DUPLICATE_DOCUMENT"
    if any(not isinstance(d.get(key), str) or not d[key]
           for d in docs for key in ("asset_id", "product_id")):
        return None, "ASSET_PRODUCT_SCOPE_NOT_UNIQUE"
    identities = {(d["asset_id"], d["product_id"]) for d in docs}
    if len(identities) != 1:
        return None, "ASSET_PRODUCT_SCOPE_NOT_UNIQUE"
    identity = next(iter(identities))
    if any(key in scope and scope[key] != identity[index]
           for index, key in enumerate(("asset_id", "product_id"))):
        return None, "ASSET_PRODUCT_SCOPE_CONFLICT"
    ad_values = [d["ad_id"] for d in docs if d.get("ad_id") is not None]
    if any(not isinstance(value, str) or not value for value in ad_values):
        return None, "ADVERTISEMENT_SCOPE_CONFLICT"
    if payload.get("ad_id") is not None and (not isinstance(payload["ad_id"], str) or not payload["ad_id"]):
        return None, "ADVERTISEMENT_SCOPE_CONFLICT"
    ad_ids = set(ad_values)
    if len(ad_ids) > 1 or (ad_ids and payload.get("ad_id") and ad_ids != {payload["ad_id"]}):
        return None, "ADVERTISEMENT_SCOPE_CONFLICT"
    revision_values = [value for d in [payload, scope, *docs] for key in REVISION_KEYS
                       if (value := d.get(key)) is not None]
    if any(not isinstance(x, str) or not x for x in revision_values):
        return None, "REVISION_SCOPE_CONFLICT"
    revisions = set(revision_values)
    if len(revisions) > 1:
        return None, "REVISION_SCOPE_CONFLICT"
    variant_values = [d["rate_variant_id"] for d in [scope, *docs]
                      if d.get("rate_variant_id") is not None]
    if any(not isinstance(x, str) or not x for x in variant_values) or len(set(variant_values)) > 1:
        return None, "RATE_VARIANT_SCOPE_CONFLICT"
    for doc in docs:
        refs, texts = doc.get("line_refs"), doc.get("line_texts")
        if refs is not None and (not isinstance(refs, list)
                or any(not isinstance(ref, str) or not ref for ref in refs)):
            return None, "INVALID_LINE_PROVENANCE"
        if texts is not None and (not isinstance(texts, dict)
                or any(not isinstance(ref, str) or not isinstance(text, str)
                       for ref, text in texts.items())):
            return None, "INVALID_LINE_PROVENANCE"
    if unresolved_scope_readings(payload, item_id):
        return None, "UNRESOLVED_SCOPE_READING"

    # Only aligned clean views supply individual line citations. A region
    # fallback is usable for completeness only if those exact source lines
    # are independently available; its geometry is never changed or inferred.
    aligned = [d for d in docs if not needs_reading_review(d)
               and d.get("span_status") != "region_level_selected_text"]
    lines, owners = {}, {}
    for doc in aligned:
        refs, texts = doc.get("line_refs"), doc.get("line_texts")
        if (not isinstance(refs, list) or not refs or len(set(refs)) != len(refs)
                or not isinstance(texts, dict) or set(refs) != set(texts)
                or any(not isinstance(r, str) or not isinstance(texts[r], str) for r in refs)):
            return None, "INCOMPLETE_LINE_PROVENANCE"
        for line_ref in refs:
            if line_ref in lines and lines[line_ref] != texts[line_ref]:
                return None, "CONFLICTING_SOURCE_LINE_VIEWS"
            lines[line_ref] = texts[line_ref]
            owners.setdefault(line_ref, doc["evidence_id"])
    if not lines:
        return None, "NO_ALIGNED_SOURCE_LINES"
    for doc in docs:
        if doc in aligned:
            continue
        refs = doc.get("line_refs")
        if not isinstance(refs, list) or not refs or any(r not in lines for r in refs):
            return None, "UNALIGNED_SOURCE_SCOPE"
    return {
        "lines": lines, "owners": owners, "scope_ids": ids,
        "asset_id": identity[0], "product_id": identity[1],
        "revision_id": next(iter(revisions)) if revisions else None,
        "revision_binding": "EXPLICIT_ID" if revisions else "FROZEN_REQUEST_EVIDENCE_SCOPE",
    }, None


def _rate_value(match, line_ref: str):
    raw = match.group("value")
    if len(raw) > 100:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    if not value.is_finite():
        return None
    return {"value": value, "unit": match.group("unit").replace("％", "%").lower(),
            "period": match.group("period"), "line_ref": line_ref,
            "span": list(match.span()), "raw_value": raw}


def _operands(bundle, full_text: str, endpoint: str, cited_refs):
    lines = bundle["lines"]
    if (not isinstance(cited_refs, list) or not cited_refs
            or any(not isinstance(r, str) or r not in lines for r in cited_refs)):
        return None, "MISSING_OR_OUT_OF_SCOPE_CITATION"
    text = "\n".join(lines.values())
    if RESTRICTION.search(text) or RESTRICTION.search(full_text):
        return None, "UNSUPPORTED_CONDITION_OR_ROUNDING"
    observations = {}
    counts = {}
    for role, label in LABELS.items():
        count = sum(len(label.findall(s)) for s in lines.values())
        found = [(r, match) for r, s in lines.items() for match in VALUES[role].finditer(s)]
        counts[role] = count
        # Equal values under distinct source references can be different
        # conditions; do not collapse them into one advertised operand.
        if count != len(found) or count > 1:
            return None, "AMBIGUOUS_OR_UNREADABLE_ROLE_" + role
        if count:
            observations[role] = _rate_value(found[0][1], found[0][0])
            if observations[role] is None:
                return None, "INVALID_DECIMAL_" + role
        # Complete full text must not contain an uncited/unretrieved operand
        # occurrence that the supplied line views have omitted.
        if len(label.findall(full_text)) != count:
            return None, "FULL_TEXT_LINE_SCOPE_DISAGREEMENT_" + role
    if not all(role in observations for role in ("base_rate", "spread_rate")):
        return None, "BASE_OR_SPREAD_NOT_OBSERVED"
    for role, ambiguity in OPTIONAL_ROLE_AMBIGUITY.items():
        if role not in observations and (ambiguity.search(text) or ambiguity.search(full_text)):
            return None, "UNRESOLVED_OPTIONAL_ROLE_" + role
        # A canonical maximum/aggregate value does not assign a second
        # discount, subsidy or condition-specific percentage to that value.
        # Preserve such a variant as unknown rather than silently ignoring it.
        remaining_text = VALUES[role].sub("", text)
        remaining_full_text = VALUES[role].sub("", full_text)
        if (UNBOUND_OPTIONAL_PERCENT[role].search(remaining_text)
                or UNBOUND_OPTIONAL_PERCENT[role].search(remaining_full_text)):
            return None, "UNBOUND_ADDITIONAL_OPTIONAL_RATE_" + role
    target = observations.get(endpoint)
    if target is None:
        singles = [(r, match) for r, s in lines.items() for match in SINGLE_RATE.finditer(s)]
        if (counts["MAX"] or counts["MIN"] or counts["bonus_rate"] or len(singles) != 1
                or len(SINGLE_RATE.findall(full_text)) != 1):
            return None, "ENDPOINT_NOT_OBSERVED"
        target = _rate_value(singles[0][1], singles[0][0])
        if target is None:
            return None, "INVALID_SINGLE_ANNUAL_RATE"
        target["endpoint_role"] = "SINGLE_RATE_WHEN_BONUS_UNMENTIONED"
    else:
        target["endpoint_role"] = endpoint
    observed = [*observations.values(), target]
    if any(row["unit"] != "%" or row["period"] not in {None, "연"} for row in observed):
        return None, "MIXED_OR_UNSUPPORTED_RATE_UNITS"
    if target["period"] != "연":
        return None, "ANNUAL_ENDPOINT_UNIT_NOT_OBSERVED"
    role_refs = {row["line_ref"] for row in observed}
    if not role_refs.intersection(cited_refs):
        return None, "CITATION_DOES_NOT_TOUCH_RATE_BUNDLE"
    defaults = []
    for role in ("bonus_rate", "subsidy_rate"):
        if role not in observations:
            observations[role] = {"value": Decimal(0), "unit": "%", "period": "연",
                "line_ref": None, "span": None, "raw_value": None}
            defaults.append(role)
    return {"observations": observations, "target": target, "defaulted": defaults,
            "evidence_line_refs": [r for r in lines if r in role_refs]}, None


def endpoint_check(adapter: dict[str, Any], check: dict[str, Any],
                   payload: dict[str, Any], item_id: str) -> dict[str, Any] | None:
    """Override a model check only with source-bound Decimal MAX/MIN equality.

    Missing bonus/subsidy roles may default to zero only because this reviewed
    adapter's source predicate expressly authorizes that arithmetic exception.
    This says nothing about the actual product's benefits or subsidy existence.
    Base, spread and endpoint never receive an absence default.
    """
    if adapter.get("kind") != KIND:
        return None
    endpoint = adapter.get("endpoint")
    if not isinstance(endpoint, str) or endpoint not in {"MAX", "MIN"}:
        return _unknown(endpoint, "UNSUPPORTED_ENDPOINT")
    bundle, error = _scope_lines(payload, item_id)
    if error:
        return _unknown(endpoint, error)
    values, error = _operands(bundle, payload["full_ad_text"], endpoint,
                              check.get("evidence_line_refs"))
    if error:
        return _unknown(endpoint, error)
    observations = values["observations"]
    roles = ["base_rate", "spread_rate"]
    if endpoint == "MIN":
        roles.append("bonus_rate")
    roles.append("subsidy_rate")
    numbers = [observations[role]["value"] for role in roles]
    with localcontext() as context:
        context.prec = max(28, max(len(v.as_tuple().digits) + abs(v.as_tuple().exponent)
                                  for v in numbers) + 4)
        expected = numbers[0] + numbers[1] - sum(numbers[2:], Decimal(0))
    actual = values["target"]["value"]
    satisfied = expected == actual
    refs = values["evidence_line_refs"]
    quotes = " / ".join('"' + bundle["lines"][r] + '"' for r in refs)
    expression = str(numbers[0]) + "+" + str(numbers[1]) + "".join("-" + str(n) for n in numbers[2:])
    reason = ("금리 산식 근거: " + quotes + ". 검산: " + expression
              + (" = " if satisfied else " != ") + str(actual) + ". 계산값: " + str(expected) + ".")
    if values["defaulted"]:
        reason += " 완전 판독에서 미기재된 우대금리/이차보전 항목에만 원문이 허용한 산식상 0 예외를 적용했습니다."
    trace = {
        "adapter": KIND, "endpoint": endpoint, "state": "SATISFIED" if satisfied else "VIOLATED",
        "scope": {key: bundle[key] for key in ("asset_id", "product_id", "revision_id", "revision_binding")},
        "operands": {role: {"value": str(row["value"]), "line_ref": row["line_ref"],
                            "span": row["span"], "defaulted": role in values["defaulted"]}
                     for role, row in observations.items() if role not in {"MAX", "MIN"}},
        "advertised_endpoint": {"value": str(actual), "line_ref": values["target"]["line_ref"],
                                "role": values["target"]["endpoint_role"]},
        "calculated_endpoint": str(expected), "decimal_comparison": "EXACT_NO_ROUNDING",
        "absence_defaults": {"roles": values["defaulted"], "basis": "COMPLETE_READABLE_FROZEN_SCOPE",
                             "scope_evidence_ids": bundle["scope_ids"], "product_nonexistence_inferred": False},
    }
    return {"status": "SATISFIED" if satisfied else "VIOLATED", "finding_basis": "OBSERVED",
            "evidence_ids": list(dict.fromkeys(bundle["owners"][r] for r in refs)),
            "evidence_line_refs": refs, "reason": reason, "calculation_trace": trace}
