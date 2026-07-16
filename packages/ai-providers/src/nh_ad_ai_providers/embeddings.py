"""Strict OpenAI-compatible ``/embeddings`` HTTP client.

The OpenAI embeddings API and vLLM's embedding server expose the same narrow
request/response shape used here.  No SDK is required, and endpoint/model/key
selection remains environment configuration rather than application code.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from math import isfinite
from typing import cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class EmbeddingProviderError(RuntimeError):
    """Redacted embedding provider configuration, transport, or schema failure."""


Transport = Callable[[Request, float], bytes]


class OpenAICompatibleEmbeddings:
    """Batch text embeddings through an OpenAI-compatible endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        dimensions: int,
        timeout_seconds: float = 30.0,
        allow_insecure_http: bool = False,
        transport: Transport | None = None,
    ) -> None:
        if not api_key.strip() or not model.strip() or dimensions <= 0 or timeout_seconds <= 0:
            raise ValueError("EMBEDDING_PROVIDER_CONFIGURATION_INVALID")
        self._validate_base_url(base_url, allow_insecure_http=allow_insecure_http)
        self.model = model.strip()
        self.dimensions = dimensions
        self._api_key = api_key
        self._endpoint = f"{base_url.rstrip('/')}/embeddings"
        self._timeout_seconds = timeout_seconds
        self._transport = transport or self._send

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        values = list(texts)
        if not values or any(not value.strip() for value in values):
            raise ValueError("EMBEDDING_INPUT_REQUIRED")
        request = Request(
            self._endpoint,
            data=json.dumps(
                {"model": self.model, "input": values, "encoding_format": "float"},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        raw = self._transport(request, self._timeout_seconds)
        try:
            decoded = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EmbeddingProviderError("EMBEDDING_RESPONSE_INVALID_JSON") from exc
        if not isinstance(decoded, dict) or not isinstance(decoded.get("data"), list):
            raise EmbeddingProviderError("EMBEDDING_RESPONSE_INVALID_SCHEMA")
        rows: list[tuple[int, tuple[float, ...]]] = []
        for value in decoded["data"]:
            if not isinstance(value, dict) or not isinstance(value.get("index"), int):
                raise EmbeddingProviderError("EMBEDDING_RESPONSE_INVALID_SCHEMA")
            vector = value.get("embedding")
            if not isinstance(vector, list) or len(vector) != self.dimensions:
                raise EmbeddingProviderError("EMBEDDING_DIMENSION_MISMATCH")
            if any(
                not isinstance(component, (int, float))
                or isinstance(component, bool)
                or not isfinite(float(component))
                for component in vector
            ):
                raise EmbeddingProviderError("EMBEDDING_VECTOR_INVALID")
            rows.append((value["index"], tuple(float(component) for component in vector)))
        if sorted(index for index, _vector in rows) != list(range(len(values))):
            raise EmbeddingProviderError("EMBEDDING_RESPONSE_INDEX_INVALID")
        return [vector for _index, vector in sorted(rows)]

    @staticmethod
    def _validate_base_url(value: str, *, allow_insecure_http: bool) -> None:
        parsed = urlsplit(value)
        local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        allowed_scheme = parsed.scheme == "https" or (
            parsed.scheme == "http" and (allow_insecure_http or local)
        )
        if not allowed_scheme or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("EMBEDDING_BASE_URL_INVALID")

    @staticmethod
    def _send(request: Request, timeout_seconds: float) -> bytes:
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
                return cast(bytes, response.read())
        except HTTPError as exc:
            raise EmbeddingProviderError(f"EMBEDDING_HTTP_{exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise EmbeddingProviderError("EMBEDDING_TRANSPORT_ERROR") from exc
