"""M2 application services: authentication, authorization, audit and advertisements."""

import secrets
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import BinaryIO

from nh_ad_backend.domain import (
    Advertisement,
    AdvertisementFile,
    AdvertisementRevision,
    AuditEvent,
    CurrentUser,
    RefreshSession,
    User,
)
from nh_ad_backend.repository import Repository
from nh_ad_backend.security import (
    LoginRateLimiter,
    TokenError,
    TokenService,
    current_user,
    verify_password,
)
from nh_ad_backend.storage import ObjectStorage, UploadValidationError, validate_upload


class ServiceError(ValueError):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class ProductGroup(StrEnum):
    DEPOSIT = "DEPOSIT"
    SAVINGS = "SAVINGS"
    DEMAND_DEPOSIT = "DEMAND_DEPOSIT"
    EVENT = "EVENT"


class AdvertisementType(StrEnum):
    BRANCH_FLYER = "BRANCH_FLYER"
    NOTICE = "NOTICE"
    MOBILE_BANNER = "MOBILE_BANNER"
    WEB_BANNER = "WEB_BANNER"
    EVENT_PAGE = "EVENT_PAGE"
    PUSH = "PUSH"
    SMS = "SMS"
    ALIMTALK = "ALIMTALK"


class AuthService:
    GENERIC_LOGIN_ERROR = "이메일 또는 비밀번호가 올바르지 않거나 로그인이 제한되었습니다."

    def __init__(
        self,
        repository: Repository,
        tokens: TokenService,
        *,
        now: Callable[[], datetime] | None = None,
        rate_limiter: LoginRateLimiter | None = None,
    ) -> None:
        self.repository = repository
        self.tokens = tokens
        self._now = now or (lambda: datetime.now(UTC))
        self._rate_limiter = rate_limiter or LoginRateLimiter(self._now)

    def login(
        self, email: str, password: str, ip: str, user_agent: str, trace_id: str
    ) -> tuple[str, str, User]:
        now = self._now()
        if not self._rate_limiter.allow(ip):
            self._audit(None, "LOGIN", "DENIED", "RATE_LIMITED", trace_id)
            raise ServiceError(429, "RATE_LIMITED", "잠시 후 다시 시도해 주세요.")
        user = self.repository.get_user_by_email(email)
        if user is None:
            self._audit(None, "LOGIN", "FAILURE", "INVALID_CREDENTIALS", trace_id)
            raise ServiceError(401, "UNAUTHORIZED", self.GENERIC_LOGIN_ERROR)
        if user.user_status != "ACTIVE":
            self._audit(user, "LOGIN", "FAILURE", "USER_INACTIVE", trace_id)
            raise ServiceError(401, "UNAUTHORIZED", self.GENERIC_LOGIN_ERROR)
        if user.locked_until is not None and user.locked_until > now:
            self._audit(user, "LOGIN", "FAILURE", "ACCOUNT_LOCKED", trace_id)
            raise ServiceError(401, "UNAUTHORIZED", self.GENERIC_LOGIN_ERROR)
        if user.locked_until is not None and user.locked_until <= now:
            self.repository.reset_login_failures(user, now)
        if not verify_password(password, user.password_hash):
            self.repository.register_login_failure(user, now)
            reason = "ACCOUNT_LOCKED" if user.locked_until else "INVALID_CREDENTIALS"
            self._audit(user, "LOGIN", "FAILURE", reason, trace_id)
            raise ServiceError(401, "UNAUTHORIZED", self.GENERIC_LOGIN_ERROR)

        self.repository.register_login_success(user, now)
        access_token = self.tokens.issue_access_token(user)
        refresh_token, refresh_hash = self.tokens.new_refresh_token()
        self.repository.save_refresh_session(
            RefreshSession(
                session_id=secrets.token_hex(16),
                user_id=user.user_id,
                token_hash=refresh_hash,
                issued_at=now,
                expires_at=now + self.tokens.refresh_ttl,
                token_version=user.auth_token_version,
            )
        )
        self._audit(user, "LOGIN", "SUCCESS", None, trace_id)
        return access_token, refresh_token, user

    def authenticate(self, access_token: str) -> CurrentUser:
        try:
            claims = self.tokens.verify_access_token(access_token)
        except TokenError as exc:
            raise ServiceError(401, "UNAUTHORIZED", "로그인이 필요합니다.") from exc
        user = self.repository.get_user(str(claims["user_id"]))
        if (
            user is None
            or user.user_status != "ACTIVE"
            or user.auth_token_version != int(claims["token_version"])
        ):
            raise ServiceError(401, "UNAUTHORIZED", "로그인이 필요합니다.")
        return current_user(user)

    def refresh(self, refresh_token: str, trace_id: str) -> tuple[str, str]:
        now = self._now()
        session = self.repository.get_refresh_session(self.tokens.hash_refresh_token(refresh_token))
        if session is None:
            raise ServiceError(401, "UNAUTHORIZED", "로그인이 필요합니다.")
        user = self.repository.get_user(session.user_id)
        if session.revoked_at is not None:
            if user is not None:
                self.repository.revoke_all_refresh_sessions(
                    user.user_id, "REFRESH_TOKEN_REUSE", now
                )
                self._audit(user, "TOKEN_REFRESH", "FAILURE", "REFRESH_TOKEN_REUSE", trace_id)
            raise ServiceError(401, "UNAUTHORIZED", "로그인이 필요합니다.")
        if session.expires_at <= now:
            raise ServiceError(401, "UNAUTHORIZED", "로그인이 필요합니다.")
        if (
            user is None
            or user.user_status != "ACTIVE"
            or session.token_version != user.auth_token_version
        ):
            if user is not None:
                self.repository.revoke_all_refresh_sessions(
                    user.user_id, "TOKEN_VERSION_CHANGED", now
                )
            raise ServiceError(401, "UNAUTHORIZED", "로그인이 필요합니다.")
        new_token, new_hash = self.tokens.new_refresh_token()
        replacement = RefreshSession(
            session_id=secrets.token_hex(16),
            user_id=user.user_id,
            token_hash=new_hash,
            issued_at=now,
            expires_at=now + self.tokens.refresh_ttl,
            token_version=user.auth_token_version,
        )
        if not self.repository.rotate_refresh_session(session, replacement, now):
            self.repository.revoke_all_refresh_sessions(user.user_id, "REFRESH_TOKEN_REUSE", now)
            self._audit(user, "TOKEN_REFRESH", "FAILURE", "REFRESH_TOKEN_REUSE", trace_id)
            raise ServiceError(401, "UNAUTHORIZED", "로그인이 필요합니다.")
        self._audit(user, "TOKEN_REFRESH", "SUCCESS", None, trace_id)
        return self.tokens.issue_access_token(user), new_token

    def logout(self, refresh_token: str, trace_id: str) -> None:
        now = self._now()
        session = self.repository.get_refresh_session(self.tokens.hash_refresh_token(refresh_token))
        if session is None or session.revoked_at is not None:
            return
        self.repository.revoke_refresh_session(session, "LOGOUT", now)
        self._audit(self.repository.get_user(session.user_id), "LOGOUT", "SUCCESS", None, trace_id)

    def _audit(
        self,
        user: User | None,
        action: str,
        result: str,
        reason: str | None,
        trace_id: str,
    ) -> None:
        self.repository.add_audit_event(
            AuditEvent(
                action_type=action,
                result=result,
                reason_code=reason,
                actor_user_id=user.user_id if user else None,
                actor_department_id=user.department_id if user else None,
                actor_role=user.roles[0] if user and user.roles else None,
                target_type="AUTH_SESSION",
                target_id=None,
                trace_id=trace_id,
                created_at=self._now(),
            )
        )


class AuthorizationService:
    ADVERTISEMENT_ROLES = frozenset(
        {"PRODUCT_DEPARTMENT_USER", "COMPLIANCE_REVIEWER", "SYSTEM_ADMIN"}
    )
    CREATE_ROLES = frozenset({"PRODUCT_DEPARTMENT_USER", "COMPLIANCE_REVIEWER"})

    @classmethod
    def can_create_advertisement(cls, actor: CurrentUser, department_id: str) -> bool:
        roles = set(actor.roles)
        if not roles & cls.CREATE_ROLES:
            return False
        return "COMPLIANCE_REVIEWER" in roles or actor.department_id == department_id

    @classmethod
    def can_read_advertisement(cls, actor: CurrentUser, advertisement: Advertisement) -> bool:
        roles = set(actor.roles)
        if not roles & cls.ADVERTISEMENT_ROLES:
            return False
        return bool(roles & {"COMPLIANCE_REVIEWER", "SYSTEM_ADMIN"}) or (
            actor.department_id == advertisement.department_id
            or actor.user_id == advertisement.owner_user_id
        )


class AdvertisementService:
    def __init__(
        self,
        repository: Repository,
        storage: ObjectStorage,
        *,
        now: Callable[[], datetime] | None = None,
        identifier: Callable[[str], str] | None = None,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self._now = now or (lambda: datetime.now(UTC))
        self._identifier = identifier or (lambda prefix: f"{prefix}-{secrets.token_hex(8).upper()}")

    def create(
        self,
        actor: CurrentUser,
        *,
        advertisement_name: str,
        product_group: str,
        advertisement_type: str,
        department_id: str,
        channel_type: str | None,
        memo: str | None,
        uploads: Sequence[tuple[str, str, str | None, BinaryIO]],
        trace_id: str,
    ) -> Advertisement:
        if not all(
            (
                advertisement_name.strip(),
                product_group.strip(),
                advertisement_type.strip(),
                department_id.strip(),
            )
        ):
            raise ServiceError(400, "BAD_REQUEST", "필수 입력값을 확인해 주세요.")
        try:
            ProductGroup(product_group)
            AdvertisementType(advertisement_type)
        except ValueError as exc:
            raise ServiceError(
                400, "BAD_REQUEST", "상품군 또는 광고 유형을 확인해 주세요."
            ) from exc
        if not AuthorizationService.can_create_advertisement(actor, department_id):
            self._audit(actor, "ADVERTISEMENT_CREATE", "DENIED", "DEPARTMENT_SCOPE", None, trace_id)
            raise ServiceError(403, "FORBIDDEN", "접근 권한이 없습니다.")
        if not uploads or not any(file_type == "ADVERTISEMENT" for file_type, *_ in uploads):
            raise ServiceError(400, "BAD_REQUEST", "광고 파일을 첨부해 주세요.")

        stored: list[AdvertisementFile] = []
        seen_checksums: set[str] = set()
        try:
            for file_type, file_name, mime_type, stream in uploads:
                try:
                    validated = validate_upload(file_name, mime_type, stream)
                except UploadValidationError as exc:
                    status_code = (
                        413
                        if exc.code == "FILE_SIZE_EXCEEDED"
                        else 415
                        if exc.code == "FILE_NOT_SUPPORTED"
                        else 400
                    )
                    raise ServiceError(status_code, exc.code, str(exc)) from exc
                if validated.checksum in seen_checksums:
                    raise ServiceError(409, "CONFLICT", "동일한 파일이 중복 첨부되었습니다.")
                seen_checksums.add(validated.checksum)
                storage_key = self.storage.put(validated.body)
                stored.append(
                    AdvertisementFile(
                        file_id=self._identifier("FILE"),
                        file_type=file_type,
                        original_file_name=validated.original_file_name,
                        storage_key=storage_key,
                        mime_type=validated.mime_type,
                        file_size=validated.size,
                        checksum=validated.checksum,
                    )
                )
            advertisement = Advertisement(
                advertisement_id=self._identifier("ADV"),
                advertisement_name=advertisement_name.strip(),
                product_group=product_group,
                advertisement_type=advertisement_type,
                channel_type=channel_type,
                department_id=department_id,
                owner_user_id=actor.user_id,
                review_status="UPLOADED",
                memo=memo,
                created_at=self._now(),
                files=stored,
            )
            try:
                self.repository.add_advertisement(advertisement)
            except ValueError as exc:
                if str(exc) == "DUPLICATE_FILE":
                    raise ServiceError(
                        409, "CONFLICT", "동일한 파일이 이미 등록되어 있습니다."
                    ) from exc
                raise
        except Exception:
            for file in stored:
                self.storage.delete(file.storage_key)
            raise
        self._audit(
            actor,
            "ADVERTISEMENT_CREATE",
            "SUCCESS",
            None,
            advertisement.advertisement_id,
            trace_id,
            {
                "fileCount": str(len(stored)),
                "fileTypes": ",".join(file.file_type for file in stored),
            },
        )
        return advertisement

    def list(self, actor: CurrentUser) -> list[Advertisement]:
        return [
            advertisement
            for advertisement in self.repository.list_advertisements(actor)
            if AuthorizationService.can_read_advertisement(actor, advertisement)
        ]

    def create_revision(
        self,
        actor: CurrentUser,
        advertisement_id: str,
        *,
        revision_memo: str | None,
        upload: tuple[str, str | None, BinaryIO],
        trace_id: str,
    ) -> AdvertisementRevision:
        advertisement = self.repository.get_advertisement(advertisement_id)
        if advertisement is None:
            raise ServiceError(404, "NOT_FOUND", "요청한 대상을 찾을 수 없습니다.")
        if not AuthorizationService.can_read_advertisement(actor, advertisement):
            self._audit(
                actor,
                "ADVERTISEMENT_REVISION_CREATE",
                "DENIED",
                "DEPARTMENT_SCOPE",
                advertisement_id,
                trace_id,
            )
            raise ServiceError(403, "FORBIDDEN", "접근 권한이 없습니다.")
        file_name, mime_type, stream = upload
        try:
            validated = validate_upload(file_name, mime_type, stream)
        except UploadValidationError as exc:
            status_code = (
                413
                if exc.code == "FILE_SIZE_EXCEEDED"
                else 415
                if exc.code == "FILE_NOT_SUPPORTED"
                else 400
            )
            raise ServiceError(status_code, exc.code, str(exc)) from exc
        revision_id = self._identifier("REVISION")
        storage_key = self.storage.put(validated.body)
        revision = AdvertisementRevision(
            revision_id=revision_id,
            advertisement_id=advertisement_id,
            revision_no=0,
            base_review_id=advertisement.latest_review_id,
            revision_memo=revision_memo.strip() if revision_memo else None,
            created_at=self._now(),
            created_by=actor.user_id,
            file=AdvertisementFile(
                file_id=self._identifier("FILE"),
                file_type="ADVERTISEMENT",
                original_file_name=validated.original_file_name,
                storage_key=storage_key,
                mime_type=validated.mime_type,
                file_size=validated.size,
                checksum=validated.checksum,
                revision_id=revision_id,
            ),
        )
        try:
            self.repository.add_revision(revision)
        except ValueError as exc:
            self.storage.delete(storage_key)
            if str(exc) == "DUPLICATE_FILE":
                raise ServiceError(
                    409, "CONFLICT", "동일한 파일이 이미 등록되어 있습니다."
                ) from exc
            raise
        except Exception:
            self.storage.delete(storage_key)
            raise
        self._audit(
            actor,
            "ADVERTISEMENT_REVISION_CREATE",
            "SUCCESS",
            None,
            revision.revision_id,
            trace_id,
            {"revisionNo": str(revision.revision_no), "fileType": revision.file.file_type},
        )
        return revision

    def get(self, actor: CurrentUser, advertisement_id: str, trace_id: str) -> Advertisement:
        advertisement = self.repository.get_advertisement(advertisement_id)
        if advertisement is None:
            raise ServiceError(404, "NOT_FOUND", "요청한 대상을 찾을 수 없습니다.")
        if not AuthorizationService.can_read_advertisement(actor, advertisement):
            self._audit(
                actor,
                "ADVERTISEMENT_READ",
                "DENIED",
                "DEPARTMENT_SCOPE",
                advertisement_id,
                trace_id,
            )
            raise ServiceError(403, "FORBIDDEN", "접근 권한이 없습니다.")
        return advertisement

    def open_file(
        self,
        actor: CurrentUser,
        file_id: str,
        trace_id: str,
        action_type: str,
    ) -> tuple[AdvertisementFile, BinaryIO]:
        if action_type not in {"FILE_PREVIEW", "FILE_DOWNLOAD"}:
            raise ValueError("invalid file audit action")
        found = self.repository.get_file(file_id)
        if found is None:
            raise ServiceError(404, "NOT_FOUND", "요청한 대상을 찾을 수 없습니다.")
        advertisement, raw_file = found
        file = raw_file
        if not isinstance(file, AdvertisementFile):
            raise TypeError("repository returned an invalid file record")
        if not AuthorizationService.can_read_advertisement(actor, advertisement):
            self._audit(actor, action_type, "DENIED", "DEPARTMENT_SCOPE", file_id, trace_id)
            raise ServiceError(403, "FORBIDDEN", "접근 권한이 없습니다.")
        self._audit(
            actor,
            action_type,
            "SUCCESS",
            None,
            file_id,
            trace_id,
            {
                "fileType": file.file_type,
                "mimeType": file.mime_type,
                "fileSize": str(file.file_size),
            },
        )
        return file, self.storage.open(file.storage_key)

    def _audit(
        self,
        actor: CurrentUser,
        action: str,
        result: str,
        reason: str | None,
        target_id: str | None,
        trace_id: str,
        metadata: dict[str, str] | None = None,
    ) -> None:
        self.repository.add_audit_event(
            AuditEvent(
                action_type=action,
                result=result,
                reason_code=reason,
                actor_user_id=actor.user_id,
                actor_department_id=actor.department_id,
                actor_role=actor.roles[0] if actor.roles else None,
                target_type=(
                    "ADVERTISEMENT_REVISION"
                    if action == "ADVERTISEMENT_REVISION_CREATE"
                    else "ADVERTISEMENT"
                    if action.startswith("ADVERTISEMENT")
                    else "FILE"
                ),
                target_id=target_id,
                trace_id=trace_id,
                created_at=self._now(),
                metadata=metadata or {},
            )
        )
