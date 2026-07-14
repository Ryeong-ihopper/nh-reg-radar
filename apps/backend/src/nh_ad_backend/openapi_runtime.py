"""Narrow fixes for FastAPI artifacts that cannot describe the runtime boundary."""

from copy import deepcopy
from typing import Any, cast

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from nh_ad_backend.api import CreateAdvertisementRequest
from nh_ad_backend.m3_openapi import M3_OPENAPI


def _without_null_branch(value: dict[str, Any]) -> dict[str, Any]:
    """Represent an optional-but-non-null OpenAPI 3.0 field emitted as 3.1 anyOf."""
    branches = value.get("anyOf")
    if not isinstance(branches, list):
        return value
    non_null = [branch for branch in branches if branch != {"type": "null"}]
    if len(non_null) != 1 or not isinstance(non_null[0], dict):
        return value
    return {**non_null[0], **{key: item for key, item in value.items() if key != "anyOf"}}


def _normalize_integral_numbers(value: Any) -> Any:
    """Avoid generator-only ``1.0`` drift for integer JSON-Schema bounds."""
    if isinstance(value, dict):
        return {key: _normalize_integral_numbers(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_integral_numbers(item) for item in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def generated_openapi(app: FastAPI) -> dict[str, Any]:
    if app.openapi_schema is not None:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        servers=app.servers,
        tags=app.openapi_tags,
    )
    for path_item in schema["paths"].values():
        for operation in path_item.values():
            if isinstance(operation, dict):
                operation.get("responses", {}).pop("422", None)
    schema["paths"]["/advertisements"]["post"]["requestBody"] = {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {"$ref": "#/components/schemas/CreateAdvertisementRequest"}
            }
        },
    }
    for path in ("/auth/refresh", "/auth/logout"):
        operation = schema["paths"][path]["post"]
        operation["parameters"] = [
            {
                "name": "Origin",
                "in": "header",
                "required": True,
                "schema": {"type": "string", "format": "uri"},
            }
        ]
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    create_schema = CreateAdvertisementRequest.model_json_schema(
        ref_template="#/components/schemas/{model}"
    )
    create_schema.pop("$defs", None)
    for property_name in (
        "additionalFiles",
        "channelType",
        "memo",
        "productDescriptionFile",
        "termsFile",
    ):
        property_schema = create_schema["properties"][property_name]
        create_schema["properties"][property_name] = _without_null_branch(property_schema)
        create_schema["properties"][property_name].pop("default", None)
    components["CreateAdvertisementRequest"] = create_schema
    components.pop("HTTPValidationError", None)
    components.pop("ValidationError", None)
    # M3 handlers return deliberately lightweight dictionaries, while the governed
    # boundary has strict response, error, parameter, and multipart schemas. Publish
    # those backend-owned fragments explicitly and keep them parity-tested against
    # the repository source contract.
    schema["paths"].update(deepcopy(M3_OPENAPI["paths"]))
    for path in M3_OPENAPI["paths"]:
        for operation in schema["paths"][path].values():
            if isinstance(operation, dict):
                operation.setdefault("security", [{"BearerAuth": []}])
    for component_kind, values in M3_OPENAPI["components"].items():
        schema.setdefault("components", {}).setdefault(component_kind, {}).update(deepcopy(values))
    schema = cast(dict[str, Any], _normalize_integral_numbers(schema))
    app.openapi_schema = schema
    return schema
