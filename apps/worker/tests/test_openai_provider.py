import base64
import json
from pathlib import Path
from urllib.request import Request

import pytest
from nh_ad_parser_contracts import DocumentInput, NormalizedDocument
from pydantic import SecretStr
from pytest import MonkeyPatch

from nh_ad_worker import main as worker_main
from nh_ad_worker.main import RunnerConfigurationError, production_runner
from nh_ad_worker.openai_provider import (
    OpenAIDocumentAdapter,
    OpenAIProviderError,
    OpenAIResponsesClient,
)
from nh_ad_worker.results import EvidenceCandidate, ReviewResultEngine
from nh_ad_worker.settings import Settings
from nh_ad_worker.suggestions import rule_suggestions


FIXTURE = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "m4" / "normalized-image-v1.json"
)


class CapturedTransport:
    def __init__(self, result: dict[str, object]) -> None:
        self.result = result
        self.requests: list[tuple[Request, float]] = []

    def __call__(self, request: Request, timeout: float) -> bytes:
        self.requests.append((request, timeout))
        return json.dumps(
            {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(self.result),
                            }
                        ],
                    }
                ],
            }
        ).encode()


def client(transport: CapturedTransport) -> OpenAIResponsesClient:
    return OpenAIResponsesClient(
        api_key="test-secret",
        model="test-model",
        base_url="https://provider.invalid/v1/",
        timeout_seconds=12.5,
        transport=transport,
    )


def request_payload(transport: CapturedTransport) -> dict[str, object]:
    request, _timeout = transport.requests[-1]
    assert request.data is not None
    return json.loads(request.data)


def test_responses_json_sends_text_only_strict_schema_without_storage() -> None:
    transport = CapturedTransport({"decision": "APPROPRIATE"})
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"decision": {"type": "string"}},
        "required": ["decision"],
    }

    assert client(transport).responses_json("review this phrase", schema) == {
        "decision": "APPROPRIATE"
    }

    request, timeout = transport.requests[0]
    payload = request_payload(transport)
    assert request.full_url == "https://provider.invalid/v1/responses"
    assert request.get_header("Authorization") == "Bearer test-secret"
    assert timeout == 12.5
    assert payload["model"] == "test-model"
    assert payload["store"] is False
    assert payload["input"] == [
        {
            "role": "user",
            "content": [{"type": "input_text", "text": "review this phrase"}],
        }
    ]
    assert payload["text"]["format"] == {  # type: ignore[index]
        "type": "json_schema",
        "name": "structured_response",
        "schema": schema,
        "strict": True,
    }


@pytest.mark.parametrize(
    ("file_name", "mime_type", "expected_type"),
    [
        ("advertisement.png", "image/png", "input_image"),
        ("advertisement.pdf", "application/pdf", "input_file"),
    ],
)
def test_document_adapter_converts_structured_pdf_and_image_response(
    file_name: str,
    mime_type: str,
    expected_type: str,
) -> None:
    fixture = NormalizedDocument.model_validate_json(FIXTURE.read_text())
    transport = CapturedTransport(
        {
            "textBlocks": [
                {
                    "text": "우대금리 연 3.0%",
                    "pageNo": 1,
                    "sourceWidth": 100,
                    "sourceHeight": 200,
                    "x": 10,
                    "y": 20,
                    "width": 60,
                    "height": 30,
                    "confidence": 0.9,
                }
            ]
        }
    )
    source = DocumentInput(
        source_file_id=fixture.source_file_id,
        review_id=fixture.review_id,
        file_name=file_name,
        mime_type=mime_type,
        body=b"synthetic-binary",
        external_ai_allowed=True,
    )

    result = OpenAIDocumentAdapter(client(transport)).parse(source)

    assert result.review_id == fixture.review_id
    assert result.source_file_id == fixture.source_file_id
    assert result.parser_name == "openai-responses"
    assert result.text_blocks[0].text_block_id == f"{fixture.review_id}-ocr-1"
    assert result.text_blocks[0].normalized_text == "우대금리 연 3.0%"
    assert result.text_blocks[0].coordinate is not None
    assert result.text_blocks[0].coordinate.normalized_x == 0.1
    payload = request_payload(transport)
    content = payload["input"][0]["content"]  # type: ignore[index]
    binary = content[1]
    assert binary["type"] == expected_type
    if expected_type == "input_image":
        assert binary["image_url"] == (
            "data:image/png;base64," + base64.b64encode(source.body).decode("ascii")
        )
    else:
        assert binary["filename"] == file_name
        assert binary["file_data"] == (
            "data:application/pdf;base64," + base64.b64encode(source.body).decode("ascii")
        )
    assert payload["text"]["format"] == {  # type: ignore[index]
        "type": "json_schema",
        "name": "document_extraction_v1",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "textBlocks": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "text": {"type": "string", "minLength": 1},
                            "pageNo": {"type": "integer", "minimum": 1},
                            "sourceWidth": {"type": "number", "exclusiveMinimum": 0},
                            "sourceHeight": {"type": "number", "exclusiveMinimum": 0},
                            "x": {"type": "number", "minimum": 0},
                            "y": {"type": "number", "minimum": 0},
                            "width": {"type": "number", "exclusiveMinimum": 0},
                            "height": {"type": "number", "exclusiveMinimum": 0},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        },
                        "required": [
                            "text",
                            "pageNo",
                            "sourceWidth",
                            "sourceHeight",
                            "x",
                            "y",
                            "width",
                            "height",
                            "confidence",
                        ],
                    },
                }
            },
            "required": ["textBlocks"],
        },
        "strict": True,
    }


def test_document_adapter_owns_document_identity_not_provider_output() -> None:
    fixture = NormalizedDocument.model_validate_json(FIXTURE.read_text())
    transport = CapturedTransport(
        {
            "textBlocks": [
                {
                    "text": "문구",
                    "pageNo": 1,
                    "sourceWidth": 100,
                    "sourceHeight": 100,
                    "x": 0,
                    "y": 0,
                    "width": 50,
                    "height": 10,
                    "confidence": 0.8,
                }
            ]
        }
    )
    source = DocumentInput(
        source_file_id=fixture.source_file_id,
        review_id=fixture.review_id,
        file_name="advertisement.png",
        mime_type="image/png",
        body=b"synthetic-binary",
        external_ai_allowed=True,
    )

    result = OpenAIDocumentAdapter(client(transport)).parse(source)

    assert result.review_id == source.review_id
    assert result.source_file_id == source.source_file_id


def test_provider_rejects_missing_structured_output() -> None:
    provider = OpenAIResponsesClient(
        api_key="test-secret",
        model="test-model",
        transport=lambda _request, _timeout: b'{"status":"completed","output":[]}',
    )

    with pytest.raises(OpenAIProviderError, match="OPENAI_OUTPUT_TEXT_MISSING"):
        provider.responses_json("prompt", {"type": "object"})


def test_provider_refines_an_evidence_bound_rule_suggestion() -> None:
    fixture = NormalizedDocument.model_validate_json(FIXTURE.read_text())
    results = ReviewResultEngine(
        search=lambda _query: [
            EvidenceCandidate(
                "EVD-1",
                "STDVER-1",
                "GUIDELINE",
                "광고 표현 기준",
                "객관적 기준 없는 절대적 표현은 사용할 수 없습니다.",
                0.9,
                "HYBRID",
            )
        ]
    ).execute(fixture)
    transport = CapturedTransport({"suggestedText": "조건 충족 시 혜택을 제공받을 수 있습니다."})

    suggestions = rule_suggestions(results, refine=client(transport).refine_suggestion)

    assert suggestions[0].suggested_text == "조건 충족 시 혜택을 제공받을 수 있습니다."
    assert "AI가 문장을 보강" in suggestions[0].suggestion_reason
    payload = request_payload(transport)
    assert payload["text"]["format"]["name"] == "suggestion_refinement_v1"  # type: ignore[index]
    prompt = payload["input"][0]["content"][0]["text"]  # type: ignore[index]
    assert "fallbackSuggestion" in prompt
    assert "객관적 기준 없는 절대적 표현" in prompt


def test_production_runner_fails_closed_when_external_ai_config_is_incomplete() -> None:
    with pytest.raises(RunnerConfigurationError, match="OPENAI_API_KEY_NOT_CONFIGURED"):
        production_runner(
            Settings(
                app_env="test",
                nh_external_ai_enabled=True,
                openai_model="test-model",
            )
        )
    with pytest.raises(RunnerConfigurationError, match="OPENAI_MODEL_NOT_CONFIGURED"):
        production_runner(
            Settings(
                app_env="test",
                nh_external_ai_enabled=True,
                openai_api_key=SecretStr("test-secret"),
            )
        )


def test_production_runner_registers_adr_0072_services_and_shared_review_client(
    monkeypatch: MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    sentinel = object()

    def capture(
        settings: Settings,
        router: object,
        response_client: OpenAIResponsesClient | None = None,
    ) -> object:
        captured.update(
            settings=settings,
            router=router,
            response_client=response_client,
        )
        return sentinel

    monkeypatch.setattr(worker_main, "compose_job_runner", capture)
    settings = Settings(
        app_env="test",
        nh_external_ai_enabled=True,
        openai_api_key=SecretStr("test-secret"),
        openai_model="test-model",
        openai_embedding_model="test-embedding-model",
    )

    assert worker_main.production_runner(settings) is sentinel
    router = captured["router"]
    assert set(router._adapters) == {"opendataloader-pdf", "paddleocr", "rhwp"}  # type: ignore[attr-defined]
    assert isinstance(captured["response_client"], OpenAIResponsesClient)


def test_worker_settings_load_external_provider_environment(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("NH_EXTERNAL_AI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "environment-secret")
    monkeypatch.setenv("OPENAI_MODEL", "environment-model")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://provider.invalid/v1")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "22.5")
    monkeypatch.setenv("OPENAI_EMBEDDING_MODEL", "embedding-model")
    monkeypatch.setenv("EMBEDDING_API_KEY", "")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "")
    monkeypatch.setenv("EMBEDDING_TIMEOUT_SECONDS", "")
    monkeypatch.setenv("OPENSEARCH_ENDPOINT", "http://search.invalid:9200")
    monkeypatch.setenv("OPENSEARCH_INDEX", "test-reference-docs")

    settings = Settings()

    assert settings.nh_external_ai_enabled is True
    assert settings.openai_api_key is not None
    assert settings.openai_api_key.get_secret_value() == "environment-secret"
    assert settings.openai_model == "environment-model"
    assert settings.openai_base_url == "https://provider.invalid/v1"
    assert settings.openai_timeout_seconds == 22.5
    assert settings.opensearch_endpoint == "http://search.invalid:9200"
    assert settings.opensearch_index == "test-reference-docs"
    assert settings.openai_embedding_model == "embedding-model"
    assert settings.resolved_embedding_api_key is not None
    assert settings.resolved_embedding_api_key.get_secret_value() == "environment-secret"
    assert settings.resolved_embedding_base_url == "https://provider.invalid/v1"
    assert settings.resolved_embedding_timeout_seconds == 22.5
