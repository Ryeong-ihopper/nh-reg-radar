"""Raw parser artifact integrity, retention, access, and redaction boundary."""

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol


class ArtifactAccessDenied(PermissionError):
    pass


class ArtifactChecksumMismatch(ValueError):
    pass


@dataclass(frozen=True)
class ArtifactMetadata:
    raw_artifact_id: str
    review_id: str
    file_id: str
    review_step_id: str
    artifact_type: str
    storage_provider: str
    bucket: str
    object_key: str
    checksum_sha256: str
    content_type: str
    file_size: int
    parser_name: str
    parser_version: str
    parser_rule_version: str
    ir_version: str
    attempt_no: int
    is_primary_attempt: bool
    is_selected_output: bool
    rerun_reason_code: str | None
    confidence_score: float | None
    confidence_status: str | None
    created_at: datetime
    retention_until: datetime
    retention_hold: bool = False
    deleted_at: datetime | None = None


class ArtifactStorage(Protocol):
    def put(self, bucket: str, object_key: str, body: bytes, content_type: str) -> None: ...
    def get(self, bucket: str, object_key: str) -> bytes: ...
    def delete(self, bucket: str, object_key: str) -> None: ...


class ArtifactMetadataRepository(Protocol):
    def add(self, metadata: ArtifactMetadata) -> ArtifactMetadata: ...
    def get(self, raw_artifact_id: str) -> ArtifactMetadata | None: ...
    def replace(self, metadata: ArtifactMetadata) -> None: ...


class InMemoryArtifactStorage:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put(self, bucket: str, object_key: str, body: bytes, _content_type: str) -> None:
        self.objects[(bucket, object_key)] = body

    def get(self, bucket: str, object_key: str) -> bytes:
        return self.objects[(bucket, object_key)]

    def delete(self, bucket: str, object_key: str) -> None:
        self.objects.pop((bucket, object_key), None)


class InMemoryArtifactMetadataRepository:
    def __init__(self) -> None:
        self.items: dict[str, ArtifactMetadata] = {}

    def add(self, metadata: ArtifactMetadata) -> ArtifactMetadata:
        return self.items.setdefault(metadata.raw_artifact_id, metadata)

    def get(self, raw_artifact_id: str) -> ArtifactMetadata | None:
        return self.items.get(raw_artifact_id)

    def replace(self, metadata: ArtifactMetadata) -> None:
        self.items[metadata.raw_artifact_id] = metadata


class ArtifactStore:
    """Keeps raw structure inaccessible to ordinary application paths."""

    PRIVILEGED_ROLES = frozenset({"SYSTEM_ADMIN", "SERVICE_ACCOUNT"})

    def __init__(
        self,
        storage: ArtifactStorage,
        repository: ArtifactMetadataRepository,
        *,
        bucket: str,
        storage_provider: str = "minio",
        audit: Callable[[dict[str, str]], None] | None = None,
    ) -> None:
        self._storage = storage
        self._repository = repository
        self._bucket = bucket
        self._storage_provider = storage_provider
        self._audit = audit or (lambda _event: None)

    def put(
        self,
        body: bytes,
        *,
        raw_artifact_id: str,
        review_id: str,
        file_id: str,
        review_step_id: str,
        artifact_type: str,
        content_type: str,
        parser_name: str,
        parser_version: str,
        parser_rule_version: str,
        ir_version: str,
        attempt_no: int,
        is_primary_attempt: bool,
        is_selected_output: bool,
        rerun_reason_code: str | None,
        confidence_score: float | None,
        confidence_status: str | None,
        created_at: datetime,
        retention_until: datetime,
    ) -> ArtifactMetadata:
        checksum = hashlib.sha256(body).hexdigest()

        def is_same_artifact(existing: ArtifactMetadata) -> bool:
            return (
                existing.review_id == review_id
                and existing.file_id == file_id
                and existing.review_step_id == review_step_id
                and existing.artifact_type == artifact_type
                and existing.checksum_sha256 == checksum
                and existing.content_type == content_type
                and existing.parser_name == parser_name
                and existing.parser_version == parser_version
                and existing.parser_rule_version == parser_rule_version
                and existing.ir_version == ir_version
                and existing.attempt_no == attempt_no
                and existing.is_primary_attempt == is_primary_attempt
                and existing.is_selected_output == is_selected_output
                and existing.rerun_reason_code == rerun_reason_code
            )

        existing = self._repository.get(raw_artifact_id)
        if existing is not None:
            if not is_same_artifact(existing):
                raise ValueError("ARTIFACT_IDEMPOTENCY_CONFLICT")
            return existing
        object_key = f"{review_id}/{secrets.token_hex(24)}"
        self._storage.put(self._bucket, object_key, body, content_type)
        metadata = ArtifactMetadata(
            raw_artifact_id=raw_artifact_id,
            review_id=review_id,
            file_id=file_id,
            review_step_id=review_step_id,
            artifact_type=artifact_type,
            storage_provider=self._storage_provider,
            bucket=self._bucket,
            object_key=object_key,
            checksum_sha256=checksum,
            content_type=content_type,
            file_size=len(body),
            parser_name=parser_name,
            parser_version=parser_version,
            parser_rule_version=parser_rule_version,
            ir_version=ir_version,
            attempt_no=attempt_no,
            is_primary_attempt=is_primary_attempt,
            is_selected_output=is_selected_output,
            rerun_reason_code=rerun_reason_code,
            confidence_score=confidence_score,
            confidence_status=confidence_status,
            created_at=created_at,
            retention_until=retention_until,
        )
        canonical = self._repository.add(metadata)
        if canonical != metadata:
            self._storage.delete(self._bucket, object_key)
            if not is_same_artifact(canonical):
                raise ValueError("ARTIFACT_IDEMPOTENCY_CONFLICT")
        return canonical

    def read_privileged(
        self, raw_artifact_id: str, *, role: str, actor_id: str, purpose: str
    ) -> bytes:
        metadata = self._required(raw_artifact_id)
        if role not in self.PRIVILEGED_ROLES or not purpose.strip():
            self._audit_event("PARSER_ARTIFACT_READ", "DENIED", metadata, actor_id)
            raise ArtifactAccessDenied("raw parser artifacts are restricted")
        body = self._storage.get(metadata.bucket, metadata.object_key)
        if hashlib.sha256(body).hexdigest() != metadata.checksum_sha256:
            self._audit_event("PARSER_ARTIFACT_READ", "FAILURE", metadata, actor_id)
            raise ArtifactChecksumMismatch(raw_artifact_id)
        self._audit_event("PARSER_ARTIFACT_READ", "SUCCESS", metadata, actor_id)
        return body

    def delete_expired(
        self, raw_artifact_id: str, *, now: datetime, approved: bool, actor_id: str
    ) -> bool:
        metadata = self._required(raw_artifact_id)
        if metadata.deleted_at is not None:
            return False
        if not approved or metadata.retention_hold or metadata.retention_until > now:
            return False
        self._storage.delete(metadata.bucket, metadata.object_key)
        self._repository.replace(replace(metadata, deleted_at=now))
        self._audit_event("PARSER_ARTIFACT_DELETE", "SUCCESS", metadata, actor_id)
        return True

    def _required(self, raw_artifact_id: str) -> ArtifactMetadata:
        metadata = self._repository.get(raw_artifact_id)
        if metadata is None:
            raise KeyError(raw_artifact_id)
        return metadata

    def _audit_event(
        self, action: str, result: str, metadata: ArtifactMetadata, actor_id: str
    ) -> None:
        self._audit(
            {
                "action": action,
                "result": result,
                "artifactId": metadata.raw_artifact_id,
                "actorId": actor_id,
            }
        )
