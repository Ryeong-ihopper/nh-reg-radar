"""Runtime settings loaded only from the process environment."""

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings shared by backend entrypoints."""

    model_config = SettingsConfigDict(extra="ignore", env_ignore_empty=True, frozen=True)

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
    redis_url: str = "redis://localhost:6379/0"
    review_queue_name: str = "review-jobs-v1"
    parser_artifacts_bucket: str = "parser-artifacts"
    rhwp_endpoint: str = "http://rhwp:8093"
    document_processor_endpoint: str = "http://document-processor:8094"
    opendataloader_pdf_endpoint: str = "http://opendataloader-pdf:8091"
    reference_parser_timeout_seconds: float = Field(default=120.0, gt=0, le=300)
    hwp_structure_attempts: int = Field(default=3, ge=1, le=5)
    hwp_preview_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    nh_external_ai_enabled: bool = False
    openai_api_key: SecretStr | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_timeout_seconds: float = Field(default=120.0, gt=0, le=300)
    openai_embedding_model: str | None = None
    embedding_api_key: SecretStr | None = None
    embedding_base_url: str | None = None
    embedding_timeout_seconds: float | None = Field(default=None, gt=0, le=300)
    embedding_dimensions: int = Field(default=1536, gt=0, le=8192)
    embedding_allow_insecure_http: bool = False

    @property
    def embedding_enabled(self) -> bool:
        return self.nh_external_ai_enabled and self.openai_embedding_model is not None

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
