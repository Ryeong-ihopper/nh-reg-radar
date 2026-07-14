from __future__ import annotations

from typing import Literal, NamedTuple

Severity = Literal["error", "warning", "info"]


class Finding(NamedTuple):
    severity: Severity
    code: str
    path: str
    message: str


class AdrPolicy(NamedTuple):
    directory: str
    index_path: str
    required_section_groups: tuple[tuple[str, ...], ...]


class TraceabilityRule(NamedTuple):
    source: str
    target: str
    declaration_pattern: str
    reference_pattern: str


class ChangeRule(NamedTuple):
    name: str
    match: tuple[str, ...]
    require_all_changed: tuple[str, ...]
    require_any_changed: tuple[str, ...]
    severity: Severity
    message: str


class GovernanceConfig(NamedTuple):
    required_documents: tuple[str, ...]
    metadata_patterns: tuple[str, ...]
    metadata_exclude: tuple[str, ...]
    active_markdown_patterns: tuple[str, ...]
    document_filename_pattern: str
    change_path_exclude: tuple[str, ...]
    adr: AdrPolicy
    traceability_rules: tuple[TraceabilityRule, ...]
    change_rules: tuple[ChangeRule, ...]
    implementation_patterns: tuple[str, ...]
    test_patterns: tuple[str, ...]

    def with_required_documents(self, required_documents: tuple[str, ...]) -> "GovernanceConfig":
        return self._replace(required_documents=required_documents)
