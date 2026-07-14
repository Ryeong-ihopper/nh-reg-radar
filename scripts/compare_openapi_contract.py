#!/usr/bin/env python3
"""Compare source and generated OpenAPI documents on contract-bearing fields."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import TypeAlias, cast

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
OPERATION_FIELDS = {
    "operationId",
    "parameters",
    "requestBody",
    "responses",
    "callbacks",
    "security",
    "deprecated",
}
PATH_ITEM_FIELDS = {"parameters", "servers"}


def _as_object(value: JsonValue | None) -> JsonObject:
    return value if isinstance(value, dict) else {}


def load_document(path: Path) -> JsonObject:
    if path.suffix.lower() == ".json":
        value = cast(JsonValue, json.loads(path.read_text(encoding="utf-8")))
    else:
        helper = Path(__file__).with_name("print_openapi_json.mjs")
        process = subprocess.run(
            ["node", str(helper), str(path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if process.returncode != 0:
            raise ValueError(process.stderr.strip() or f"Could not parse {path}")
        value = cast(JsonValue, json.loads(process.stdout))
    if not isinstance(value, dict):
        raise ValueError(f"OpenAPI document must be an object: {path}")
    return value


def contract_projection(document: JsonObject) -> JsonObject:
    projected_paths: JsonObject = {}
    for path, path_item_value in sorted(_as_object(document.get("paths")).items()):
        if not isinstance(path_item_value, dict):
            projected_paths[path] = path_item_value
            continue
        path_item = path_item_value
        projected_item: JsonObject = {
            key: path_item[key] for key in sorted(PATH_ITEM_FIELDS) if key in path_item
        }
        for method, operation_value in sorted(path_item.items()):
            if method.lower() not in HTTP_METHODS:
                continue
            if isinstance(operation_value, dict):
                projected_item[method.lower()] = {
                    key: operation_value[key]
                    for key in sorted(OPERATION_FIELDS)
                    if key in operation_value
                }
            else:
                projected_item[method.lower()] = operation_value
        projected_paths[path] = projected_item

    return {
        "security": document.get("security", []),
        "paths": projected_paths,
        "components": _as_object(document.get("components")),
    }


def compare_contracts(source: JsonObject, generated: JsonObject) -> list[str]:
    source_projection = contract_projection(source)
    generated_projection = contract_projection(generated)
    if source_projection == generated_projection:
        return []
    source_text = json.dumps(
        source_projection, ensure_ascii=False, indent=2, sort_keys=True
    )
    generated_text = json.dumps(
        generated_projection, ensure_ascii=False, indent=2, sort_keys=True
    )
    return [
        "OpenAPI contract drift detected",
        f"source={source_text}",
        f"generated={generated_text}",
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("source", type=Path)
    _ = parser.add_argument("generated", type=Path)
    args = parser.parse_args(argv)
    source_path = cast(Path, args.source)
    generated_path = cast(Path, args.generated)
    try:
        differences = compare_contracts(
            load_document(source_path), load_document(generated_path)
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"OpenAPI comparison failed: {error}", file=sys.stderr)
        return 2
    if differences:
        print("\n".join(differences), file=sys.stderr)
        return 1
    print("OpenAPI contracts are semantically equivalent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
