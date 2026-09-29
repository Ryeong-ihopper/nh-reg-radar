"""General operational gates derived from the input contract and regulation v2.

Nothing in this module contains advertisement IDs, answer keys or case-specific
corrections.  It only turns explicit routing provenance into hard/soft gates and
extracts deterministic text facts that can constrain model reasoning.
"""
from __future__ import annotations

import re
from typing import Any, Iterable
from .reading_quality import needs_reading_review


CONFIRMED_STATUSES = {"confirmed", "verified", "provided"}
SUPPORTED_PRODUCT_GROUPS = {"예금성", "대출성", "투자성"}

REVIEW_NUMBER = re.compile(
    r"(?:(?:준법감시인\s*)?(?:심의필(?:번호)?|심사필(?:번호)?|심의번호|심사번호)\s*[:：]?\s*"
    r"(?:[가-힣A-Za-z]*[-_ ]*)?(?:\d|O|○|□|X){2,}(?:[-_/](?:\d|O|○|□|X){1,})*"
    r"|(?:\d|O|○|□|X){4}[-_/](?:\d|O|○|□|X){2,}(?=\s*\(\s*심의일))",
    re.I,
)
REVIEW_VALIDITY_PLACEHOLDER_RANGE = re.compile(
    r"유효기간\s*[:：]?\s*"
    r"(?:20\d{2}|[0O○□X]{4})\s*[./-]\s*[0O○□X]{1,2}\s*[./-]\s*[0O○□X]{1,2}\s*[.]?"
    r"\s*(?:~|〜|～|–|—|부터)\s*"
    r"(?:20\d{2}|[0O○□X]{4})\s*[./-]\s*[0O○□X]{1,2}\s*[./-]\s*[0O○□X]{1,2}\s*[.]?",
    re.I,
)
BULLET_MARKER = re.compile(r"(?m)^\s*(?:[•▪◦‣⁃※■□◆◇▶▷●○\uf0a7*+\-]|\d+[.)])\s*")
DATE_TOKEN = re.compile(
    r"(?:20\d{2}[./-]\s*\d{1,2}[./-]\s*\d{1,2}|"
    r"20\d{2}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일)"
)
PHONE_TOKEN = re.compile(r"(?<!\d)(?:0\d{1,2}[- ]?)?\d{3,4}[- ]?\d{4}(?!\d)")
EMAIL_TOKEN = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)


def routing_field(raw: Any, *, default_source: str | None = None) -> dict[str, Any]:
    """Normalize scalar and structured routing fields without upgrading trust."""
    if isinstance(raw, dict):
        value = raw.get("value")
        status = str(raw.get("status") or "unknown").lower()
        return {
            "value": value,
            "source": raw.get("source") or default_source,
            "status": status,
        }
    return {
        "value": raw,
        "source": default_source,
        "status": "unknown" if raw in (None, "") else "inferred",
    }


def confirmed_value(field: Any) -> Any | None:
    normalized = routing_field(field)
    if normalized["status"] not in CONFIRMED_STATUSES:
        return None
    return normalized["value"]


def require_confirmed_product_group(routing: dict[str, Any]) -> str:
    raw = routing.get("product_group")
    if isinstance(raw, dict) and "candidate_product_groups" in raw:
        groups = raw.get("candidate_product_groups") or []
        value = (
            groups[0]
            if len(groups) == 1
            and raw.get("routing_provisional") is False
            and raw.get("status") == "confirmed"
            else None
        )
    else:
        value = confirmed_value(raw)
    if value not in SUPPORTED_PRODUCT_GROUPS:
        raise ValueError(
            "product_group must be 예금성, 대출성, or 투자성 with status "
            "confirmed, verified, or provided"
        )
    return str(value)


def confirmed_template(routing: dict[str, Any]) -> str | None:
    for name in ("template_id", "product_subtype"):
        value = confirmed_value(routing.get(name))
        if value:
            return str(value)
    return None


def confirmed_templates(routing: dict[str, Any]) -> list[str]:
    from .product_context import validate_selected_templates
    primary = confirmed_template(routing)
    if not primary:
        return []
    selected = confirmed_value(routing.get("selected_templates"))
    return validate_selected_templates(primary, selected if selected is not None else [primary])


def parser_visibility_facts(ad: dict[str, Any] | None) -> dict[str, Any]:
    """Pass parser/OCR visibility and line-style measurements through unchanged."""
    pages = []
    for page in (ad or {}).get("pages") or []:
        regions = []
        for region in page.get("regions") or []:
            visibility = region.get("visibility")
            line_styles = [
                {
                    "line_ref": line.get("line_ref"),
                    "bbox": line.get("bbox"),
                    "style": line.get("style"),
                }
                for line in region.get("lines") or []
                if line.get("style") is not None
            ]
            if visibility is not None or line_styles:
                regions.append({
                    "evidence_id": region.get("evidence_id"),
                    "region_id": region.get("region_id"),
                    "visibility": visibility,
                    "line_styles": line_styles,
                })
        pages.append({
            "page_no": page.get("page_no"),
            "canvas_w": page.get("canvas_w"),
            "canvas_h": page.get("canvas_h"),
            "dpi": page.get("dpi"),
            "physical_width_mm": page.get("physical_width_mm"),
            "physical_height_mm": page.get("physical_height_mm"),
            "regions": regions,
        })
    return {
        "source": "parser_or_ocr",
        "pages": pages,
        "recalculated_by_review_pipeline": False,
    }


def deterministic_facts(
    rows: Iterable[dict[str, Any]], *, ad: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Extract format-equivalent observations; do not infer compliance here."""
    rows = list(rows)
    trusted_rows = [row for row in rows if not needs_reading_review(row)]
    text = "\n".join(str(row.get("text_canonical") or row.get("text_search") or "") for row in trusted_rows)
    review_number = REVIEW_NUMBER.search(text)
    return {
        "review_number_present": bool(review_number),
        "uncertain_text_rows_excluded": len(rows) - len(trusted_rows),
        "review_number_placeholder_present": bool(
            review_number
            and re.search(r"(?:0|O|○|□|X){2,}", review_number.group(0), re.I)
        ),
        "review_number_policy": (
            "자리표시용 0/O/○/□/X도 번호 형식이 있으면 존재로 인정한다"
        ),
        "review_validity_placeholder_range_present": bool(
            REVIEW_VALIDITY_PLACEHOLDER_RANGE.search(text)
        ),
        "review_validity_placeholder_policy": (
            "심의 전에는 00.00.00.~00.00.00. 자리표시자로도 "
            "광고 유효기간의 시작일~종료일 형식을 충족한다"
        ),
        "bullet_marker_count": len(BULLET_MARKER.findall(text)),
        "bullet_policy": "불릿 기호의 종류 자체는 의무 형식이 아니다",
        "date_token_count": len(DATE_TOKEN.findall(text)),
        "date_policy": "날짜 표면형식이 달라도 의미상 동일하면 허용한다",
        "phone_token_count": len(PHONE_TOKEN.findall(text)),
        "email_token_count": len(EMAIL_TOKEN.findall(text)),
        "parser_visibility": parser_visibility_facts(ad),
    }


def enforce_review_policy(judgment: dict[str, Any]) -> dict[str, Any]:
    """Keep model verdicts intact but prevent uncalibrated automatic publication."""
    if judgment.get("verdict") in {"VIOLATION", "UNDETERMINED"}:
        judgment["needs_researcher_review"] = True
    return judgment
