"""Load the reviewed canonical plans into the operational runner.

The adapter keeps source rows and execution IDs stable while replacing the
superseded template inventory.  Supplemental plans reuse the v2 rule body for
legal provenance and add the canonical applicability/obligation contract.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from rag.judgment.family_prompts import project_plan


PLAN_SCHEMA = "canonical-execution-plans-v2"
MIGRATION_SCHEMA = "operational-catalog-migration-v1"
DISPOSITION_SCHEMA = "operational-rule-dispositions-v1"


@dataclass(frozen=True)
class OperationalCatalog:
    plans: dict[str, dict[str, Any]]
    template_rules: list[dict[str, Any]]
    supplemental_rules: dict[str, dict[str, Any]]
    dispositions: dict[str, dict[str, Any]]
    source_sha256: str
    migration_sha256: str
    disposition_sha256: str
    counts: dict[str, int]


def audit_canonical_template_coverage(
    catalog: OperationalCatalog,
    section: str,
    requested_ids: Iterable[str],
    deferred: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    selected = [rule for rule in catalog.template_rules
                if rule.get("product_subtype") == section]
    if not selected:
        raise ValueError("selected template has no canonical execution plans")
    requested = set(requested_ids)
    deferred_ids = {str(row.get("item_id") or "") for row in deferred}
    expected = {str(rule["item_id"]) for rule in selected}
    missing = expected - requested - deferred_ids
    if missing:
        raise ValueError("canonical template plans have no disposition: "
                         + ", ".join(sorted(missing)))
    return {
        "policy": "canonical-selected-template-coverage-v2",
        "template_section": section,
        "plan_count": len(expected),
        "requested_count": len(expected & requested),
        "manual_or_input_review_count": len(expected & deferred_ids),
        "missing_count": 0,
        "items": [{
            "item_id": rule["item_id"],
            "legacy_item_ids": rule.get("legacy_item_ids") or [],
            "title": rule["title"],
            "requested": rule["item_id"] in requested,
            "manual_review_required": rule["item_id"] in deferred_ids,
        } for rule in selected],
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load(path: Path, schema: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != schema:
        raise ValueError(f"{path}: expected {schema}")
    return value


def load_operational_catalog(
    plans_path: Path,
    migration_path: Path,
    disposition_path: Path,
    *,
    legacy_template_rules: Iterable[dict[str, Any]],
    v2_rules: Iterable[dict[str, Any]],
    include_supplements: bool = True,
) -> OperationalCatalog:
    document = _load(plans_path, PLAN_SCHEMA)
    migration = _load(migration_path, MIGRATION_SCHEMA)
    disposition = _load(disposition_path, DISPOSITION_SCHEMA)
    if document.get("scope") != "DEPOSIT_LOAN_INVESTMENT":
        raise ValueError("canonical plans are outside the operational scope")
    if (document.get("policies") or {}).get("operationally_connected") is not True:
        raise ValueError("canonical plans are not released to the operational catalog")
    if disposition.get("canonical_source_binding_sha256") != document.get("source_binding_sha256"):
        raise ValueError("rule dispositions are not bound to the canonical source snapshot")

    plans = _unique(document.get("plans"), "plan_id", "canonical plan")
    migration_rows = _unique(migration.get("rows"), "plan_id", "migration row")
    if set(plans) != set(migration_rows):
        raise ValueError("canonical plans and migration rows have different IDs")
    for plan_id, row in migration_rows.items():
        if row.get("source_sha256") != plans[plan_id].get("source_sha256"):
            raise ValueError(f"migration source hash differs for {plan_id}")

    dispositions = _unique(disposition.get("entries"), "item_id", "disposition")
    _validate_dispositions(disposition, dispositions, plans)
    legacy = _unique(list(legacy_template_rules), "item_id", "legacy template rule")
    v2 = _unique(list(v2_rules), "item_id", "v2 rule")

    template_rules: list[dict[str, Any]] = []
    supplement_rules: dict[str, dict[str, Any]] = {}
    for plan_id, plan in plans.items():
        source_kind = str((plan.get("source") or {}).get("source_kind") or "")
        if source_kind == "TEMPLATE":
            _validate_template_scope_gate(plan_id, plan)
            row = migration_rows[plan_id]
            aliases = list(row.get("legacy_item_ids") or [])
            if row.get("migration_state") == "EXACT_LEGACY_ALIAS":
                if len(aliases) != 1:
                    raise ValueError(f"{plan_id}: exact migration must have one legacy ID")
                # Operational rules may have collapsed several physical
                # ``[방식 N]`` rows into a composite ID after the migration
                # audit. The canonical plan remains sufficient to construct
                # the current rule; a missing physical alias is recorded, not
                # treated as permission to restore a superseded row.
                if aliases[0] in legacy:
                    rule = dict(legacy[aliases[0]])
                    source = plan["source"]
                    template, template_status = _template_identity(source)
                    rule.update({
                        "item_id": plan_id,
                        "legacy_item_ids": aliases,
                        "product_subtype": template,
                        "template_source_status": template_status,
                        "product_groups": _groups(template),
                        "title": source.get("label") or plan_id,
                        "question": source.get("label") or plan_id,
                        "canonical_execution_plan": project_plan(plan),
                        "canonical_source_sha256": plan["source_sha256"],
                        "canonical_prompt_family": plan["prompt_family"],
                        "criterion": _criterion(plan),
                        "example_text": "",
                        "runtime_alias_resolved": True,
                    })
                    _replace_template_basis(rule, plan)
                else:
                    rule = _template_rule(plan)
                    rule["legacy_item_ids"] = aliases
                    rule["runtime_alias_resolved"] = False
                template_rules.append(rule)
            elif row.get("migration_state") == "NEW_OR_REVISED_SOURCE_ROW":
                template_rules.append(_template_rule(plan))
            else:
                raise ValueError(f"{plan_id}: unresolved migration state")
            continue

        if not include_supplements:
            continue
        if plan_id not in dispositions or dispositions[plan_id].get("state") != "ACTIVE_SUPPLEMENT":
            raise ValueError(f"{plan_id}: supplemental plan lacks active disposition")
        if plan_id not in v2:
            raise ValueError(f"{plan_id}: v2 source definition is unavailable")
        rule = dict(v2[plan_id])
        rule["canonical_execution_plan"] = project_plan(plan)
        rule["canonical_source_sha256"] = plan["source_sha256"]
        rule["canonical_prompt_family"] = plan["prompt_family"]
        rule["canonical_activation"] = dispositions[plan_id].get("activation")
        supplement_rules[plan_id] = rule

    for alias_id, row in dispositions.items():
        if not include_supplements:
            break
        if row.get("state") != "ALIAS":
            continue
        target = str(row.get("target_id") or "")
        if target not in supplement_rules or alias_id not in v2:
            raise ValueError(f"{alias_id}: alias source or target is unavailable")
        target_rule = supplement_rules[target]
        supporting = list(target_rule.get("supporting_rules") or [])
        if alias_id not in supporting:
            supporting.append(alias_id)
        target_rule["supporting_rules"] = supporting
        target_rule.setdefault("canonical_aliases", []).append({
            "item_id": alias_id,
            "relation": row.get("relation"),
            "source_title": v2[alias_id].get("title"),
        })

    expected = document.get("counts") or {}
    if len(template_rules) != int(expected.get("template_records") or -1):
        raise ValueError("operational template count differs from canonical count")
    expected_supplements = int(expected.get("supplemental_records") or -1) if include_supplements else 0
    if len(supplement_rules) != expected_supplements:
        raise ValueError("operational supplemental count differs from canonical count")
    return OperationalCatalog(
        plans=plans,
        template_rules=template_rules,
        supplemental_rules=supplement_rules,
        dispositions=dispositions,
        source_sha256=_sha256(plans_path),
        migration_sha256=_sha256(migration_path),
        disposition_sha256=_sha256(disposition_path),
        counts={
            "plans": len(plans),
            "templates": len(template_rules),
            "supplements": len(supplement_rules),
            "new_or_revised": sum(
                row.get("migration_state") in {"NEW_OR_REVISED_SOURCE_ROW", "NEW_SUPPLEMENTAL_PLAN"}
                for row in migration_rows.values()
            ),
        },
    )


def _validate_template_scope_gate(plan_id: str, plan: dict[str, Any]) -> None:
    """Require every template rule to be bound to its selected template.

    ``selected_template`` is a routing scope, not a substantive advertising
    condition.  Source-authored conditional rows may add A2/A3/E1, while an
    unconditional template duty has only this scope gate.  Failing closed here
    prevents a deposit/loan/investment rule from leaking into another selected
    template when catalogs are rebuilt.
    """
    inputs = plan.get("applicability_inputs") or []
    if not inputs:
        raise ValueError(f"{plan_id}: template plan has no selected-template scope")
    first = inputs[0]
    if first != {
        "fact_id": "A1",
        "name": "selected_template",
        "owner": "RULE",
        "type": "CONFIRMED_METADATA",
        "unknown_policy": "UNDETERMINED",
    }:
        raise ValueError(f"{plan_id}: template plan has an invalid selected-template scope")
    logic = plan.get("applicability_logic") or {}
    children = logic.get("all") if isinstance(logic, dict) else None
    if not isinstance(children, list) or {"fact": "A1"} not in children:
        raise ValueError(f"{plan_id}: selected-template scope is absent from applicability logic")


def _unique(rows: Any, key: str, label: str) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list):
        raise ValueError(f"{label}s must be a list")
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = str((row or {}).get(key) or "")
        if not value or value in output:
            raise ValueError(f"missing or duplicate {label} id: {value!r}")
        output[value] = row
    return output


def _validate_dispositions(
    document: dict[str, Any],
    rows: dict[str, dict[str, Any]],
    plans: dict[str, dict[str, Any]],
) -> None:
    active = {plan_id for plan_id, plan in plans.items()
              if (plan.get("source") or {}).get("source_kind") != "TEMPLATE"}
    registered_active = {item_id for item_id, row in rows.items()
                         if row.get("state") == "ACTIVE_SUPPLEMENT"}
    if registered_active != active:
        raise ValueError("active supplemental dispositions differ from canonical plans")
    aliases = {item_id: row.get("target_id") for item_id, row in rows.items()
               if row.get("state") == "ALIAS"}
    if aliases != {"D-190": "C-015", "D-204": "C-099"}:
        raise ValueError("canonical alias registry differs from the reviewed relation")
    held = {item_id for item_id, row in rows.items() if row.get("state") == "HOLD"}
    if held != {"C-048", "C-049", "C-055", "C-138", "D-155", "D-170", "D-187", "D-198"}:
        raise ValueError("canonical hold registry differs from the reviewed set")
    if (document.get("counts") or {}).get("active_supplement") != len(active):
        raise ValueError("disposition count is inconsistent")


TEMPLATE_STATUS_MARKER = re.compile(r"\s*\[(정식|잠정)\]\s*$")


def _template_identity(source: dict[str, Any]) -> tuple[str, str]:
    """Split the template routing key from its review-status marker.

    Compiled plans append ``[정식]``/``[잠정]`` to record how far the source
    template was reviewed. Routing selects a template by its section name, so
    the marker is kept as its own field rather than inside the key; leaving it
    in the key makes every marked section look like it has no plans.
    """
    raw = str(source.get("product_template") or "")
    marker = TEMPLATE_STATUS_MARKER.search(raw)
    return TEMPLATE_STATUS_MARKER.sub("", raw), (marker.group(1) if marker else "")


def _groups(template: str) -> list[str]:
    return [group for group in ("예금성", "대출성", "투자성") if template.startswith(group)]


def _criterion(plan: dict[str, Any]) -> str:
    facts = "\n".join(f"- {row['name']}" for row in plan["applicability_inputs"])
    obligations = "\n".join(f"- {row['text']}" for row in plan["obligations"]
                            if not row["owners"].get("human"))
    return (
        "적용조건을 먼저 각각 TRUE/FALSE/UNKNOWN으로 관찰하고 코드가 논리를 계산한다. "
        "UNKNOWN을 미해당이나 충족으로 바꾸지 않는다.\n"
        f"[적용조건]\n{facts or '- 선택 템플릿'}\n"
        f"[자동 판정 원자 의무]\n{obligations or '- 없음(사람 검토 전용)'}"
    )


def _replace_template_basis(rule: dict[str, Any], plan: dict[str, Any]) -> None:
    basis = dict(rule.get("template_basis") or {})
    source = plan["source"]
    visual = any(atom["owners"].get("human") for atom in plan["obligations"])
    automatic = any(not atom["owners"].get("human") for atom in plan["obligations"])
    legal_basis = source.get("legal_basis") or {}
    legal_refs = list(dict.fromkeys(
        str(value).strip()
        for key in ("statute", "association")
        for value in [legal_basis.get(key)]
        if str(value or "").strip() and str(value or "").strip() != "-"
    ))
    basis.update({
        "item_id": plan["plan_id"],
        "basis_type": "CANONICAL_TEMPLATE_PLAN",
        "source_sha256": plan["source_sha256"],
        "source_ref": f"CANONICAL_PLAN:{plan['plan_id']}",
        "template_section": source.get("product_template"),
        "structure_status": "STRUCTURED",
        "text_review_ready": automatic,
        "text_facet_only": visual and automatic,
        "manual_review_required": visual,
        "canonical_plan": project_plan(plan),
        "legal_basis_refs": legal_refs,
    })
    rule["template_basis"] = basis


def _template_rule(plan: dict[str, Any]) -> dict[str, Any]:
    source = plan["source"]
    fields = source.get("source_fields") or {}
    template, template_status = _template_identity(source)
    if not _groups(template):
        raise ValueError(f"{plan['plan_id']}: unsupported template scope")
    automatic = any(not atom["owners"].get("human") for atom in plan["obligations"])
    rule = {
        "item_id": plan["plan_id"],
        "source_sheet": "HWPX_TEMPLATE",
        "category": "PRESENCE",
        "category_label": "템플릿 점검",
        "product_groups": _groups(template),
        "product_subtype": template,
        "template_source_status": template_status,
        "template_required": "CONDITIONAL" if len(plan["applicability_inputs"]) > 1 else "REQUIRED",
        "title": source.get("label") or plan["plan_id"],
        "question": source.get("label") or plan["plan_id"],
        "criterion": _criterion(plan),
        "guide": "\n".join(str(fields.get(key) or "") for key in ("satisfied", "violated", "review")
                           if str(fields.get(key) or "").strip()),
        "example_text": "",
        "example_policy": "예시는 비구속 검색 힌트이며 광고 증거가 아님",
        "input_requirement": "광고물" if automatic else "원본형식",
        "judgment_type": "LLM" if automatic else "사람검토",
        "required_medium": "텍스트" if automatic else "원본형식",
        "canonical_execution_plan": project_plan(plan),
        "canonical_source_sha256": plan["source_sha256"],
        "canonical_prompt_family": plan["prompt_family"],
    }
    _replace_template_basis(rule, plan)
    return rule
