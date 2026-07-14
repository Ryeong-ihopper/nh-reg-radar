"""Fail when dev and prod resource namespaces can overlap.

This check intentionally reports variable names, never values, because DSNs and
credential placeholders are present in the same env example files.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import cast


RESOURCE_KEYS: dict[str, tuple[str, ...]] = {
    "compose": ("COMPOSE_PROJECT_NAME",),
    "postgres": ("POSTGRES_DB",),
    "object-storage": (
        "OBJECT_STORAGE_BUCKET_PREFIX",
        "AD_ORIGINALS_BUCKET",
        "REFERENCE_DOCUMENTS_BUCKET",
        "REPORTS_BUCKET",
    ),
    "qdrant": ("QDRANT_COLLECTION",),
    "opensearch": ("OPENSEARCH_INDEX",),
    "redis": ("REDIS_QUEUE_PREFIX", "REDIS_CACHE_PREFIX"),
}

EXPECTED_PREFIXES: dict[str, tuple[str, str]] = {
    "COMPOSE_PROJECT_NAME": ("nh-ad-dev", "nh-ad-prod"),
    "POSTGRES_DB": ("nh_ad_dev", "nh_ad_prod"),
    "OBJECT_STORAGE_BUCKET_PREFIX": ("dev-", "prod-"),
    "AD_ORIGINALS_BUCKET": ("dev-", "prod-"),
    "REFERENCE_DOCUMENTS_BUCKET": ("dev-", "prod-"),
    "REPORTS_BUCKET": ("dev-", "prod-"),
    "QDRANT_COLLECTION": ("dev_", "prod_"),
    "OPENSEARCH_INDEX": ("dev_", "prod_"),
    "REDIS_QUEUE_PREFIX": ("dev:", "prod:"),
    "REDIS_CACHE_PREFIX": ("dev:", "prod:"),
}


def load_env(path: Path) -> dict[str, str]:
    """Parse the simple KEY=VALUE syntax used by committed env examples."""

    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"{path}:{line_number}: expected KEY=VALUE")
        key, value = line.split("=", maxsplit=1)
        key = key.strip()
        if not key or key in values:
            raise ValueError(f"{path}:{line_number}: invalid or duplicate key")
        values[key] = value.strip()
    return values


def validate_isolation(dev: dict[str, str], prod: dict[str, str]) -> list[str]:
    """Return safe, key-only validation errors."""

    errors: list[str] = []
    for category, keys in RESOURCE_KEYS.items():
        for key in keys:
            dev_value = dev.get(key, "")
            prod_value = prod.get(key, "")
            if not dev_value or not prod_value:
                errors.append(f"{category}: {key} must be non-empty in both environments")
                continue
            if dev_value == prod_value:
                errors.append(f"{category}: {key} must differ between dev and prod")

            dev_prefix, prod_prefix = EXPECTED_PREFIXES[key]
            if not dev_value.startswith(dev_prefix):
                errors.append(f"{category}: {key} does not use the dev namespace")
            if not prod_value.startswith(prod_prefix):
                errors.append(f"{category}: {key} does not use the prod namespace")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--dev", type=Path, default=Path(".env.dev.example"))
    _ = parser.add_argument("--prod", type=Path, default=Path(".env.prod.example"))
    args = cast("dict[str, object]", vars(parser.parse_args()))
    dev_path = cast(Path, args["dev"])
    prod_path = cast(Path, args["prod"])

    try:
        errors = validate_isolation(load_env(dev_path), load_env(prod_path))
    except (OSError, ValueError) as caught_error:
        print(f"environment isolation check failed: {caught_error}")
        return 1

    if errors:
        for validation_error in errors:
            print(f"environment isolation check failed: {validation_error}")
        return 1

    checked = sum(len(keys) for keys in RESOURCE_KEYS.values())
    print(f"environment isolation check passed: {checked} resource keys")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
