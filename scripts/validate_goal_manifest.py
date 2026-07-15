from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import NamedTuple, Protocol


JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
Manifest = dict[str, JsonValue]


class JsonLoader(Protocol):
    def __call__(self, s: str) -> JsonValue: ...


class ManifestFinding(NamedTuple):
    code: str
    path: str
    message: str


TRACE_SOURCES = {
    "requirements": (
        "docs/requirements-definition.md",
        re.compile(r"^##\s+((?:BR|UR|FR|DR|NFR|AC)-\d{3})\b", re.MULTILINE),
    ),
    "functions": (
        "docs/functional-specification.md",
        re.compile(r"\b(F-\d{3})\b"),
    ),
    "screens": (
        "docs/screen-specification.md",
        re.compile(r"\b(S-\d{3})\b"),
    ),
}
TEST_CASE_SOURCE = "docs/test-cases.md"
TEST_CASE_PATTERN = re.compile(r"^\|\s*(TC-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d{3})\s*\|", re.MULTILINE)
API_SOURCE = "docs/api-specification.md"
API_OPERATION_PATTERN = re.compile(
    r"^\|\s*Method\s*\|\s*(GET|POST|PUT|PATCH|DELETE)\s*\|.*?^\|\s*URI\s*\|\s*`([^`]+)`\s*\|",
    re.MULTILINE | re.DOTALL,
)
DB_SOURCE = "docs/database-specification.md"
DB_OBJECT_PATTERN = re.compile(r"^##\s+\d+\.\d+\s+([a-z][a-z0-9_]*)\s*$", re.MULTILINE)
API_CHANGE_PATTERNS = (
    "openapi/**",
    "apps/backend/api/**",
    "apps/backend/**/api/**",
    "apps/backend/routes/**",
    "apps/backend/**/routes/**",
)
API_SYNC_DOCUMENTS = {API_SOURCE, TEST_CASE_SOURCE}
REQUIRED_TOP_LEVEL = {
    "schema_version",
    "goal_id",
    "capability",
    "trace",
    "test_cases",
    "changed_paths",
    "synchronized_documents",
}
REQUIRED_TRACE_FIELDS = {
    "requirements",
    "functions",
    "screens",
    "api_operations",
    "db_objects",
}
G009_RELEASE_GOAL_ID = "G009-m8-release"
G009_EXPECTED_PROVIDER_FREE = {"passed": 4, "failed": 0, "skipped": 0}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _decode_json(source: str, loader: JsonLoader = json.loads) -> JsonValue:
    return loader(source)


def _load_json(path: Path) -> tuple[Manifest | None, list[ManifestFinding]]:
    try:
        value = _decode_json(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return None, [ManifestFinding("MANIFEST_READ", str(path), str(error))]
    if not isinstance(value, dict):
        return None, [
            ManifestFinding("MANIFEST_TYPE", str(path), "manifest root must be an object")
        ]
    return value, []


def _strings(
    value: JsonValue, field: str, manifest_path: str
) -> tuple[list[str], list[ManifestFinding]]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return [], [
            ManifestFinding("MANIFEST_TYPE", manifest_path, f"{field} must be an array of strings")
        ]
    return [item for item in value if isinstance(item, str)], []


def _duplicates(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _declared_ids(root: Path, relative: str, pattern: re.Pattern[str]) -> set[str]:
    path = root / relative
    if not path.is_file():
        return set()
    return {match.group(1) for match in pattern.finditer(path.read_text(encoding="utf-8"))}


def _validate_string_list(
    manifest_path: str,
    field: str,
    value: JsonValue,
    declarations: set[str] | None = None,
) -> tuple[list[str], list[ManifestFinding]]:
    values, findings = _strings(value, field, manifest_path)
    for duplicate in sorted(_duplicates(values)):
        findings.append(
            ManifestFinding(
                "TRACE_DUPLICATE",
                manifest_path,
                f"{field} contains duplicate: {duplicate}",
            )
        )
    if declarations is not None:
        for unknown in sorted(set(values) - declarations):
            findings.append(
                ManifestFinding(
                    "TRACE_UNKNOWN_ID",
                    manifest_path,
                    f"{field} is not declared in its source document: {unknown}",
                )
            )
    return values, findings


def _api_operations(root: Path) -> set[str]:
    path = root / API_SOURCE
    if not path.is_file():
        return set()
    return {
        f"{match.group(1)} {match.group(2)}"
        for match in API_OPERATION_PATTERN.finditer(path.read_text(encoding="utf-8"))
    }


def _db_objects(root: Path) -> set[str]:
    path = root / DB_SOURCE
    if not path.is_file():
        return set()
    return {
        match.group(1) for match in DB_OBJECT_PATTERN.finditer(path.read_text(encoding="utf-8"))
    }


def _test_node_finding(root: Path, manifest_path: str, node: str) -> ManifestFinding | None:
    if "::" not in node:
        return ManifestFinding(
            "TEST_NODE_INVALID", manifest_path, f"test node must contain '::': {node}"
        )
    relative, symbol = node.split("::", 1)
    test_path = root / relative
    if not test_path.is_file():
        return ManifestFinding(
            "TEST_NODE_MISSING",
            manifest_path,
            f"test node file does not exist: {relative}",
        )
    leaf_symbol = symbol.rsplit("::", 1)[-1]
    if not leaf_symbol or leaf_symbol not in test_path.read_text(encoding="utf-8"):
        return ManifestFinding(
            "TEST_NODE_MISSING",
            manifest_path,
            f"test node symbol was not found: {node}",
        )
    return None


def _validate_test_cases(root: Path, manifest_path: str, value: JsonValue) -> list[ManifestFinding]:
    if not isinstance(value, list):
        return [ManifestFinding("MANIFEST_TYPE", manifest_path, "test_cases must be an array")]
    if not value:
        return [
            ManifestFinding(
                "TEST_CASE_MISSING",
                manifest_path,
                "test_cases must contain at least one docs/test-cases.md ID",
            )
        ]
    declared = _declared_ids(root, TEST_CASE_SOURCE, TEST_CASE_PATTERN)
    findings: list[ManifestFinding] = []
    identifiers: list[str] = []
    for index, entry in enumerate(value):
        field = f"test_cases[{index}]"
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            findings.append(
                ManifestFinding("MANIFEST_TYPE", manifest_path, f"{field}.id must be a string")
            )
            continue
        identifier_value = entry["id"]
        if not isinstance(identifier_value, str):
            continue
        identifier = identifier_value
        identifiers.append(identifier)
        if identifier not in declared:
            findings.append(
                ManifestFinding(
                    "TRACE_UNKNOWN_ID",
                    manifest_path,
                    f"{field}.id is not declared in {TEST_CASE_SOURCE}: {identifier}",
                )
            )
        nodes_value = entry.get("nodes", [])
        if not isinstance(nodes_value, list) or any(
            not isinstance(node, str) for node in nodes_value
        ):
            findings.append(
                ManifestFinding(
                    "MANIFEST_TYPE",
                    manifest_path,
                    f"{field}.nodes must be an array of strings",
                )
            )
            nodes: list[str] = []
        else:
            nodes = [node for node in nodes_value if isinstance(node, str)]
        manual = entry.get("manual")
        external = entry.get("external")
        if (
            not nodes
            and not (isinstance(manual, str) and manual.strip())
            and not (isinstance(external, str) and external.strip())
        ):
            findings.append(
                ManifestFinding(
                    "TEST_CASE_UNMAPPED",
                    manifest_path,
                    f"{identifier} needs an executable node or explicit manual/external mapping",
                )
            )
        for node in nodes:
            node_finding = _test_node_finding(root, manifest_path, node)
            if node_finding is not None:
                findings.append(node_finding)
    for duplicate in sorted(_duplicates(identifiers)):
        findings.append(
            ManifestFinding(
                "TRACE_DUPLICATE",
                manifest_path,
                f"test_cases contains duplicate: {duplicate}",
            )
        )
    return findings


def _validate_current_file_sha(
    root: Path,
    manifest_path: str,
    field: str,
    value: JsonValue,
) -> list[ManifestFinding]:
    if not isinstance(value, dict):
        return [ManifestFinding("MANIFEST_TYPE", manifest_path, f"{field} must be an object")]
    path_value = value.get("path")
    sha256_value = value.get("sha256")
    if not isinstance(path_value, str) or not path_value.strip():
        return [
            ManifestFinding(
                "MANIFEST_TYPE", manifest_path, f"{field}.path must be a non-empty string"
            )
        ]
    if not isinstance(sha256_value, str) or not SHA256_PATTERN.fullmatch(sha256_value):
        return [
            ManifestFinding(
                "MANIFEST_TYPE",
                manifest_path,
                f"{field}.sha256 must be a lowercase SHA-256",
            )
        ]

    root = root.resolve()
    current_file = (root / path_value).resolve()
    if not current_file.is_relative_to(root):
        return [
            ManifestFinding(
                "EVIDENCE_PATH_INVALID",
                manifest_path,
                f"{field}.path escapes the repository: {path_value}",
            )
        ]
    if not current_file.is_file():
        return [
            ManifestFinding(
                "EVIDENCE_FILE_MISSING",
                manifest_path,
                f"{field}.path is not a current repository file: {path_value}",
            )
        ]
    current_sha256 = hashlib.sha256(current_file.read_bytes()).hexdigest()
    if current_sha256 != sha256_value:
        return [
            ManifestFinding(
                "EVIDENCE_SHA_MISMATCH",
                manifest_path,
                f"{field}.sha256 does not match current file: {path_value}",
            )
        ]
    return []


def _validate_g009_release_evidence(
    root: Path, manifest_path: str, manifest: Manifest
) -> list[ManifestFinding]:
    if manifest.get("goal_id") != G009_RELEASE_GOAL_ID:
        return []

    findings: list[ManifestFinding] = []
    for field in ("openapi", "generated_client", "migration"):
        findings.extend(_validate_current_file_sha(root, manifest_path, field, manifest.get(field)))

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        findings.append(
            ManifestFinding("MANIFEST_TYPE", manifest_path, "artifacts must be a non-empty array")
        )
    else:
        for index, artifact in enumerate(artifacts):
            findings.extend(
                _validate_current_file_sha(
                    root,
                    manifest_path,
                    f"artifacts[{index}]",
                    artifact,
                )
            )

    automation = manifest.get("automation")
    provider_free = automation.get("provider_free") if isinstance(automation, dict) else None
    expected = provider_free.get("expected") if isinstance(provider_free, dict) else None
    if expected != G009_EXPECTED_PROVIDER_FREE:
        findings.append(
            ManifestFinding(
                "PROVIDER_FREE_EXPECTED_MISMATCH",
                manifest_path,
                f"automation.provider_free.expected must be exactly {G009_EXPECTED_PROVIDER_FREE}",
            )
        )
    return findings


def validate_manifest(root: Path, manifest_path: Path) -> list[ManifestFinding]:
    manifest, findings = _load_json(manifest_path)
    display_path = (
        str(manifest_path.relative_to(root))
        if manifest_path.is_relative_to(root)
        else str(manifest_path)
    )
    if manifest is None:
        return findings

    missing_fields = REQUIRED_TOP_LEVEL - manifest.keys()
    for field in sorted(missing_fields):
        findings.append(
            ManifestFinding("MANIFEST_FIELD_MISSING", display_path, f"missing field: {field}")
        )
    if manifest.get("schema_version") != 1:
        findings.append(
            ManifestFinding("MANIFEST_VERSION", display_path, "schema_version must be 1")
        )
    for field in ("goal_id", "capability"):
        value = manifest.get(field)
        if not isinstance(value, str) or not value.strip():
            findings.append(
                ManifestFinding(
                    "MANIFEST_TYPE", display_path, f"{field} must be a non-empty string"
                )
            )

    trace = manifest.get("trace")
    if not isinstance(trace, dict):
        findings.append(ManifestFinding("MANIFEST_TYPE", display_path, "trace must be an object"))
    else:
        for field in sorted(REQUIRED_TRACE_FIELDS - trace.keys()):
            findings.append(
                ManifestFinding(
                    "MANIFEST_FIELD_MISSING",
                    display_path,
                    f"missing trace field: {field}",
                )
            )
        for field, (source, pattern) in TRACE_SOURCES.items():
            _, field_findings = _validate_string_list(
                display_path,
                f"trace.{field}",
                trace.get(field),
                _declared_ids(root, source, pattern),
            )
            findings.extend(field_findings)
        _, api_findings = _validate_string_list(
            display_path,
            "trace.api_operations",
            trace.get("api_operations"),
            _api_operations(root),
        )
        findings.extend(api_findings)
        db_values, db_findings = _validate_string_list(
            display_path, "trace.db_objects", trace.get("db_objects")
        )
        findings.extend(db_findings)
        declared_db_objects = _db_objects(root)
        for db_object in db_values:
            table_name = db_object.rsplit(".", 1)[-1]
            if table_name not in declared_db_objects:
                findings.append(
                    ManifestFinding(
                        "TRACE_UNKNOWN_ID",
                        display_path,
                        f"trace.db_objects is not declared in {DB_SOURCE}: {db_object}",
                    )
                )

    findings.extend(_validate_test_cases(root, display_path, manifest.get("test_cases")))
    changed_paths, changed_findings = _validate_string_list(
        display_path, "changed_paths", manifest.get("changed_paths")
    )
    findings.extend(changed_findings)
    synchronized, synchronized_findings = _validate_string_list(
        display_path, "synchronized_documents", manifest.get("synchronized_documents")
    )
    findings.extend(synchronized_findings)
    api_changed = any(
        fnmatch.fnmatch(path, pattern) for path in changed_paths for pattern in API_CHANGE_PATTERNS
    )
    if api_changed:
        for missing in sorted(API_SYNC_DOCUMENTS - set(synchronized)):
            findings.append(
                ManifestFinding(
                    "API_DOC_SYNC_MISSING",
                    display_path,
                    f"API contract changes require synchronized document: {missing}",
                )
            )
    findings.extend(_validate_g009_release_evidence(root, display_path, manifest))
    return findings


class CliOptions(argparse.Namespace):
    manifests: list[str] = []
    root: str = "."


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate capability goal trace manifests.")
    _ = parser.add_argument(
        "manifests",
        nargs="*",
        help="manifest paths (default: governance/goal-manifests/*.json)",
    )
    _ = parser.add_argument("--root", default=".", help="repository root")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    options = CliOptions()
    _ = _parser().parse_args(arguments, namespace=options)
    root = Path(options.root).resolve()
    manifest_paths = [root / path for path in options.manifests]
    if not manifest_paths:
        manifest_paths = sorted((root / "governance" / "goal-manifests").glob("*.json"))
    if not manifest_paths:
        print("[ERROR] MANIFEST_MISSING | governance/goal-manifests | no manifests found")
        return 1
    findings = [
        finding
        for manifest_path in manifest_paths
        for finding in validate_manifest(root, manifest_path)
    ]
    for finding in sorted(findings):
        print(f"[ERROR] {finding.code} | {finding.path} | {finding.message}")
    print(f"\nGoal manifest validation: {len(findings)} error(s).")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
