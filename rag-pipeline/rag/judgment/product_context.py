"""Explicit product composition; no product inference from filenames or examples."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def product_contexts():
    path = Path(__file__).resolve().parents[2] / "config/product-contexts-v1.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != "product-contexts-v1":
        raise ValueError("unsupported product context policy")
    return value["contexts"]


def resolve_product_templates(product, *, available_templates=None):
    """Return base + confirmed components, preserving an incomplete scope."""
    base = product["product_classification_code"]
    codes = product.get("underlying_products") or []
    status = product.get("underlying_products_status", "UNCONFIRMED")
    if not isinstance(codes, list) or len(codes) != len(set(codes)):
        raise ValueError("underlying products must be a unique list")
    if status not in {"CONFIRMED", "UNCONFIRMED"}:
        raise ValueError("invalid underlying product confirmation")
    context = next((c for c in product_contexts() if c["base_template"] == base), None)
    if not context:
        if codes:
            raise ValueError("underlying products are unsupported for this template")
        if any(base in c["restricted_standalone_templates"] for c in product_contexts()):
            raise ValueError("현재 펀드·ETF·ELB 심의방법은 퇴직연금 운용상품 범위에서 사용합니다.")
        return [base], None, True
    components = {c["code"]: c["template"] for c in context["components"]}
    if set(codes) - set(components):
        raise ValueError("unsupported underlying product")
    if codes and status != "CONFIRMED":
        raise ValueError("confirm the mentioned underlying products before selection")
    selected = [base, *(components[code] for code in codes)]
    if available_templates is not None and set(selected) - set(available_templates):
        raise ValueError("product context references unavailable canonical templates")
    return selected, context["code"], status == "CONFIRMED"


def validate_selected_templates(primary, selected):
    """Fail closed on arbitrary unions, even outside the web intake path."""
    if not isinstance(selected, list) or not selected or selected[0] != primary:
        raise ValueError("selected templates must start with the confirmed base template")
    if len(selected) != len(set(selected)) or any(not isinstance(v, str) for v in selected):
        raise ValueError("selected templates must be unique strings")
    if len(selected) == 1:
        return selected
    context = next((c for c in product_contexts() if c["base_template"] == primary), None)
    allowed = {c["template"] for c in context["components"]} if context else set()
    if not context or set(selected[1:]) - allowed:
        raise ValueError("unsupported product/template composition")
    return selected
