"""FastAPI application factory for health and the M2 vertical slice."""

import secrets
from typing import Literal

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import create_engine

from nh_ad_backend.api import ApplicationServices, error_response, install_routes
from nh_ad_backend.openapi_runtime import generated_openapi
from nh_ad_backend.repository import InMemoryRepository, PostgresRepository, Repository
from nh_ad_backend.s3_storage import S3ObjectStorage
from nh_ad_backend.security import TokenService
from nh_ad_backend.services import AdvertisementService, AuthService, ServiceError
from nh_ad_backend.settings import Settings, get_settings
from nh_ad_backend.storage import ObjectStorage, PrivateFileStorage


class HealthResponse(BaseModel):
    """Non-domain health response used by Compose and deployment probes."""

    status: Literal["ok"] = "ok"
    service: str
    environment: str


def build_services(settings: Settings) -> ApplicationServices:
    product_environment = settings.app_env in {"dev", "prod"}
    if product_environment and settings.nh_db_runtime_url is None:
        raise ValueError("NH_DB_RUNTIME_URL is required outside tests")
    if product_environment and settings.jwt_secret is None:
        raise ValueError("JWT_SECRET is required outside tests")
    storage_configured = bool(
        settings.object_storage_endpoint
        and settings.object_storage_access_key
        and settings.object_storage_secret_key
    )
    if product_environment and not storage_configured:
        raise ValueError("private object storage configuration is required outside tests")
    if settings.nh_db_runtime_url is not None:
        engine = create_engine(settings.nh_db_runtime_url.get_secret_value(), pool_pre_ping=True)
        repository: Repository = PostgresRepository(
            engine,
            storage_provider="minio",
            bucket=settings.ad_originals_bucket,
        )
    else:
        repository = InMemoryRepository()
    if storage_configured:
        assert settings.object_storage_endpoint is not None
        assert settings.object_storage_access_key is not None
        assert settings.object_storage_secret_key is not None
        storage: ObjectStorage = S3ObjectStorage(
            settings.object_storage_endpoint,
            settings.object_storage_access_key.get_secret_value(),
            settings.object_storage_secret_key.get_secret_value(),
            settings.ad_originals_bucket,
            region=settings.object_storage_region,
        )
    else:
        storage = PrivateFileStorage(settings.private_storage_path)
    jwt_secret = (
        settings.jwt_secret.get_secret_value()
        if settings.jwt_secret is not None
        else secrets.token_urlsafe(48)
    )
    tokens = TokenService(jwt_secret)
    return ApplicationServices(
        repository=repository,
        auth=AuthService(repository, tokens),
        advertisements=AdvertisementService(repository, storage),
    )


def create_app(
    settings: Settings | None = None,
    services: ApplicationServices | None = None,
) -> FastAPI:
    """Build an application without binding tests to process globals."""

    resolved_settings = settings or get_settings()
    application = FastAPI(
        title="NH Advertisement Compliance API",
        description=(
            "Source contract for the advertisement-compliance PoC. "
            "Capability-specific paths and schemas are added only when their "
            "implementation slice begins."
        ),
        version="0.2.0",
        root_path="/api/v1",
        servers=[{"url": "/api/v1"}],
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
    )

    @application.middleware("http")
    async def request_security(request: Request, call_next: object) -> object:
        request.state.trace_id = (
            request.headers.get("x-request-id") or f"req-{secrets.token_hex(12)}"
        )
        response = await call_next(request)  # type: ignore[operator]
        response.headers["X-Request-Id"] = request.state.trace_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
        if request.url.path != "/health":
            response.headers["Cache-Control"] = "no-store"
        if resolved_settings.app_env == "prod":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @application.exception_handler(ServiceError)
    async def handle_service_error(request: Request, exc: ServiceError) -> JSONResponse:
        return error_response(request, exc.status_code, exc.code, exc.message)

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, _exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(request, 400, "BAD_REQUEST", "요청값을 확인해 주세요.")

    @application.get("/health", include_in_schema=False, response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            service=resolved_settings.service_name,
            environment=resolved_settings.app_env,
        )

    api_router = APIRouter()
    install_routes(api_router, services or build_services(resolved_settings), resolved_settings)
    application.include_router(api_router)
    setattr(application, "openapi", lambda: generated_openapi(application))

    return application
