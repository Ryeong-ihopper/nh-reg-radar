"""Worker health and readiness process."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Response, status
from pydantic import BaseModel

from nh_ad_worker.queue import QueueReadiness, RedisQueueReadiness
from nh_ad_worker.settings import Settings, get_settings


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    environment: str


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    queue: Literal["ready", "not_ready"]


def create_app(
    settings: Settings | None = None,
    queue_readiness: QueueReadiness | None = None,
) -> FastAPI:
    """Create a probe process around the future queue consumer boundary."""

    resolved_settings = settings or get_settings()
    queue = queue_readiness or RedisQueueReadiness(resolved_settings.redis_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        close = getattr(queue, "close", None)
        if close is not None:
            await close()

    application = FastAPI(
        title="NH Advertisement Compliance Worker",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    @application.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            service=resolved_settings.service_name,
            environment=resolved_settings.app_env,
        )

    @application.get("/ready", response_model=ReadinessResponse)
    async def ready(response: Response) -> ReadinessResponse:
        if await queue.ready():
            return ReadinessResponse(status="ready", queue="ready")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(status="not_ready", queue="not_ready")

    return application


app = create_app()
