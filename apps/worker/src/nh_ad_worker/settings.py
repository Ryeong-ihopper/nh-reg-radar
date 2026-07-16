"""Worker process settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration required by the M1 worker platform boundary."""

    model_config = SettingsConfigDict(extra="ignore", env_ignore_empty=True, frozen=True)

    app_env: Literal["dev", "prod", "test"] = "dev"
    service_name: str = "worker"
    redis_url: str = "redis://localhost:6379/0"
    nh_db_runtime_url: SecretStr | None = None
    review_queue_name: str = "review-jobs-v1"
    review_dead_letter_name: str = "review-jobs-v1-dead-letter"
    worker_id: str = "worker-1"
    object_storage_endpoint: str | None = None
    object_storage_access_key: SecretStr | None = None
    object_storage_secret_key: SecretStr | None = None
    object_storage_region: str = "us-east-1"
    parser_artifacts_bucket: str = "parser-artifacts"
    openai_api_key: SecretStr | None = None
    openai_model: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    nh_external_ai_enabled: bool = False
    opensearch_endpoint: str = "http://opensearch:9200"
    opensearch_index: str = "dev_reference_docs"
    qdrant_endpoint: str = "http://qdrant:6333"
    qdrant_collection: str = "dev_reference_chunks"
    openai_embedding_model: str | None = None
    embedding_api_key: SecretStr | None = None
    embedding_base_url: str | None = None
    embedding_timeout_seconds: float | None = Field(default=None, gt=0, le=300)
    embedding_dimensions: int = Field(default=1536, gt=0, le=8192)
    embedding_allow_insecure_http: bool = False

    @property
    def resolved_embedding_api_key(self) -> SecretStr | None:
        if self.embedding_api_key and self.embedding_api_key.get_secret_value().strip():
            return self.embedding_api_key
        return self.openai_api_key

    @property
    def resolved_embedding_base_url(self) -> str:
        return self.embedding_base_url or self.openai_base_url

    @property
    def resolved_embedding_timeout_seconds(self) -> float:
        return self.embedding_timeout_seconds or self.openai_timeout_seconds


@lru_cache
def get_settings() -> Settings:
    return Settings()
