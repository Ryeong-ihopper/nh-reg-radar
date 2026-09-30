"""Deterministic first-stage selection for canonical supplemental plans."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable


CONFIRMED = {"provided", "confirmed", "verified"}
ELECTRONIC = {"PUSH", "SMS", "MMS", "LMS", "ALIMTALK", "EMAIL"}
ONLINE = {"WEB", "WEB_PRODUCT_PAGE", "EVENT_PAGE", "MOBILE_WEB", "MOBILE_APP",
          "WEB_BANNER", "MOBILE_BANNER", "POPUP", "SEARCH_AD", "SNS", "SOCIAL_MEDIA"}
BANNER_POPUP = {"WEB_BANNER", "MOBILE_BANNER", "POPUP"}


def _template_identity(value: Any) -> str:
    """Compare template identities independently of catalog status labels."""
    return re.sub(r"\s*\[(?:정식|잠정)\]\s*$", "", str(value or "")).strip()


@dataclass(frozen=True)
class Selection:
    enumerate_ids: tuple[str, ...]
    retrieval_ids: tuple[str, ...]
    human_ids: tuple[str, ...]
    excluded: tuple[dict[str, Any], ...]
    pending: tuple[dict[str, Any], ...]
    confirmed_facts: tuple[dict[str, Any], ...]


def select_supplemental_plans(
    plans: Iterable[dict[str, Any]],
    *,
    product_groups: Iterable[str],
    template_id: str | None,
    routing: dict[str, Any],
    layout_available: bool | None = None,
) -> Selection:
    """Apply confirmed metadata gates before retrieval or judgment.

    RULE-owned facts must be understood here. Semantic or external facts are
    intentionally left for evidence retrieval and the plan-specific model
    request; they never become False merely because retrieval missed.
    """
    groups = {str(value) for value in product_groups}
    enumerated: list[str] = []
    retrieved: list[str] = []
    human: list[str] = []
    excluded: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    confirmed_facts: list[dict[str, Any]] = []
    for plan in plans:
        plan_id = str(plan["plan_id"])
        facts: list[dict[str, Any]] = []
        hard_false = False
        hard_unknown = False
        semantic = False
        for fact in plan["applicability_inputs"]:
            if fact["fact_id"].startswith("E"):
                semantic = True
                continue
            owner = str(fact["owner"])
            if owner == "RULE":
                # Evidence-dependent deterministic adapters (for example the
                # D-163 arithmetic checker) run after retrieval against the
                # advertisement text.  They are not intake metadata facts.
                if fact.get("type") == "DETERMINISTIC_ADAPTER":
                    semantic = True
                    continue
                observed = confirmed_metadata_facts(
                    plan, product_groups=groups, template_id=template_id,
                    routing=routing, layout_available=layout_available,
                )
                selected = next(row for row in observed if row["fact_id"] == fact["fact_id"])
                value = selected["value"]
                facts.append(selected)
                hard_false = hard_false or value is False
                hard_unknown = hard_unknown or value is None
            else:
                semantic = True
        confirmed_facts.append({"item_id": plan_id, "facts": facts})
        if hard_false:
            excluded.append({"item_id": plan_id, "reason": "CONFIRMED_METADATA_FALSE", "facts": facts})
            continue
        if hard_unknown:
            pending.append({"item_id": plan_id, "reason": "CONFIRMED_METADATA_REQUIRED", "facts": facts})
            continue
        if plan["prompt_family"] == "HUMAN_VISUAL":
            human.append(plan_id)
        elif semantic:
            retrieved.append(plan_id)
        else:
            enumerated.append(plan_id)
    return Selection(tuple(enumerated), tuple(retrieved), tuple(human),
                     tuple(excluded), tuple(pending), tuple(confirmed_facts))


def _confirmed_value(raw: Any) -> str | None:
    if not isinstance(raw, dict) or str(raw.get("status") or "").lower() not in CONFIRMED:
        return None
    value = str(raw.get("value") or "").strip().upper()
    return value or None


def confirmed_metadata_facts(
    plan: dict[str, Any], *, product_groups: Iterable[str], template_id: str | None,
    routing: dict[str, Any], layout_available: bool | None = None,
) -> list[dict[str, Any]]:
    """Evaluate every RULE-owned fact from confirmed runtime inputs only."""
    groups = {str(value) for value in product_groups}
    media = _confirmed_value(routing.get("media_type"))
    expected_template = str((plan.get("source") or {}).get("product_template") or "")
    output = []
    for fact in plan.get("applicability_inputs") or []:
        if (fact.get("owner") != "RULE"
                or fact.get("type") == "DETERMINISTIC_ADAPTER"):
            continue
        if fact.get("metadata_key") == "media_type":
            output.append({"fact_id": fact["fact_id"], "value": media == fact["equals"] if media else None,
                           "basis": "media_type"})
            continue
        if fact.get("metadata_key") == "product_context":
            context = _confirmed_value(routing.get("product_context"))
            output.append({"fact_id": fact["fact_id"], "value": context == fact["equals"] if context else None,
                           "basis": "product_context"})
            continue
        if fact["name"] == "selected_template":
            from .policy import confirmed_templates
            selected = confirmed_templates(routing)
            # Older callers pass an already confirmed template separately.
            selected = selected or ([template_id] if template_id else [])
            output.append({"fact_id": fact["fact_id"],
                           "value": _template_identity(expected_template) in {_template_identity(v) for v in selected} if selected else None,
                           "basis": "selected_templates" if len(selected) > 1 else "template_id"})
            continue
        value, basis = _metadata_fact(
            str(fact["name"]), groups=groups, template_id=template_id, media=media,
            routing=routing, layout_available=layout_available,
            expected_template=expected_template,
        )
        output.append({"fact_id": fact["fact_id"], "value": value, "basis": basis})
    return output


def _metadata_fact(
    name: str,
    *,
    groups: set[str],
    template_id: str | None,
    media: str | None,
    routing: dict[str, Any],
    layout_available: bool | None,
    expected_template: str,
) -> tuple[bool | None, str]:
    compact = "".join(name.split())
    template = _template_identity(template_id)
    if compact == "selected_template":
        return (
            template == _template_identity(expected_template)
            if template and expected_template else None
        ), "template_id"
    if compact in {"투자광고인가", "투자상품광고인가"}:
        return "투자성" in groups, "product_group"
    if compact == "신탁광고인가":
        return ("신탁" in template if template else None), "template_id"
    if compact == "IRP광고인가":
        return ("IRP" in template.upper() if template else None), "template_id"
    if compact == "온라인광고인가":
        return (media in ONLINE if media else None), "media_type"
    if compact in {"광고성전자적전송인가", "전달매체가규정의적용매체인가",
                   "전달매체가원문적용매체인가",
                   "전달매체가전송자표시기준적용매체인가"}:
        return (media in ELECTRONIC if media else None), "media_type"
    if compact == "전달매체가LMS또는MMS인가":
        return (media in {"LMS", "MMS"} if media else None), "media_type"
    if compact == "매체형식이배너또는팝업인가":
        return (media in BANNER_POPUP if media else None), "media_type"
    if compact == "해당문구의배경색비교영역을확인할수있는가":
        return layout_available, "parser_original_layout_input"
    raise ValueError(f"unsupported RULE-owned applicability fact: {name}")


def activate_retrieved(
    retrieved_rows: Iterable[dict[str, Any]], allowed_ids: Iterable[str]
) -> list[dict[str, Any]]:
    allowed = set(allowed_ids)
    output = []
    for row in retrieved_rows:
        if row.get("item_id") not in allowed:
            continue
        output.append({
            **row,
            "discovery_method": "canonical_plan_retrieval_then_applicability",
            "execution_tier": "PRODUCT_CONTENT_CONDITIONED_V2",
        })
    return output


def visual_exemption_confirmed(rule, routing):
    program = (rule.get('canonical_execution_plan') or {}).get('review_program') or {}
    exemption = program.get('visual_exemption') or {}
    key = exemption.get('metadata_key')
    return bool(key and _confirmed_value(routing.get(key)) == exemption.get('equals'))
