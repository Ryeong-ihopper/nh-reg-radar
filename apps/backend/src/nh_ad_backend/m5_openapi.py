"""Frozen M5 Review Result, Evidence mapping, and Annotation OpenAPI fragments.

This module contains the capability entry gate only. It deliberately defines
no handlers, provider adapters, credentials, or network behavior.
"""

from typing import Any


def _read_responses(schema: str) -> dict[str, Any]:
    return {
        "200": {
            "description": "Scoped review result returned.",
            "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{schema}"}}},
        },
        "400": {"$ref": "#/components/responses/BadRequest"},
        "401": {"$ref": "#/components/responses/Unauthorized"},
        "403": {"$ref": "#/components/responses/Forbidden"},
        "404": {"$ref": "#/components/responses/NotFound"},
    }


M5_OPENAPI: dict[str, Any] = {
    "components": {
        "parameters": {
            "ReviewItemId": {
                "in": "path",
                "name": "reviewItemId",
                "required": True,
                "schema": {"type": "string", "pattern": "^ITEM-[A-Za-z0-9-]+$"},
            },
            "ReviewTypeQuery": {
                "in": "query",
                "name": "reviewType",
                "schema": {"$ref": "#/components/schemas/ReviewType"},
            },
            "RiskLevelQuery": {
                "in": "query",
                "name": "riskLevel",
                "schema": {"$ref": "#/components/schemas/RiskLevel"},
            },
            "ResultStatusQuery": {
                "in": "query",
                "name": "resultStatus",
                "schema": {"$ref": "#/components/schemas/ReviewResultStatus"},
            },
            "EvidenceRequiredQuery": {
                "in": "query",
                "name": "evidenceRequired",
                "schema": {"type": "boolean"},
            },
            "PageNoQuery": {
                "in": "query",
                "name": "pageNo",
                "schema": {"type": "integer", "minimum": 1},
            },
        },
        "schemas": {
            "RiskLevel": {
                "type": "string",
                "enum": ["HIGH", "MEDIUM", "LOW", "CHECK_REQUIRED"],
            },
            "ReviewResultStatus": {
                "type": "string",
                "enum": ["APPROPRIATE", "NEEDS_REVISION", "NEEDS_CONFIRMATION"],
            },
            "EvidenceStatus": {
                "type": "string",
                "enum": ["CONNECTED", "NOT_REQUIRED", "INSUFFICIENT", "SEARCH_UNAVAILABLE"],
            },
            "ReviewEngineType": {
                "type": "string",
                "enum": ["RULE", "RAG", "MULTIMODAL", "LLM"],
            },
            "StructuredOutputStatus": {
                "type": "string",
                "enum": ["NOT_RUN", "VALID", "INVALID_SCHEMA"],
            },
            "AnnotationDisplayMode": {
                "type": "string",
                "enum": ["BOX", "TEXT_HIGHLIGHT", "LIST_ONLY", "UNAVAILABLE"],
            },
            "AnnotationStatus": {
                "type": "string",
                "enum": [
                    "LOCATED",
                    "PARTIALLY_LOCATED",
                    "NOT_LOCATED",
                    "LOW_CONFIDENCE",
                    "DOCUMENT_LEVEL_ISSUE",
                ],
            },
            "RiskRuleScore": {
                "type": "object",
                "additionalProperties": False,
                "required": ["matched", "ruleIds", "severity"],
                "properties": {
                    "matched": {"type": "boolean"},
                    "ruleIds": {"type": "array", "items": {"type": "string"}},
                    "severity": {
                        "oneOf": [
                            {"$ref": "#/components/schemas/RiskLevel"},
                            {"type": "null"},
                        ]
                    },
                },
            },
            "RiskRagScore": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "topRelevanceScore",
                    "evidenceCount",
                    "evidenceSufficient",
                    "status",
                    "failureCode",
                ],
                "properties": {
                    "topRelevanceScore": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
                    "evidenceCount": {"type": "integer", "minimum": 0, "maximum": 5},
                    "evidenceSufficient": {"type": "boolean"},
                    "status": {"$ref": "#/components/schemas/EvidenceStatus"},
                    "failureCode": {
                        "oneOf": [
                            {
                                "type": "string",
                                "enum": ["RAG_SEARCH_UNAVAILABLE", "RAG_SEARCH_FAILED"],
                            },
                            {"type": "null"},
                        ]
                    },
                },
            },
            "RiskLlmScore": {
                "type": "object",
                "additionalProperties": False,
                "required": ["schemaVersion", "status", "decision", "confidence"],
                "properties": {
                    "schemaVersion": {"const": "review-structured-output-v1", "type": "string"},
                    "status": {"$ref": "#/components/schemas/StructuredOutputStatus"},
                    "decision": {"type": ["string", "null"]},
                    "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
                },
            },
            "RiskParserScore": {
                "type": "object",
                "additionalProperties": False,
                "required": ["confidenceStatus"],
                "properties": {
                    "confidenceStatus": {"$ref": "#/components/schemas/ConfidenceStatus"}
                },
            },
            "RiskFinalScore": {
                "type": "object",
                "additionalProperties": False,
                "required": ["riskLevel", "decisionRule"],
                "properties": {
                    "riskLevel": {"$ref": "#/components/schemas/RiskLevel"},
                    "decisionRule": {"type": "string", "minLength": 1},
                },
            },
            "RiskScoreDetail": {
                "type": "object",
                "additionalProperties": False,
                "required": ["rule", "rag", "llm", "parser", "final"],
                "properties": {
                    "rule": {"$ref": "#/components/schemas/RiskRuleScore"},
                    "rag": {"$ref": "#/components/schemas/RiskRagScore"},
                    "llm": {"$ref": "#/components/schemas/RiskLlmScore"},
                    "parser": {"$ref": "#/components/schemas/RiskParserScore"},
                    "final": {"$ref": "#/components/schemas/RiskFinalScore"},
                },
            },
            "RiskRationale": {
                "type": "object",
                "additionalProperties": False,
                "required": ["riskLevel", "policyVersion", "reasonCodes", "scoreDetail"],
                "properties": {
                    "riskLevel": {"$ref": "#/components/schemas/RiskLevel"},
                    "policyVersion": {"type": "string", "minLength": 1},
                    "reasonCodes": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1},
                        "minItems": 1,
                        "uniqueItems": True,
                    },
                    "scoreDetail": {"$ref": "#/components/schemas/RiskScoreDetail"},
                },
            },
            "ReviewTypeSummary": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "reviewType",
                    "totalCount",
                    "needsRevisionCount",
                    "needsConfirmationCount",
                ],
                "properties": {
                    "reviewType": {"$ref": "#/components/schemas/ReviewType"},
                    "totalCount": {"type": "integer", "minimum": 0},
                    "needsRevisionCount": {"type": "integer", "minimum": 0},
                    "needsConfirmationCount": {"type": "integer", "minimum": 0},
                },
            },
            "TopRisk": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "reviewItemId",
                    "riskLevel",
                    "riskPolicyVersion",
                    "riskReasonCodes",
                    "targetText",
                    "reason",
                    "evidenceStatus",
                ],
                "properties": {
                    "reviewItemId": {"type": "string"},
                    "riskLevel": {"$ref": "#/components/schemas/RiskLevel"},
                    "riskPolicyVersion": {"type": "string"},
                    "riskReasonCodes": {"type": "array", "items": {"type": "string"}},
                    "targetText": {"type": "string"},
                    "reason": {"type": "string"},
                    "evidenceStatus": {"$ref": "#/components/schemas/EvidenceStatus"},
                },
            },
            "ReviewSummary": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "reviewId",
                    "advertisementId",
                    "standardEffectiveDate",
                    "standardVersionIds",
                    "overallRiskLevel",
                    "totalItemCount",
                    "needsRevisionCount",
                    "needsConfirmationCount",
                    "reviewTypeSummary",
                    "topRisks",
                    "completedAt",
                ],
                "properties": {
                    "reviewId": {"type": "string"},
                    "advertisementId": {"type": "string"},
                    "standardEffectiveDate": {"type": "string", "format": "date"},
                    "standardVersionIds": {"type": "array", "items": {"type": "string"}},
                    "overallRiskLevel": {"$ref": "#/components/schemas/RiskLevel"},
                    "totalItemCount": {"type": "integer", "minimum": 0},
                    "needsRevisionCount": {"type": "integer", "minimum": 0},
                    "needsConfirmationCount": {"type": "integer", "minimum": 0},
                    "reviewTypeSummary": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/ReviewTypeSummary"},
                    },
                    "topRisks": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/TopRisk"},
                    },
                    "completedAt": {"type": "string", "format": "date-time"},
                },
            },
            "ReviewItemSummary": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "reviewItemId",
                    "reviewType",
                    "targetText",
                    "resultStatus",
                    "riskLevel",
                    "riskPolicyVersion",
                    "riskReasonCodes",
                    "reason",
                    "evidenceStatus",
                    "evidenceFailureCode",
                    "evidenceCount",
                    "pageNo",
                    "hasAnnotation",
                    "sourceEngine",
                    "sourceVersion",
                ],
                "properties": {
                    "reviewItemId": {"type": "string"},
                    "reviewType": {"$ref": "#/components/schemas/ReviewType"},
                    "targetText": {"type": "string"},
                    "resultStatus": {"$ref": "#/components/schemas/ReviewResultStatus"},
                    "riskLevel": {"$ref": "#/components/schemas/RiskLevel"},
                    "riskPolicyVersion": {"type": "string"},
                    "riskReasonCodes": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                    "evidenceStatus": {"$ref": "#/components/schemas/EvidenceStatus"},
                    "evidenceFailureCode": {
                        "oneOf": [
                            {
                                "type": "string",
                                "enum": ["RAG_SEARCH_UNAVAILABLE", "RAG_SEARCH_FAILED"],
                            },
                            {"type": "null"},
                        ]
                    },
                    "evidenceCount": {"type": "integer", "minimum": 0, "maximum": 5},
                    "pageNo": {"type": ["integer", "null"], "minimum": 1},
                    "hasAnnotation": {"type": "boolean"},
                    "sourceEngine": {"$ref": "#/components/schemas/ReviewEngineType"},
                    "sourceVersion": {"type": "string", "minLength": 1},
                },
            },
            "ReviewItemPage": {
                "type": "object",
                "additionalProperties": False,
                "required": ["contents", "page", "size", "totalElements", "totalPages"],
                "properties": {
                    "contents": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/ReviewItemSummary"},
                    },
                    "page": {"type": "integer", "minimum": 1},
                    "size": {"type": "integer", "minimum": 1, "maximum": 100},
                    "totalElements": {"type": "integer", "minimum": 0},
                    "totalPages": {"type": "integer", "minimum": 0},
                },
            },
            "ReviewItemEvidence": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "evidenceId",
                    "evidenceChunkId",
                    "standardVersionId",
                    "evidenceType",
                    "title",
                    "matchedText",
                    "rankNo",
                    "relevanceScore",
                    "matchSource",
                ],
                "properties": {
                    "evidenceId": {"type": "string"},
                    "evidenceChunkId": {"type": ["string", "null"]},
                    "standardVersionId": {"type": "string"},
                    "evidenceType": {"$ref": "#/components/schemas/EvidenceType"},
                    "title": {"type": "string"},
                    "articleNo": {"type": ["string", "null"]},
                    "matchedText": {"type": "string"},
                    "rankNo": {"type": "integer", "minimum": 1, "maximum": 5},
                    "relevanceScore": {"type": "number", "minimum": 0, "maximum": 1},
                    "matchSource": {
                        "type": "string",
                        "enum": ["KEYWORD", "VECTOR", "HYBRID", "RULE_METADATA"],
                    },
                },
            },
            "Annotation": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "annotationId",
                    "reviewItemId",
                    "reviewType",
                    "riskLevel",
                    "targetText",
                    "annotationDisplayMode",
                    "annotationStatus",
                    "locationConfidence",
                    "confidencePolicyVersion",
                    "displayReason",
                    "pageNo",
                    "coordinate",
                    "textBlockId",
                    "textPath",
                    "rawStartOffset",
                    "rawEndOffset",
                    "normalizedStartOffset",
                    "normalizedEndOffset",
                    "matchedText",
                ],
                "properties": {
                    "annotationId": {"type": "string"},
                    "reviewItemId": {"type": "string"},
                    "reviewType": {"$ref": "#/components/schemas/ReviewType"},
                    "riskLevel": {"$ref": "#/components/schemas/RiskLevel"},
                    "targetText": {"type": "string"},
                    "annotationDisplayMode": {"$ref": "#/components/schemas/AnnotationDisplayMode"},
                    "annotationStatus": {"$ref": "#/components/schemas/AnnotationStatus"},
                    "locationConfidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
                    "confidencePolicyVersion": {"type": "string"},
                    "displayReason": {"type": "string"},
                    "pageNo": {"type": ["integer", "null"], "minimum": 1},
                    "coordinate": {
                        "oneOf": [
                            {"$ref": "#/components/schemas/Coordinate"},
                            {"type": "null"},
                        ]
                    },
                    "textBlockId": {"type": ["string", "null"]},
                    "textPath": {"type": ["string", "null"]},
                    "rawStartOffset": {"type": ["integer", "null"], "minimum": 0},
                    "rawEndOffset": {"type": ["integer", "null"], "minimum": 0},
                    "normalizedStartOffset": {"type": ["integer", "null"], "minimum": 0},
                    "normalizedEndOffset": {"type": ["integer", "null"], "minimum": 0},
                    "matchedText": {"type": ["string", "null"]},
                },
            },
            "AnnotationCollection": {
                "type": "object",
                "additionalProperties": False,
                "required": ["reviewId", "fileId", "fileType", "pageNo", "annotations"],
                "properties": {
                    "reviewId": {"type": "string"},
                    "fileId": {"type": "string"},
                    "fileType": {"type": "string"},
                    "pageNo": {"type": ["integer", "null"], "minimum": 1},
                    "annotations": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/Annotation"},
                    },
                },
            },
            "ReviewItemDetail": {
                "allOf": [
                    {"$ref": "#/components/schemas/ReviewItemSummary"},
                    {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["riskRationale", "evidences", "recommendation", "annotation"],
                        "properties": {
                            "riskRationale": {"$ref": "#/components/schemas/RiskRationale"},
                            "evidences": {
                                "type": "array",
                                "maxItems": 3,
                                "items": {"$ref": "#/components/schemas/ReviewItemEvidence"},
                            },
                            "recommendation": {"type": ["string", "null"]},
                            "annotation": {
                                "oneOf": [
                                    {"$ref": "#/components/schemas/Annotation"},
                                    {"type": "null"},
                                ]
                            },
                        },
                    },
                ]
            },
        },
    },
    "paths": {
        "/reviews/{reviewId}/summary": {
            "get": {
                "tags": ["Review Results"],
                "operationId": "getReviewSummary",
                "description": "Returns the immutable standard-version snapshot and risk summary.",
                "parameters": [{"$ref": "#/components/parameters/ReviewId"}],
                "responses": _read_responses("ReviewSummary"),
            }
        },
        "/reviews/{reviewId}/items": {
            "get": {
                "tags": ["Review Results"],
                "operationId": "listReviewItems",
                "description": "Lists scoped result items without hiding evidence insufficiency or search failure.",
                "parameters": [
                    {"$ref": "#/components/parameters/ReviewId"},
                    {"$ref": "#/components/parameters/ReviewTypeQuery"},
                    {"$ref": "#/components/parameters/RiskLevelQuery"},
                    {"$ref": "#/components/parameters/ResultStatusQuery"},
                    {"$ref": "#/components/parameters/EvidenceRequiredQuery"},
                    {"$ref": "#/components/parameters/Page"},
                    {"$ref": "#/components/parameters/Size"},
                ],
                "responses": _read_responses("ReviewItemPage"),
            }
        },
        "/reviews/{reviewId}/items/{reviewItemId}": {
            "get": {
                "tags": ["Review Results"],
                "operationId": "getReviewItem",
                "description": "Returns risk rationale, frozen evidence versions, and optional display location.",
                "parameters": [
                    {"$ref": "#/components/parameters/ReviewId"},
                    {"$ref": "#/components/parameters/ReviewItemId"},
                ],
                "responses": _read_responses("ReviewItemDetail"),
            }
        },
        "/reviews/{reviewId}/annotations": {
            "get": {
                "tags": ["Annotations"],
                "operationId": "listReviewAnnotations",
                "description": "Returns BOX, TEXT_HIGHLIGHT, or list fallback annotations.",
                "parameters": [
                    {"$ref": "#/components/parameters/ReviewId"},
                    {"$ref": "#/components/parameters/PageNoQuery"},
                    {"$ref": "#/components/parameters/ReviewTypeQuery"},
                    {"$ref": "#/components/parameters/RiskLevelQuery"},
                ],
                "responses": _read_responses("AnnotationCollection"),
            }
        },
    },
}
