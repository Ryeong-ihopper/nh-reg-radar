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

from nh_ad_ai_providers import OpenAICompatibleEmbeddings

from nh_ad_worker.evidence_search import OpenSearchEvidenceSearch
from nh_ad_worker.jobs import ParserJobProcessor
from nh_ad_worker.object_storage import S3ArtifactStorage
from nh_ad_worker.openai_provider import (
    OpenAIResponsesClient,
)
from nh_ad_worker.parser_services import parser_service_adapters
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
from nh_ad_worker.qdrant_evidence_search import HybridEvidenceSearch, QdrantEvidenceSearch
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


def compose_job_runner(
    settings: Settings,
    router: ParserRouter,
    response_client: OpenAIResponsesClient | None = None,
) -> JobRunner:
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
    repository = PostgresJobRepository(
        engine,
        storage.get,
        external_ai_allowed=response_client is not None,
    )
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
        result_engine=ReviewResultEngine(
            search=_live_evidence_search(settings) if response_client else None,
            structured_output=response_client.review_decision if response_client else None,
        ),
        suggestion_refiner=response_client.refine_suggestion if response_client else None,
    )
    return JobRunner(queue, processor, repository)


def production_runner(settings: Settings) -> Runner:
    """Compose parser/OCR services independently from optional external AI."""

    router = _parser_router(settings)
    if not settings.nh_external_ai_enabled:
        return compose_job_runner(settings, router)
    api_key = (
        settings.openai_api_key.get_secret_value() if settings.openai_api_key is not None else None
    )
    if not api_key:
        raise RunnerConfigurationError("OPENAI_API_KEY_NOT_CONFIGURED")
    if not settings.openai_model:
        raise RunnerConfigurationError("OPENAI_MODEL_NOT_CONFIGURED")
    embedding_key = settings.resolved_embedding_api_key
    if not embedding_key or not settings.openai_embedding_model:
        raise RunnerConfigurationError("OPENAI_EMBEDDING_NOT_CONFIGURED")
    client = OpenAIResponsesClient(
        api_key=api_key,
        model=settings.openai_model,
        base_url=settings.openai_base_url,
        timeout_seconds=settings.openai_timeout_seconds,
    )
    return compose_job_runner(
        settings,
        router,
        response_client=client,
    )


def _parser_router(settings: Settings) -> ParserRouter:
    """Register private parser services unless explicitly disabled for a test/runtime."""

    if not settings.nh_parser_services_enabled:
        return ParserRouter()
    return ParserRouter(
        parser_service_adapters(
            opendataloader_endpoint=settings.opendataloader_pdf_endpoint,
            paddleocr_endpoint=settings.paddleocr_endpoint,
            rhwp_endpoint=settings.rhwp_endpoint,
            document_processor_endpoint=settings.document_processor_endpoint,
            timeout_seconds=settings.parser_service_timeout_seconds,
            hwp_structure_attempts=settings.hwp_structure_attempts,
        )
    )


def _live_evidence_search(settings: Settings) -> HybridEvidenceSearch:
    embedding_key = settings.resolved_embedding_api_key
    if embedding_key is None or not settings.openai_embedding_model:
        raise RunnerConfigurationError("OPENAI_EMBEDDING_NOT_CONFIGURED")
    embeddings = OpenAICompatibleEmbeddings(
        api_key=embedding_key.get_secret_value(),
        model=settings.openai_embedding_model,
        base_url=settings.resolved_embedding_base_url,
        dimensions=settings.embedding_dimensions,
        timeout_seconds=settings.resolved_embedding_timeout_seconds,
        allow_insecure_http=settings.embedding_allow_insecure_http,
    )
    return HybridEvidenceSearch(
        keyword=OpenSearchEvidenceSearch(settings.opensearch_endpoint, settings.opensearch_index),
        vector=QdrantEvidenceSearch(
            settings.qdrant_endpoint,
            settings.qdrant_collection,
            embeddings,
        ),
    )


def create_app(
    settings: Settings | None = None,
    queue_readiness: QueueReadiness | None = None,
    runner_factory: RunnerFactory | None = production_runner,
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
