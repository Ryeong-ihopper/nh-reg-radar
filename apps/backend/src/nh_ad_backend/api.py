"""HTTP boundary for the capability-local M2 OpenAPI contract."""

import math
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import APIKeyCookie, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from nh_ad_backend.domain import (
    Advertisement as AdvertisementRecord,
    AdvertisementFile as AdvertisementFileRecord,
    AuditEvent,
    CurrentUser,
    User,
)
from nh_ad_backend.multipart import MultipartError, parse_multipart
from nh_ad_backend.repository import Repository
from nh_ad_backend.services import AdvertisementService, AuthService, ServiceError
from nh_ad_backend.settings import Settings
from nh_ad_backend.standards import StandardService


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class LoginRequest(ContractModel):
    email: str = Field(max_length=255, json_schema_extra={"format": "email"})
    password: str = Field(min_length=10, max_length=256, json_schema_extra={"writeOnly": True})


class Role(StrEnum):
    PRODUCT_DEPARTMENT_USER = "PRODUCT_DEPARTMENT_USER"
    COMPLIANCE_REVIEWER = "COMPLIANCE_REVIEWER"
    STANDARD_MANAGER = "STANDARD_MANAGER"
    SYSTEM_ADMIN = "SYSTEM_ADMIN"


class CodeGroup(StrEnum):
    PRODUCT_GROUPS = "product-groups"
    ADVERTISEMENT_TYPES = "advertisement-types"
    REVIEW_STATUSES = "review-statuses"


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


class ReviewStatus(StrEnum):
    UPLOADED = "UPLOADED"
    REVISED = "REVISED"


class FileType(StrEnum):
    ADVERTISEMENT = "ADVERTISEMENT"
    PRODUCT_DESCRIPTION = "PRODUCT_DESCRIPTION"
    TERMS = "TERMS"
    ADDITIONAL = "ADDITIONAL"


class UserContext(ContractModel):
    user_id: str = Field(alias="userId")
    user_name: str = Field(alias="userName")
    department_id: str = Field(alias="departmentId")
    department_name: str = Field(alias="departmentName")
    roles: list[Role] = Field(min_length=1, json_schema_extra={"uniqueItems": True})


class AccessTokenResponse(ContractModel):
    access_token: str = Field(alias="accessToken", min_length=1)
    token_type: Literal["Bearer"] = Field(alias="tokenType")
    expires_in: Literal[1800] = Field(alias="expiresIn")


class AuthTokenResponse(AccessTokenResponse):
    user: UserContext


class CommonCode(ContractModel):
    code: str
    name: str
    sort_order: int = Field(alias="sortOrder")
    enabled: bool


class AdvertisementFile(ContractModel):
    file_id: str = Field(alias="fileId")
    file_type: FileType = Field(alias="fileType")
    file_name: str = Field(alias="fileName")
    mime_type: str = Field(alias="mimeType")
    file_size: int = Field(alias="fileSize", ge=0, le=52_428_800)


class AdvertisementSummary(ContractModel):
    advertisement_id: str = Field(alias="advertisementId")
    advertisement_name: str = Field(alias="advertisementName")
    product_group: ProductGroup = Field(alias="productGroup")
    advertisement_type: AdvertisementType = Field(alias="advertisementType")
    department_id: str = Field(alias="departmentId")
    registered_by: str = Field(alias="registeredBy")
    registered_at: datetime = Field(alias="registeredAt")
    review_status: ReviewStatus = Field(alias="reviewStatus")


class AdvertisementPage(ContractModel):
    contents: list[AdvertisementSummary]
    page: int = Field(ge=1)
    size: int = Field(ge=1)
    total_elements: int = Field(alias="totalElements", ge=0)
    total_pages: int = Field(alias="totalPages", ge=0)


class AdvertisementCreated(ContractModel):
    advertisement_id: str = Field(alias="advertisementId")
    advertisement_name: str = Field(alias="advertisementName")
    review_status: ReviewStatus = Field(alias="reviewStatus")
    files: list[AdvertisementFile] = Field(min_length=1)
    created_at: datetime = Field(alias="createdAt")


class AdvertisementDetail(AdvertisementSummary):
    channel_type: str | None = Field(None, alias="channelType")
    memo: str | None = None
    files: list[AdvertisementFile]


class FilePreview(ContractModel):
    file_id: str = Field(alias="fileId")
    page_no: int = Field(alias="pageNo", ge=1)
    total_pages: int = Field(alias="totalPages", ge=1)
    preview_path: str = Field(alias="previewPath", pattern=r"^/api/v1/files/[^/]+/preview/content$")
    width: int | None = Field(None, ge=1)
    height: int | None = Field(None, ge=1)


class AuditLogSummary(ContractModel):
    audit_log_id: str = Field(alias="auditLogId", json_schema_extra={"format": "uuid"})
    actor_id: str | None = Field(None, alias="actorId")
    actor_department_id: str | None = Field(None, alias="actorDepartmentId")
    actor_role: Role | None = Field(None, alias="actorRole")
    action_type: str = Field(alias="actionType")
    target_type: str = Field(alias="targetType")
    target_id: str | None = Field(None, alias="targetId")
    result: Literal["SUCCESS", "FAILURE", "DENIED"]
    reason_code: str | None = Field(None, alias="reasonCode")
    trace_id: str = Field(alias="traceId")
    created_at: datetime = Field(alias="createdAt")


class AuditLogPage(ContractModel):
    contents: list[AuditLogSummary]
    page: int = Field(ge=1)
    size: int = Field(ge=1)
    total_elements: int = Field(alias="totalElements", ge=0)
    total_pages: int = Field(alias="totalPages", ge=0)


class ErrorResponse(ContractModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: list[dict[str, object]] = Field(default_factory=list)
    trace_id: str = Field(alias="traceId", min_length=1)
    timestamp: datetime


class CreateAdvertisementRequest(ContractModel):
    advertisement_name: str = Field(alias="advertisementName", min_length=1, max_length=300)
    product_group: ProductGroup = Field(alias="productGroup")
    advertisement_type: AdvertisementType = Field(alias="advertisementType")
    department_id: str = Field(alias="departmentId", max_length=50)
    channel_type: str | None = Field(None, alias="channelType", max_length=50)
    memo: str | None = Field(None, max_length=2000)
    advertisement_file: bytes = Field(
        alias="advertisementFile",
        json_schema_extra={
            "format": "binary",
            "description": "jpg/jpeg/png/pdf/hwp/hwpx; maximum 50 MiB.",
        },
    )
    product_description_file: bytes | None = Field(
        None, alias="productDescriptionFile", json_schema_extra={"format": "binary"}
    )
    terms_file: bytes | None = Field(
        None, alias="termsFile", json_schema_extra={"format": "binary"}
    )
    additional_files: list[bytes] | None = Field(None, alias="additionalFiles", max_length=10)


def error_models(*statuses: int) -> dict[int | str, dict[str, Any]]:
    return {status: {"model": ErrorResponse} for status in statuses}


@dataclass(frozen=True)
class ApplicationServices:
    repository: Repository
    auth: AuthService
    advertisements: AdvertisementService
    standards: StandardService


def _user_response(user: User | CurrentUser) -> UserContext:
    return UserContext(
        userId=user.user_id,
        userName=user.user_name,
        departmentId=user.department_id,
        departmentName=user.department_name,
        roles=[Role(role) for role in user.roles],
    )


def _file_response(file: AdvertisementFileRecord) -> dict[str, object]:
    return {
        "fileId": file.file_id,
        "fileType": file.file_type,
        "fileName": file.original_file_name,
        "mimeType": file.mime_type,
        "fileSize": file.file_size,
    }


def _summary(advertisement: AdvertisementRecord) -> dict[str, object]:
    return {
        "advertisementId": advertisement.advertisement_id,
        "advertisementName": advertisement.advertisement_name,
        "productGroup": advertisement.product_group,
        "advertisementType": advertisement.advertisement_type,
        "departmentId": advertisement.department_id,
        "registeredBy": advertisement.owner_user_id,
        "registeredAt": advertisement.created_at,
        "reviewStatus": advertisement.review_status,
    }


def error_response(request: Request, status_code: int, code: str, message: str) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", "unknown")
    headers = {"Cache-Control": "no-store"}
    if status_code == 429:
        headers["Retry-After"] = "60"
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "code": code,
            "message": message,
            "traceId": trace_id,
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        },
    )


def install_routes(
    router: APIRouter,
    services: ApplicationServices,
    settings: Settings,
) -> None:
    bearer_scheme = HTTPBearer(auto_error=False, scheme_name="BearerAuth", bearerFormat="JWT")
    refresh_cookie_scheme = APIKeyCookie(
        name="refreshToken", auto_error=False, scheme_name="RefreshCookie"
    )

    async def actor(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
    ) -> CurrentUser:
        if credentials is None or credentials.scheme.casefold() != "bearer":
            raise ServiceError(401, "UNAUTHORIZED", "로그인이 필요합니다.")
        return services.auth.authenticate(credentials.credentials)

    def check_origin(origin: str | None, referer: str | None) -> None:
        candidate = origin.rstrip("/") if origin else None
        if candidate is None and referer:
            candidate = next(
                (
                    allowed
                    for allowed in settings.allowed_origins
                    if referer.startswith(f"{allowed}/")
                ),
                None,
            )
        if candidate not in settings.allowed_origins:
            raise ServiceError(403, "FORBIDDEN", "허용되지 않은 요청 출처입니다.")

    Actor = Annotated[CurrentUser, Depends(actor)]

    from nh_ad_backend.standards_api import install_standard_routes

    install_standard_routes(router, services.standards, actor)

    @router.post(
        "/auth/login",
        response_model=AuthTokenResponse,
        operation_id="login",
        responses={
            200: {"headers": {"Set-Cookie": {"schema": {"type": "string"}}}},
            **error_models(401),
            429: {
                "model": ErrorResponse,
                "headers": {"Retry-After": {"schema": {"type": "integer", "minimum": 1}}},
            },
        },
    )
    async def login(
        payload: LoginRequest, request: Request, response: Response
    ) -> AuthTokenResponse:
        access_token, refresh_token, user = services.auth.login(
            payload.email,
            payload.password,
            request.client.host if request.client else "unknown",
            request.headers.get("user-agent", ""),
            request.state.trace_id,
        )
        response.set_cookie(
            "refreshToken",
            refresh_token,
            max_age=7 * 24 * 60 * 60,
            httponly=True,
            secure=settings.refresh_cookie_secure,
            samesite="lax",
            path="/api/v1/auth",
        )
        response.headers["Cache-Control"] = "no-store"
        return AuthTokenResponse(
            accessToken=access_token,
            tokenType="Bearer",
            expiresIn=1800,
            user=_user_response(user),
        )

    @router.post(
        "/auth/refresh",
        response_model=AccessTokenResponse,
        operation_id="refreshAccessToken",
        responses={
            200: {"headers": {"Set-Cookie": {"schema": {"type": "string"}}}},
            **error_models(401, 403),
        },
    )
    async def refresh(
        request: Request,
        response: Response,
        refresh_token: Annotated[str | None, Depends(refresh_cookie_scheme)] = None,
        origin: Annotated[str | None, Header(alias="Origin")] = None,
        referer: Annotated[str | None, Header(alias="Referer", include_in_schema=False)] = None,
    ) -> AccessTokenResponse:
        check_origin(origin, referer)
        if not refresh_token:
            raise ServiceError(401, "UNAUTHORIZED", "로그인이 필요합니다.")
        access_token, rotated_token = services.auth.refresh(refresh_token, request.state.trace_id)
        response.set_cookie(
            "refreshToken",
            rotated_token,
            max_age=7 * 24 * 60 * 60,
            httponly=True,
            secure=settings.refresh_cookie_secure,
            samesite="lax",
            path="/api/v1/auth",
        )
        response.headers["Cache-Control"] = "no-store"
        return AccessTokenResponse(
            accessToken=access_token,
            tokenType="Bearer",
            expiresIn=1800,
        )

    @router.post(
        "/auth/logout",
        status_code=204,
        operation_id="logout",
        responses={
            204: {"headers": {"Set-Cookie": {"schema": {"type": "string"}}}},
            **error_models(401, 403),
        },
    )
    async def logout(
        request: Request,
        response: Response,
        refresh_token: Annotated[str | None, Depends(refresh_cookie_scheme)] = None,
        origin: Annotated[str | None, Header(alias="Origin")] = None,
        referer: Annotated[str | None, Header(alias="Referer", include_in_schema=False)] = None,
    ) -> None:
        check_origin(origin, referer)
        if not refresh_token:
            raise ServiceError(401, "UNAUTHORIZED", "로그인이 필요합니다.")
        services.auth.logout(refresh_token, request.state.trace_id)
        response.delete_cookie("refreshToken", path="/api/v1/auth")

    @router.get(
        "/users/me",
        response_model=UserContext,
        operation_id="getCurrentUser",
        responses=error_models(401),
    )
    async def get_me(current: Actor) -> UserContext:
        return _user_response(current)

    @router.get(
        "/codes/{codeGroup}",
        response_model=list[CommonCode],
        operation_id="listCommonCodes",
        responses=error_models(401, 404),
    )
    async def list_codes(
        code_group: Annotated[CodeGroup, Path(alias="codeGroup")],
        _current: Actor,
    ) -> list[dict[str, object]]:
        values = services.repository.list_common_codes(code_group.value)
        if not values:
            raise ServiceError(404, "NOT_FOUND", "요청한 대상을 찾을 수 없습니다.")
        return values

    @router.get(
        "/advertisements",
        response_model=AdvertisementPage,
        operation_id="listAdvertisements",
        responses=error_models(401),
    )
    async def list_advertisements(
        current: Actor,
        keyword: Annotated[str | None, Query(max_length=300)] = None,
        product_group: Annotated[ProductGroup | None, Query(alias="productGroup")] = None,
        advertisement_type: Annotated[
            AdvertisementType | None, Query(alias="advertisementType")
        ] = None,
        review_status: Annotated[ReviewStatus | None, Query(alias="reviewStatus")] = None,
        page: Annotated[int, Query(ge=1)] = 1,
        size: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> dict[str, object]:
        values = services.advertisements.list(current)
        if keyword:
            values = [
                item for item in values if keyword.casefold() in item.advertisement_name.casefold()
            ]
        if product_group:
            values = [item for item in values if item.product_group == product_group.value]
        if advertisement_type:
            values = [
                item for item in values if item.advertisement_type == advertisement_type.value
            ]
        if review_status:
            values = [item for item in values if item.review_status == review_status.value]
        total = len(values)
        contents = values[(page - 1) * size : page * size]
        return {
            "contents": [_summary(item) for item in contents],
            "page": page,
            "size": size,
            "totalElements": total,
            "totalPages": math.ceil(total / size),
        }

    @router.post(
        "/advertisements",
        status_code=201,
        response_model=AdvertisementCreated,
        operation_id="createAdvertisement",
        responses=error_models(400, 401, 403, 409, 413, 415),
    )
    async def create_advertisement(
        request: Request,
        current: Actor,
    ) -> dict[str, object]:
        try:
            form = await parse_multipart(request)
        except MultipartError as exc:
            raise ServiceError(exc.status_code, exc.code, str(exc)) from exc
        file_fields = (
            ("ADVERTISEMENT", "advertisementFile"),
            ("PRODUCT_DESCRIPTION", "productDescriptionFile"),
            ("TERMS", "termsFile"),
            ("ADDITIONAL", "additionalFiles"),
        )
        uploads = [
            (file_type, file.file_name, file.content_type, file.stream)
            for file_type, field_name in file_fields
            for file in form.files.get(field_name, [])
        ]
        advertisement = services.advertisements.create(
            current,
            advertisement_name=form.fields.get("advertisementName", ""),
            product_group=form.fields.get("productGroup", ""),
            advertisement_type=form.fields.get("advertisementType", ""),
            department_id=form.fields.get("departmentId", ""),
            channel_type=form.fields.get("channelType"),
            memo=form.fields.get("memo"),
            uploads=uploads,
            trace_id=request.state.trace_id,
        )
        return {
            "advertisementId": advertisement.advertisement_id,
            "advertisementName": advertisement.advertisement_name,
            "reviewStatus": advertisement.review_status,
            "files": [_file_response(file) for file in advertisement.files],
            "createdAt": advertisement.created_at,
        }

    @router.get(
        "/advertisements/{advertisementId}",
        response_model=AdvertisementDetail,
        operation_id="getAdvertisement",
        responses=error_models(401, 403, 404),
    )
    async def get_advertisement(
        advertisement_id: Annotated[
            str, Path(alias="advertisementId", pattern=r"^ADV-[A-Za-z0-9-]+$")
        ],
        request: Request,
        current: Actor,
    ) -> dict[str, object]:
        advertisement = services.advertisements.get(
            current, advertisement_id, request.state.trace_id
        )
        return {
            **_summary(advertisement),
            "channelType": advertisement.channel_type,
            "memo": advertisement.memo,
            "files": [_file_response(file) for file in advertisement.files],
        }

    @router.get(
        "/files/{fileId}/preview",
        response_model=FilePreview,
        operation_id="getFilePreview",
        responses=error_models(401, 403, 404),
    )
    async def get_file_preview(
        file_id: Annotated[str, Path(alias="fileId", pattern=r"^FILE-[A-Za-z0-9-]+$")],
        request: Request,
        current: Actor,
        page_no: Annotated[int, Query(alias="pageNo", ge=1)] = 1,
    ) -> dict[str, object]:
        file, stream = services.advertisements.open_file(
            current, file_id, request.state.trace_id, "FILE_PREVIEW"
        )
        stream.close()
        return {
            "fileId": file.file_id,
            "pageNo": page_no,
            "totalPages": 1,
            "previewPath": f"/api/v1/files/{file.file_id}/preview/content",
            "width": None,
            "height": None,
        }

    @router.get(
        "/files/{fileId}/preview/content",
        operation_id="getFilePreviewContent",
        response_class=StreamingResponse,
        responses={
            200: {"content": {"image/png": {"schema": {"type": "string", "format": "binary"}}}},
            **error_models(401, 403, 404),
        },
    )
    async def get_file_preview_content(
        file_id: Annotated[str, Path(alias="fileId", pattern=r"^FILE-[A-Za-z0-9-]+$")],
        request: Request,
        current: Actor,
        page_no: Annotated[int, Query(alias="pageNo", ge=1)],
    ) -> StreamingResponse:
        del page_no
        file, stream = services.advertisements.open_file(
            current, file_id, request.state.trace_id, "FILE_PREVIEW"
        )
        if file.mime_type != "image/png":
            stream.close()
            raise ServiceError(400, "FILE_READ_FAILED", "미리보기를 생성할 수 없습니다.")
        return StreamingResponse(
            stream, media_type="image/png", headers={"Cache-Control": "no-store"}
        )

    @router.get(
        "/files/{fileId}/download",
        operation_id="downloadFile",
        response_class=StreamingResponse,
        responses={
            200: {
                "content": {
                    "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
                },
                "headers": {"Content-Disposition": {"schema": {"type": "string"}}},
            },
            **error_models(401, 403, 404),
        },
    )
    async def download_file(
        file_id: Annotated[str, Path(alias="fileId", pattern=r"^FILE-[A-Za-z0-9-]+$")],
        request: Request,
        current: Actor,
    ) -> StreamingResponse:
        file, stream = services.advertisements.open_file(
            current, file_id, request.state.trace_id, "FILE_DOWNLOAD"
        )

        def body() -> Iterator[bytes]:
            try:
                while chunk := stream.read(1024 * 1024):
                    yield chunk
            finally:
                stream.close()

        encoded_name = quote(file.original_file_name, safe="")
        return StreamingResponse(
            body(),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @router.get(
        "/admin/audit-logs",
        response_model=AuditLogPage,
        operation_id="listAuditLogs",
        responses=error_models(401, 403),
    )
    async def list_audit_logs(
        request: Request,
        current: Actor,
        user_id: Annotated[str | None, Query(alias="userId")] = None,
        action_type: Annotated[str | None, Query(alias="actionType")] = None,
        from_date: Annotated[date | None, Query(alias="fromDate")] = None,
        to_date: Annotated[date | None, Query(alias="toDate")] = None,
        page: Annotated[int, Query(ge=1)] = 1,
        size: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> dict[str, object]:
        if "SYSTEM_ADMIN" not in current.roles:
            services.repository.add_audit_event(
                AuditEvent(
                    action_type="AUDIT_LOG_READ",
                    result="DENIED",
                    reason_code="ROLE_REQUIRED",
                    actor_user_id=current.user_id,
                    actor_department_id=current.department_id,
                    actor_role=current.roles[0] if current.roles else None,
                    target_type="AUDIT_LOG",
                    target_id=None,
                    trace_id=request.state.trace_id,
                    created_at=datetime.now(UTC),
                )
            )
            raise ServiceError(403, "FORBIDDEN", "접근 권한이 없습니다.")
        events = services.repository.list_audit_events()
        if user_id:
            events = [event for event in events if event.actor_user_id == user_id]
        if action_type:
            events = [event for event in events if event.action_type == action_type]
        if from_date:
            events = [event for event in events if event.created_at.date() >= from_date]
        if to_date:
            events = [event for event in events if event.created_at.date() <= to_date]
        total = len(events)
        contents = events[(page - 1) * size : page * size]
        return {
            "contents": [_audit_response(event) for event in contents],
            "page": page,
            "size": size,
            "totalElements": total,
            "totalPages": math.ceil(total / size),
        }


def _audit_response(event: AuditEvent) -> dict[str, object]:
    return {
        "auditLogId": event.audit_log_id,
        "actorId": event.actor_user_id,
        "actorDepartmentId": event.actor_department_id,
        "actorRole": event.actor_role,
        "actionType": event.action_type,
        "targetType": event.target_type or "UNKNOWN",
        "targetId": event.target_id,
        "result": event.result,
        "reasonCode": event.reason_code,
        "traceId": event.trace_id,
        "createdAt": event.created_at,
    }
