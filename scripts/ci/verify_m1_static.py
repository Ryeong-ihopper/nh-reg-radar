#!/usr/bin/env python3
"""Deterministic M1 namespace and privileged-credential CI checks."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ENV_LINE = re.compile(r"^(?:export\s+)?([A-Z][A-Z0-9_]*)=(.*)$")
PRIVILEGED_NAME = re.compile(
    r"\b(?=[A-Z0-9_]*(?:BOOTSTRAP|ADMIN))"
    r"(?=[A-Z0-9_]*(?:DATABASE_URL|DSN|PASSWORD|SECRET))[A-Z][A-Z0-9_]+\b"
)
NAMESPACE_GROUPS = {
    "postgres database": re.compile(r"POSTGRES.*(?:_DB|DATABASE_NAME)$"),
    "MinIO bucket": re.compile(r"(?:MINIO.*)?BUCKET"),
    "Qdrant collection": re.compile(r"QDRANT.*COLLECTION"),
    "OpenSearch index": re.compile(r"OPENSEARCH.*INDEX"),
    "Redis prefix": re.compile(r"REDIS.*PREFIX"),
}


class VerificationError(ValueError):
    """Raised when an M1 static contract is violated."""


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = ENV_LINE.fullmatch(line)
        if match is None:
            raise VerificationError(f"{path}:{number}: invalid env assignment")
        key, value = match.groups()
        if key in values:
            raise VerificationError(f"{path}:{number}: duplicate key {key}")
        values[key] = value.strip().strip("'\"")
    return values


def verify_namespaces(dev_path: Path, prod_path: Path) -> None:
    dev = parse_env(dev_path)
    prod = parse_env(prod_path)
    failures: list[str] = []
    shared_keys = set(dev) & set(prod)
    for label, pattern in NAMESPACE_GROUPS.items():
        keys = sorted(key for key in shared_keys if pattern.search(key))
        if not keys:
            failures.append(f"missing shared {label} key")
            continue
        for key in keys:
            if not dev[key] or not prod[key]:
                failures.append(f"{key} must be non-empty in both environments")
            elif dev[key] == prod[key]:
                failures.append(f"{key} is shared by dev and prod")
    if failures:
        raise VerificationError("; ".join(failures))


def workflow_job_blocks(text: str) -> dict[str, str]:
    jobs_match = re.search(r"(?m)^jobs:\s*$", text)
    if jobs_match is None:
        raise VerificationError("workflow has no jobs mapping")
    lines = text[jobs_match.end() :].splitlines(keepends=True)
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        match = re.match(r"^  ([a-zA-Z0-9_-]+):\s*(?:#.*)?$", line)
        if match:
            current = match.group(1)
            blocks[current] = [line]
        elif current is not None:
            if line and not line.startswith((" ", "\t", "\n", "\r")):
                break
            blocks[current].append(line)
    return {name: "".join(block) for name, block in blocks.items()}


def verify_privileged_ci_boundary(workflow_path: Path) -> None:
    blocks = workflow_job_blocks(workflow_path.read_text(encoding="utf-8"))
    dedicated = "m1-db-bootstrap-privilege-probe"
    if dedicated not in blocks:
        raise VerificationError(f"workflow is missing dedicated job {dedicated}")
    leaking_jobs = [
        name
        for name, block in blocks.items()
        if name != dedicated and PRIVILEGED_NAME.search(block)
    ]
    if leaking_jobs:
        raise VerificationError(
            "privileged credential names leak into normal CI jobs: "
            + ", ".join(sorted(leaking_jobs))
        )


def verify_product_sources(root: Path) -> None:
    failures: list[str] = []
    apps = root / "apps"
    if not apps.is_dir():
        raise VerificationError("apps directory is missing")
    for path in apps.rglob("*"):
        if not path.is_file() or "node_modules" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if PRIVILEGED_NAME.search(text):
            failures.append(str(path.relative_to(root)))
    if failures:
        raise VerificationError(
            "privileged credential names found in product sources: " + ", ".join(sorted(failures))
        )


def _environment_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return {key for key in value if isinstance(key, str)}
    if isinstance(value, list):
        return {item.split("=", 1)[0] for item in value if isinstance(item, str) and "=" in item}
    return set()


def verify_compose_json(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    services = payload.get("services") if isinstance(payload, dict) else None
    if not isinstance(services, dict):
        raise VerificationError(f"{path}: rendered Compose has no services mapping")
    failures: list[str] = []
    bootstrap = services.get("db-bootstrap")
    if not isinstance(bootstrap, dict):
        failures.append("missing db-bootstrap service")
    else:
        bootstrap_environment = bootstrap.get("environment")
        revoke_value = (
            bootstrap_environment.get("NH_DB_REVOKE_BOOTSTRAP_LOGIN")
            if isinstance(bootstrap_environment, dict)
            else None
        )
        if str(revoke_value).lower() not in {"1", "true"}:
            failures.append("db-bootstrap:NH_DB_REVOKE_BOOTSTRAP_LOGIN must be true")
        bootstrap_command = "\n".join(str(item) for item in bootstrap.get("command", []))
        if 'pg_isready -h 127.0.0.1 -U "$$POSTGRES_USER"' not in bootstrap_command:
            failures.append("db-bootstrap readiness must use POSTGRES_USER")

    postgres = services.get("postgres")
    if not isinstance(postgres, dict):
        failures.append("missing postgres service")
    else:
        dependencies = postgres.get("depends_on")
        bootstrap_dependency = (
            dependencies.get("db-bootstrap") if isinstance(dependencies, dict) else None
        )
        condition = (
            bootstrap_dependency.get("condition")
            if isinstance(bootstrap_dependency, dict)
            else None
        )
        if condition != "service_completed_successfully":
            failures.append("postgres must depend on successful one-shot db-bootstrap completion")
        healthcheck = postgres.get("healthcheck")
        healthcheck_test = healthcheck.get("test") if isinstance(healthcheck, dict) else None
        if not isinstance(healthcheck_test, list) or not any(
            "pg_isready" in str(item) and "-U app" in str(item) for item in healthcheck_test
        ):
            failures.append("postgres healthcheck must use the app role")
        leaked = sorted(
            key
            for key in _environment_keys(postgres.get("environment"))
            if PRIVILEGED_NAME.search(key)
        )
        failures.extend(f"postgres:{key}" for key in leaked)

    opensearch = services.get("opensearch")
    if not isinstance(opensearch, dict):
        failures.append("missing opensearch service")
    else:
        opensearch_environment = opensearch.get("environment")
        security_disabled = (
            opensearch_environment.get("DISABLE_SECURITY_PLUGIN")
            if isinstance(opensearch_environment, dict)
            else None
        )
        if str(security_disabled).lower() not in {"1", "true"}:
            failures.append("opensearch:DISABLE_SECURITY_PLUGIN must be true")
        if (
            isinstance(opensearch_environment, dict)
            and "plugins.security.disabled" in opensearch_environment
        ):
            failures.append("opensearch must not duplicate the security-disabled setting")
    for service_name in ("backend", "worker", "frontend"):
        service = services.get(service_name)
        if not isinstance(service, dict):
            failures.append(f"missing product service {service_name}")
            continue
        leaked = sorted(
            key
            for key in _environment_keys(service.get("environment"))
            if PRIVILEGED_NAME.search(key)
        )
        failures.extend(f"{service_name}:{key}" for key in leaked)
    if failures:
        raise VerificationError("rendered Compose contract violations: " + ", ".join(failures))


def verify_image_inspect_json(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise VerificationError(f"{path}: image inspect payload must be a non-empty array")
    failures: list[str] = []
    for image in payload:
        if not isinstance(image, dict):
            raise VerificationError(f"{path}: invalid image inspect entry")
        image_id = image.get("Id", "unknown-image")
        config = image.get("Config")
        environment = config.get("Env") if isinstance(config, dict) else None
        leaked = sorted(
            key for key in _environment_keys(environment) if PRIVILEGED_NAME.search(key)
        )
        failures.extend(f"{image_id}:{key}" for key in leaked)
    if failures:
        raise VerificationError(
            "privileged credential names found in product image config: " + ", ".join(failures)
        )


def verify(root: Path) -> None:
    verify_namespaces(root / ".env.dev.example", root / ".env.prod.example")
    verify_privileged_ci_boundary(root / ".github/workflows/ci.yml")
    verify_product_sources(root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--compose-json", type=Path, action="append", default=[])
    parser.add_argument("--image-inspect-json", type=Path, action="append", default=[])
    args = parser.parse_args(argv)
    try:
        verify(args.root.resolve())
        for path in args.compose_json:
            verify_compose_json(path)
        for path in args.image_inspect_json:
            verify_image_inspect_json(path)
    except (OSError, VerificationError) as error:
        print(f"M1 static verification failed: {error}", file=sys.stderr)
        return 1
    print("PASS: M1 namespace, config and privileged-credential verification")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
