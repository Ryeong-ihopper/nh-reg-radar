"""Frozen M7 validation dataset and KPI OpenAPI fragments.

The runtime publishes this provider-free boundary before the backend service lane
implements the deterministic repositories and KPI evaluation.
"""

from typing import Any


M7_OPENAPI: dict[str, Any] = {
    "components": {
        "schemas": {
            "ExcludeReasonCode": {
                "type": "string",
                "enum": [
                    "OCR_UNREADABLE",
                    "PRODUCT_CONDITION_AMBIGUOUS",
                    "REFERENCE_NOT_PROVIDED",
                    "SOURCE_FILE_CORRUPTED",
                    "LABEL_UNCLEAR",
                    "DUPLICATE_SAMPLE",
                    "OUT_OF_SCOPE",
                ],
            },
            "ValidationMetricCode": {
                "type": "string",
                "enum": [
                    "REQUIRED_PHRASE_ACCURACY",
                    "MISLEADING_EXPRESSION_ACCURACY",
                    "EVIDENCE_PRECISION",
                    "HUMAN_AGREEMENT_RATE",
                ],
            },
            "ValidationEvaluationStatus": {"type": "string", "enum": ["COMPLETED", "FAILED"]},
            "ReviewSelectionPolicy": {"type": "string", "enum": ["LATEST_COMPLETED"]},
            "CreateValidationDatasetRequest": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "datasetName",
                    "productGroup",
                    "advertisementType",
                    "advertisementFile",
                ],
                "properties": {
                    "datasetName": {"type": "string", "minLength": 1, "maxLength": 300},
                    "productGroup": {"$ref": "#/components/schemas/ProductGroup"},
                    "advertisementType": {"$ref": "#/components/schemas/AdvertisementType"},
                    "advertisementFile": {"type": "string", "format": "binary"},
                    "productConditionFile": {"type": "string", "format": "binary"},
                    "humanReviewComment": {"type": "string", "maxLength": 4000},
                    "labelJson": {
                        "type": "string",
                        "description": "JSON-serialized "
                        "synthetic "
                        "or "
                        "approved "
                        "label "
                        "payload "
                        "persisted "
                        "as "
                        "JSONB.",
                    },
                    "excluded": {"type": "boolean", "default": False},
                    "excludeReasonCode": {"$ref": "#/components/schemas/ExcludeReasonCode"},
                    "excludeReasonDetail": {"type": "string", "maxLength": 2000},
                },
            },
            "ValidationDataset": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "datasetId",
                    "datasetName",
                    "productGroup",
                    "advertisementType",
                    "datasetVersion",
                    "excluded",
                    "createdAt",
                ],
                "properties": {
                    "datasetId": {"type": "string", "pattern": "^DATASET-[A-Za-z0-9-]+$"},
                    "datasetName": {"type": "string"},
                    "productGroup": {"$ref": "#/components/schemas/ProductGroup"},
                    "advertisementType": {"$ref": "#/components/schemas/AdvertisementType"},
                    "advertisementId": {"type": ["string", "null"]},
                    "sampleFileId": {"type": ["string", "null"]},
                    "productConditionFileId": {"type": ["string", "null"]},
                    "humanReviewComment": {"type": ["string", "null"]},
                    "labelJson": {"type": ["object", "null"], "additionalProperties": True},
                    "datasetVersion": {"type": "integer", "minimum": 1},
                    "excluded": {"type": "boolean"},
                    "excludeReasonCode": {
                        "oneOf": [
                            {"$ref": "#/components/schemas/ExcludeReasonCode"},
                            {"type": "null"},
                        ]
                    },
                    "excludeReasonDetail": {"type": ["string", "null"]},
                    "excludedBy": {"type": ["string", "null"]},
                    "excludedAt": {"type": ["string", "null"], "format": "date-time"},
                    "createdAt": {"type": "string", "format": "date-time"},
                    "updatedAt": {"type": ["string", "null"], "format": "date-time"},
                },
            },
            "ValidationDatasetPage": {
                "type": "object",
                "additionalProperties": False,
                "required": ["items", "page", "size", "totalElements", "totalPages"],
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/ValidationDataset"},
                    },
                    "page": {"type": "integer", "minimum": 0},
                    "size": {"type": "integer", "minimum": 1},
                    "totalElements": {"type": "integer", "minimum": 0},
                    "totalPages": {"type": "integer", "minimum": 0},
                },
            },
            "ValidationJudgmentInput": {
                "type": "object",
                "additionalProperties": False,
                "required": ["targetText", "reviewType", "expectedStatus"],
                "properties": {
                    "targetText": {"type": "string", "minLength": 1},
                    "reviewType": {"$ref": "#/components/schemas/ReviewType"},
                    "expectedStatus": {"$ref": "#/components/schemas/ReviewResultStatus"},
                    "riskLevel": {
                        "oneOf": [{"$ref": "#/components/schemas/RiskLevel"}, {"type": "null"}]
                    },
                    "comment": {"type": ["string", "null"]},
                    "excluded": {"type": "boolean", "default": False},
                    "excludeReasonCode": {
                        "oneOf": [
                            {"$ref": "#/components/schemas/ExcludeReasonCode"},
                            {"type": "null"},
                        ]
                    },
                    "excludeReasonDetail": {"type": ["string", "null"]},
                },
            },
            "CreateValidationJudgmentsRequest": {
                "type": "object",
                "additionalProperties": False,
                "required": ["judgments"],
                "properties": {
                    "judgments": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"$ref": "#/components/schemas/ValidationJudgmentInput"},
                    }
                },
            },
            "ValidationJudgment": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "judgmentId",
                    "datasetId",
                    "targetText",
                    "reviewType",
                    "expectedStatus",
                    "excluded",
                    "judgmentVersion",
                    "judgedBy",
                    "judgedAt",
                ],
                "properties": {
                    "judgmentId": {"type": "string", "pattern": "^JUDG-[A-Za-z0-9-]+$"},
                    "datasetId": {"type": "string", "pattern": "^DATASET-[A-Za-z0-9-]+$"},
                    "targetText": {"type": "string"},
                    "reviewType": {"$ref": "#/components/schemas/ReviewType"},
                    "expectedStatus": {"$ref": "#/components/schemas/ReviewResultStatus"},
                    "riskLevel": {
                        "oneOf": [{"$ref": "#/components/schemas/RiskLevel"}, {"type": "null"}]
                    },
                    "comment": {"type": ["string", "null"]},
                    "excluded": {"type": "boolean"},
                    "excludeReasonCode": {
                        "oneOf": [
                            {"$ref": "#/components/schemas/ExcludeReasonCode"},
                            {"type": "null"},
                        ]
                    },
                    "excludeReasonDetail": {"type": ["string", "null"]},
                    "judgmentVersion": {"type": "integer", "minimum": 1},
                    "judgedBy": {"type": "string"},
                    "judgedAt": {"type": "string", "format": "date-time"},
                },
            },
            "ValidationJudgmentsCreated": {
                "type": "object",
                "additionalProperties": False,
                "required": ["datasetId", "judgments"],
                "properties": {
                    "datasetId": {"type": "string", "pattern": "^DATASET-[A-Za-z0-9-]+$"},
                    "judgments": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/ValidationJudgment"},
                    },
                },
            },
            "CreateValidationEvaluationRequest": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "datasetIds",
                    "metrics",
                    "excludeInvalidSamples",
                    "reviewSelectionPolicy",
                ],
                "properties": {
                    "datasetIds": {
                        "type": "array",
                        "minItems": 1,
                        "uniqueItems": True,
                        "items": {"type": "string", "pattern": "^DATASET-[A-Za-z0-9-]+$"},
                    },
                    "metrics": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 4,
                        "uniqueItems": True,
                        "items": {"$ref": "#/components/schemas/ValidationMetricCode"},
                    },
                    "excludeInvalidSamples": {"type": "boolean"},
                    "reviewSelectionPolicy": {"$ref": "#/components/schemas/ReviewSelectionPolicy"},
                },
            },
            "ValidationExclusionSummary": {
                "type": "object",
                "additionalProperties": False,
                "required": ["excludeReasonCode", "count"],
                "properties": {
                    "excludeReasonCode": {"$ref": "#/components/schemas/ExcludeReasonCode"},
                    "count": {"type": "integer", "minimum": 1},
                },
            },
            "ValidationMetric": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "metricCode",
                    "metricName",
                    "score",
                    "numerator",
                    "denominator",
                    "excludedCount",
                    "partialCount",
                    "notApplicable",
                    "targetScore",
                    "achieved",
                ],
                "properties": {
                    "metricCode": {"$ref": "#/components/schemas/ValidationMetricCode"},
                    "metricName": {"type": "string"},
                    "score": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
                    "numerator": {"type": "number", "minimum": 0, "multipleOf": 0.5},
                    "denominator": {"type": "integer", "minimum": 0},
                    "excludedCount": {"type": "integer", "minimum": 0},
                    "partialCount": {"type": "integer", "minimum": 0},
                    "notApplicable": {"type": "boolean"},
                    "targetScore": {"type": "number", "minimum": 0, "maximum": 100},
                    "achieved": {"type": "boolean"},
                },
            },
            "ValidationVersionSnapshot": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "standardVersionIds",
                    "modelVersion",
                    "promptVersion",
                    "parserOcrPolicy",
                    "ragSearchPolicy",
                ],
                "properties": {
                    "standardVersionIds": {"type": "array", "items": {"type": "string"}},
                    "modelVersion": {"type": "string"},
                    "promptVersion": {"type": "string"},
                    "parserOcrPolicy": {"type": "string"},
                    "ragSearchPolicy": {"type": "string"},
                },
            },
            "ValidationEvaluation": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "evaluationId",
                    "evaluationStatus",
                    "snapshotHash",
                    "snapshotCreatedAt",
                    "datasetSnapshotCount",
                    "reviewSelectionPolicy",
                    "versionSnapshot",
                    "exclusionSummary",
                    "metrics",
                ],
                "properties": {
                    "evaluationId": {"type": "string", "pattern": "^EVAL-[A-Za-z0-9-]+$"},
                    "evaluationStatus": {"$ref": "#/components/schemas/ValidationEvaluationStatus"},
                    "snapshotHash": {"type": "string", "pattern": "^sha256:[a-f0-9]{64}$"},
                    "snapshotCreatedAt": {"type": "string", "format": "date-time"},
                    "datasetSnapshotCount": {"type": "integer", "minimum": 0},
                    "reviewSelectionPolicy": {"$ref": "#/components/schemas/ReviewSelectionPolicy"},
                    "versionSnapshot": {"$ref": "#/components/schemas/ValidationVersionSnapshot"},
                    "exclusionSummary": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/ValidationExclusionSummary"},
                    },
                    "metrics": {
                        "type": "array",
                        "minItems": 4,
                        "maxItems": 4,
                        "items": {"$ref": "#/components/schemas/ValidationMetric"},
                    },
                },
            },
        }
    },
    "paths": {
        "/validation/datasets": {
            "get": {
                "description": "Lists versioned validation datasets "
                "from the PostgreSQL source of truth.",
                "operationId": "listValidationDatasets",
                "parameters": [
                    {"$ref": "#/components/parameters/Page"},
                    {"$ref": "#/components/parameters/Size"},
                ],
                "responses": {
                    "200": {
                        "description": "Scope-authorized validation dataset page.",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ValidationDatasetPage"}
                            }
                        },
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                },
                "tags": ["Validation"],
                "security": [{"BearerAuth": []}],
            },
            "post": {
                "description": "Creates version 1 of a validation "
                "dataset in the PostgreSQL source of "
                "truth.",
                "operationId": "createValidationDataset",
                "requestBody": {
                    "required": True,
                    "content": {
                        "multipart/form-data": {
                            "schema": {
                                "$ref": "#/components/schemas/CreateValidationDatasetRequest"
                            }
                        }
                    },
                },
                "responses": {
                    "201": {
                        "description": "Versioned validation dataset created.",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ValidationDataset"}
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "409": {"$ref": "#/components/responses/Conflict"},
                },
                "tags": ["Validation"],
                "security": [{"BearerAuth": []}],
            },
        },
        "/validation/datasets/{datasetId}/judgments": {
            "post": {
                "description": "Appends "
                "versioned "
                "golden "
                "judgments "
                "without "
                "rewriting "
                "evaluation "
                "snapshots.",
                "operationId": "createValidationJudgments",
                "parameters": [
                    {
                        "in": "path",
                        "name": "datasetId",
                        "required": True,
                        "schema": {"type": "string", "pattern": "^DATASET-[A-Za-z0-9-]+$"},
                    }
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/CreateValidationJudgmentsRequest"
                            }
                        }
                    },
                },
                "responses": {
                    "201": {
                        "description": "Versioned golden judgments created.",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/ValidationJudgmentsCreated"
                                }
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "409": {"$ref": "#/components/responses/Conflict"},
                },
                "tags": ["Validation"],
                "security": [{"BearerAuth": []}],
            }
        },
        "/validation/evaluations": {
            "post": {
                "description": "Creates an immutable provider-free "
                "KPI evaluation from canonical "
                "persisted snapshots.",
                "operationId": "createValidationEvaluation",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/CreateValidationEvaluationRequest"
                            }
                        }
                    },
                },
                "responses": {
                    "201": {
                        "description": "Immutable evaluation and four stored KPI results created.",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ValidationEvaluation"}
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "409": {"$ref": "#/components/responses/Conflict"},
                },
                "tags": ["Validation"],
                "security": [{"BearerAuth": []}],
            }
        },
        "/validation/evaluations/{evaluationId}": {
            "get": {
                "description": "Returns stored KPI "
                "values and the "
                "immutable execution "
                "snapshot provenance.",
                "operationId": "getValidationEvaluation",
                "parameters": [
                    {
                        "in": "path",
                        "name": "evaluationId",
                        "required": True,
                        "schema": {"type": "string", "pattern": "^EVAL-[A-Za-z0-9-]+$"},
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Immutable evaluation snapshot and stored KPI values.",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ValidationEvaluation"}
                            }
                        },
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
                "tags": ["Validation"],
                "security": [{"BearerAuth": []}],
            }
        },
    },
}
