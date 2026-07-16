"""Dependency-free OpenAI Responses boundary for document and review JSON."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable
from pathlib import PurePath
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from nh_ad_parser_contracts import DocumentInput, NormalizedDocument

from nh_ad_worker.results import ReviewResultItem


class OpenAIProviderError(RuntimeError):
    """A redacted provider, transport, or response-contract failure."""


Transport = Callable[[Request, float], bytes]


REVIEW_DECISION_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "decision": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reasonCode": {"type": "string"},
        "explanation": {"type": "string"},
    },
    "required": ["decision", "confidence", "reasonCode", "explanation"],
}


class OpenAIResponsesClient:
    """Minimal Responses API client with strict JSON output extraction."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 60.0,
        transport: Transport | None = None,
    ) -> None:
        if not api_key.strip() or not model.strip():
            raise ValueError("OPENAI_CLIENT_CONFIGURATION_INVALID")
        if timeout_seconds <= 0:
            raise ValueError("OPENAI_TIMEOUT_INVALID")
        self.model = model
        self._api_key = api_key
        self._endpoint = f"{base_url.rstrip('/')}/responses"
        self._timeout_seconds = timeout_seconds
        self._transport = transport or self._send

    def responses_json(self, prompt: str, schema: dict[str, object]) -> dict[str, object]:
        """Send a text-only request and return a schema-constrained JSON object."""

        if not prompt.strip():
            raise ValueError("OPENAI_PROMPT_REQUIRED")
        return self._request_json(
            [{"type": "input_text", "text": prompt}],
            schema,
            format_name="structured_response",
            strict=True,
        )

    def document_json(self, document: DocumentInput) -> dict[str, object]:
        """Send one supported document as an inline Responses image/file input."""

        extension = PurePath(document.file_name).suffix.casefold()
        prompt = (
            "Extract every visible advertising phrase and its page coordinates. "
            "Return normalized-document-v1 JSON only. Preserve the supplied reviewId "
            "and sourceFileId exactly."
        )
        content: list[dict[str, object]] = [{"type": "input_text", "text": prompt}]
        if extension == ".pdf" or document.mime_type == "application/pdf":
            content.append(
                {
                    "type": "input_file",
                    "filename": document.file_name,
                    "file_data": base64.b64encode(document.body).decode("ascii"),
                }
            )
        elif extension in {".jpg", ".jpeg", ".png"} or document.mime_type.startswith("image/"):
            encoded = base64.b64encode(document.body).decode("ascii")
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:{document.mime_type};base64,{encoded}",
                    "detail": "high",
                }
            )
        else:
            raise ValueError("OPENAI_DOCUMENT_TYPE_NOT_SUPPORTED")
        return self._request_json(
            content,
            NormalizedDocument.model_json_schema(by_alias=True),
            format_name="normalized_document_v1",
            strict=False,
        )

    def review_decision(self, item: ReviewResultItem) -> dict[str, object]:
        """Produce the M5 structured review shape without exposing provider objects."""

        prompt = json.dumps(
            {
                "instruction": "Review the advertisement phrase and return the requested JSON.",
                "targetText": item.target_text,
                "ruleDecision": item.result_status,
                "ruleRiskLevel": item.risk_level,
                "ruleReasonCodes": item.risk_reason_codes,
                "evidence": [
                    {
                        "matchedText": evidence.candidate.matched_text,
                        "relevanceScore": evidence.candidate.relevance_score,
                    }
                    for evidence in item.evidences
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return self.responses_json(prompt, REVIEW_DECISION_SCHEMA)

    def _request_json(
        self,
        content: list[dict[str, object]],
        schema: dict[str, object],
        *,
        format_name: str,
        strict: bool,
    ) -> dict[str, object]:
        payload = {
            "model": self.model,
            "store": False,
            "input": [{"role": "user", "content": content}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": format_name,
                    "schema": schema,
                    "strict": strict,
                }
            },
        }
        request = Request(
            self._endpoint,
            data=json.dumps(payload, separators=(",", ":")).encode(),
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        raw = self._transport(request, self._timeout_seconds)
        try:
            response = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OpenAIProviderError("OPENAI_RESPONSE_INVALID_JSON") from exc
        if not isinstance(response, dict) or response.get("status") not in {None, "completed"}:
            raise OpenAIProviderError("OPENAI_RESPONSE_INCOMPLETE")
        output_text = self._output_text(response)
        try:
            value = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise OpenAIProviderError("OPENAI_STRUCTURED_OUTPUT_INVALID") from exc
        if not isinstance(value, dict):
            raise OpenAIProviderError("OPENAI_STRUCTURED_OUTPUT_NOT_OBJECT")
        return value

    @staticmethod
    def _output_text(response: dict[str, Any]) -> str:
        direct = response.get("output_text")
        if isinstance(direct, str) and direct:
            return direct
        output = response.get("output")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict) or not isinstance(item.get("content"), list):
                    continue
                for content in item["content"]:
                    if (
                        isinstance(content, dict)
                        and content.get("type") == "output_text"
                        and isinstance(content.get("text"), str)
                    ):
                        return cast(str, content["text"])
        raise OpenAIProviderError("OPENAI_OUTPUT_TEXT_MISSING")

    @staticmethod
    def _send(request: Request, timeout_seconds: float) -> bytes:
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
                return cast(bytes, response.read())
        except HTTPError as exc:
            raise OpenAIProviderError(f"OPENAI_HTTP_{exc.code}") from exc
        except (URLError, TimeoutError) as exc:
            raise OpenAIProviderError("OPENAI_TRANSPORT_ERROR") from exc


class OpenAIDocumentAdapter:
    """ParserAdapter for PDF and raster-image extraction through Responses."""

    name = "openai-responses"

    def __init__(self, client: OpenAIResponsesClient) -> None:
        self._client = client

    def parse(self, document: DocumentInput) -> NormalizedDocument:
        value = self._client.document_json(document)
        normalized = NormalizedDocument.model_validate(value)
        if (
            normalized.review_id != document.review_id
            or normalized.source_file_id != document.source_file_id
        ):
            raise OpenAIProviderError("OPENAI_DOCUMENT_IDENTITY_MISMATCH")
        return normalized
