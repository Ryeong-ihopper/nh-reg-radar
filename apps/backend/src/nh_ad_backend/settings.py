"""Runtime settings loaded only from the process environment."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings shared by backend entrypoints."""

    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    app_env: Literal["dev", "prod", "test"] = "dev"
    service_name: str = "backend"
    nh_db_runtime_url: SecretStr | None = None


@lru_cache
def get_settings() -> Settings:
    """Return one immutable process-level settings instance."""

    return Settings()
