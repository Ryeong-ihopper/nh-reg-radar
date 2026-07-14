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


@lru_cache
def get_settings() -> Settings:
    return Settings()
