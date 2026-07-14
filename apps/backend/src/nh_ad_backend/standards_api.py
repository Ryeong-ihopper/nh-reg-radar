"""FastAPI routes implementing the frozen M3 Standards/Search contract."""

import json
import math
from collections.abc import Callable
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from nh_ad_backend.domain import CurrentUser
from nh_ad_backend.multipart import MultipartError, parse_multipart
from nh_ad_backend.standards import (
    EvidenceChunk,
    ReindexJob,
    Standard,
    StandardService,
    StandardVersion,
)


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class UpdateStandardRequest(RequestModel):
    title: str | None = Field(None, min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=1_000_000)
    effective_date: date | None = Field(None, alias="effectiveDate")
    expired_date: date | None = Field(None, alias="expiredDate")
    metadata: dict[str, object]
    change_reason: str = Field(alias="changeReason", min_length=1, max_length=2000)


class DeactivateStandardRequest(RequestModel):
    reason: str = Field(min_length=1, max_length=2000)


class ReindexStandardRequest(RequestModel):
    reindex_scope: str = Field(alias="reindexScope")
    reason: str = Field(min_length=1, max_length=2000)
    parser_rule_version: str | None = Field(None, alias="parserRuleVersion", max_length=100)
    chunking_policy_version: str = Field(
        alias="chunkingPolicyVersion", min_length=1, max_length=100
    )
    embedding_model: str | None = Field(None, alias="embeddingModel", max_length=100)
    search_schema_version: str = Field(alias="searchSchemaVersion", min_length=1, max_length=100)
    opensearch_analyzer_version: str | None = Field(
        None, alias="opensearchAnalyzerVersion", max_length=100
    )
    synonym_version: str | None = Field(None, alias="synonymVersion", max_length=100)
    target_indexes: list[str] = Field(alias="targetIndexes", min_length=1)


def install_standard_routes(
    router: APIRouter,
    service: StandardService,
    actor_dependency: Callable[..., object],
) -> None:
    Actor = Annotated[CurrentUser, Depends(actor_dependency)]

    @router.get("/standards", operation_id="listStandards")
    async def list_standards(
        request: Request,
        current: Actor,
        keyword: Annotated[str | None, Query(max_length=300)] = None,
        evidence_type: Annotated[str | None, Query(alias="evidenceType")] = None,
        product_group: Annotated[str | None, Query(alias="productGroup")] = None,
        advertisement_type: Annotated[str | None, Query(alias="advertisementType")] = None,
        rule_type: Annotated[str | None, Query(alias="ruleType")] = None,
        active_only: Annotated[bool, Query(alias="activeOnly")] = True,
        page: Annotated[int, Query(ge=1)] = 1,
        size: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> dict[str, object]:
        values = service.list_standards(
            current,
            keyword=keyword,
            evidence_type=evidence_type,
            product_group=product_group,
            advertisement_type=advertisement_type,
            rule_type=rule_type,
            active_only=active_only,
            trace_id=request.state.trace_id,
        )
        contents = values[(page - 1) * size : page * size]
        return {
            "contents": [_standard_summary(value) for value in contents],
            "page": page,
            "size": size,
            "totalElements": len(values),
            "totalPages": math.ceil(len(values) / size),
        }

    @router.post("/standards", status_code=201, operation_id="createStandard")
    async def create_standard(request: Request, current: Actor) -> dict[str, object]:
        try:
            form = await parse_multipart(request)
            metadata = json.loads(form.fields.get("metadata", "{}"))
        except (MultipartError, json.JSONDecodeError) as exc:
            raise _bad_request("metadata 형식을 확인해 주세요.") from exc
        if not isinstance(metadata, dict):
            raise _bad_request("metadata 형식을 확인해 주세요.")
        created = service.create(
            current,
            title=form.fields.get("title", ""),
            evidence_type=form.fields.get("evidenceType", ""),
            product_group=form.fields.get("productGroup"),
            advertisement_type=form.fields.get("advertisementType"),
            rule_type=form.fields.get("ruleType", ""),
            importance=form.fields.get("importance", "MEDIUM"),
            effective_date=_form_date(form.fields.get("effectiveDate")),
            expired_date=_form_date(form.fields.get("expiredDate")),
            metadata=metadata,
            content=form.fields.get("content", ""),
            trace_id=request.state.trace_id,
        )
        return {
            "standardId": created.standard_id,
            "evidenceId": created.evidence_id,
            "standardVersionId": created.standard_version_id,
            "version": created.version,
            "isActive": created.is_active,
        }

    @router.get("/standards/{standardId}", operation_id="getStandard")
    async def get_standard(
        standard_id: Annotated[str, Path(alias="standardId")],
        request: Request,
        current: Actor,
    ) -> dict[str, object]:
        standard, version = service.manager_detail(
            current, standard_id, trace_id=request.state.trace_id
        )
        return _standard_detail(standard, version)

    @router.patch("/standards/{standardId}", operation_id="updateStandard")
    async def update_standard(
        standard_id: Annotated[str, Path(alias="standardId")],
        payload: UpdateStandardRequest,
        request: Request,
        current: Actor,
    ) -> dict[str, object]:
        standard, _old = service.manager_detail(
            current, standard_id, trace_id=request.state.trace_id
        )
        created = service.update(
            current,
            standard_id,
            title=payload.title or standard.title,
            content=payload.content,
            effective_date=payload.effective_date,
            expired_date=payload.expired_date,
            metadata=payload.metadata,
            change_reason=payload.change_reason,
            trace_id=request.state.trace_id,
        )
        standard, version = service.detail(created.standard_id)
        return _standard_detail(standard, version)

    @router.patch("/standards/{standardId}/deactivate", operation_id="deactivateStandard")
    async def deactivate_standard(
        standard_id: Annotated[str, Path(alias="standardId")],
        payload: DeactivateStandardRequest,
        request: Request,
        current: Actor,
    ) -> dict[str, object]:
        service.deactivate(
            current, standard_id, reason=payload.reason, trace_id=request.state.trace_id
        )
        standard, version = service.detail(standard_id)
        return _standard_detail(standard, version)

    @router.get("/standards/{standardId}/histories", operation_id="listStandardHistories")
    async def list_histories(
        standard_id: Annotated[str, Path(alias="standardId")],
        request: Request,
        current: Actor,
        page: Annotated[int, Query(ge=1)] = 1,
        size: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> dict[str, object]:
        standard, _current = service.manager_detail(
            current, standard_id, trace_id=request.state.trace_id
        )
        versions = service.manager_histories(current, standard_id, trace_id=request.state.trace_id)
        contents = versions[(page - 1) * size : page * size]
        return {
            "contents": [_standard_detail(standard, version) for version in contents],
            "page": page,
            "size": size,
            "totalElements": len(versions),
            "totalPages": math.ceil(len(versions) / size),
        }

    @router.get("/evidences/search", operation_id="searchEvidences")
    async def search_evidences(
        _request: Request,
        _current: Actor,
        keyword: Annotated[str, Query(min_length=1, max_length=300)],
        evidence_type: Annotated[str | None, Query(alias="evidenceType")] = None,
        product_group: Annotated[str | None, Query(alias="productGroup")] = None,
        advertisement_type: Annotated[str | None, Query(alias="advertisementType")] = None,
        rule_type: Annotated[str | None, Query(alias="ruleType")] = None,
        effective_date: Annotated[date | None, Query(alias="effectiveDate")] = None,
        search_mode: Annotated[str, Query(alias="searchMode")] = "HYBRID",
        limit: Annotated[int, Query(ge=1, le=20)] = 20,
    ) -> list[dict[str, object]]:
        filters = {
            key: value
            for key, value in {
                "evidence_type": evidence_type,
                "product_group": product_group,
                "advertisement_type": advertisement_type,
                "rule_type": rule_type,
            }.items()
            if value is not None
        }
        hits = service.search(
            keyword,
            mode=search_mode,  # type: ignore[arg-type]
            limit=limit,
            effective_on=effective_date,
            filters=filters,
        )
        return [
            {
                "evidenceId": hit.document.evidence_id,
                "evidenceChunkId": hit.document.evidence_chunk_id,
                "standardVersionId": hit.document.standard_version_id,
                "evidenceType": hit.document.evidence_type,
                "title": hit.document.title,
                "articleNo": hit.document.article_no,
                "ruleType": hit.document.rule_type,
                "productGroup": hit.document.product_group,
                "advertisementType": hit.document.advertisement_type,
                "contentSummary": hit.document.chunk_text[:500],
                "effectiveDate": hit.document.effective_date,
                "version": hit.document.version,
                "rankNo": hit.rank_no,
                "relevanceScore": hit.relevance_score,
                "matchSource": hit.match_source,
                "highlights": hit.highlights,
            }
            for hit in hits
        ]

    @router.get("/evidences/{evidenceId}", operation_id="getEvidence")
    async def get_evidence(
        evidence_id: Annotated[str, Path(alias="evidenceId")],
        _request: Request,
        _current: Actor,
    ) -> dict[str, object]:
        standard, version = service.evidence(evidence_id)
        return _evidence_detail(standard, version)

    @router.post(
        "/standards/{standardId}/versions/{standardVersionId}/reindex",
        status_code=202,
        operation_id="requestStandardReindex",
    )
    async def request_reindex(
        standard_id: Annotated[str, Path(alias="standardId")],
        standard_version_id: Annotated[str, Path(alias="standardVersionId")],
        payload: ReindexStandardRequest,
        request: Request,
        current: Actor,
    ) -> dict[str, object]:
        job = service.reindex(
            current,
            standard_id,
            standard_version_id,
            reindex_scope=payload.reindex_scope,
            reason=payload.reason,
            embedding_model=payload.embedding_model or "fixed-fixture-v1",
            chunking_policy_version=payload.chunking_policy_version,
            search_schema_version=payload.search_schema_version,
            opensearch_analyzer_version=payload.opensearch_analyzer_version or "ko-v1",
            synonym_version=payload.synonym_version or "synonym-v1",
            parser_rule_version=payload.parser_rule_version or "direct-text-v1",
            trace_id=request.state.trace_id,
        )
        return _job(job)

    @router.get("/standard-reindex-jobs/{jobId}", operation_id="getStandardReindexJob")
    async def get_reindex_job(
        job_id: Annotated[str, Path(alias="jobId")],
        request: Request,
        current: Actor,
    ) -> dict[str, object]:
        return _job(service.manager_reindex_job(current, job_id, trace_id=request.state.trace_id))

    @router.get("/evidences/{evidenceId}/chunks", operation_id="listEvidenceChunks")
    async def list_chunks(
        evidence_id: Annotated[str, Path(alias="evidenceId")],
        request: Request,
        current: Actor,
        page: Annotated[int, Query(ge=1)] = 1,
        size: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> dict[str, object]:
        chunks = service.manager_chunks(current, evidence_id, trace_id=request.state.trace_id)
        contents = chunks[(page - 1) * size : page * size]
        return {
            "contents": [_chunk(chunk) for chunk in contents],
            "page": page,
            "size": size,
            "totalElements": len(chunks),
            "totalPages": math.ceil(len(chunks) / size),
        }

    @router.get("/evidence-chunks/{evidenceChunkId}", operation_id="getEvidenceChunk")
    async def get_chunk(
        evidence_chunk_id: Annotated[str, Path(alias="evidenceChunkId")],
        request: Request,
        current: Actor,
    ) -> dict[str, object]:
        return _chunk(
            service.manager_chunk(current, evidence_chunk_id, trace_id=request.state.trace_id)
        )


def _bad_request(message: str) -> Exception:
    from nh_ad_backend.standards import StandardsError

    return StandardsError(400, "BAD_REQUEST", message)


def _form_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise _bad_request("날짜 형식을 확인해 주세요.") from exc


def _standard_summary(standard: Standard) -> dict[str, object]:
    return {
        "standardId": standard.standard_id,
        "title": standard.title,
        "evidenceType": standard.evidence_type,
        "productGroup": standard.product_group,
        "advertisementType": standard.advertisement_type,
        "ruleType": standard.rule_type,
        "importance": standard.importance,
        "effectiveDate": standard.effective_date,
        "expiredDate": standard.expired_date,
        "currentVersion": standard.current_version,
        "isActive": standard.is_active,
        "createdAt": standard.created_at,
    }


def _standard_detail(standard: Standard, version: StandardVersion) -> dict[str, object]:
    return {
        "standardId": standard.standard_id,
        "evidenceId": version.evidence_id,
        "standardVersionId": version.standard_version_id,
        "version": version.version,
        "title": version.title,
        "evidenceType": standard.evidence_type,
        "productGroup": standard.product_group,
        "advertisementType": standard.advertisement_type,
        "ruleType": standard.rule_type,
        "importance": standard.importance,
        "effectiveDate": version.effective_date,
        "expiredDate": version.expired_date,
        "metadata": version.metadata,
        "content": version.content,
        "changeReason": version.change_reason,
        "isActive": standard.is_active,
        "createdAt": version.created_at,
        "createdBy": version.created_by,
    }


def _evidence_detail(standard: Standard, version: StandardVersion) -> dict[str, object]:
    return {
        "evidenceId": version.evidence_id,
        "standardId": standard.standard_id,
        "standardVersionId": version.standard_version_id,
        "evidenceType": standard.evidence_type,
        "title": version.title,
        "articleNo": version.metadata.get("articleNo", version.metadata.get("article_no")),
        "content": version.content,
        "contentSummary": version.content[:500],
        "productGroup": standard.product_group,
        "advertisementType": standard.advertisement_type,
        "ruleType": standard.rule_type,
        "importance": standard.importance,
        "effectiveDate": version.effective_date,
        "expiredDate": version.expired_date,
        "version": version.version,
        "isActive": standard.is_active,
    }


def _job(job: ReindexJob) -> dict[str, object]:
    return {
        "jobId": job.job_id,
        "standardId": job.standard_id,
        "standardVersionId": job.standard_version_id,
        "reindexScope": job.reindex_scope,
        "jobStatus": job.job_status,
        "targetIndexes": list(job.target_indexes),
        "parserRuleVersion": job.parser_rule_version,
        "chunkingPolicyVersion": job.chunking_policy_version,
        "embeddingModel": job.embedding_model,
        "searchSchemaVersion": job.search_schema_version,
        "opensearchAnalyzerVersion": job.opensearch_analyzer_version,
        "synonymVersion": job.synonym_version,
        "createdChunkCount": job.created_chunk_count,
        "indexedChunkCount": job.indexed_chunk_count,
        "qdrantStatus": job.qdrant_status,
        "opensearchStatus": job.opensearch_status,
        "failedReasonCode": job.failed_reason_code,
        "failedReasonMessage": job.failed_reason_message,
        "requestedBy": job.requested_by,
        "requestedAt": job.requested_at,
        "startedAt": job.started_at,
        "completedAt": job.completed_at,
    }


def _chunk(chunk: EvidenceChunk) -> dict[str, object]:
    return {
        "evidenceChunkId": chunk.evidence_chunk_id,
        "evidenceId": chunk.evidence_id,
        "standardId": chunk.standard_id,
        "standardVersionId": chunk.standard_version_id,
        "chunkNo": chunk.chunk_no,
        "chunkText": chunk.chunk_text,
        "tokenCount": chunk.token_count,
        "sectionPath": chunk.section_path,
        "articleNo": chunk.article_no,
        "pageNo": None,
        "sourceSpan": {"start": chunk.source_start, "end": chunk.source_end},
        "structureConfidence": 1.0,
        "parserRuleVersion": chunk.parser_rule_version,
        "chunkingPolicyVersion": chunk.chunking_policy_version,
        "embeddingModel": chunk.embedding_model,
        "searchSchemaVersion": chunk.search_schema_version,
        "opensearchAnalyzerVersion": chunk.opensearch_analyzer_version,
        "synonymVersion": chunk.synonym_version,
        "qdrantIndexStatus": chunk.qdrant_index_status,
        "qdrantIndexErrorCode": chunk.qdrant_error_code,
        "opensearchIndexStatus": chunk.opensearch_index_status,
        "opensearchIndexErrorCode": chunk.opensearch_error_code,
        "createdAt": chunk.created_at,
    }
