from __future__ import annotations

import fnmatch
import unicodedata
from collections.abc import Iterable, Sequence
from pathlib import PurePath

from .models import Finding, GovernanceConfig


def path_matches(path: str, pattern: str) -> bool:
    normalized_path = unicodedata.normalize("NFC", path.replace("\\", "/"))
    normalized_pattern = unicodedata.normalize("NFC", pattern.replace("\\", "/"))
    return fnmatch.fnmatch(normalized_path, normalized_pattern) or PurePath(
        normalized_path
    ).match(normalized_pattern)


def _matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(path_matches(path, pattern) for pattern in patterns)


def _matching_paths(paths: Sequence[str], patterns: Iterable[str]) -> list[str]:
    return sorted({path for path in paths if _matches_any(path, patterns)})


def _required_pattern_changed(changed: Sequence[str], pattern: str) -> bool:
    return any(path_matches(path, pattern) for path in changed)


def filter_changed_paths(changed: Sequence[str], config: GovernanceConfig) -> list[str]:
    return sorted(
        path for path in changed if not _matches_any(path, config.change_path_exclude)
    )


def validate_change_impact(
    changed: Sequence[str], config: GovernanceConfig
) -> list[Finding]:
    findings: list[Finding] = []
    if not changed:
        return findings

    for rule in config.change_rules:
        triggers = _matching_paths(changed, rule.match)
        if not triggers:
            continue
        missing_all = [
            pattern
            for pattern in rule.require_all_changed
            if not _required_pattern_changed(changed, pattern)
        ]
        missing_any = bool(rule.require_any_changed) and not any(
            _required_pattern_changed(changed, pattern)
            for pattern in rule.require_any_changed
        )
        if not missing_all and not missing_any:
            continue
        requirements: list[str] = []
        if missing_all:
            requirements.append("필수: " + ", ".join(missing_all))
        if missing_any:
            requirements.append("다음 중 하나: " + ", ".join(rule.require_any_changed))
        findings.append(
            Finding(
                rule.severity,
                "CHANGE_IMPACT",
                ", ".join(triggers[:5]),
                f"{rule.message} ({'; '.join(requirements)})",
            )
        )

    implementation = _matching_paths(changed, config.implementation_patterns)
    tests_changed = any(_matches_any(path, config.test_patterns) for path in changed)
    if implementation and not tests_changed:
        findings.append(
            Finding(
                "error",
                "TEST_IMPACT",
                ", ".join(implementation[:5]),
                "구현 코드 변경에는 자동 테스트 갱신이 필요합니다.",
            )
        )
    return findings


def impact_report(changed: Sequence[str], config: GovernanceConfig) -> str:
    lines = ["변경 영향 분석", "- 변경 파일:"]
    lines.extend(f"  - {path}" for path in changed)
    matched = False
    for rule in config.change_rules:
        if not _matching_paths(changed, rule.match):
            continue
        matched = True
        lines.append(f"- {rule.name} [{rule.severity}]")
        lines.extend(f"  - 반드시 갱신: {path}" for path in rule.require_all_changed)
        if rule.require_any_changed:
            lines.append("  - 다음 중 하나 이상 갱신:")
            lines.extend(f"    - {path}" for path in rule.require_any_changed)
        lines.append(f"  - 이유: {rule.message}")
    if not matched:
        lines.append(
            "- 자동 매핑된 계약 영향이 없습니다. 문서와 테스트 영향을 수동 검토하세요."
        )
    return "\n".join(lines)
