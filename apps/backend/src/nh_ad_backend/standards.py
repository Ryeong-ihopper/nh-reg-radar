"""M3 reference-standard versioning and reindex application service."""

from __future__ import annotations

import secrets
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from threading import RLock
from typing import Protocol

from nh_ad_backend.domain import AuditEvent, CurrentUser
from nh_ad_backend.search import (
    HybridSearch,
    SearchDocument,
    SearchHit,
    SearchInfrastructureError,
    SearchMode,
    deterministic_index_id,
    direct_text_chunks,
)


@dataclass(frozen=True)
class Standard:
    standard_id: str
    title: str
    evidence_type: str
    product_group: str | None
    advertisement_type: str | None
    rule_type: str
    importance: str
    effective_date: date | None
    expired_date: date | None
    metadata: dict[str, object]
    current_version: str
    is_active: bool
    created_at: datetime
    created_by: str
    updated_at: datetime | None = None
    updated_by: str | None = None


@dataclass(frozen=True)
class StandardVersion:
    standard_version_id: str
    standard_id: str
    evidence_id: str
    version: str
    title: str
    content: str
    change_reason: str | None
    effective_date: date | None
    expired_date: date | None
    metadata: dict[str, object]
    created_at: datetime
    created_by: str


@dataclass
class EvidenceChunk:
    evidence_chunk_id: str
    evidence_id: str
    standard_id: str
    standard_version_id: str
    chunk_no: int
    chunk_text: str
    source_start: int
    source_end: int
    section_path: str | None
    article_no: str | None
    token_count: int
    parser_rule_version: str
    chunking_policy_version: str
    embedding_model: str | None = None
    search_schema_version: str = "search-schema-v1"
    opensearch_analyzer_version: str | None = None
    synonym_version: str | None = None
    deterministic_index_id: str | None = None
    qdrant_index_status: str = "PENDING"
    opensearch_index_status: str = "PENDING"
    qdrant_error_code: str | None = None
    opensearch_error_code: str | None = None
    created_at: datetime | None = None


@dataclass
class ReindexJob:
    job_id: str
    standard_id: str
    standard_version_id: str
    reindex_scope: str
    job_status: str
    target_indexes: tuple[str, ...]
    parser_rule_version: str
    chunking_policy_version: str
    embedding_model: str
    search_schema_version: str
    opensearch_analyzer_version: str
    synonym_version: str
    requested_by: str
    requested_at: datetime
    reason: str | None = None
    created_chunk_count: int = 0
    indexed_chunk_count: int = 0
    qdrant_status: str = "PENDING"
    opensearch_status: str = "PENDING"
    failed_reason_code: str | None = None
    failed_reason_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass(frozen=True)
class StandardCreated:
    standard_id: str
    evidence_id: str
    standard_version_id: str
    version: str
    is_active: bool


class StandardsError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


class StandardRepository(Protocol):
    def create(
        self,
        standard: Standard,
        version: StandardVersion,
        chunks: Sequence[EvidenceChunk],
    ) -> None: ...

    def get_standard(self, standard_id: str) -> Standard | None: ...

    def save_standard(self, standard: Standard) -> None: ...

    def add_version(self, version: StandardVersion, chunks: Sequence[EvidenceChunk]) -> None: ...

    def get_version(self, standard_version_id: str) -> StandardVersion | None: ...

    def get_version_by_evidence(self, evidence_id: str) -> StandardVersion | None: ...

    def histories(self, standard_id: str) -> list[StandardVersion]: ...

    def chunks_for_version(self, standard_version_id: str) -> list[EvidenceChunk]: ...

    def save_chunks(self, chunks: Sequence[EvidenceChunk]) -> None: ...

    def get_chunk(self, evidence_chunk_id: str) -> EvidenceChunk | None: ...

    def chunks_for_evidence(self, evidence_id: str) -> list[EvidenceChunk]: ...

    def save_reindex_job(self, job: ReindexJob) -> None: ...

    def get_reindex_job(self, job_id: str) -> ReindexJob | None: ...

    def list_standards(self) -> list[Standard]: ...


class InMemoryStandardRepository:
    def __init__(self) -> None:
        self._lock = RLock()
        self.standards: dict[str, Standard] = {}
        self.versions: dict[str, StandardVersion] = {}
        self.chunks: list[EvidenceChunk] = []
        self.reindex_jobs: dict[str, ReindexJob] = {}

    def create(
        self,
        standard: Standard,
        version: StandardVersion,
        chunks: Sequence[EvidenceChunk],
    ) -> None:
        with self._lock:
            if standard.standard_id in self.standards:
                raise ValueError("DUPLICATE_STANDARD")
            self.standards[standard.standard_id] = standard
            self.versions[version.standard_version_id] = version
            self.chunks.extend(chunks)

    def get_standard(self, standard_id: str) -> Standard | None:
        return self.standards.get(standard_id)

    def save_standard(self, standard: Standard) -> None:
        with self._lock:
            self.standards[standard.standard_id] = standard

    def add_version(self, version: StandardVersion, chunks: Sequence[EvidenceChunk]) -> None:
        with self._lock:
            if version.standard_version_id in self.versions:
                raise ValueError("DUPLICATE_STANDARD_VERSION")
            self.versions[version.standard_version_id] = version
            self.chunks.extend(chunks)

    def get_version(self, standard_version_id: str) -> StandardVersion | None:
        return self.versions.get(standard_version_id)

    def get_version_by_evidence(self, evidence_id: str) -> StandardVersion | None:
        return next(
            (version for version in self.versions.values() if version.evidence_id == evidence_id),
            None,
        )

    def histories(self, standard_id: str) -> list[StandardVersion]:
        return sorted(
            (item for item in self.versions.values() if item.standard_id == standard_id),
            key=lambda item: (_version_number(item.version), item.created_at),
            reverse=True,
        )

    def chunks_for_version(self, standard_version_id: str) -> list[EvidenceChunk]:
        return sorted(
            (chunk for chunk in self.chunks if chunk.standard_version_id == standard_version_id),
            key=lambda chunk: chunk.chunk_no,
        )

    def save_chunks(self, chunks: Sequence[EvidenceChunk]) -> None:
        del chunks

    def get_chunk(self, evidence_chunk_id: str) -> EvidenceChunk | None:
        return next(
            (chunk for chunk in self.chunks if chunk.evidence_chunk_id == evidence_chunk_id),
            None,
        )

    def chunks_for_evidence(self, evidence_id: str) -> list[EvidenceChunk]:
        return sorted(
            (chunk for chunk in self.chunks if chunk.evidence_id == evidence_id),
            key=lambda chunk: chunk.chunk_no,
        )

    def save_reindex_job(self, job: ReindexJob) -> None:
        with self._lock:
            self.reindex_jobs[job.job_id] = job

    def get_reindex_job(self, job_id: str) -> ReindexJob | None:
        return self.reindex_jobs.get(job_id)

    def list_standards(self) -> list[Standard]:
        return sorted(self.standards.values(), key=lambda item: item.created_at, reverse=True)


_required_metadata: dict[str, tuple[tuple[str, ...], ...]] = {
    "LAW": (
        ("agency",),
        ("documentName", "document_name"),
        ("articleNo", "article_no"),
        ("effectiveDate", "effective_date"),
        ("revisionDate", "revision_date"),
        ("sourceUrl", "source_url"),
    ),
    "REGULATION": (
        ("agency",),
        ("documentName", "document_name"),
        ("articleNo", "article_no"),
        ("effectiveDate", "effective_date"),
        ("revisionDate", "revision_date"),
        ("sourceUrl", "source_url"),
    ),
    "INTERNAL_STANDARD": (
        ("owningDepartment", "owning_department"),
        ("documentName", "document_name"),
        ("sectionPath", "section_path"),
        ("effectiveDate", "effective_date"),
        ("version",),
        ("productGroup", "product_group"),
    ),
    "GUIDELINE": (
        ("documentName", "document_name"),
        ("documentType", "document_type"),
        ("sectionPath", "section_path"),
        ("productGroup", "product_group"),
        ("advertisementType", "advertisement_type"),
        ("version",),
    ),
    "MANUAL": (
        ("documentName", "document_name"),
        ("documentType", "document_type"),
        ("sectionPath", "section_path"),
        ("productGroup", "product_group"),
        ("advertisementType", "advertisement_type"),
        ("version",),
    ),
    "REVIEW_CASE": (
        ("caseNumber", "case_number"),
        ("productGroup", "product_group"),
        ("advertisementType", "advertisement_type"),
        ("decisionType", "decision_type"),
        ("issue",),
        ("actionResult", "action_result"),
        ("decisionDate", "decision_date"),
    ),
    "TEMPLATE": (
        ("phraseType", "phrase_type"),
        ("ruleType", "rule_type"),
        ("productGroup", "product_group"),
        ("advertisementType", "advertisement_type"),
        ("conditions",),
    ),
    "PRODUCT_STANDARD": (
        ("productName", "product_name"),
        ("productGroup", "product_group"),
        ("terms",),
        ("effectiveDate", "effective_date"),
        ("fileVersion", "file_version"),
    ),
}


def validate_metadata(evidence_type: str, metadata: dict[str, object]) -> None:
    groups = _required_metadata.get(evidence_type)
    if groups is None:
        raise StandardsError(
            400, "REFERENCE_METADATA_INVALID", "지원하지 않는 기준자료 유형입니다."
        )
    missing = [
        aliases[0]
        for aliases in groups
        if not any(alias in metadata and metadata[alias] not in (None, "") for alias in aliases)
    ]
    if missing:
        raise StandardsError(
            400,
            "REFERENCE_METADATA_INVALID",
            f"필수 메타데이터가 누락되었습니다: {', '.join(missing)}",
        )


def _version_number(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError as exc:
        raise ValueError("standard version must contain numeric components") from exc


class StandardService:
    MANAGE_ROLES = {"STANDARD_MANAGER", "SYSTEM_ADMIN"}

    def __init__(
        self,
        repository: StandardRepository,
        search: HybridSearch,
        *,
        now: Callable[[], datetime] | None = None,
        identifier: Callable[[str], str] | None = None,
        environment: str = "dev",
        audit_sink: Callable[[AuditEvent], None] | None = None,
    ) -> None:
        self.repository = repository
        self.search_engine = search
        self._now = now or (lambda: datetime.now(UTC))
        self._identifier = identifier or (lambda prefix: f"{prefix}-{secrets.token_hex(8).upper()}")
        self._environment = environment
        self._audit_sink = audit_sink

    def create(
        self,
        actor: CurrentUser,
        *,
        title: str,
        evidence_type: str,
        product_group: str | None,
        advertisement_type: str | None,
        rule_type: str,
        importance: str,
        effective_date: date | None,
        expired_date: date | None,
        metadata: dict[str, object],
        content: str,
        trace_id: str,
    ) -> StandardCreated:
        self._authorize(actor, "STANDARD_CREATE", None, trace_id)
        if (
            not title.strip()
            or not content.strip()
            or rule_type
            not in {
                "REQUIRED",
                "PROHIBITED",
                "RECOMMENDED",
                "REFERENCE",
            }
        ):
            raise StandardsError(400, "BAD_REQUEST", "필수 입력값을 확인해 주세요.")
        if importance not in {"HIGH", "MEDIUM", "LOW"}:
            raise StandardsError(400, "BAD_REQUEST", "중요도 값을 확인해 주세요.")
        if effective_date and expired_date and effective_date > expired_date:
            raise StandardsError(400, "BAD_REQUEST", "적용 종료일을 확인해 주세요.")
        validate_metadata(evidence_type, metadata)
        now = self._now()
        standard_id = self._identifier("STD")
        version_id = self._identifier("STDVER")
        evidence_id = self._identifier("EVD")
        standard = Standard(
            standard_id,
            title.strip(),
            evidence_type,
            product_group,
            advertisement_type,
            rule_type,
            importance,
            effective_date,
            expired_date,
            dict(metadata),
            "1.0",
            True,
            now,
            actor.user_id,
        )
        version = StandardVersion(
            version_id,
            standard_id,
            evidence_id,
            "1.0",
            title.strip(),
            content.strip(),
            "initial registration",
            effective_date,
            expired_date,
            dict(metadata),
            now,
            actor.user_id,
        )
        chunks = self._chunks(standard, version)
        self.repository.create(standard, version, chunks)
        self._audit(actor, "STANDARD_CREATE", "SUCCESS", standard_id, trace_id)
        return StandardCreated(standard_id, evidence_id, version_id, "1.0", True)

    def update(
        self,
        actor: CurrentUser,
        standard_id: str,
        *,
        title: str,
        content: str,
        effective_date: date | None,
        expired_date: date | None,
        metadata: dict[str, object],
        change_reason: str,
        trace_id: str,
    ) -> StandardCreated:
        self._authorize(actor, "STANDARD_UPDATE", standard_id, trace_id)
        standard = self._standard(standard_id)
        if not standard.is_active:
            raise StandardsError(409, "CONFLICT", "비활성 기준자료는 수정할 수 없습니다.")
        if not title.strip() or not content.strip() or not change_reason.strip():
            raise StandardsError(400, "BAD_REQUEST", "필수 입력값을 확인해 주세요.")
        validate_metadata(standard.evidence_type, metadata)
        major = _version_number(standard.current_version)[0] + 1
        version_text = f"{major}.0"
        now = self._now()
        version_id = self._identifier("STDVER")
        evidence_id = self._identifier("EVD")
        version = StandardVersion(
            version_id,
            standard_id,
            evidence_id,
            version_text,
            title.strip(),
            content.strip(),
            change_reason.strip(),
            effective_date,
            expired_date,
            dict(metadata),
            now,
            actor.user_id,
        )
        updated = replace(
            standard,
            title=title.strip(),
            effective_date=effective_date,
            expired_date=expired_date,
            metadata=dict(metadata),
            current_version=version_text,
            updated_at=now,
            updated_by=actor.user_id,
        )
        self.repository.add_version(version, self._chunks(updated, version))
        self.repository.save_standard(updated)
        self._audit(actor, "STANDARD_UPDATE", "SUCCESS", standard_id, trace_id)
        return StandardCreated(standard_id, evidence_id, version_id, version_text, True)

    def deactivate(
        self, actor: CurrentUser, standard_id: str, *, reason: str, trace_id: str
    ) -> Standard:
        self._authorize(actor, "STANDARD_DEACTIVATE", standard_id, trace_id)
        if not reason.strip():
            raise StandardsError(400, "BAD_REQUEST", "비활성화 사유를 입력해 주세요.")
        standard = self._standard(standard_id)
        updated = replace(
            standard,
            is_active=False,
            updated_at=self._now(),
            updated_by=actor.user_id,
        )
        self.repository.save_standard(updated)
        for version in self.repository.histories(standard_id):
            for chunk in self.repository.chunks_for_version(version.standard_version_id):
                chunk.qdrant_index_status = "EXCLUDED"
                chunk.opensearch_index_status = "EXCLUDED"
        self.search_engine.keyword.exclude(standard_id)
        self.search_engine.vector.exclude(standard_id)
        self._audit(
            actor,
            "STANDARD_DEACTIVATE",
            "SUCCESS",
            standard_id,
            trace_id,
            {"reason": reason.strip()},
        )
        return updated

    def version_on(self, standard_id: str, effective_on: date) -> StandardVersion:
        standard = self._standard(standard_id)
        if not standard.is_active:
            raise StandardsError(404, "NOT_FOUND", "요청한 기준자료를 찾을 수 없습니다.")
        eligible = [
            version
            for version in self.repository.histories(standard_id)
            if (version.effective_date is None or version.effective_date <= effective_on)
            and (version.expired_date is None or version.expired_date >= effective_on)
        ]
        if not eligible:
            raise StandardsError(404, "NOT_FOUND", "적용 가능한 기준자료 버전이 없습니다.")
        return max(
            eligible,
            key=lambda item: (item.effective_date or date.min, _version_number(item.version)),
        )

    def detail(self, standard_id: str) -> tuple[Standard, StandardVersion]:
        standard = self._standard(standard_id)
        versions = self.repository.histories(standard_id)
        if not versions:
            raise StandardsError(404, "NOT_FOUND", "요청한 기준자료를 찾을 수 없습니다.")
        version = next(
            (item for item in versions if item.version == standard.current_version),
            versions[0],
        )
        return standard, version

    def list_standards(
        self,
        actor: CurrentUser,
        *,
        keyword: str | None = None,
        evidence_type: str | None = None,
        product_group: str | None = None,
        advertisement_type: str | None = None,
        rule_type: str | None = None,
        active_only: bool = True,
        trace_id: str,
    ) -> list[Standard]:
        self._authorize(actor, "STANDARD_LIST", None, trace_id)
        values = self.repository.list_standards()
        if keyword:
            values = [item for item in values if keyword.casefold() in item.title.casefold()]
        if evidence_type:
            values = [item for item in values if item.evidence_type == evidence_type]
        if product_group:
            values = [item for item in values if item.product_group == product_group]
        if advertisement_type:
            values = [item for item in values if item.advertisement_type == advertisement_type]
        if rule_type:
            values = [item for item in values if item.rule_type == rule_type]
        if active_only:
            values = [item for item in values if item.is_active]
        return values

    def manager_detail(
        self, actor: CurrentUser, standard_id: str, *, trace_id: str
    ) -> tuple[Standard, StandardVersion]:
        self._authorize(actor, "STANDARD_READ", standard_id, trace_id)
        return self.detail(standard_id)

    def manager_histories(
        self, actor: CurrentUser, standard_id: str, *, trace_id: str
    ) -> list[StandardVersion]:
        self._authorize(actor, "STANDARD_HISTORY_READ", standard_id, trace_id)
        self._standard(standard_id)
        return self.repository.histories(standard_id)

    def manager_chunks(
        self, actor: CurrentUser, evidence_id: str, *, trace_id: str
    ) -> list[EvidenceChunk]:
        self._authorize(actor, "STANDARD_CHUNK_READ", evidence_id, trace_id)
        self.evidence(evidence_id)
        return self.repository.chunks_for_evidence(evidence_id)

    def manager_chunk(
        self, actor: CurrentUser, evidence_chunk_id: str, *, trace_id: str
    ) -> EvidenceChunk:
        self._authorize(actor, "STANDARD_CHUNK_READ", evidence_chunk_id, trace_id)
        return self.chunk(evidence_chunk_id)

    def manager_reindex_job(self, actor: CurrentUser, job_id: str, *, trace_id: str) -> ReindexJob:
        self._authorize(actor, "STANDARD_REINDEX_READ", job_id, trace_id)
        job = self.repository.get_reindex_job(job_id)
        if job is None:
            raise StandardsError(404, "NOT_FOUND", "요청한 재색인 작업을 찾을 수 없습니다.")
        return job

    def evidence(self, evidence_id: str) -> tuple[Standard, StandardVersion]:
        version = self.repository.get_version_by_evidence(evidence_id)
        if version is None:
            raise StandardsError(404, "NOT_FOUND", "요청한 근거를 찾을 수 없습니다.")
        return self._standard(version.standard_id), version

    def chunk(self, evidence_chunk_id: str) -> EvidenceChunk:
        chunk = self.repository.get_chunk(evidence_chunk_id)
        if chunk is None:
            raise StandardsError(404, "NOT_FOUND", "요청한 Chunk를 찾을 수 없습니다.")
        return chunk

    def reindex(
        self,
        actor: CurrentUser,
        standard_id: str,
        standard_version_id: str,
        *,
        reindex_scope: str,
        reason: str,
        embedding_model: str,
        chunking_policy_version: str,
        search_schema_version: str,
        opensearch_analyzer_version: str,
        synonym_version: str,
        target_indexes: Sequence[str],
        trace_id: str,
        parser_rule_version: str = "direct-text-v1",
    ) -> ReindexJob:
        self._authorize(actor, "STANDARD_REINDEX", standard_id, trace_id)
        if reindex_scope not in {
            "INDEX_ONLY",
            "CHUNK_AND_INDEX",
            "KEYWORD_ONLY",
            "VECTOR_ONLY",
        }:
            raise StandardsError(400, "BAD_REQUEST", "재색인 범위를 확인해 주세요.")
        standard = self._standard(standard_id)
        version = self.repository.get_version(standard_version_id)
        if version is None or version.standard_id != standard_id:
            raise StandardsError(404, "NOT_FOUND", "요청한 기준자료 버전을 찾을 수 없습니다.")
        now = self._now()
        targets = tuple(target_indexes)
        if (
            not targets
            or len(targets) != len(set(targets))
            or any(target not in {"QDRANT", "OPENSEARCH"} for target in targets)
            or (reindex_scope == "KEYWORD_ONLY" and targets != ("OPENSEARCH",))
            or (reindex_scope == "VECTOR_ONLY" and targets != ("QDRANT",))
        ):
            raise StandardsError(400, "BAD_REQUEST", "재색인 범위와 대상 인덱스를 확인해 주세요.")
        job = ReindexJob(
            self._identifier("SRJ"),
            standard_id,
            standard_version_id,
            reindex_scope,
            "RUNNING",
            targets,
            parser_rule_version,
            chunking_policy_version,
            embedding_model,
            search_schema_version,
            opensearch_analyzer_version,
            synonym_version,
            actor.user_id,
            now,
            reason=reason.strip(),
            started_at=now,
        )
        self.repository.save_reindex_job(job)
        chunks = self.repository.chunks_for_version(standard_version_id)
        for chunk in chunks:
            chunk.parser_rule_version = parser_rule_version
            chunk.chunking_policy_version = chunking_policy_version
            chunk.embedding_model = embedding_model
            chunk.search_schema_version = search_schema_version
            chunk.opensearch_analyzer_version = opensearch_analyzer_version
            chunk.synonym_version = synonym_version
            chunk.deterministic_index_id = deterministic_index_id(
                self._environment,
                standard_version_id,
                chunk.evidence_chunk_id,
                embedding_model,
                chunking_policy_version,
            )
        documents = [self._document(standard, version, chunk) for chunk in chunks]
        try:
            if "QDRANT" in targets:
                self.search_engine.vector.upsert(documents)
                job.qdrant_status = "ACTIVE"
                for chunk in chunks:
                    chunk.qdrant_index_status = "ACTIVE"
                    chunk.qdrant_error_code = None
            if "OPENSEARCH" in targets:
                self.search_engine.keyword.upsert(documents)
                job.opensearch_status = "ACTIVE"
                for chunk in chunks:
                    chunk.opensearch_index_status = "ACTIVE"
                    chunk.opensearch_error_code = None
        except SearchInfrastructureError as exc:
            failed = exc.backend.upper()
            if "QDRANT" in failed:
                job.qdrant_status = "FAILED"
                for chunk in chunks:
                    chunk.qdrant_index_status = "FAILED"
                    chunk.qdrant_error_code = "RAG_SEARCH_UNAVAILABLE"
            if "OPENSEARCH" in failed:
                job.opensearch_status = "FAILED"
                for chunk in chunks:
                    chunk.opensearch_index_status = "FAILED"
                    chunk.opensearch_error_code = "RAG_SEARCH_UNAVAILABLE"
            job.job_status = "FAILED"
            job.failed_reason_code = "RAG_SEARCH_UNAVAILABLE"
            job.failed_reason_message = str(exc)
            job.completed_at = self._now()
            self.repository.save_chunks(chunks)
            self.repository.save_reindex_job(job)
            self._audit(actor, "STANDARD_REINDEX", "FAILURE", standard_id, trace_id)
            raise
        job.job_status = "SUCCEEDED"
        job.indexed_chunk_count = len(chunks)
        job.completed_at = self._now()
        self.repository.save_chunks(chunks)
        self.repository.save_reindex_job(job)
        self._audit(actor, "STANDARD_REINDEX", "SUCCESS", standard_id, trace_id)
        return job

    def search(
        self,
        keyword: str,
        *,
        mode: SearchMode = "HYBRID",
        limit: int = 20,
        effective_on: date | None = None,
        filters: dict[str, str] | None = None,
    ) -> list[SearchHit]:
        return self.search_engine.search(
            keyword,
            mode=mode,
            limit=limit,
            effective_on=effective_on,
            filters=filters,
        )

    def _chunks(self, standard: Standard, version: StandardVersion) -> list[EvidenceChunk]:
        section_path = _metadata_value(version.metadata, "sectionPath", "section_path")
        article_no = _metadata_value(version.metadata, "articleNo", "article_no")
        return [
            EvidenceChunk(
                chunk.evidence_chunk_id,
                version.evidence_id,
                standard.standard_id,
                version.standard_version_id,
                chunk.chunk_no,
                chunk.chunk_text,
                chunk.source_start,
                chunk.source_end,
                str(section_path) if section_path is not None else None,
                str(article_no) if article_no is not None else None,
                len(chunk.chunk_text.split()),
                "direct-text-v1",
                "reference-chunking-v1",
                created_at=version.created_at,
            )
            for chunk in direct_text_chunks(version.standard_version_id, version.content)
        ]

    @staticmethod
    def _document(
        standard: Standard, version: StandardVersion, chunk: EvidenceChunk
    ) -> SearchDocument:
        return SearchDocument(
            chunk.evidence_chunk_id,
            chunk.evidence_id,
            standard.standard_id,
            version.standard_version_id,
            standard.evidence_type,
            version.title,
            chunk.chunk_text,
            chunk.article_no,
            chunk.section_path,
            standard.product_group,
            standard.advertisement_type,
            standard.rule_type,
            standard.importance,
            version.effective_date,
            version.expired_date,
            version.version,
            standard.is_active,
            chunk.opensearch_analyzer_version,
            chunk.synonym_version,
        )

    def _standard(self, standard_id: str) -> Standard:
        standard = self.repository.get_standard(standard_id)
        if standard is None:
            raise StandardsError(404, "NOT_FOUND", "요청한 기준자료를 찾을 수 없습니다.")
        return standard

    def _authorize(
        self, actor: CurrentUser, action: str, target_id: str | None, trace_id: str
    ) -> None:
        if not set(actor.roles) & self.MANAGE_ROLES:
            self._audit(actor, action, "DENIED", target_id, trace_id)
            raise StandardsError(403, "FORBIDDEN", "접근 권한이 없습니다.")

    def _audit(
        self,
        actor: CurrentUser,
        action: str,
        result: str,
        target_id: str | None,
        trace_id: str,
        metadata: dict[str, str] | None = None,
    ) -> None:
        if self._audit_sink is None:
            return
        self._audit_sink(
            AuditEvent(
                action,
                result,
                "ROLE_SCOPE" if result == "DENIED" else None,
                actor.user_id,
                actor.department_id,
                actor.roles[0] if actor.roles else None,
                "STANDARD",
                target_id,
                trace_id,
                self._now(),
                metadata or {},
            )
        )


def _metadata_value(metadata: dict[str, object], *keys: str) -> object | None:
    return next((metadata[key] for key in keys if key in metadata), None)
