from __future__ import annotations

import json
from urllib.request import Request

import pytest

from nh_ad_backend.openai_reference_extractor import (
    OpenAIReferenceExtractor,
    OpenAIReferenceExtractorError,
)


PDF = b"%PDF-1.7\nsynthetic\n%%EOF"


def response_body(payload: dict[str, object]) -> bytes:
    return json.dumps(
        {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": json.dumps(payload)}],
                }
            ],
        }
    ).encode()


def extracted_payload() -> dict[str, object]:
    return {
        "title": "예금광고 감독규정",
        "content": "광고에는 적용 금리 조건을 명확히 표시해야 한다.",
        "evidence_type": "REGULATION",
        "product_group": "DEPOSIT",
        "advertisement_type": None,
        "rule_type": "REQUIRED",
        "importance": "HIGH",
        "effective_date": "2026-01-01",
        "expired_date": None,
        "metadata": {
            "agency": "Synthetic regulator",
            "documentName": "예금광고 감독규정",
            "articleNo": "MULTIPLE",
            "effectiveDate": "2026-01-01",
            "revisionDate": "2026-01-01",
            "sourceUrl": "local-reference://regulation.pdf",
        },
    }


def test_sends_pdf_to_responses_with_non_stored_strict_output() -> None:
    captured: dict[str, object] = {}

    def transport(request: Request, timeout: float) -> bytes:
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data or b"{}")
        return response_body(extracted_payload())

    extractor = OpenAIReferenceExtractor(
        api_key="secret-test-key",
        model="gpt-test",
        base_url="https://api.openai.example/v1",
        timeout=42,
        transport=transport,
    )
    result = extractor.extract(file_name="regulation.pdf", pdf_bytes=PDF)

    body = captured["body"]
    assert isinstance(body, dict)
    assert captured["url"] == "https://api.openai.example/v1/responses"
    assert captured["authorization"] == "Bearer secret-test-key"
    assert captured["timeout"] == 42
    assert body["store"] is False
    assert body["model"] == "gpt-test"
    assert "secret-test-key" not in json.dumps(body)
    content = body["input"][0]["content"]  # type: ignore[index]
    assert content[0]["file_data"].startswith("data:application/pdf;base64,")
    output_format = body["text"]["format"]  # type: ignore[index]
    assert output_format["type"] == "json_schema"
    assert output_format["strict"] is True
    assert output_format["schema"]["additionalProperties"] is False
    assert result.title == "예금광고 감독규정"
    assert result.effective_date is not None
    assert result.effective_date.isoformat() == "2026-01-01"


def test_environment_configuration_and_responses_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for variable in (
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "OPENAI_BASE_URL",
        "OPENAI_TIMEOUT",
        "OPENAI_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(variable, raising=False)
    with pytest.raises(OpenAIReferenceExtractorError, match="OPENAI_API_KEY"):
        OpenAIReferenceExtractor()

    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    with pytest.raises(OpenAIReferenceExtractorError, match="OPENAI_MODEL"):
        OpenAIReferenceExtractor()

    with pytest.raises(OpenAIReferenceExtractorError, match="HTTPS"):
        OpenAIReferenceExtractor(
            api_key="secret",
            model="gpt-test",
            base_url="http://remote.example/v1",
        )


def test_rejects_invalid_or_refused_structured_output() -> None:
    invalid = OpenAIReferenceExtractor(
        api_key="secret",
        model="gpt-test",
        transport=lambda _request, _timeout: response_body({"title": "incomplete"}),
    )
    with pytest.raises(OpenAIReferenceExtractorError, match="structured output"):
        invalid.extract(file_name="regulation.pdf", pdf_bytes=PDF)

    refused = OpenAIReferenceExtractor(
        api_key="secret",
        model="gpt-test",
        transport=lambda _request, _timeout: json.dumps(
            {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "refusal", "refusal": "cannot comply"}],
                    }
                ],
            }
        ).encode(),
    )
    with pytest.raises(OpenAIReferenceExtractorError, match="refused"):
        refused.extract(file_name="regulation.pdf", pdf_bytes=PDF)
