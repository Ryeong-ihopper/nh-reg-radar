"""Frozen M4 Review/Job/Parser OpenAPI fragments.

This module defines the capability entry gate only. Runtime handlers are owned
by the downstream M4 backend/worker slice.
"""

from typing import Any, cast

from nh_ad_parser_contracts import NormalizedDocument


def _as_openapi_30(value: Any) -> Any:
    """Translate Pydantic's JSON Schema null branches to OpenAPI 3.0."""
    if isinstance(value, list):
        return [_as_openapi_30(item) for item in value]
    if not isinstance(value, dict):
        return value

    normalized = {
        key: _as_openapi_30(item)
        for key, item in value.items()
        if not (key == "default" and item is None)
    }
    branches = normalized.get("anyOf")
    if not isinstance(branches, list):
        return normalized
    non_null = [branch for branch in branches if branch != {"type": "null"}]
    if len(non_null) != 1 or len(non_null) == len(branches):
        return normalized
    branch = non_null[0]
    if not isinstance(branch, dict):
        return normalized
    siblings = {key: item for key, item in normalized.items() if key != "anyOf"}
    return {**branch, **siblings, "nullable": True}


def _normalized_document_schemas() -> dict[str, Any]:
    root = NormalizedDocument.model_json_schema(ref_template="#/components/schemas/{model}")
    definitions = root.pop("$defs")
    return cast(dict[str, Any], _as_openapi_30({**definitions, "NormalizedDocument": root}))


REVIEWS_OPENAPI: dict[str, Any] = {
    "components": {
        "parameters": {
            "AdvertisementId": {
                "in": "path",
                "name": "advertisementId",
                "required": True,
                "schema": {"type": "string", "pattern": "^ADV-[A-Za-z0-9-]+$"},
            },
            "ReviewId": {
                "in": "path",
                "name": "reviewId",
                "required": True,
                "schema": {"type": "string", "pattern": "^REV-[A-Za-z0-9-]+$"},
            },
        },
        "schemas": {
            **_normalized_document_schemas(),
            "AIReviewStatus": {
                "type": "string",
                "enum": [
                    "ANALYSIS_REQUESTED",
                    "ANALYZING",
                    "CHECK_REQUIRED",
                    "REVIEW_COMPLETED",
                    "REVIEW_FAILED",
                ],
            },
            "ReviewJobStatus": {
                "type": "string",
                "enum": [
                    "PENDING",
                    "RUNNING",
                    "RETRY_PENDING",
                    "STALE",
                    "COMPLETED",
                    "FAILED",
                    "FAILED_FINAL",
                    "CANCELED",
                ],
            },
            "ReviewType": {
                "type": "string",
                "enum": [
                    "REQUIRED_PHRASE",
                    "INTEREST_RATE",
                    "MISLEADING_EXPRESSION",
                    "PRODUCT_CONSISTENCY",
                    "VISIBILITY",
                    "OCR_QUALITY",
                ],
            },
            "CreateReviewRequest": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "standardEffectiveDate": {"type": ["string", "null"], "format": "date"},
                    "reviewTypes": {
                        "type": ["array", "null"],
                        "items": {"$ref": "#/components/schemas/ReviewType"},
                        "minItems": 1,
                        "uniqueItems": True,
                    },
                    "includeSuggestion": {"type": "boolean", "default": True},
                    "includeOpinionDraft": {"type": "boolean", "default": False},
                    "requestMemo": {"type": ["string", "null"], "maxLength": 2000},
                },
            },
            "ReviewAccepted": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "reviewId",
                    "advertisementId",
                    "reviewStatus",
                    "jobId",
                    "standardEffectiveDate",
                    "standardVersionIds",
                    "requestedAt",
                ],
                "properties": {
                    "reviewId": {"type": "string"},
                    "advertisementId": {"type": "string"},
                    "reviewStatus": {"const": "ANALYSIS_REQUESTED", "type": "string"},
                    "jobId": {"type": "string"},
                    "standardEffectiveDate": {"type": "string", "format": "date"},
                    "standardVersionIds": {"type": "array", "items": {"type": "string"}},
                    "requestedAt": {"type": "string", "format": "date-time"},
                },
            },
            "ReviewStepStatus": {
                "type": "object",
                "additionalProperties": False,
                "required": ["stepCode", "stepName", "status", "timeoutAt"],
                "properties": {
                    "stepCode": {"type": "string"},
                    "stepName": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": [
                            "PENDING",
                            "RUNNING",
                            "RETRY_PENDING",
                            "COMPLETED",
                            "FAILED",
                            "SKIPPED",
                        ],
                    },
                    "timeoutAt": {"type": ["string", "null"], "format": "date-time"},
                    "failedReasonCode": {"type": ["string", "null"]},
                },
            },
            "ReviewProgress": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "reviewId",
                    "advertisementId",
                    "reviewStatus",
                    "jobId",
                    "jobStatus",
                    "progressRate",
                    "retryCount",
                    "maxRetries",
                    "isRetryable",
                    "timeoutAt",
                    "steps",
                    "updatedAt",
                ],
                "properties": {
                    "reviewId": {"type": "string"},
                    "advertisementId": {"type": "string"},
                    "reviewStatus": {"$ref": "#/components/schemas/AIReviewStatus"},
                    "jobId": {"type": "string"},
                    "jobStatus": {"$ref": "#/components/schemas/ReviewJobStatus"},
                    "currentStep": {"type": ["string", "null"]},
                    "progressRate": {"type": "number", "minimum": 0, "maximum": 100},
                    "retryCount": {"type": "integer", "minimum": 0, "maximum": 3},
                    "maxRetries": {"const": 3, "type": "integer"},
                    "nextRetryAt": {"type": ["string", "null"], "format": "date-time"},
                    "isRetryable": {"type": "boolean"},
                    "failedReasonCode": {"type": ["string", "null"]},
                    "failedReason": {"type": ["string", "null"]},
                    "timeoutAt": {"type": "string", "format": "date-time"},
                    "steps": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/ReviewStepStatus"},
                    },
                    "updatedAt": {"type": "string", "format": "date-time"},
                },
            },
            "ReviewHistory": {
                "type": "object",
                "additionalProperties": False,
                "required": ["reviewId", "reviewRound", "reviewStatus", "requestedAt"],
                "properties": {
                    "reviewId": {"type": "string"},
                    "reviewRound": {"type": "integer", "minimum": 1},
                    "reviewStatus": {"$ref": "#/components/schemas/AIReviewStatus"},
                    "overallRiskLevel": {"type": ["string", "null"]},
                    "requestedAt": {"type": "string", "format": "date-time"},
                    "completedAt": {"type": ["string", "null"], "format": "date-time"},
                },
            },
            "RerunReviewRequest": {
                "type": "object",
                "additionalProperties": False,
                "required": ["reason"],
                "properties": {
                    "reason": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "reviewTypes": {
                        "type": ["array", "null"],
                        "items": {"$ref": "#/components/schemas/ReviewType"},
                        "minItems": 1,
                        "uniqueItems": True,
                    },
                },
            },
            "RerunReviewAccepted": {
                "type": "object",
                "additionalProperties": False,
                "required": ["newReviewId", "previousReviewId", "reviewStatus", "jobId"],
                "properties": {
                    "newReviewId": {"type": "string"},
                    "previousReviewId": {"type": "string"},
                    "reviewStatus": {"const": "ANALYSIS_REQUESTED", "type": "string"},
                    "jobId": {"type": "string"},
                },
            },
            "ReviewQueueMessageV1": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "messageVersion",
                    "jobId",
                    "reviewId",
                    "jobType",
                    "correlationId",
                    "idempotencyKey",
                ],
                "properties": {
                    "messageVersion": {"const": "review-job-v1", "type": "string"},
                    "jobId": {"type": "string"},
                    "reviewId": {"type": "string"},
                    "jobType": {"type": "string", "enum": ["REVIEW_ANALYSIS", "RE_REVIEW"]},
                    "correlationId": {"type": "string"},
                    "idempotencyKey": {"type": "string"},
                },
                "description": "Redis delivery payload. Raw files, OCR text, and provider output are forbidden.",
            },
        },
    },
    "paths": {
        "/advertisements/{advertisementId}/reviews": {
            "post": {
                "tags": ["Reviews"],
                "operationId": "requestAdvertisementReview",
                "description": "Persists review/job/steps before minimal Redis delivery.",
                "parameters": [{"$ref": "#/components/parameters/AdvertisementId"}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/CreateReviewRequest"}
                        }
                    },
                },
                "responses": {
                    "202": {
                        "description": "Review job accepted.",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ReviewAccepted"}
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "409": {"$ref": "#/components/responses/Conflict"},
                },
            },
            "get": {
                "tags": ["Reviews"],
                "operationId": "listAdvertisementReviews",
                "description": "Lists immutable review rounds for an advertisement.",
                "parameters": [{"$ref": "#/components/parameters/AdvertisementId"}],
                "responses": {
                    "200": {
                        "description": "Immutable review history.",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {"$ref": "#/components/schemas/ReviewHistory"},
                                }
                            }
                        },
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
            },
        },
        "/reviews/{reviewId}/status": {
            "get": {
                "tags": ["Reviews"],
                "operationId": "getReviewStatus",
                "description": "Returns PostgreSQL-sourced job and step progress.",
                "parameters": [{"$ref": "#/components/parameters/ReviewId"}],
                "responses": {
                    "200": {
                        "description": "PostgreSQL-sourced job and step progress.",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ReviewProgress"}
                            }
                        },
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
            }
        },
        "/reviews/{reviewId}/events": {
            "get": {
                "tags": ["Reviews"],
                "operationId": "streamReviewProgress",
                "description": "Streams PostgreSQL-sourced review progress changes as server-sent events.",
                "parameters": [{"$ref": "#/components/parameters/ReviewId"}],
                "responses": {
                    "200": {
                        "description": "Progress events. Each progress event contains a ReviewProgress payload.",
                        "content": {"text/event-stream": {"schema": {"type": "string"}}},
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
            }
        },
        "/reviews/{reviewId}/rerun": {
            "post": {
                "tags": ["Reviews"],
                "operationId": "rerunReview",
                "description": "Creates a new review round without overwriting history.",
                "parameters": [{"$ref": "#/components/parameters/ReviewId"}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/RerunReviewRequest"}
                        }
                    },
                },
                "responses": {
                    "202": {
                        "description": "New review round accepted without overwriting history.",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/RerunReviewAccepted"}
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "409": {"$ref": "#/components/responses/Conflict"},
                },
            }
        },
    },
}
