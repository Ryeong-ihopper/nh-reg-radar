"""Private parser/OCR service API shared by ADR-0072 engine containers."""

from __future__ import annotations

import base64
from binascii import Error as BinasciiError
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


class ParseRequest(BaseModel):
    source_file_id: str = Field(alias="sourceFileId")
    review_id: str = Field(alias="reviewId")
    file_name: str = Field(alias="fileName")
    mime_type: str = Field(alias="mimeType")
    content_base64: str = Field(alias="contentBase64")

    model_config = {"populate_by_name": True}

    def body(self) -> bytes:
        try:
            return base64.b64decode(self.content_base64, validate=True)
        except (BinasciiError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="invalid contentBase64") from exc


def app_for(engine: Any) -> FastAPI:
    """Expose one narrowly scoped, private normalized-document endpoint."""

    app = FastAPI(title=f"{engine.name} private parser service")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "engine": engine.name}

    @app.post("/v1/parse")
    def parse(request: ParseRequest) -> dict[str, object]:
        try:
            return engine.parse(request, request.body())
        except HTTPException:
            raise
        except Exception as exc:  # engine internals must never leak to the worker
            raise HTTPException(status_code=422, detail=f"{engine.name}_PARSE_FAILED") from exc

    return app


def normalized_document(
    request: ParseRequest,
    *,
    engine: str,
    version: str,
    pages: list[dict[str, object]],
    blocks: list[dict[str, object]],
    layout_blocks: list[dict[str, object]] | None = None,
    tables: list[dict[str, object]] | None = None,
    warnings: list[dict[str, object]] | None = None,
    raw_artifact_ref: str | None = None,
) -> dict[str, object]:
    """Return the repository-owned NormalizedDocument v1 wire representation."""

    confidence = min((float(block["confidenceScore"]) for block in blocks), default=0.0)
    return {
        "documentId": f"doc-{request.source_file_id}",
        "sourceFileId": request.source_file_id,
        "reviewId": request.review_id,
        "sourceFileType": request.file_name.rsplit(".", 1)[-1].casefold(),
        "parserName": engine,
        "parserVersion": version,
        "parserRuleVersion": f"{engine}-normalized-v1",
        "irVersion": "normalized-document-v1",
        "pages": pages,
        "textBlocks": blocks,
        "layoutBlocks": layout_blocks or [],
        "tables": tables or [],
        "warnings": warnings or [],
        "confidence": {
            "score": confidence,
            "status": _confidence_status(confidence),
            "policyVersion": "confidence-thresholds-v1",
        },
        "rawArtifactRef": raw_artifact_ref or f"{engine}-service-v1",
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }


def text_block(
    request: ParseRequest,
    *,
    engine: str,
    index: int,
    page_no: int,
    text: str,
    source_width: float,
    source_height: float,
    x: float,
    y: float,
    width: float,
    height: float,
    confidence: float,
    text_path: str | None = None,
    raw_start_offset: int | None = None,
    raw_end_offset: int | None = None,
) -> dict[str, object]:
    score = max(0.0, min(float(confidence), 1.0))
    value: dict[str, object] = {
        "textBlockId": f"{request.review_id}-{engine}-{index}",
        "fileId": request.source_file_id,
        "pageNo": page_no,
        "textBlockType": "BODY",
        "rawText": text,
        "normalizedText": text,
        "parserName": engine,
        "parserVersion": "v1",
        "parserRuleVersion": f"{engine}-normalized-v1",
        "irVersion": "normalized-document-v1",
        "confidenceScore": score,
        "confidenceStatus": _confidence_status(score),
        "confidencePolicyVersion": "confidence-thresholds-v1",
        "coordinate": {
            "sourceWidth": source_width,
            "sourceHeight": source_height,
            "sourceUnit": "pixel",
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "normalizedX": x / source_width,
            "normalizedY": y / source_height,
            "normalizedWidth": width / source_width,
            "normalizedHeight": height / source_height,
            "coordinateConfidence": score,
        },
    }
    if text_path is not None:
        value["textPath"] = text_path
    if raw_start_offset is not None and raw_end_offset is not None:
        value.update(
            {
                "rawStartOffset": raw_start_offset,
                "rawEndOffset": raw_end_offset,
                "normalizedStartOffset": raw_start_offset,
                "normalizedEndOffset": raw_end_offset,
            }
        )
    return value


def page(page_no: int, width: float, height: float) -> dict[str, object]:
    return {"pageNo": page_no, "width": width, "height": height, "unit": "pixel"}


def _confidence_status(score: float) -> str:
    if score >= 0.8:
        return "READABLE"
    if score >= 0.5:
        return "LOW_CONFIDENCE"
    return "UNREADABLE"
