"""Worker process settings."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration required by the M1 worker platform boundary."""

    model_config = SettingsConfigDict(extra="ignore", frozen=True)

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
