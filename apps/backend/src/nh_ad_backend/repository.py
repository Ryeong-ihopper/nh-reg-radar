"""Repository boundary and deterministic in-memory implementation."""

import json
from collections.abc import Iterable
from datetime import datetime, timedelta
from threading import RLock
from typing import Protocol
from uuid import UUID

from sqlalchemy import Engine, bindparam, text

from nh_ad_backend.domain import (
    Advertisement,
    AdvertisementFile,
    AdvertisementRevision,
    AuditEvent,
    CurrentUser,
    RefreshSession,
    User,
)


class Repository(Protocol):
    def get_user_by_email(self, email: str) -> User | None: ...
    def get_user(self, user_id: str) -> User | None: ...
    def register_login_failure(self, user: User, now: datetime) -> None: ...
    def register_login_success(self, user: User, now: datetime) -> None: ...
    def reset_login_failures(self, user: User, now: datetime) -> None: ...
    def save_refresh_session(self, session: RefreshSession) -> None: ...
    def get_refresh_session(self, token_hash: str) -> RefreshSession | None: ...
    def revoke_refresh_session(
        self, session: RefreshSession, reason: str, now: datetime
    ) -> None: ...
    def revoke_all_refresh_sessions(self, user_id: str, reason: str, now: datetime) -> None: ...
    def add_advertisement(self, advertisement: Advertisement) -> None: ...
    def add_revision(self, revision: AdvertisementRevision) -> None: ...
    def get_revision(self, revision_id: str) -> AdvertisementRevision | None: ...
    def get_advertisement(self, advertisement_id: str) -> Advertisement | None: ...
    def get_file(self, file_id: str) -> tuple[Advertisement, AdvertisementFile] | None: ...
    def list_advertisements(self, actor: CurrentUser) -> list[Advertisement]: ...
    def add_audit_event(self, event: AuditEvent) -> None: ...
    def list_common_codes(self, code_group: str) -> list[dict[str, object]]: ...
    def list_audit_events(self) -> list[AuditEvent]: ...


class InMemoryRepository:
    """Thread-safe repository used by deterministic tests and local smoke runs."""

    def __init__(self, users: Iterable[User] = ()) -> None:
        self._lock = RLock()
        self.users = {user.user_id: user for user in users}
        self.refresh_sessions: dict[str, RefreshSession] = {}
        self.advertisements: dict[str, Advertisement] = {}
        self.revisions: dict[str, AdvertisementRevision] = {}
        self.audit_events: list[AuditEvent] = []

    def get_user_by_email(self, email: str) -> User | None:
        normalized = email.casefold()
        return next(
            (user for user in self.users.values() if user.email.casefold() == normalized), None
        )

    def get_user(self, user_id: str) -> User | None:
        return self.users.get(user_id)

    def register_login_failure(self, user: User, now: datetime) -> None:
        with self._lock:
            user.failed_login_count += 1
            user.last_failed_login_at = now
            if user.failed_login_count >= 5:
                user.locked_until = now + timedelta(minutes=15)

    def register_login_success(self, user: User, now: datetime) -> None:
        with self._lock:
            user.failed_login_count = 0
            user.last_failed_login_at = None
            user.locked_until = None
            user.last_login_at = now

    def reset_login_failures(self, user: User, _now: datetime) -> None:
        with self._lock:
            user.failed_login_count = 0
            user.last_failed_login_at = None
            user.locked_until = None

    def save_refresh_session(self, session: RefreshSession) -> None:
        with self._lock:
            self.refresh_sessions[session.token_hash] = session

    def get_refresh_session(self, token_hash: str) -> RefreshSession | None:
        return self.refresh_sessions.get(token_hash)

    def revoke_refresh_session(self, session: RefreshSession, reason: str, now: datetime) -> None:
        with self._lock:
            session.revoked_at = now
            session.revoked_reason = reason

    def revoke_all_refresh_sessions(self, user_id: str, reason: str, now: datetime) -> None:
        with self._lock:
            for session in self.refresh_sessions.values():
                if session.user_id == user_id and session.revoked_at is None:
                    session.revoked_at = now
                    session.revoked_reason = reason

    def add_advertisement(self, advertisement: Advertisement) -> None:
        with self._lock:
            checksums = {
                file.checksum for current in self.advertisements.values() for file in current.files
            }
            if any(file.checksum in checksums for file in advertisement.files):
                raise ValueError("DUPLICATE_FILE")
            self.advertisements[advertisement.advertisement_id] = advertisement

    def get_advertisement(self, advertisement_id: str) -> Advertisement | None:
        advertisement = self.advertisements.get(advertisement_id)
        if advertisement is None:
            return None
        return advertisement

    def add_revision(self, revision: AdvertisementRevision) -> None:
        with self._lock:
            advertisement = self.advertisements.get(revision.advertisement_id)
            if advertisement is None:
                raise ValueError("ADVERTISEMENT_NOT_FOUND")
            if any(
                file.checksum == revision.file.checksum
                for value in self.advertisements.values()
                for file in value.files
            ):
                raise ValueError("DUPLICATE_FILE")
            revision.revision_no = 1 + max(
                (
                    value.revision_no
                    for value in self.revisions.values()
                    if value.advertisement_id == revision.advertisement_id
                ),
                default=0,
            )
            self.revisions[revision.revision_id] = revision
            advertisement.files.append(revision.file)
            advertisement.review_status = "REVISED"

    def get_revision(self, revision_id: str) -> AdvertisementRevision | None:
        return self.revisions.get(revision_id)

    def get_file(self, file_id: str) -> tuple[Advertisement, AdvertisementFile] | None:
        for advertisement in self.advertisements.values():
            for file in advertisement.files:
                if file.file_id == file_id:
                    return advertisement, file
        return None

    def list_advertisements(self, actor: CurrentUser) -> list[Advertisement]:
        unrestricted = bool(set(actor.roles) & {"COMPLIANCE_REVIEWER", "SYSTEM_ADMIN"})
        values = (
            advertisement
            for advertisement in self.advertisements.values()
            if unrestricted
            or advertisement.department_id == actor.department_id
            or advertisement.owner_user_id == actor.user_id
        )
        return sorted(values, key=lambda item: item.created_at, reverse=True)

    def add_audit_event(self, event: AuditEvent) -> None:
        with self._lock:
            self.audit_events.append(event)

    def list_common_codes(self, code_group: str) -> list[dict[str, object]]:
        values = {
            "product-groups": ("DEPOSIT", "SAVINGS", "DEMAND_DEPOSIT", "EVENT"),
            "advertisement-types": (
                "BRANCH_FLYER",
                "NOTICE",
                "MOBILE_BANNER",
                "WEB_BANNER",
                "EVENT_PAGE",
                "PUSH",
                "SMS",
                "ALIMTALK",
            ),
            "review-statuses": ("UPLOADED", "REVISED"),
        }.get(code_group, ())
        return [
            {"code": value, "name": value, "sortOrder": order, "enabled": True}
            for order, value in enumerate(values, 1)
        ]

    def list_audit_events(self) -> list[AuditEvent]:
        return sorted(self.audit_events, key=lambda event: event.created_at, reverse=True)


class PostgresRepository:
    """Product repository using the M2 PostgreSQL owner tables."""

    def __init__(self, engine: Engine, *, storage_provider: str, bucket: str) -> None:
        self._engine = engine
        self._storage_provider = storage_provider
        self._bucket = bucket

    @staticmethod
    def _to_user(row: object) -> User:
        item = row._mapping  # type: ignore[attr-defined]
        return User(
            user_id=item["user_id"],
            user_name=item["user_name"],
            email=item["email"],
            password_hash=item["password_hash"] or "",
            department_id=item["department_id"],
            department_name=item["department_name"],
            roles=tuple(item["roles"] or ()),
            user_status=item["user_status"],
            auth_token_version=item["auth_token_version"],
            failed_login_count=item["failed_login_count"],
            last_failed_login_at=item["last_failed_login_at"],
            locked_until=item["locked_until"],
            last_login_at=item["last_login_at"],
        )

    def _find_user(self, clause: str, value: str) -> User | None:
        statement = text(f"""
            SELECT u.*, d.department_name,
                   ARRAY_AGG(ur.role_id ORDER BY ur.role_id) FILTER (WHERE ur.role_id IS NOT NULL) roles
              FROM app.users u
              JOIN app.departments d ON d.department_id = u.department_id
              LEFT JOIN app.user_roles ur ON ur.user_id = u.user_id
             WHERE {clause} = :value
             GROUP BY u.user_id, d.department_name
        """)
        with self._engine.connect() as connection:
            row = connection.execute(statement, {"value": value}).first()
        return self._to_user(row) if row else None

    def get_user_by_email(self, email: str) -> User | None:
        return self._find_user("LOWER(u.email)", email.casefold())

    def get_user(self, user_id: str) -> User | None:
        return self._find_user("u.user_id", user_id)

    def register_login_failure(self, user: User, now: datetime) -> None:
        count = user.failed_login_count + 1
        locked_until = now + timedelta(minutes=15) if count >= 5 else None
        with self._engine.begin() as connection:
            connection.execute(
                text("""
                UPDATE app.users SET failed_login_count=:count, last_failed_login_at=:now,
                       locked_until=COALESCE(:locked_until, locked_until), updated_at=:now
                 WHERE user_id=:user_id
            """),
                {"count": count, "now": now, "locked_until": locked_until, "user_id": user.user_id},
            )
        user.failed_login_count, user.last_failed_login_at = count, now
        user.locked_until = locked_until or user.locked_until

    def register_login_success(self, user: User, now: datetime) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text("""
                UPDATE app.users SET failed_login_count=0, last_failed_login_at=NULL,
                       locked_until=NULL, last_login_at=:now, updated_at=:now WHERE user_id=:user_id
            """),
                {"now": now, "user_id": user.user_id},
            )
        (
            user.failed_login_count,
            user.last_failed_login_at,
            user.locked_until,
            user.last_login_at,
        ) = 0, None, None, now

    def reset_login_failures(self, user: User, now: datetime) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text("""
                UPDATE app.users SET failed_login_count=0, last_failed_login_at=NULL,
                       locked_until=NULL, updated_at=:now WHERE user_id=:user_id
            """),
                {"now": now, "user_id": user.user_id},
            )
        user.failed_login_count, user.last_failed_login_at, user.locked_until = 0, None, None

    def save_refresh_session(self, session: RefreshSession) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text("""
                INSERT INTO app.refresh_tokens
                (refresh_token_id,user_id,token_hash,issued_at,expires_at,token_version,created_at)
                VALUES (:id,:user_id,:token_hash,:issued_at,:expires_at,:token_version,:issued_at)
            """),
                {
                    "id": UUID(session.session_id),
                    "user_id": session.user_id,
                    "token_hash": session.token_hash,
                    "issued_at": session.issued_at,
                    "expires_at": session.expires_at,
                    "token_version": session.token_version,
                },
            )

    def get_refresh_session(self, token_hash: str) -> RefreshSession | None:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text("SELECT * FROM app.refresh_tokens WHERE token_hash=:token_hash"),
                    {"token_hash": token_hash},
                )
                .mappings()
                .first()
            )
        if not row:
            return None
        return RefreshSession(
            session_id=str(row["refresh_token_id"]),
            user_id=row["user_id"],
            token_hash=row["token_hash"],
            issued_at=row["issued_at"],
            expires_at=row["expires_at"],
            revoked_at=row["revoked_at"],
            revoked_reason=row["revoked_reason"],
            token_version=row["token_version"],
        )

    def revoke_refresh_session(self, session: RefreshSession, reason: str, now: datetime) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE app.refresh_tokens SET revoked_at=:now, revoked_reason=:reason WHERE token_hash=:token_hash AND revoked_at IS NULL"
                ),
                {"now": now, "reason": reason, "token_hash": session.token_hash},
            )
        session.revoked_at, session.revoked_reason = now, reason

    def revoke_all_refresh_sessions(self, user_id: str, reason: str, now: datetime) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text("""
                UPDATE app.refresh_tokens SET revoked_at=:now, revoked_reason=:reason
                 WHERE user_id=:user_id AND revoked_at IS NULL
            """),
                {"now": now, "reason": reason, "user_id": user_id},
            )

    def add_advertisement(self, advertisement: Advertisement) -> None:
        checksums = [file.checksum for file in advertisement.files]
        duplicate_query = text(
            "SELECT 1 FROM app.advertisement_files WHERE checksum_sha256 IN :checksums LIMIT 1"
        ).bindparams(bindparam("checksums", expanding=True))
        with self._engine.begin() as connection:
            if checksums and connection.execute(duplicate_query, {"checksums": checksums}).first():
                raise ValueError("DUPLICATE_FILE")
            connection.execute(
                text("""
                INSERT INTO app.advertisements
                (advertisement_id,advertisement_name,product_group,advertisement_type,channel_type,
                 department_id,owner_user_id,review_status,memo,created_at,created_by,is_deleted)
                VALUES (:advertisement_id,:advertisement_name,:product_group,:advertisement_type,:channel_type,
                        :department_id,:owner_user_id,:review_status,:memo,:created_at,:owner_user_id,false)
            """),
                advertisement.__dict__,
            )
            for file in advertisement.files:
                connection.execute(
                    text("""
                    INSERT INTO app.advertisement_files
                    (file_id,advertisement_id,file_type,original_file_name,storage_provider,bucket,object_key,
                     mime_type,file_size,checksum_sha256,preview_status,created_at,created_by)
                    VALUES (:file_id,:advertisement_id,:file_type,:original_file_name,:storage_provider,:bucket,:storage_key,
                            :mime_type,:file_size,:checksum,'AVAILABLE',:created_at,:created_by)
                """),
                    {
                        **file.__dict__,
                        "advertisement_id": advertisement.advertisement_id,
                        "created_at": advertisement.created_at,
                        "created_by": advertisement.owner_user_id,
                        "storage_provider": self._storage_provider,
                        "bucket": self._bucket,
                    },
                )

    def add_revision(self, revision: AdvertisementRevision) -> None:
        with self._engine.begin() as connection:
            locked_advertisement = connection.execute(
                text(
                    "SELECT advertisement_id FROM app.advertisements "
                    "WHERE advertisement_id=:advertisement_id AND NOT is_deleted FOR UPDATE"
                ),
                {"advertisement_id": revision.advertisement_id},
            ).scalar_one_or_none()
            if locked_advertisement is None:
                raise ValueError("ADVERTISEMENT_NOT_FOUND")
            if connection.execute(
                text(
                    "SELECT 1 FROM app.advertisement_files "
                    "WHERE checksum_sha256=:checksum LIMIT 1"
                ),
                {"checksum": revision.file.checksum},
            ).first():
                raise ValueError("DUPLICATE_FILE")
            revision.revision_no = int(
                connection.execute(
                    text(
                        "SELECT COALESCE(MAX(revision_no),0)+1 "
                        "FROM app.advertisement_revisions "
                        "WHERE advertisement_id=:advertisement_id"
                    ),
                    {"advertisement_id": revision.advertisement_id},
                ).scalar_one()
            )
            connection.execute(
                text("""
                    INSERT INTO app.advertisement_revisions
                    (revision_id,advertisement_id,revision_no,base_review_id,revision_memo,
                     created_at,created_by)
                    VALUES (:revision_id,:advertisement_id,:revision_no,:base_review_id,
                            :revision_memo,:created_at,:created_by)
                """),
                {
                    "revision_id": revision.revision_id,
                    "advertisement_id": revision.advertisement_id,
                    "revision_no": revision.revision_no,
                    "base_review_id": revision.base_review_id,
                    "revision_memo": revision.revision_memo,
                    "created_at": revision.created_at,
                    "created_by": revision.created_by,
                },
            )
            connection.execute(
                text("""
                    INSERT INTO app.advertisement_files
                    (file_id,advertisement_id,revision_id,file_type,original_file_name,
                     storage_provider,bucket,object_key,mime_type,file_size,checksum_sha256,
                     preview_status,created_at,created_by)
                    VALUES (:file_id,:advertisement_id,:revision_id,:file_type,:original_file_name,
                            :storage_provider,:bucket,:storage_key,:mime_type,:file_size,:checksum,
                            'AVAILABLE',:created_at,:created_by)
                """),
                {
                    **revision.file.__dict__,
                    "advertisement_id": revision.advertisement_id,
                    "created_at": revision.created_at,
                    "created_by": revision.created_by,
                    "storage_provider": self._storage_provider,
                    "bucket": self._bucket,
                },
            )
            connection.execute(
                text(
                    "UPDATE app.advertisements "
                    "SET review_status='REVISED',updated_at=:created_at "
                    "WHERE advertisement_id=:advertisement_id"
                ),
                {
                    "created_at": revision.created_at,
                    "advertisement_id": revision.advertisement_id,
                },
            )

    def get_revision(self, revision_id: str) -> AdvertisementRevision | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                text("""
                    SELECT r.*,f.file_id,f.file_type,f.original_file_name,f.object_key,
                           f.mime_type,f.file_size,f.checksum_sha256
                      FROM app.advertisement_revisions r
                      JOIN app.advertisement_files f ON f.revision_id=r.revision_id
                     WHERE r.revision_id=:revision_id
                """),
                {"revision_id": revision_id},
            ).mappings().first()
        if row is None:
            return None
        return AdvertisementRevision(
            revision_id=row["revision_id"],
            advertisement_id=row["advertisement_id"],
            revision_no=row["revision_no"],
            base_review_id=row["base_review_id"],
            revision_memo=row["revision_memo"],
            created_at=row["created_at"],
            created_by=row["created_by"],
            file=AdvertisementFile(
                file_id=row["file_id"],
                file_type=row["file_type"],
                original_file_name=row["original_file_name"],
                storage_key=row["object_key"],
                mime_type=row["mime_type"],
                file_size=row["file_size"],
                checksum=row["checksum_sha256"] or "",
                revision_id=row["revision_id"],
            ),
        )

    @staticmethod
    def _to_advertisement(
        row: object, files: list[AdvertisementFile] | None = None
    ) -> Advertisement:
        item = row._mapping  # type: ignore[attr-defined]
        return Advertisement(
            advertisement_id=item["advertisement_id"],
            advertisement_name=item["advertisement_name"],
            product_group=item["product_group"],
            advertisement_type=item["advertisement_type"],
            channel_type=item["channel_type"],
            department_id=item["department_id"],
            owner_user_id=item["owner_user_id"],
            review_status=item["review_status"],
            memo=item["memo"],
            created_at=item["created_at"],
            files=files or [],
            overall_risk_level=item["overall_risk_level"],
            latest_review_id=item["latest_review_id"],
        )

    def _files(self, advertisement_id: str) -> list[AdvertisementFile]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT * FROM app.advertisement_files WHERE advertisement_id=:id ORDER BY created_at,file_id"
                    ),
                    {"id": advertisement_id},
                )
                .mappings()
                .all()
            )
        return [
            AdvertisementFile(
                file_id=row["file_id"],
                file_type=row["file_type"],
                original_file_name=row["original_file_name"],
                storage_key=row["object_key"],
                mime_type=row["mime_type"],
                file_size=row["file_size"],
                checksum=row["checksum_sha256"] or "",
                revision_id=row["revision_id"],
            )
            for row in rows
        ]

    def get_advertisement(self, advertisement_id: str) -> Advertisement | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT * FROM app.advertisements WHERE advertisement_id=:id AND NOT is_deleted"
                ),
                {"id": advertisement_id},
            ).first()
        return self._to_advertisement(row, self._files(advertisement_id)) if row else None

    def get_file(self, file_id: str) -> tuple[Advertisement, AdvertisementFile] | None:
        with self._engine.connect() as connection:
            row = connection.execute(
                text("SELECT advertisement_id FROM app.advertisement_files WHERE file_id=:id"),
                {"id": file_id},
            ).first()
        if not row:
            return None
        advertisement = self.get_advertisement(row.advertisement_id)
        if advertisement is None:
            return None
        file = next(item for item in advertisement.files if item.file_id == file_id)
        return advertisement, file

    def list_advertisements(self, actor: CurrentUser) -> list[Advertisement]:
        unrestricted = bool(set(actor.roles) & {"COMPLIANCE_REVIEWER", "SYSTEM_ADMIN"})
        with self._engine.connect() as connection:
            rows = connection.execute(
                text("""
                SELECT * FROM app.advertisements
                 WHERE NOT is_deleted
                   AND (:unrestricted OR department_id=:department_id OR owner_user_id=:user_id)
                 ORDER BY created_at DESC
            """),
                {
                    "unrestricted": unrestricted,
                    "department_id": actor.department_id,
                    "user_id": actor.user_id,
                },
            ).all()
        return [self._to_advertisement(row) for row in rows]

    def add_audit_event(self, event: AuditEvent) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text("""
                INSERT INTO audit.audit_logs
                (audit_log_id,user_id,actor_department_id,actor_role,action_type,target_type,target_id,
                 result,reason_code,request_id,metadata_json,created_at)
                VALUES (:audit_log_id,:actor_user_id,:actor_department_id,:actor_role,:action_type,:target_type,
                        :target_id,:result,:reason_code,:trace_id,CAST(:metadata AS jsonb),:created_at)
            """),
                {
                    **event.__dict__,
                    "audit_log_id": UUID(event.audit_log_id),
                    "metadata": json.dumps(event.metadata, separators=(",", ":")),
                },
            )

    def list_common_codes(self, code_group: str) -> list[dict[str, object]]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT code,code_name,sort_order,is_enabled FROM app.common_codes WHERE code_group=:group AND is_enabled ORDER BY sort_order,code"
                    ),
                    {"group": code_group},
                )
                .mappings()
                .all()
            )
        return [
            {
                "code": row["code"],
                "name": row["code_name"],
                "sortOrder": row["sort_order"] or 0,
                "enabled": row["is_enabled"],
            }
            for row in rows
        ]

    def list_audit_events(self) -> list[AuditEvent]:
        with self._engine.connect() as connection:
            rows = (
                connection.execute(text("SELECT * FROM audit.audit_logs ORDER BY created_at DESC"))
                .mappings()
                .all()
            )
        return [
            AuditEvent(
                action_type=row["action_type"],
                result=row["result"],
                reason_code=row["reason_code"],
                actor_user_id=row["user_id"],
                actor_department_id=row["actor_department_id"],
                actor_role=row["actor_role"],
                target_type=row["target_type"],
                target_id=row["target_id"],
                trace_id=row["request_id"] or "unknown",
                created_at=row["created_at"],
                metadata={},
                audit_log_id=str(row["audit_log_id"]),
            )
            for row in rows
        ]


def empty_local_repository() -> InMemoryRepository:
    """Create an empty state; dev/test users must come from explicit seed/setup code."""

    return InMemoryRepository()
