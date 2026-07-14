from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final, Literal

from .config import ConfigError, load_config
from .git_changes import GitCommandError, Scope, changed_files, find_repository_root
from .impact import filter_changed_paths, impact_report, validate_change_impact
from .models import Finding
from .validators import governed_markdown_paths, validate_repository

Command = Literal["validate", "impact", "files"]
OutputFormat = Literal["text", "json"]

SEVERITY_ORDER: Final = {"error": 0, "warning": 1, "info": 2}


class CliOptions(argparse.Namespace):
    command: Command = "validate"
    root: str = "."
    config: str = "governance/document-policy.json"
    scope: Scope = "all"
    base_ref: str | None = None
    output_format: OutputFormat = "text"


def _print_findings(findings: Sequence[Finding], output_format: OutputFormat) -> int:
    ordered = sorted(
        findings,
        key=lambda finding: (
            SEVERITY_ORDER.get(finding.severity, 9),
            finding.path,
            finding.code,
        ),
    )
    if output_format == "json":
        print(
            json.dumps(
                {"findings": [finding._asdict() for finding in ordered]},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        for finding in ordered:
            level = finding.severity.upper()
            print(f"[{level}] {finding.code} | {finding.path} | {finding.message}")
        errors = sum(finding.severity == "error" for finding in ordered)
        warnings = sum(finding.severity == "warning" for finding in ordered)
        print(f"\nDocument governance: {errors} error(s), {warnings} warning(s).")
    return 1 if any(finding.severity == "error" for finding in ordered) else 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate project document governance rules."
    )
    _ = parser.add_argument(
        "command",
        choices=("validate", "impact", "files"),
        nargs="?",
        default="validate",
    )
    _ = parser.add_argument("--root", default=".")
    _ = parser.add_argument("--config", default="governance/document-policy.json")
    _ = parser.add_argument(
        "--scope", choices=("all", "staged", "working", "diff"), default="all"
    )
    _ = parser.add_argument("--base-ref")
    _ = parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        dest="output_format",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    options = CliOptions()
    _ = _parser().parse_args(arguments, namespace=options)
    root = find_repository_root(Path(options.root))
    config_path = Path(options.config)
    if not config_path.is_absolute():
        config_path = root / config_path
    try:
        config = load_config(config_path)
    except (ConfigError, OSError, json.JSONDecodeError) as error:
        print(f"[error] CONFIG | {error}", file=sys.stderr)
        return 2

    if options.command == "files":
        paths = governed_markdown_paths(root, config)
        output = "\0".join(str(path.relative_to(root)) for path in paths)
        if output:
            _ = sys.stdout.write(output + "\0")
        return 0

    try:
        changed = changed_files(root, options.scope, options.base_ref)
    except GitCommandError as error:
        print(f"[error] GIT | {error}", file=sys.stderr)
        return 2
    changed = filter_changed_paths(changed, config)
    if options.command == "impact":
        print(impact_report(changed, config))
        return 0

    findings = validate_repository(root, config)
    findings.extend(validate_change_impact(changed, config))
    return _print_findings(findings, options.output_format)
