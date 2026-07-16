"""Standards, evidence, and search OpenAPI fragment frozen at milestone M3.

This backend-owned projection is guarded against the governed source contract by tests.
"""

from typing import Any

STANDARDS_OPENAPI: dict[str, Any] = {
    "components": {
        "parameters": {
            "AdvertisementTypeQuery": {
                "in": "query",
                "name": "advertisementType",
                "schema": {"$ref": "#/components/schemas/AdvertisementType"},
            },
            "EvidenceChunkId": {
                "in": "path",
                "name": "evidenceChunkId",
                "required": True,
                "schema": {"pattern": "^ECH-[A-Za-z0-9-]+$", "type": "string"},
            },
            "EvidenceId": {
                "in": "path",
                "name": "evidenceId",
                "required": True,
                "schema": {"pattern": "^EVD-[A-Za-z0-9-]+$", "type": "string"},
            },
            "Keyword": {
                "in": "query",
                "name": "keyword",
                "schema": {"maxLength": 300, "type": "string"},
            },
            "Page": {
                "in": "query",
                "name": "page",
                "schema": {"default": 1, "minimum": 1, "type": "integer"},
            },
            "ProductGroupQuery": {
                "in": "query",
                "name": "productGroup",
                "schema": {"$ref": "#/components/schemas/ProductGroup"},
            },
            "ReindexJobId": {
                "in": "path",
                "name": "jobId",
                "required": True,
                "schema": {"pattern": "^SRJ-[A-Za-z0-9-]+$", "type": "string"},
            },
            "Size": {
                "in": "query",
                "name": "size",
                "schema": {"default": 20, "maximum": 100, "minimum": 1, "type": "integer"},
            },
            "StandardId": {
                "in": "path",
                "name": "standardId",
                "required": True,
                "schema": {"pattern": "^STD-[A-Za-z0-9-]+$", "type": "string"},
            },
            "StandardVersionId": {
                "in": "path",
                "name": "standardVersionId",
                "required": True,
                "schema": {"pattern": "^STDVER-[A-Za-z0-9-]+$", "type": "string"},
            },
        },
        "responses": {
            "BadRequest": {
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}
                },
                "description": "Request validation or file integrity failed.",
            },
            "Conflict": {
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}
                },
                "description": "Duplicate or conflicting request.",
            },
            "Forbidden": {
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}
                },
                "description": "Authenticated caller is outside the "
                "permitted role or resource scope.",
            },
            "NotFound": {
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}
                },
                "description": "Resource not found.",
            },
            "SearchUnavailable": {
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}
                },
                "description": "Qdrant, OpenSearch, or index "
                "consistency is unavailable; no "
                "keyword-only or vector-only "
                "fallback is returned as normal "
                "evidence.",
            },
            "Unauthorized": {
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}
                },
                "description": "Authentication failed without revealing account state.",
            },
        },
        "schemas": {
            "AdvertisementType": {
                "enum": [
                    "BRANCH_FLYER",
                    "NOTICE",
                    "MOBILE_BANNER",
                    "WEB_BANNER",
                    "EVENT_PAGE",
                    "PUSH",
                    "SMS",
                    "ALIMTALK",
                ],
                "type": "string",
            },
            "CreateStandardRequest": {
                "additionalProperties": False,
                "properties": {
                    "advertisementType": {"$ref": "#/components/schemas/AdvertisementType"},
                    "content": {
                        "description": "Directly "
                        "entered "
                        "reference "
                        "body; "
                        "M3 "
                        "does "
                        "not "
                        "parse "
                        "an "
                        "attachment.",
                        "maxLength": 1000000,
                        "minLength": 1,
                        "type": "string",
                    },
                    "effectiveDate": {"format": "date", "type": "string"},
                    "evidenceType": {"$ref": "#/components/schemas/EvidenceType"},
                    "expiredDate": {"format": "date", "type": "string"},
                    "importance": {"$ref": "#/components/schemas/Importance"},
                    "metadata": {
                        "additionalProperties": True,
                        "description": "Evidence-type-required metadata defined by ADR-0050.",
                        "type": "object",
                    },
                    "productGroup": {"$ref": "#/components/schemas/ProductGroup"},
                    "ruleType": {"$ref": "#/components/schemas/RuleType"},
                    "sourceFile": {
                        "description": "Optional "
                        "archival "
                        "original; "
                        "its "
                        "content "
                        "is "
                        "outside "
                        "the "
                        "M3 "
                        "parser "
                        "boundary.",
                        "format": "binary",
                        "type": "string",
                    },
                    "title": {"maxLength": 500, "minLength": 1, "type": "string"},
                },
                "required": ["title", "evidenceType", "ruleType", "metadata", "content"],
                "type": "object",
            },
            "DeactivateStandardRequest": {
                "additionalProperties": False,
                "properties": {"reason": {"maxLength": 2000, "minLength": 1, "type": "string"}},
                "required": ["reason"],
                "type": "object",
            },
            "ErrorResponse": {
                "additionalProperties": False,
                "example": {
                    "code": "FILE_NOT_SUPPORTED",
                    "details": [
                        {
                            "field": "advertisementFile",
                            "reason": "jpg, jpeg, png, pdf, hwp, hwpx 파일만 업로드할 수 있습니다.",
                        }
                    ],
                    "message": "지원하지 않는 파일 형식입니다.",
                    "timestamp": "2026-07-14T06:00:00Z",
                    "traceId": "req-example-000001",
                },
                "properties": {
                    "code": {"minLength": 1, "type": "string"},
                    "details": {
                        "items": {"additionalProperties": True, "type": "object"},
                        "type": "array",
                    },
                    "message": {"minLength": 1, "type": "string"},
                    "timestamp": {"format": "date-time", "type": "string"},
                    "traceId": {"minLength": 1, "type": "string"},
                },
                "required": ["code", "message", "traceId", "timestamp"],
                "type": "object",
            },
            "EvidenceChunk": {
                "additionalProperties": False,
                "properties": {
                    "articleNo": {"type": ["string", "null"]},
                    "chunkNo": {"minimum": 1, "type": "integer"},
                    "chunkText": {"type": "string"},
                    "chunkingPolicyVersion": {"type": "string"},
                    "createdAt": {"format": "date-time", "type": "string"},
                    "embeddingModel": {"type": ["string", "null"]},
                    "evidenceChunkId": {"type": "string"},
                    "evidenceId": {"type": "string"},
                    "opensearchAnalyzerVersion": {"type": ["string", "null"]},
                    "opensearchHighlights": {
                        "additionalProperties": {"items": {"type": "string"}, "type": "array"},
                        "type": "object",
                    },
                    "opensearchIndexErrorCode": {"type": ["string", "null"]},
                    "opensearchIndexStatus": {"$ref": "#/components/schemas/IndexStatus"},
                    "pageNo": {"minimum": 1, "type": ["integer", "null"]},
                    "parserRuleVersion": {"type": ["string", "null"]},
                    "qdrantIndexErrorCode": {"type": ["string", "null"]},
                    "qdrantIndexStatus": {"$ref": "#/components/schemas/IndexStatus"},
                    "searchSchemaVersion": {"type": "string"},
                    "sectionPath": {"type": ["string", "null"]},
                    "sourceSpan": {"additionalProperties": True, "type": ["object", "null"]},
                    "standardId": {"type": "string"},
                    "standardVersionId": {"type": "string"},
                    "structureConfidence": {"maximum": 1, "minimum": 0, "type": ["number", "null"]},
                    "synonymVersion": {"type": ["string", "null"]},
                    "tokenCount": {"minimum": 0, "type": ["integer", "null"]},
                },
                "required": [
                    "evidenceChunkId",
                    "evidenceId",
                    "standardId",
                    "standardVersionId",
                    "chunkNo",
                    "chunkText",
                    "chunkingPolicyVersion",
                    "searchSchemaVersion",
                    "qdrantIndexStatus",
                    "opensearchIndexStatus",
                    "createdAt",
                ],
                "type": "object",
            },
            "EvidenceChunkPage": {
                "additionalProperties": False,
                "properties": {
                    "contents": {
                        "items": {"$ref": "#/components/schemas/EvidenceChunk"},
                        "type": "array",
                    },
                    "page": {"minimum": 1, "type": "integer"},
                    "size": {"minimum": 1, "type": "integer"},
                    "totalElements": {"minimum": 0, "type": "integer"},
                    "totalPages": {"minimum": 0, "type": "integer"},
                },
                "required": ["contents", "page", "size", "totalElements", "totalPages"],
                "type": "object",
            },
            "EvidenceDetail": {
                "additionalProperties": False,
                "properties": {
                    "advertisementType": {
                        "oneOf": [
                            {"$ref": "#/components/schemas/AdvertisementType"},
                            {"type": "null"},
                        ]
                    },
                    "articleNo": {"type": ["string", "null"]},
                    "content": {"type": "string"},
                    "contentSummary": {"type": ["string", "null"]},
                    "effectiveDate": {"format": "date", "type": ["string", "null"]},
                    "evidenceId": {"type": "string"},
                    "evidenceType": {"$ref": "#/components/schemas/EvidenceType"},
                    "expiredDate": {"format": "date", "type": ["string", "null"]},
                    "importance": {
                        "oneOf": [{"$ref": "#/components/schemas/Importance"}, {"type": "null"}]
                    },
                    "isActive": {"type": "boolean"},
                    "productGroup": {
                        "oneOf": [{"$ref": "#/components/schemas/ProductGroup"}, {"type": "null"}]
                    },
                    "ruleType": {"$ref": "#/components/schemas/RuleType"},
                    "standardId": {"type": "string"},
                    "standardVersionId": {"type": "string"},
                    "title": {"type": "string"},
                    "version": {"type": "string"},
                },
                "required": [
                    "evidenceId",
                    "standardId",
                    "standardVersionId",
                    "evidenceType",
                    "title",
                    "content",
                    "ruleType",
                    "version",
                    "isActive",
                ],
                "type": "object",
            },
            "EvidenceSearchResult": {
                "additionalProperties": False,
                "properties": {
                    "advertisementType": {
                        "oneOf": [
                            {"$ref": "#/components/schemas/AdvertisementType"},
                            {"type": "null"},
                        ]
                    },
                    "articleNo": {"type": ["string", "null"]},
                    "contentSummary": {"type": "string"},
                    "effectiveDate": {"format": "date", "type": ["string", "null"]},
                    "evidenceChunkId": {"type": "string"},
                    "evidenceId": {"type": "string"},
                    "evidenceType": {"$ref": "#/components/schemas/EvidenceType"},
                    "highlights": {
                        "additionalProperties": {"items": {"type": "string"}, "type": "array"},
                        "type": "object",
                    },
                    "matchSource": {"$ref": "#/components/schemas/SearchMode"},
                    "productGroup": {
                        "oneOf": [{"$ref": "#/components/schemas/ProductGroup"}, {"type": "null"}]
                    },
                    "rankNo": {"maximum": 20, "minimum": 1, "type": "integer"},
                    "relevanceScore": {"maximum": 1, "minimum": 0, "type": "number"},
                    "ruleType": {"$ref": "#/components/schemas/RuleType"},
                    "standardVersionId": {"type": "string"},
                    "title": {"type": "string"},
                    "version": {"type": "string"},
                },
                "required": [
                    "evidenceId",
                    "evidenceChunkId",
                    "standardVersionId",
                    "evidenceType",
                    "title",
                    "ruleType",
                    "contentSummary",
                    "version",
                    "rankNo",
                    "relevanceScore",
                    "matchSource",
                ],
                "type": "object",
            },
            "EvidenceType": {
                "enum": [
                    "LAW",
                    "REGULATION",
                    "INTERNAL_STANDARD",
                    "GUIDELINE",
                    "MANUAL",
                    "REVIEW_CASE",
                    "TEMPLATE",
                    "PRODUCT_STANDARD",
                ],
                "type": "string",
            },
            "Importance": {"enum": ["HIGH", "MEDIUM", "LOW"], "type": "string"},
            "IndexStatus": {
                "enum": ["PENDING", "INDEXING", "ACTIVE", "FAILED", "EXCLUDED", "DELETED"],
                "type": "string",
            },
            "ProductGroup": {
                "enum": ["DEPOSIT", "SAVINGS", "DEMAND_DEPOSIT", "EVENT"],
                "type": "string",
            },
            "ReindexJobStatus": {
                "enum": ["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELED"],
                "type": "string",
            },
            "ReindexScope": {
                "enum": ["INDEX_ONLY", "CHUNK_AND_INDEX", "KEYWORD_ONLY", "VECTOR_ONLY"],
                "type": "string",
            },
            "ReindexStandardRequest": {
                "additionalProperties": False,
                "properties": {
                    "chunkingPolicyVersion": {"maxLength": 100, "minLength": 1, "type": "string"},
                    "embeddingModel": {
                        "description": "Reproducibility label; M3 makes no provider network call.",
                        "maxLength": 100,
                        "type": ["string", "null"],
                    },
                    "opensearchAnalyzerVersion": {"maxLength": 100, "type": ["string", "null"]},
                    "parserRuleVersion": {"maxLength": 100, "type": ["string", "null"]},
                    "reason": {"maxLength": 2000, "minLength": 1, "type": "string"},
                    "reindexScope": {"$ref": "#/components/schemas/ReindexScope"},
                    "searchSchemaVersion": {"maxLength": 100, "minLength": 1, "type": "string"},
                    "synonymVersion": {"maxLength": 100, "type": ["string", "null"]},
                    "targetIndexes": {
                        "items": {"$ref": "#/components/schemas/SearchBackend"},
                        "minItems": 1,
                        "type": "array",
                        "uniqueItems": True,
                    },
                },
                "required": [
                    "reindexScope",
                    "reason",
                    "chunkingPolicyVersion",
                    "searchSchemaVersion",
                    "targetIndexes",
                ],
                "type": "object",
            },
            "RuleType": {
                "enum": ["REQUIRED", "PROHIBITED", "RECOMMENDED", "REFERENCE"],
                "type": "string",
            },
            "SearchBackend": {"enum": ["QDRANT", "OPENSEARCH"], "type": "string"},
            "SearchMode": {
                "default": "HYBRID",
                "enum": ["KEYWORD", "VECTOR", "HYBRID"],
                "type": "string",
            },
            "StandardCreated": {
                "additionalProperties": False,
                "properties": {
                    "evidenceId": {"type": "string"},
                    "isActive": {"type": "boolean"},
                    "standardId": {"type": "string"},
                    "standardVersionId": {"type": "string"},
                    "version": {"type": "string"},
                },
                "required": [
                    "standardId",
                    "evidenceId",
                    "standardVersionId",
                    "version",
                    "isActive",
                ],
                "type": "object",
            },
            "StandardDetail": {
                "additionalProperties": False,
                "properties": {
                    "advertisementType": {
                        "oneOf": [
                            {"$ref": "#/components/schemas/AdvertisementType"},
                            {"type": "null"},
                        ]
                    },
                    "changeReason": {"type": ["string", "null"]},
                    "content": {"type": "string"},
                    "createdAt": {"format": "date-time", "type": "string"},
                    "createdBy": {"type": "string"},
                    "effectiveDate": {"format": "date", "type": ["string", "null"]},
                    "evidenceId": {"type": "string"},
                    "evidenceType": {"$ref": "#/components/schemas/EvidenceType"},
                    "expiredDate": {"format": "date", "type": ["string", "null"]},
                    "importance": {
                        "oneOf": [{"$ref": "#/components/schemas/Importance"}, {"type": "null"}]
                    },
                    "isActive": {"type": "boolean"},
                    "metadata": {"additionalProperties": True, "type": "object"},
                    "productGroup": {
                        "oneOf": [{"$ref": "#/components/schemas/ProductGroup"}, {"type": "null"}]
                    },
                    "ruleType": {"$ref": "#/components/schemas/RuleType"},
                    "standardId": {"type": "string"},
                    "standardVersionId": {"type": "string"},
                    "title": {"type": "string"},
                    "version": {"type": "string"},
                },
                "required": [
                    "standardId",
                    "evidenceId",
                    "standardVersionId",
                    "version",
                    "title",
                    "evidenceType",
                    "ruleType",
                    "metadata",
                    "content",
                    "isActive",
                    "createdAt",
                    "createdBy",
                ],
                "type": "object",
            },
            "StandardHistoryPage": {
                "additionalProperties": False,
                "properties": {
                    "contents": {
                        "items": {"$ref": "#/components/schemas/StandardDetail"},
                        "type": "array",
                    },
                    "page": {"minimum": 1, "type": "integer"},
                    "size": {"minimum": 1, "type": "integer"},
                    "totalElements": {"minimum": 0, "type": "integer"},
                    "totalPages": {"minimum": 0, "type": "integer"},
                },
                "required": ["contents", "page", "size", "totalElements", "totalPages"],
                "type": "object",
            },
            "StandardPage": {
                "additionalProperties": False,
                "properties": {
                    "contents": {
                        "items": {"$ref": "#/components/schemas/StandardSummary"},
                        "type": "array",
                    },
                    "page": {"minimum": 1, "type": "integer"},
                    "size": {"minimum": 1, "type": "integer"},
                    "totalElements": {"minimum": 0, "type": "integer"},
                    "totalPages": {"minimum": 0, "type": "integer"},
                },
                "required": ["contents", "page", "size", "totalElements", "totalPages"],
                "type": "object",
            },
            "StandardReindexJob": {
                "additionalProperties": False,
                "properties": {
                    "chunkingPolicyVersion": {"type": ["string", "null"]},
                    "completedAt": {"format": "date-time", "type": ["string", "null"]},
                    "createdChunkCount": {"minimum": 0, "type": "integer"},
                    "embeddingModel": {"type": ["string", "null"]},
                    "failedReasonCode": {"type": ["string", "null"]},
                    "failedReasonMessage": {"type": ["string", "null"]},
                    "indexedChunkCount": {"minimum": 0, "type": "integer"},
                    "jobId": {"type": "string"},
                    "jobStatus": {"$ref": "#/components/schemas/ReindexJobStatus"},
                    "opensearchAnalyzerVersion": {"type": ["string", "null"]},
                    "opensearchStatus": {
                        "oneOf": [{"$ref": "#/components/schemas/IndexStatus"}, {"type": "null"}]
                    },
                    "parserRuleVersion": {"type": ["string", "null"]},
                    "qdrantStatus": {
                        "oneOf": [{"$ref": "#/components/schemas/IndexStatus"}, {"type": "null"}]
                    },
                    "reindexScope": {"$ref": "#/components/schemas/ReindexScope"},
                    "requestedAt": {"format": "date-time", "type": "string"},
                    "requestedBy": {"type": "string"},
                    "searchSchemaVersion": {"type": ["string", "null"]},
                    "standardId": {"type": "string"},
                    "standardVersionId": {"type": "string"},
                    "startedAt": {"format": "date-time", "type": ["string", "null"]},
                    "synonymVersion": {"type": ["string", "null"]},
                    "targetIndexes": {
                        "items": {"$ref": "#/components/schemas/SearchBackend"},
                        "minItems": 1,
                        "type": "array",
                        "uniqueItems": True,
                    },
                },
                "required": [
                    "jobId",
                    "standardId",
                    "standardVersionId",
                    "reindexScope",
                    "jobStatus",
                    "targetIndexes",
                    "createdChunkCount",
                    "indexedChunkCount",
                    "requestedBy",
                    "requestedAt",
                ],
                "type": "object",
            },
            "StandardSummary": {
                "additionalProperties": False,
                "properties": {
                    "advertisementType": {
                        "oneOf": [
                            {"$ref": "#/components/schemas/AdvertisementType"},
                            {"type": "null"},
                        ]
                    },
                    "createdAt": {"format": "date-time", "type": "string"},
                    "currentVersion": {"type": "string"},
                    "effectiveDate": {"format": "date", "type": ["string", "null"]},
                    "evidenceType": {"$ref": "#/components/schemas/EvidenceType"},
                    "expiredDate": {"format": "date", "type": ["string", "null"]},
                    "importance": {
                        "oneOf": [{"$ref": "#/components/schemas/Importance"}, {"type": "null"}]
                    },
                    "isActive": {"type": "boolean"},
                    "productGroup": {
                        "oneOf": [{"$ref": "#/components/schemas/ProductGroup"}, {"type": "null"}]
                    },
                    "ruleType": {"$ref": "#/components/schemas/RuleType"},
                    "standardId": {"type": "string"},
                    "title": {"type": "string"},
                },
                "required": [
                    "standardId",
                    "title",
                    "evidenceType",
                    "ruleType",
                    "currentVersion",
                    "isActive",
                    "createdAt",
                ],
                "type": "object",
            },
            "UpdateStandardRequest": {
                "additionalProperties": False,
                "properties": {
                    "changeReason": {"maxLength": 2000, "minLength": 1, "type": "string"},
                    "content": {"maxLength": 1000000, "minLength": 1, "type": "string"},
                    "effectiveDate": {"format": "date", "type": ["string", "null"]},
                    "expiredDate": {"format": "date", "type": ["string", "null"]},
                    "metadata": {"additionalProperties": True, "type": "object"},
                    "title": {"maxLength": 500, "minLength": 1, "type": "string"},
                },
                "required": ["content", "metadata", "changeReason"],
                "type": "object",
            },
        },
    },
    "paths": {
        "/evidence-chunks/{evidenceChunkId}": {
            "get": {
                "description": "Administrator-only redacted chunk detail.",
                "operationId": "getEvidenceChunk",
                "parameters": [{"$ref": "#/components/parameters/EvidenceChunkId"}],
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/EvidenceChunk"}
                            }
                        },
                        "description": "Redacted evidence chunk detail.",
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
                "tags": ["Search Operations"],
            }
        },
        "/evidences/search": {
            "get": {
                "description": "Searches only active, basis-date-valid "
                "chunks. Hybrid mode requires both Qdrant "
                "and OpenSearch; a backend failure is "
                "never converted to a keyword-only or "
                "vector-only success.",
                "operationId": "searchEvidences",
                "parameters": [
                    {
                        "in": "query",
                        "name": "keyword",
                        "required": True,
                        "schema": {"maxLength": 300, "minLength": 1, "type": "string"},
                    },
                    {
                        "in": "query",
                        "name": "evidenceType",
                        "schema": {"$ref": "#/components/schemas/EvidenceType"},
                    },
                    {"$ref": "#/components/parameters/ProductGroupQuery"},
                    {"$ref": "#/components/parameters/AdvertisementTypeQuery"},
                    {
                        "in": "query",
                        "name": "ruleType",
                        "schema": {"$ref": "#/components/schemas/RuleType"},
                    },
                    {
                        "in": "query",
                        "name": "effectiveDate",
                        "schema": {"format": "date", "type": "string"},
                    },
                    {
                        "in": "query",
                        "name": "searchMode",
                        "schema": {"$ref": "#/components/schemas/SearchMode"},
                    },
                    {
                        "in": "query",
                        "name": "limit",
                        "schema": {"default": 20, "maximum": 20, "minimum": 1, "type": "integer"},
                    },
                ],
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "items": {"$ref": "#/components/schemas/EvidenceSearchResult"},
                                    "maxItems": 20,
                                    "type": "array",
                                }
                            }
                        },
                        "description": "Deterministically ranked evidence chunks.",
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "503": {"$ref": "#/components/responses/SearchUnavailable"},
                },
                "tags": ["Evidence"],
            }
        },
        "/evidences/{evidenceId}": {
            "get": {
                "description": "Returns evidence bound to one immutable standard version.",
                "operationId": "getEvidence",
                "parameters": [{"$ref": "#/components/parameters/EvidenceId"}],
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/EvidenceDetail"}
                            }
                        },
                        "description": "Evidence "
                        "detail for "
                        "the selected "
                        "immutable "
                        "standard "
                        "version.",
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
                "tags": ["Evidence"],
            }
        },
        "/evidences/{evidenceId}/chunks": {
            "get": {
                "description": "Administrator-only chunk "
                "inspection without internal "
                "index identifiers.",
                "operationId": "listEvidenceChunks",
                "parameters": [
                    {"$ref": "#/components/parameters/EvidenceId"},
                    {"$ref": "#/components/parameters/Page"},
                    {"$ref": "#/components/parameters/Size"},
                ],
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/EvidenceChunkPage"}
                            }
                        },
                        "description": "Redacted evidence chunk page.",
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
                "tags": ["Search Operations"],
            }
        },
        "/standard-reindex-jobs/{jobId}": {
            "get": {
                "description": "Returns independent Qdrant and OpenSearch processing states.",
                "operationId": "getStandardReindexJob",
                "parameters": [{"$ref": "#/components/parameters/ReindexJobId"}],
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/StandardReindexJob"}
                            }
                        },
                        "description": "Reindex status including independent backend results.",
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "503": {"$ref": "#/components/responses/SearchUnavailable"},
                },
                "tags": ["Search Operations"],
            }
        },
        "/standards": {
            "get": {
                "description": "Lists standards for standard managers and system administrators.",
                "operationId": "listStandards",
                "parameters": [
                    {"$ref": "#/components/parameters/Keyword"},
                    {
                        "in": "query",
                        "name": "evidenceType",
                        "schema": {"$ref": "#/components/schemas/EvidenceType"},
                    },
                    {"$ref": "#/components/parameters/ProductGroupQuery"},
                    {"$ref": "#/components/parameters/AdvertisementTypeQuery"},
                    {
                        "in": "query",
                        "name": "ruleType",
                        "schema": {"$ref": "#/components/schemas/RuleType"},
                    },
                    {
                        "in": "query",
                        "name": "activeOnly",
                        "schema": {"default": True, "type": "boolean"},
                    },
                    {"$ref": "#/components/parameters/Page"},
                    {"$ref": "#/components/parameters/Size"},
                ],
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/StandardPage"}
                            }
                        },
                        "description": "Scope-authorized standards page.",
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                },
                "tags": ["Standards"],
            },
            "post": {
                "description": "Creates a standard and immutable version 1.0 "
                "from directly entered text.",
                "operationId": "createStandard",
                "requestBody": {
                    "content": {
                        "multipart/form-data": {
                            "schema": {"$ref": "#/components/schemas/CreateStandardRequest"}
                        }
                    },
                    "required": True,
                },
                "responses": {
                    "201": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/StandardCreated"}
                            }
                        },
                        "description": "Standard, immutable version, and evidence created.",
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "409": {"$ref": "#/components/responses/Conflict"},
                },
                "tags": ["Standards"],
            },
        },
        "/standards/{standardId}": {
            "get": {
                "description": "Returns the standard master with its current immutable version.",
                "operationId": "getStandard",
                "parameters": [{"$ref": "#/components/parameters/StandardId"}],
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/StandardDetail"}
                            }
                        },
                        "description": "Current standard master and immutable version.",
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
                "tags": ["Standards"],
            },
            "patch": {
                "description": "Appends a new immutable standard "
                "version; it never overwrites "
                "history.",
                "operationId": "updateStandard",
                "parameters": [{"$ref": "#/components/parameters/StandardId"}],
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/UpdateStandardRequest"}
                        }
                    },
                    "required": True,
                },
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/StandardDetail"}
                            }
                        },
                        "description": "Newly created immutable version.",
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "409": {"$ref": "#/components/responses/Conflict"},
                },
                "tags": ["Standards"],
            },
        },
        "/standards/{standardId}/deactivate": {
            "patch": {
                "description": "Soft-deactivates a standard and excludes its chunks from search.",
                "operationId": "deactivateStandard",
                "parameters": [{"$ref": "#/components/parameters/StandardId"}],
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/DeactivateStandardRequest"}
                        }
                    },
                    "required": True,
                },
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/StandardDetail"}
                            }
                        },
                        "description": "Deactivated standard.",
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
                "tags": ["Standards"],
            }
        },
        "/standards/{standardId}/histories": {
            "get": {
                "description": "Lists immutable versions in descending effective/version order.",
                "operationId": "listStandardHistories",
                "parameters": [
                    {"$ref": "#/components/parameters/StandardId"},
                    {"$ref": "#/components/parameters/Page"},
                    {"$ref": "#/components/parameters/Size"},
                ],
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/StandardHistoryPage"}
                            }
                        },
                        "description": "Immutable version history.",
                    },
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                },
                "tags": ["Standards"],
            }
        },
        "/standards/{standardId}/versions/{standardVersionId}/reindex": {
            "post": {
                "description": "Queues "
                "an "
                "idempotent "
                "deterministic-ID "
                "reindex "
                "for "
                "directly "
                "entered "
                "text.",
                "operationId": "requestStandardReindex",
                "parameters": [
                    {"$ref": "#/components/parameters/StandardId"},
                    {"$ref": "#/components/parameters/StandardVersionId"},
                ],
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ReindexStandardRequest"}
                        }
                    },
                    "required": True,
                },
                "responses": {
                    "202": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/StandardReindexJob"}
                            }
                        },
                        "description": "Reindex job accepted.",
                    },
                    "400": {"$ref": "#/components/responses/BadRequest"},
                    "401": {"$ref": "#/components/responses/Unauthorized"},
                    "403": {"$ref": "#/components/responses/Forbidden"},
                    "404": {"$ref": "#/components/responses/NotFound"},
                    "409": {"$ref": "#/components/responses/Conflict"},
                    "503": {"$ref": "#/components/responses/SearchUnavailable"},
                },
                "tags": ["Search Operations"],
            }
        },
    },
}
