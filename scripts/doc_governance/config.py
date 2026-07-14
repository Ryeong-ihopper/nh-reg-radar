from __future__ import annotations

import json
from pathlib import Path
from typing import Final, Protocol, Union

from .models import AdrPolicy, ChangeRule, GovernanceConfig, Severity, TraceabilityRule

JsonScalar = Union[str, int, float, bool, None]
JsonValue = Union[JsonScalar, list["JsonValue"], dict[str, "JsonValue"]]
SEVERITY_VALUES: Final[dict[str, Severity]] = {
    "error": "error",
    "warning": "warning",
    "info": "info",
}


class JsonLoader(Protocol):
    def __call__(self, s: str) -> JsonValue: ...


def _decode_json(source: str, loader: JsonLoader = json.loads) -> JsonValue:
    return loader(source)


class ConfigError(RuntimeError):
    pass


def _mapping(value: JsonValue, field: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ConfigError(f"{field} must be an object")
    return value


def _list(value: JsonValue, field: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise ConfigError(f"{field} must be an array")
    return value


def _string(value: JsonValue, field: str) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"{field} must be a string")
    return value


def _strings(value: JsonValue, field: str) -> tuple[str, ...]:
    values = _list(value, field)
    return tuple(_string(item, field) for item in values)


def _severity(value: JsonValue, field: str) -> Severity:
    severity = _string(value, field)
    parsed = SEVERITY_VALUES.get(severity)
    if parsed is None:
        raise ConfigError(f"{field} must be error, warning, or info")
    return parsed


def _change_rule(value: JsonValue, index: int) -> ChangeRule:
    field = f"change_rules[{index}]"
    rule = _mapping(value, field)
    return ChangeRule(
        name=_string(rule.get("name"), f"{field}.name"),
        match=_strings(rule.get("match"), f"{field}.match"),
        require_all_changed=_strings(
            rule.get("require_all_changed", []),
            f"{field}.require_all_changed",
        ),
        require_any_changed=_strings(
            rule.get("require_any_changed", []),
            f"{field}.require_any_changed",
        ),
        severity=_severity(rule.get("severity", "error"), f"{field}.severity"),
        message=_string(rule.get("message"), f"{field}.message"),
    )


def _traceability_rule(value: JsonValue, index: int) -> TraceabilityRule:
    field = f"traceability_rules[{index}]"
    rule = _mapping(value, field)
    return TraceabilityRule(
        source=_string(rule.get("source"), f"{field}.source"),
        target=_string(rule.get("target"), f"{field}.target"),
        declaration_pattern=_string(
            rule.get("declaration_pattern"), f"{field}.declaration_pattern"
        ),
        reference_pattern=_string(
            rule.get("reference_pattern"), f"{field}.reference_pattern"
        ),
    )


def load_config(path: Path) -> GovernanceConfig:
    raw = _decode_json(path.read_text(encoding="utf-8"))
    policy = _mapping(raw, "policy")
    adr_raw = _mapping(policy.get("adr"), "adr")
    section_values = _list(
        adr_raw.get("required_section_groups"), "adr.required_section_groups"
    )
    section_groups = tuple(
        _strings(value, "adr.required_section_groups[]") for value in section_values
    )
    trace_values = _list(policy.get("traceability_rules", []), "traceability_rules")
    change_values = _list(policy.get("change_rules", []), "change_rules")

    return GovernanceConfig(
        required_documents=_strings(
            policy.get("required_documents"), "required_documents"
        ),
        metadata_patterns=_strings(
            policy.get("metadata_patterns"), "metadata_patterns"
        ),
        metadata_exclude=_strings(
            policy.get("metadata_exclude", []), "metadata_exclude"
        ),
        active_markdown_patterns=_strings(
            policy.get("active_markdown_patterns"),
            "active_markdown_patterns",
        ),
        document_filename_pattern=_string(
            policy.get("document_filename_pattern"),
            "document_filename_pattern",
        ),
        change_path_exclude=_strings(
            policy.get("change_path_exclude", []),
            "change_path_exclude",
        ),
        adr=AdrPolicy(
            directory=_string(adr_raw.get("directory"), "adr.directory"),
            index_path=_string(adr_raw.get("index"), "adr.index"),
            required_section_groups=section_groups,
        ),
        traceability_rules=tuple(
            _traceability_rule(value, index) for index, value in enumerate(trace_values)
        ),
        change_rules=tuple(
            _change_rule(value, index) for index, value in enumerate(change_values)
        ),
        implementation_patterns=_strings(
            policy.get("implementation_patterns", []), "implementation_patterns"
        ),
        test_patterns=_strings(policy.get("test_patterns", []), "test_patterns"),
    )
