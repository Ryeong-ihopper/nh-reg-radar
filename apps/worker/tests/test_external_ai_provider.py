"""Credentialed live smoke kept outside provider-free PR automation."""

import os
from pathlib import Path

import pytest
from nh_ad_parser_contracts import DocumentInput

from nh_ad_worker.openai_provider import OpenAIDocumentAdapter, OpenAIResponsesClient


@pytest.mark.external_ai
def test_openai_extracts_approved_local_sample_pdf() -> None:
    if os.getenv("NH_RUN_EXTERNAL_AI") != "1":
        pytest.skip("set NH_RUN_EXTERNAL_AI=1 for an approved credentialed smoke")
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL")
    assert api_key, "OPENAI_API_KEY must be injected by the approved manual environment"
    assert model, "OPENAI_MODEL must be supplied by the approved manual environment"

    sample = (
        Path(__file__).resolve().parents[3] / "docs" / "광고예시" / "NH농협은행-2026_001-예금성.pdf"
    )
    assert sample.is_file(), "approved local sample is required by the manual workflow"
    document = DocumentInput(
        source_file_id="FILE-EXTERNAL-SMOKE",
        review_id="REV-EXTERNAL-SMOKE",
        file_name=sample.name,
        mime_type="application/pdf",
        body=sample.read_bytes(),
        external_ai_allowed=True,
    )

    result = OpenAIDocumentAdapter(
        OpenAIResponsesClient(
            api_key=api_key,
            model=model,
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            timeout_seconds=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "120")),
        )
    ).parse(document)

    assert (result.review_id, result.source_file_id) == (
        document.review_id,
        document.source_file_id,
    )
    assert result.text_blocks
