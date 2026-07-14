"""FastAPI application factory for platform health checks."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from nh_ad_backend.settings import Settings, get_settings


class HealthResponse(BaseModel):
    """Non-domain health response used by Compose and deployment probes."""

    status: Literal["ok"] = "ok"
    service: str
    environment: str


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build an application without binding tests to process globals."""

    resolved_settings = settings or get_settings()
    application = FastAPI(
        title="NH Advertisement Compliance API",
        description=(
            "Source contract for the advertisement-compliance PoC. "
            "Capability-specific paths and schemas are added only when their "
            "implementation slice begins."
        ),
        version="0.1.0",
        servers=[{"url": "/api/v1"}],
    )

    @application.get("/health", include_in_schema=False, response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            service=resolved_settings.service_name,
            environment=resolved_settings.app_env,
        )

    return application


app = create_app()
