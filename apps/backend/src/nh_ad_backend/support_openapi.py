"""Frozen M6 support-output OpenAPI fragments.

The fragment is deliberately provider-independent: it defines the governed
boundary only, while deterministic services implement it behind this contract.
"""

from typing import Any


def _json_response(schema: str, *errors: str) -> dict[str, Any]:
    responses: dict[str, Any] = {
        "200": {
            "description": "Scoped support output returned.",
            "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{schema}"}}},
        }
    }
    for status, response in (
        ("400", "BadRequest"),
        ("401", "Unauthorized"),
        ("403", "Forbidden"),
        ("404", "NotFound"),
        ("409", "Conflict"),
        ("503", "SearchUnavailable"),
    ):
        if status in errors:
            responses[status] = {"$ref": f"#/components/responses/{response}"}
    return responses


def _json_array_response(schema: str, *errors: str) -> dict[str, Any]:
    responses = _json_response(schema, *errors)
    responses["200"]["content"]["application/json"]["schema"] = {
        "type": "array",
        "items": {"$ref": f"#/components/schemas/{schema}"},
    }
    return responses


def _body(schema: str) -> dict[str, Any]:
    return {
        "required": True,
        "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{schema}"}}},
    }


SUPPORT_OPENAPI: dict[str, Any] = {
    "components": {
        "parameters": {
            "SuggestionId": {
                "in": "path",
                "name": "suggestionId",
                "required": True,
                "schema": {"type": "string", "pattern": "^SUG-[A-Za-z0-9-]+$"},
            },
            "DraftId": {
                "in": "path",
                "name": "draftId",
                "required": True,
                "schema": {"type": "string", "pattern": "^DRAFT-[A-Za-z0-9-]+$"},
            },
            "ReportId": {
                "in": "path",
                "name": "reportId",
                "required": True,
                "schema": {"type": "string", "pattern": "^RPT-[A-Za-z0-9-]+$"},
            },
            "ComparisonId": {
                "in": "path",
                "name": "comparisonId",
                "required": True,
                "schema": {"type": "string", "pattern": "^CMP-[A-Za-z0-9-]+$"},
            },
        },
        "schemas": {
            "SuggestionDecisionStatus": {
                "type": "string",
                "enum": ["PENDING", "ACCEPTED", "REJECTED", "MODIFIED_AND_USED"],
            },
            "ReportFormat": {"type": "string", "enum": ["HWPX", "PDF"]},
            "ReportStatus": {"type": "string", "enum": ["CREATED", "FAILED"]},
            "ResolutionStatus": {
                "type": "string",
                "enum": ["RESOLVED", "UNRESOLVED", "NEW_ISSUE", "CHECK_REQUIRED"],
            },
            "Suggestion": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "suggestionId",
                    "reviewItemId",
                    "originalText",
                    "suggestedText",
                    "decisionStatus",
                ],
                "properties": {
                    "suggestionId": {"type": "string"},
                    "reviewItemId": {"type": "string"},
                    "originalText": {"type": "string"},
                    "suggestedText": {"type": "string"},
                    "suggestionReason": {"type": ["string", "null"]},
                    "evidenceIds": {"type": "array", "items": {"type": "string"}},
                    "decisionStatus": {"$ref": "#/components/schemas/SuggestionDecisionStatus"},
                },
            },
            "SuggestionDecisionRequest": {
                "type": "object",
                "additionalProperties": False,
                "required": ["decisionStatus"],
                "properties": {
                    "decisionStatus": {
                        "type": "string",
                        "enum": ["ACCEPTED", "REJECTED", "MODIFIED_AND_USED"],
                    },
                    "finalText": {"type": ["string", "null"]},
                    "comment": {"type": ["string", "null"]},
                },
            },
            "SuggestionDecision": {
                "type": "object",
                "additionalProperties": False,
                "required": ["suggestionId", "decisionStatus", "finalText", "updatedAt"],
                "properties": {
                    "suggestionId": {"type": "string"},
                    "decisionStatus": {"$ref": "#/components/schemas/SuggestionDecisionStatus"},
                    "finalText": {"type": ["string", "null"]},
                    "updatedAt": {"type": "string", "format": "date-time"},
                },
            },
            "QaQuestionRequest": {
                "type": "object",
                "additionalProperties": False,
                "required": ["question"],
                "properties": {
                    "question": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "productGroup": {"type": ["string", "null"]},
                    "advertisementType": {"type": ["string", "null"]},
                    "standardEffectiveDate": {"type": ["string", "null"], "format": "date"},
                },
            },
            "QaEvidence": {
                "type": "object",
                "additionalProperties": False,
                "required": ["evidenceId", "standardVersionId", "title", "matchedText"],
                "properties": {
                    "evidenceId": {"type": "string"},
                    "standardVersionId": {"type": "string"},
                    "title": {"type": "string"},
                    "articleNo": {"type": ["string", "null"]},
                    "matchedText": {"type": "string"},
                },
            },
            "QaAnswer": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "qaId",
                    "answerSummary",
                    "answerDetail",
                    "evidences",
                    "suggestedPhrases",
                    "needsHumanReview",
                ],
                "properties": {
                    "qaId": {"type": "string"},
                    "answerSummary": {"type": "string"},
                    "answerDetail": {"type": "string"},
                    "evidences": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/QaEvidence"},
                    },
                    "suggestedPhrases": {"type": "array", "items": {"type": "string"}},
                    "needsHumanReview": {"type": "boolean"},
                },
            },
            "OpinionDraftRequest": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "includeReviewItemIds": {"type": "array", "items": {"type": "string"}},
                    "templateType": {"type": "string"},
                    "additionalInstruction": {"type": ["string", "null"]},
                },
            },
            "OpinionDraftUpdateRequest": {
                "type": "object",
                "additionalProperties": False,
                "required": ["finalContent"],
                "properties": {"finalContent": {"type": "string", "minLength": 1}},
            },
            "OpinionDraft": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "draftId",
                    "reviewId",
                    "draftContent",
                    "includedReviewItemIds",
                    "createdAt",
                ],
                "properties": {
                    "draftId": {"type": "string"},
                    "reviewId": {"type": "string"},
                    "draftContent": {"type": "string"},
                    "finalContent": {"type": ["string", "null"]},
                    "includedReviewItemIds": {"type": "array", "items": {"type": "string"}},
                    "createdAt": {"type": "string", "format": "date-time"},
                    "updatedAt": {"type": ["string", "null"], "format": "date-time"},
                },
            },
            "ReportRequest": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "reportType": {"type": "string", "enum": ["FULL", "SELECTED"]},
                    "format": {"$ref": "#/components/schemas/ReportFormat"},
                    "includeAnnotations": {"type": "boolean"},
                    "includeSuggestions": {"type": "boolean"},
                    "includeOpinionDraft": {"type": "boolean"},
                    "includeEvidenceDetails": {"type": "boolean"},
                },
            },
            "Report": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "reportId",
                    "reviewId",
                    "sourceReportId",
                    "reportType",
                    "format",
                    "reportStatus",
                    "snapshotHash",
                    "snapshotVersion",
                    "createdAt",
                ],
                "properties": {
                    "reportId": {"type": "string"},
                    "reviewId": {"type": "string"},
                    "sourceReportId": {"type": ["string", "null"]},
                    "reportType": {"type": "string"},
                    "format": {"$ref": "#/components/schemas/ReportFormat"},
                    "reportStatus": {"$ref": "#/components/schemas/ReportStatus"},
                    "snapshotHash": {"type": "string", "pattern": "^sha256:[a-f0-9]{64}$"},
                    "snapshotVersion": {"type": "string"},
                    "rendererVersion": {"type": ["string", "null"]},
                    "converterVersion": {"type": ["string", "null"]},
                    "downloadUrl": {"type": ["string", "null"]},
                    "createdAt": {"type": "string", "format": "date-time"},
                },
            },
            "ComparisonRequest": {
                "type": "object",
                "additionalProperties": False,
                "required": ["baseReviewId", "revisionId"],
                "properties": {
                    "baseReviewId": {"type": "string"},
                    "revisionId": {"type": "string"},
                    "compareTypes": {"type": "array", "items": {"type": "string"}},
                },
            },
            "AdvertisementRevisionRequest": {
                "type": "object",
                "additionalProperties": False,
                "required": ["revisedAdvertisementFile"],
                "properties": {
                    "revisionMemo": {"type": "string", "maxLength": 2000},
                    "revisedAdvertisementFile": {"type": "string", "format": "binary"},
                },
            },
            "AdvertisementRevision": {
                "type": "object",
                "additionalProperties": False,
                "required": ["advertisementId", "revisionId", "reviewStatus"],
                "properties": {
                    "advertisementId": {
                        "type": "string",
                        "pattern": "^ADV-[A-Za-z0-9-]+$",
                    },
                    "revisionId": {
                        "type": "string",
                        "pattern": "^REVISION-[A-Za-z0-9-]+$",
                    },
                    "reviewStatus": {"type": "string", "const": "REVISED"},
                },
            },
            "ComparisonItem": {
                "type": "object",
                "additionalProperties": False,
                "required": ["resolutionStatus"],
                "properties": {
                    "reviewItemId": {"type": ["string", "null"]},
                    "originalText": {"type": ["string", "null"]},
                    "revisedText": {"type": ["string", "null"]},
                    "resolutionStatus": {"$ref": "#/components/schemas/ResolutionStatus"},
                    "comment": {"type": ["string", "null"]},
                    "reanalysisReviewId": {"type": ["string", "null"]},
                },
            },
            "Comparison": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "comparisonId",
                    "advertisementId",
                    "comparisonStatus",
                    "resolvedIssueCount",
                    "unresolvedIssueCount",
                    "newIssueCount",
                ],
                "properties": {
                    "comparisonId": {"type": "string"},
                    "advertisementId": {"type": "string"},
                    "comparisonStatus": {"type": "string"},
                    "resolvedIssueCount": {"type": "integer", "minimum": 0},
                    "unresolvedIssueCount": {"type": "integer", "minimum": 0},
                    "newIssueCount": {"type": "integer", "minimum": 0},
                    "items": {
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/ComparisonItem"},
                    },
                },
            },
        },
    },
    "paths": {
        "/reviews/{reviewId}/suggestions": {
            "get": {
                "operationId": "listReviewSuggestions",
                "parameters": [{"$ref": "#/components/parameters/ReviewId"}],
                "responses": _json_array_response("Suggestion", "400", "401", "403", "404"),
            }
        },
        "/suggestions/{suggestionId}/decision": {
            "patch": {
                "operationId": "recordSuggestionDecision",
                "parameters": [{"$ref": "#/components/parameters/SuggestionId"}],
                "requestBody": _body("SuggestionDecisionRequest"),
                "responses": _json_response("SuggestionDecision", "400", "401", "403", "404"),
            }
        },
        "/qa/questions": {
            "post": {
                "operationId": "askComplianceQuestion",
                "requestBody": _body("QaQuestionRequest"),
                "responses": _json_response("QaAnswer", "400", "401", "403", "503"),
            },
            "get": {
                "operationId": "listComplianceQuestions",
                "responses": _json_response("QaAnswer", "401", "403"),
            },
        },
        "/reviews/{reviewId}/opinion-drafts": {
            "post": {
                "operationId": "createOpinionDraft",
                "parameters": [{"$ref": "#/components/parameters/ReviewId"}],
                "requestBody": _body("OpinionDraftRequest"),
                "responses": _json_response("OpinionDraft", "400", "401", "403", "404"),
            },
            "get": {
                "operationId": "listOpinionDrafts",
                "parameters": [{"$ref": "#/components/parameters/ReviewId"}],
                "responses": _json_array_response("OpinionDraft", "401", "403", "404"),
            },
        },
        "/opinion-drafts/{draftId}": {
            "patch": {
                "operationId": "updateOpinionDraft",
                "parameters": [{"$ref": "#/components/parameters/DraftId"}],
                "requestBody": _body("OpinionDraftUpdateRequest"),
                "responses": _json_response("OpinionDraft", "400", "401", "403", "404"),
            }
        },
        "/reviews/{reviewId}/reports": {
            "post": {
                "operationId": "createReviewReport",
                "parameters": [{"$ref": "#/components/parameters/ReviewId"}],
                "requestBody": _body("ReportRequest"),
                "responses": _json_response("Report", "400", "401", "403", "404", "409"),
            }
        },
        "/reports/{reportId}": {
            "get": {
                "operationId": "getReviewReport",
                "parameters": [{"$ref": "#/components/parameters/ReportId"}],
                "responses": _json_response("Report", "401", "403", "404"),
            }
        },
        "/reports/{reportId}/download": {
            "get": {
                "operationId": "downloadReviewReport",
                "parameters": [{"$ref": "#/components/parameters/ReportId"}],
                "responses": {
                    "200": {
                        "description": "Authorized immutable report snapshot.",
                        "content": {
                            "application/octet-stream": {
                                "schema": {"type": "string", "format": "binary"}
                            }
                        },
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
            }
        },
        "/advertisements/{advertisementId}/comparisons": {
            "post": {
                "operationId": "createAdvertisementComparison",
                "parameters": [{"$ref": "#/components/parameters/AdvertisementId"}],
                "requestBody": _body("ComparisonRequest"),
                "responses": _json_response("Comparison", "400", "401", "403", "404"),
            }
        },
        "/advertisements/{advertisementId}/revisions": {
            "post": {
                "operationId": "createAdvertisementRevision",
                "parameters": [{"$ref": "#/components/parameters/AdvertisementId"}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "multipart/form-data": {
                            "schema": {"$ref": "#/components/schemas/AdvertisementRevisionRequest"}
                        }
                    },
                },
                "responses": {
                    "201": {
                        "description": "Stored advertisement revision registered.",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/AdvertisementRevision"}
                            }
                        },
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "409": {"$ref": "#/components/responses/Conflict"},
                    "413": {
                        "description": "Request entity too large.",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                            }
                        },
                    },
                    "415": {
                        "description": "Unsupported media type.",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                            }
                        },
                    },
                },
            }
        },
        "/comparisons/{comparisonId}": {
            "get": {
                "operationId": "getAdvertisementComparison",
                "parameters": [{"$ref": "#/components/parameters/ComparisonId"}],
                "responses": _json_response("Comparison", "401", "403", "404"),
            }
        },
    },
}
