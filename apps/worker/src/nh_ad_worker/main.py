"""Worker health, readiness, and supervised queue-consumer process."""

import asyncio
import logging
from collections.abc import AsyncIterator
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Literal

from fastapi import FastAPI, Response, status
from nh_ad_parser_contracts import ArtifactStore, ParserRouter
from pydantic import BaseModel
from sqlalchemy import create_engine

from nh_ad_worker.jobs import ParserJobProcessor
from nh_ad_worker.object_storage import S3ArtifactStorage
from nh_ad_worker.postgres import (
    PostgresArtifactAudit,
    PostgresArtifactMetadataRepository,
    PostgresJobRepository,
)
from nh_ad_worker.queue import (
    QueueReadiness,
    RedisDeadLetterSink,
    RedisJobQueue,
    RedisQueueReadiness,
)
from nh_ad_worker.results import ReviewResultEngine
from nh_ad_worker.runtime import JobRunner, Runner
from nh_ad_worker.settings import Settings, get_settings


LOGGER = logging.getLogger(__name__)


class RunnerConfigurationError(RuntimeError):
    """A production consumer dependency is intentionally unavailable."""


RunnerFactory = Callable[[Settings], Runner]


@dataclass
class ConsumerState:
    runner: Runner | None = None
    task: asyncio.Task[None] | None = None
    startup_error: Exception | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    environment: str


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    queue: Literal["ready", "not_ready"]
    consumer: Literal["ready", "not_ready"]


def compose_job_runner(settings: Settings, router: ParserRouter) -> JobRunner:
    """Compose the provider-independent runtime around explicitly supplied adapters."""

    database_url = (
        settings.nh_db_runtime_url.get_secret_value()
        if settings.nh_db_runtime_url is not None
        else None
    )
    access_key = (
        settings.object_storage_access_key.get_secret_value()
        if settings.object_storage_access_key is not None
        else None
    )
    secret_key = (
        settings.object_storage_secret_key.get_secret_value()
        if settings.object_storage_secret_key is not None
        else None
    )
    if not database_url:
        raise RunnerConfigurationError("WORKER_DATABASE_NOT_CONFIGURED")
    if not settings.object_storage_endpoint or not access_key or not secret_key:
        raise RunnerConfigurationError("WORKER_OBJECT_STORAGE_NOT_CONFIGURED")

    engine = create_engine(database_url, pool_pre_ping=True)
    storage = S3ArtifactStorage(
        settings.object_storage_endpoint,
        access_key,
        secret_key,
        region=settings.object_storage_region,
    )
    repository = PostgresJobRepository(engine, storage.get)
    queue = RedisJobQueue(
        settings.redis_url,
        queue_name=settings.review_queue_name,
        dead_letter_name=settings.review_dead_letter_name,
    )
    artifacts = ArtifactStore(
        storage,
        PostgresArtifactMetadataRepository(engine),
        bucket=settings.parser_artifacts_bucket,
        audit=PostgresArtifactAudit(engine),
    )
    processor = ParserJobProcessor(
        repository,
        router,
        artifacts,
        RedisDeadLetterSink(queue),
        worker_id=settings.worker_id,
        result_engine=ReviewResultEngine(),
    )
    return JobRunner(queue, processor, repository)


def unconfigured_production_runner(_: Settings) -> Runner:
    """Fail closed until the manual external-engine lane supplies real adapters."""

    raise RunnerConfigurationError("PARSER_ADAPTER_NOT_CONFIGURED")


def create_app(
    settings: Settings | None = None,
    queue_readiness: QueueReadiness | None = None,
    runner_factory: RunnerFactory | None = unconfigured_production_runner,
) -> FastAPI:
    """Create probes around a supervised, dependency-injected job consumer."""

    resolved_settings = settings or get_settings()
    queue = queue_readiness or RedisQueueReadiness(resolved_settings.redis_url)
    consumer = ConsumerState()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if runner_factory is not None:
            try:
                consumer.runner = runner_factory(resolved_settings)
                consumer.task = asyncio.create_task(asyncio.to_thread(consumer.runner.run_forever))
                await asyncio.sleep(0)
            except Exception as exc:
                consumer.startup_error = exc
                LOGGER.exception("worker consumer failed to start")
        try:
            yield
        finally:
            if consumer.runner is not None:
                consumer.runner.stop()
            if consumer.task is not None:
                try:
                    await consumer.task
                except Exception:
                    LOGGER.exception("worker consumer stopped unexpectedly")
            if consumer.runner is not None:
                consumer.runner.close()
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
        queue_ready = await queue.ready()
        consumer_ready = runner_factory is None or (
            consumer.startup_error is None
            and consumer.task is not None
            and not consumer.task.done()
        )
        if queue_ready and consumer_ready:
            return ReadinessResponse(status="ready", queue="ready", consumer="ready")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(
            status="not_ready",
            queue="ready" if queue_ready else "not_ready",
            consumer="ready" if consumer_ready else "not_ready",
        )

    return application


app = create_app()
