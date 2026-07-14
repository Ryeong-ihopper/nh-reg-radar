"""Runtime settings loaded only from the process environment."""

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings shared by backend entrypoints."""

    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    app_env: Literal["dev", "prod", "test"] = "dev"
    service_name: str = "backend"
    nh_db_runtime_url: SecretStr | None = None
    jwt_secret: SecretStr | None = None
    cors_allowed_origins: str = "http://localhost:5173"
    refresh_cookie_secure: bool = True
    private_storage_path: Path = Path("/tmp/nh-ad-private-storage")
    object_storage_endpoint: str | None = None
    object_storage_access_key: SecretStr | None = None
    object_storage_secret_key: SecretStr | None = None
    ad_originals_bucket: str = "nh-ad-originals"
    object_storage_region: str = "us-east-1"
    qdrant_endpoint: str = "http://qdrant:6333"
    qdrant_collection: str = "dev_reference_chunks"
    opensearch_endpoint: str = "http://opensearch:9200"
    opensearch_index: str = "dev_reference_docs"

    @property
    def allowed_origins(self) -> tuple[str, ...]:
        return tuple(
            origin.strip().rstrip("/")
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        )

    @model_validator(mode="after")
    def validate_cookie_security(self) -> Self:
        if self.app_env == "prod" and not self.refresh_cookie_secure:
            raise ValueError("production refresh cookies must be Secure")
        if not self.refresh_cookie_secure and any(
            not origin.startswith(("http://localhost", "http://127.0.0.1"))
            for origin in self.allowed_origins
        ):
            raise ValueError("insecure refresh cookies are allowed only for local HTTP origins")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return one immutable process-level settings instance."""

    return Settings()
