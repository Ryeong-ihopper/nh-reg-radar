import json
from urllib.request import Request

import pytest

from nh_ad_ai_providers import EmbeddingProviderError, OpenAICompatibleEmbeddings


def test_openai_compatible_embeddings_send_batch_and_order_by_index() -> None:
    captured: dict[str, object] = {}

    def transport(request: Request, timeout: float) -> bytes:
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        captured["payload"] = json.loads(request.data or b"{}")
        return b'{"data":[{"index":1,"embedding":[0.3,0.4]},{"index":0,"embedding":[0.1,0.2]}]}'

    client = OpenAICompatibleEmbeddings(
        api_key="secret",
        model="embedding-model",
        base_url="https://provider.invalid/v1",
        dimensions=2,
        timeout_seconds=12,
        transport=transport,
    )

    assert client.embed(["first", "second"]) == [(0.1, 0.2), (0.3, 0.4)]
    assert captured["url"] == "https://provider.invalid/v1/embeddings"
    assert captured["authorization"] == "Bearer secret"
    assert captured["timeout"] == 12
    assert captured["payload"] == {
        "model": "embedding-model",
        "input": ["first", "second"],
        "encoding_format": "float",
    }


def test_embedding_dimension_mismatch_and_insecure_endpoint_fail_closed() -> None:
    client = OpenAICompatibleEmbeddings(
        api_key="secret",
        model="embedding-model",
        base_url="https://provider.invalid/v1",
        dimensions=3,
        transport=lambda _request, _timeout: b'{"data":[{"index":0,"embedding":[0.1]}]}',
    )
    with pytest.raises(EmbeddingProviderError, match="EMBEDDING_DIMENSION_MISMATCH"):
        client.embed(["text"])
    with pytest.raises(ValueError, match="EMBEDDING_BASE_URL_INVALID"):
        OpenAICompatibleEmbeddings(
            api_key="secret",
            model="embedding-model",
            base_url="http://vllm.internal/v1",
            dimensions=2,
        )


def test_insecure_internal_vllm_endpoint_requires_explicit_opt_in() -> None:
    client = OpenAICompatibleEmbeddings(
        api_key="EMPTY",
        model="local-embedding-model",
        base_url="http://vllm.internal/v1",
        dimensions=2,
        allow_insecure_http=True,
        transport=lambda _request, _timeout: b'{"data":[{"index":0,"embedding":[0.1,0.2]}]}',
    )
    assert client.embed(["폐쇄망 문장"]) == [(0.1, 0.2)]
