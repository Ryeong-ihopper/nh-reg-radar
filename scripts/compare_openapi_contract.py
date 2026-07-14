#!/usr/bin/env python3
"""Compare source and generated OpenAPI documents semantically.

Generator-only details such as component names and descriptions are ignored. Contract-bearing
paths, parameters, security, status codes, media types, headers, and resolved schemas remain
strictly compared.
"""

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
DESCRIPTIVE_FIELDS = {"description", "example", "examples", "externalDocs", "title", "xml"}
EMPTY_REFERENCES: frozenset[str] = frozenset()


def _as_object(value: JsonValue | None) -> JsonObject:
    return value if isinstance(value, dict) else {}


def load_document(path: Path) -> JsonObject:
    if path.suffix.lower() == ".json":
        value = cast(JsonValue, json.loads(path.read_text(encoding="utf-8")))
    else:
        helper = Path(__file__).with_name("print_openapi_json.mjs")
        process = subprocess.run(
            ["node", str(helper), str(path)], check=False, capture_output=True, text=True
        )
        if process.returncode != 0:
            raise ValueError(process.stderr.strip() or f"Could not parse {path}")
        value = cast(JsonValue, json.loads(process.stdout))
    if not isinstance(value, dict):
        raise ValueError(f"OpenAPI document must be an object: {path}")
    return value


def _resolve_ref(document: JsonObject, reference: str) -> JsonValue:
    if not reference.startswith("#/"):
        return {"$ref": reference}
    current: JsonValue = document
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"Unresolved OpenAPI reference: {reference}")
        current = current[part]
    return current


def _json_sort_key(value: JsonValue) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonical_schema(
    value: JsonValue,
    document: JsonObject,
    resolving: frozenset[str] = EMPTY_REFERENCES,
) -> JsonValue:
    if isinstance(value, list):
        return [_canonical_schema(item, document, resolving) for item in value]
    if not isinstance(value, dict):
        return value

    reference = value.get("$ref")
    if isinstance(reference, str):
        if reference in resolving:
            return {"$recursiveRef": reference.rsplit("/", 1)[-1]}
        resolved = _canonical_schema(
            _resolve_ref(document, reference), document, resolving | {reference}
        )
        siblings = {key: item for key, item in value.items() if key != "$ref"}
        if not siblings:
            return resolved
        return _canonical_schema({"allOf": [resolved, siblings]}, document, resolving)

    result: JsonObject = {}
    nullable = False
    for key, item in sorted(value.items()):
        if key in DESCRIPTIVE_FIELDS:
            continue
        if key == "additionalProperties" and item is True:
            continue
        if key == "required" and isinstance(item, list):
            required = cast(list[JsonValue], sorted(str(entry) for entry in item))
            if required:
                result[key] = required
            continue
        if key == "enum" and isinstance(item, list):
            result[key] = sorted(
                (_canonical_schema(entry, document, resolving) for entry in item),
                key=_json_sort_key,
            )
            continue
        if key == "type" and isinstance(item, list):
            types = cast(
                list[JsonValue],
                sorted(str(entry) for entry in item if entry != "null"),
            )
            nullable = "null" in item
            result[key] = types[0] if len(types) == 1 else types
            continue
        if key in {"allOf", "anyOf", "oneOf"} and isinstance(item, list):
            branches = [_canonical_schema(entry, document, resolving) for entry in item]
            non_null = [entry for entry in branches if entry != {"type": "null"}]
            if key in {"anyOf", "oneOf"} and len(non_null) != len(branches):
                nullable = True
                if len(non_null) == 1 and isinstance(non_null[0], dict):
                    for nested_key, nested_value in non_null[0].items():
                        result[nested_key] = nested_value
                    continue
                branches = non_null
            result[key] = sorted(branches, key=_json_sort_key)
            continue
        result[key] = _canonical_schema(item, document, resolving)
    if nullable:
        result["nullable"] = True
    return result


def _canonical_security(value: JsonValue | None) -> JsonValue:
    if not isinstance(value, list):
        return []
    normalized: list[JsonValue] = []
    for requirement in value:
        if not isinstance(requirement, dict):
            normalized.append(requirement)
            continue
        normalized.append(
            cast(
                JsonObject,
                {
                    scheme: sorted(str(scope) for scope in scopes)
                    if isinstance(scopes, list)
                    else scopes
                    for scheme, scopes in sorted(requirement.items())
                },
            )
        )
    return sorted(normalized, key=_json_sort_key)


def _canonical_parameter(value: JsonValue, document: JsonObject) -> JsonValue:
    if isinstance(value, dict) and isinstance(value.get("$ref"), str):
        value = _resolve_ref(document, cast(str, value["$ref"]))
    if not isinstance(value, dict):
        return value
    location = value.get("in")
    result: JsonObject = {
        "name": value.get("name"),
        "in": location,
        "required": True if location == "path" else bool(value.get("required", False)),
    }
    for key in ("deprecated", "allowEmptyValue", "style", "explode", "allowReserved"):
        if key in value:
            result[key] = value[key]
    if "schema" in value:
        schema = _canonical_schema(value["schema"], document)
        # For an optional HTTP parameter, omission is the only portable representation of null.
        # FastAPI nevertheless emits a JSON-Schema null branch for ``T | None``.
        if not result["required"] and isinstance(schema, dict):
            _ = schema.pop("nullable", None)
        result["schema"] = schema
    if "content" in value:
        result["content"] = _canonical_content(value["content"], document)
    return result


def _canonical_header(value: JsonValue, document: JsonObject) -> JsonValue:
    if isinstance(value, dict) and isinstance(value.get("$ref"), str):
        value = _resolve_ref(document, cast(str, value["$ref"]))
    if not isinstance(value, dict):
        return value
    result: JsonObject = {}
    for key in ("required", "deprecated", "style", "explode"):
        if key in value:
            result[key] = value[key]
    if "schema" in value:
        result["schema"] = _canonical_schema(value["schema"], document)
    if "content" in value:
        result["content"] = _canonical_content(value["content"], document)
    return result


def _canonical_content(value: JsonValue, document: JsonObject) -> JsonValue:
    if not isinstance(value, dict):
        return value
    result: JsonObject = {}
    for media_type, media_value in sorted(value.items()):
        if not isinstance(media_value, dict):
            result[media_type] = media_value
            continue
        media: JsonObject = {}
        if "schema" in media_value:
            media["schema"] = _canonical_schema(media_value["schema"], document)
        if "encoding" in media_value:
            media["encoding"] = _canonical_schema(media_value["encoding"], document)
        result[media_type] = media
    return result


def _canonical_response(value: JsonValue, document: JsonObject) -> JsonValue:
    if isinstance(value, dict) and isinstance(value.get("$ref"), str):
        value = _resolve_ref(document, cast(str, value["$ref"]))
    if not isinstance(value, dict):
        return value
    result: JsonObject = {}
    headers = value.get("headers")
    if isinstance(headers, dict):
        result["headers"] = {
            name.casefold(): _canonical_header(header, document)
            for name, header in sorted(headers.items())
        }
    if "content" in value:
        result["content"] = _canonical_content(value["content"], document)
    if "links" in value:
        result["links"] = _canonical_schema(value["links"], document)
    return result


def _canonical_request_body(value: JsonValue, document: JsonObject) -> JsonValue:
    if isinstance(value, dict) and isinstance(value.get("$ref"), str):
        value = _resolve_ref(document, cast(str, value["$ref"]))
    if not isinstance(value, dict):
        return value
    result: JsonObject = {"required": bool(value.get("required", False))}
    if "content" in value:
        result["content"] = _canonical_content(value["content"], document)
    return result


def contract_projection(document: JsonObject) -> JsonObject:
    root_security = document.get("security", [])
    projected_paths: JsonObject = {}
    for path, path_item_value in sorted(_as_object(document.get("paths")).items()):
        if not isinstance(path_item_value, dict):
            projected_paths[path] = path_item_value
            continue
        common_parameters = path_item_value.get("parameters", [])
        projected_item: JsonObject = {}
        for method, operation_value in sorted(path_item_value.items()):
            if method.lower() not in HTTP_METHODS:
                continue
            if not isinstance(operation_value, dict):
                projected_item[method.lower()] = operation_value
                continue
            parameters: list[JsonValue] = []
            for collection in (common_parameters, operation_value.get("parameters", [])):
                if isinstance(collection, list):
                    parameters.extend(
                        _canonical_parameter(parameter, document) for parameter in collection
                    )
            parameters.sort(key=_json_sort_key)
            operation: JsonObject = {
                "operationId": operation_value.get("operationId"),
                "parameters": parameters,
                "security": _canonical_security(operation_value.get("security", root_security)),
                "responses": {
                    str(status): _canonical_response(response, document)
                    for status, response in sorted(
                        _as_object(operation_value.get("responses")).items()
                    )
                },
            }
            if "requestBody" in operation_value:
                operation["requestBody"] = _canonical_request_body(
                    operation_value["requestBody"], document
                )
            if operation_value.get("deprecated") is True:
                operation["deprecated"] = True
            projected_item[method.lower()] = operation
        projected_paths[path] = projected_item

    security_schemes = _as_object(_as_object(document.get("components")).get("securitySchemes"))
    return {
        "paths": projected_paths,
        "securitySchemes": {
            name: _canonical_schema(scheme, document)
            for name, scheme in sorted(security_schemes.items())
        },
    }


def compare_contracts(source: JsonObject, generated: JsonObject) -> list[str]:
    source_projection = contract_projection(source)
    generated_projection = contract_projection(generated)
    if source_projection == generated_projection:
        return []
    source_text = json.dumps(source_projection, ensure_ascii=False, indent=2, sort_keys=True)
    generated_text = json.dumps(generated_projection, ensure_ascii=False, indent=2, sort_keys=True)
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
        differences = compare_contracts(load_document(source_path), load_document(generated_path))
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
