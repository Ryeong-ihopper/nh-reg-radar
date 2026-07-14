from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from .impact import path_matches
from .models import Finding, GovernanceConfig

ADR_FILE_PATTERN = re.compile(r"^(ADR-\d{4})-.+\.md$")
HEADING_PATTERN = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
VERSION_PATTERN = re.compile(r"^\|\s*현행 버전\s*\|\s*(v[^|\s]+)\s*\|", re.MULTILINE)
DATE_PATTERN = re.compile(r"^\|\s*기준일\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|", re.MULTILINE)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _headings(text: str) -> set[str]:
    return {match.group(1).strip() for match in HEADING_PATTERN.finditer(text)}


def _metadata_paths(root: Path, config: GovernanceConfig) -> list[Path]:
    paths: set[Path] = set()
    for pattern in config.metadata_patterns:
        paths.update(path for path in root.glob(pattern) if path.is_file())
    return sorted(
        path
        for path in paths
        if not any(
            path_matches(str(path.relative_to(root)), pattern)
            for pattern in config.metadata_exclude
        )
    )


def governed_markdown_paths(root: Path, config: GovernanceConfig) -> list[Path]:
    paths = {
        root / relative
        for relative in config.required_documents
        if relative.endswith(".md") and (root / relative).is_file()
    }
    for pattern in config.active_markdown_patterns:
        paths.update(path for path in root.glob(pattern) if path.is_file())
    return sorted(paths)


def _validate_required_documents(root: Path, config: GovernanceConfig) -> list[Finding]:
    return [
        Finding("error", "DOC_MISSING", relative, "필수 문서가 없습니다.")
        for relative in config.required_documents
        if not (root / relative).is_file()
    ]


def _validate_document_filenames(root: Path, config: GovernanceConfig) -> list[Finding]:
    pattern = re.compile(config.document_filename_pattern)
    return [
        Finding(
            "error",
            "DOC_FILENAME",
            str(path.relative_to(root)),
            "활성 Markdown 문서 파일명은 영문 kebab-case여야 합니다.",
        )
        for path in governed_markdown_paths(root, config)
        if pattern.fullmatch(path.name) is None
    ]


def _first_changelog_entry(text: str) -> tuple[str, str] | None:
    heading = re.search(r"^##\s+변경 이력\s*$", text, re.MULTILINE)
    if heading is None:
        return None
    section = text[heading.end() :]
    next_heading = re.search(r"^##\s+", section, re.MULTILINE)
    if next_heading is not None:
        section = section[: next_heading.start()]
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = tuple(cell.strip() for cell in line.strip().strip("|").split("|"))
        if len(cells) < 3 or cells[0] == "버전" or set(cells[0]) <= {"-", ":"}:
            continue
        return cells[0], cells[1]
    return None


def _validate_metadata(root: Path, config: GovernanceConfig) -> list[Finding]:
    findings: list[Finding] = []
    for path in _metadata_paths(root, config):
        relative = str(path.relative_to(root))
        text = _read(path)
        headings = _headings(text)
        version = VERSION_PATTERN.search(text)
        current_date = DATE_PATTERN.search(text)
        if "문서 현행 정보" not in headings or version is None or current_date is None:
            findings.append(
                Finding(
                    "error",
                    "DOC_CURRENT_INFO",
                    relative,
                    "문서 현행 정보에 현행 버전과 기준일이 필요합니다.",
                )
            )
        if "변경 이력" not in headings:
            findings.append(
                Finding(
                    "error",
                    "DOC_CHANGELOG",
                    relative,
                    "변경 이력 섹션이 필요합니다.",
                )
            )
        elif version is not None and current_date is not None:
            first_entry = _first_changelog_entry(text)
            expected_entry = version.group(1), current_date.group(1)
            if first_entry != expected_entry:
                findings.append(
                    Finding(
                        "error",
                        "DOC_CHANGELOG_CURRENT",
                        relative,
                        "현행 버전과 기준일이 변경 이력의 최신 행에 없습니다.",
                    )
                )
    return findings


def _field_value(text: str, field: str) -> str | None:
    heading_pattern = re.compile(
        rf"^##\s+{re.escape(field)}[ \t]*$(?:[ \t]*\n)+([^\n]+)",
        re.MULTILINE,
    )
    heading_match = heading_pattern.search(text)
    if heading_match is not None:
        return heading_match.group(1).strip()
    table_pattern = re.compile(rf"^\|\s*{re.escape(field)}\s*\|\s*([^|]+?)\s*\|", re.MULTILINE)
    table_match = table_pattern.search(text)
    return table_match.group(1).strip() if table_match is not None else None


def _validate_adr_file(
    relative: str, path: Path, adr_id: str, section_groups: Iterable[tuple[str, ...]]
) -> list[Finding]:
    text = _read(path)
    headings = _headings(text)
    findings: list[Finding] = []
    if not text.startswith(f"# {adr_id}:"):
        findings.append(
            Finding(
                "error",
                "ADR_TITLE",
                relative,
                f"제목은 '# {adr_id}: ...' 형식이어야 합니다.",
            )
        )
    status = _field_value(text, "상태")
    if status not in {"Accepted", "Proposed", "Deprecated"} and not (
        status is not None and status.startswith("Superseded")
    ):
        findings.append(Finding("error", "ADR_STATUS", relative, "유효한 ADR 상태가 필요합니다."))
    for alternatives in section_groups:
        if not any(section in headings for section in alternatives):
            findings.append(
                Finding(
                    "error",
                    "ADR_SECTION",
                    relative,
                    "ADR 필수 섹션이 없습니다: " + " 또는 ".join(alternatives),
                )
            )
    if _field_value(text, "관련 문서") is None and "관련 문서" not in headings:
        findings.append(
            Finding("error", "ADR_RELATED_DOCS", relative, "관련 문서 정보가 필요합니다.")
        )
    return findings


def _validate_adrs(root: Path, config: GovernanceConfig) -> list[Finding]:
    findings: list[Finding] = []
    adr_dir = root / config.adr.directory
    index_path = root / config.adr.index_path
    if not adr_dir.is_dir() or not index_path.is_file():
        return findings
    index_text = _read(index_path)
    seen: set[str] = set()
    for path in sorted(adr_dir.glob("ADR-[0-9][0-9][0-9][0-9]-*.md")):
        match = ADR_FILE_PATTERN.match(path.name)
        if match is None:
            continue
        adr_id = match.group(1)
        relative = str(path.relative_to(root))
        if adr_id in seen:
            findings.append(
                Finding("error", "ADR_DUPLICATE", relative, f"ADR ID가 중복됩니다: {adr_id}")
            )
        seen.add(adr_id)
        findings.extend(
            _validate_adr_file(relative, path, adr_id, config.adr.required_section_groups)
        )
        if path.name not in index_text:
            findings.append(
                Finding(
                    "error",
                    "ADR_INDEX_MISSING",
                    relative,
                    "ADR 공식 목록에 파일 링크가 없습니다.",
                )
            )
    return findings


def _validate_traceability(root: Path, config: GovernanceConfig) -> list[Finding]:
    findings: list[Finding] = []
    for rule in config.traceability_rules:
        source = root / rule.source
        target = root / rule.target
        if not source.is_file() or not target.is_file():
            continue
        declarations = {
            match.group(1)
            for match in re.finditer(
                rule.declaration_pattern,
                _read(source),
                re.MULTILINE,
            )
        }
        references = {
            match.group(0) for match in re.finditer(rule.reference_pattern, _read(target))
        }
        for identifier in sorted(references - declarations):
            findings.append(
                Finding(
                    "error",
                    "TRACE_UNKNOWN_ID",
                    rule.target,
                    f"원천 문서에 선언되지 않은 ID를 참조합니다: {identifier}",
                )
            )
    return findings


def validate_repository(root: Path, config: GovernanceConfig) -> list[Finding]:
    findings: list[Finding] = []
    findings.extend(_validate_required_documents(root, config))
    findings.extend(_validate_document_filenames(root, config))
    findings.extend(_validate_metadata(root, config))
    findings.extend(_validate_adrs(root, config))
    findings.extend(_validate_traceability(root, config))
    return findings
