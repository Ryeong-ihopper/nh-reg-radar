"""Engine-independent ``normalized-document-v1`` models."""

from datetime import datetime
from enum import StrEnum
from math import isclose

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ConfidenceStatus(StrEnum):
    READABLE = "READABLE"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    UNREADABLE = "UNREADABLE"


def confidence_status(score: float) -> ConfidenceStatus:
    if score >= 0.80:
        return ConfidenceStatus.READABLE
    if score >= 0.50:
        return ConfidenceStatus.LOW_CONFIDENCE
    return ConfidenceStatus.UNREADABLE


class Confidence(ContractModel):
    score: float = Field(ge=0, le=1)
    status: ConfidenceStatus
    policy_version: str = Field(alias="policyVersion", min_length=1)

    @model_validator(mode="after")
    def status_matches_score(self) -> "Confidence":
        if self.status != confidence_status(self.score):
            raise ValueError("confidence status does not match confidence-thresholds-v1")
        return self


class Coordinate(ContractModel):
    source_width: float = Field(alias="sourceWidth", gt=0)
    source_height: float = Field(alias="sourceHeight", gt=0)
    source_unit: str = Field(alias="sourceUnit", min_length=1)
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    normalized_x: float = Field(alias="normalizedX", ge=0, le=1)
    normalized_y: float = Field(alias="normalizedY", ge=0, le=1)
    normalized_width: float = Field(alias="normalizedWidth", gt=0, le=1)
    normalized_height: float = Field(alias="normalizedHeight", gt=0, le=1)
    rotation: float = 0
    coordinate_confidence: float = Field(alias="coordinateConfidence", ge=0, le=1)

    @model_validator(mode="after")
    def normalized_values_match_source(self) -> "Coordinate":
        expected = (
            self.x / self.source_width,
            self.y / self.source_height,
            self.width / self.source_width,
            self.height / self.source_height,
        )
        actual = (
            self.normalized_x,
            self.normalized_y,
            self.normalized_width,
            self.normalized_height,
        )
        if self.x + self.width > self.source_width or self.y + self.height > self.source_height:
            raise ValueError("coordinate exceeds the source bounds")
        if any(not isclose(left, right, abs_tol=0.0001) for left, right in zip(expected, actual)):
            raise ValueError("normalized coordinates do not match source coordinates")
        return self


class Page(ContractModel):
    page_no: int = Field(alias="pageNo", ge=1)
    width: float | None = Field(default=None, gt=0)
    height: float | None = Field(default=None, gt=0)
    unit: str | None = None


class TextBlock(ContractModel):
    text_block_id: str = Field(alias="textBlockId", min_length=1)
    file_id: str = Field(alias="fileId", min_length=1)
    page_no: int | None = Field(default=None, alias="pageNo", ge=1)
    text_path: str | None = Field(default=None, alias="textPath")
    text_block_type: str = Field(alias="textBlockType", min_length=1)
    raw_text: str = Field(alias="rawText")
    normalized_text: str = Field(alias="normalizedText")
    raw_start_offset: int | None = Field(default=None, alias="rawStartOffset", ge=0)
    raw_end_offset: int | None = Field(default=None, alias="rawEndOffset", ge=0)
    normalized_start_offset: int | None = Field(default=None, alias="normalizedStartOffset", ge=0)
    normalized_end_offset: int | None = Field(default=None, alias="normalizedEndOffset", ge=0)
    parser_name: str = Field(alias="parserName", min_length=1)
    parser_version: str = Field(alias="parserVersion", min_length=1)
    parser_rule_version: str = Field(alias="parserRuleVersion", min_length=1)
    ir_version: str = Field(alias="irVersion", min_length=1)
    confidence_score: float = Field(alias="confidenceScore", ge=0, le=1)
    confidence_status: ConfidenceStatus = Field(alias="confidenceStatus")
    confidence_policy_version: str = Field(alias="confidencePolicyVersion", min_length=1)
    coordinate: Coordinate | None = None

    @model_validator(mode="after")
    def validate_location_and_confidence(self) -> "TextBlock":
        if self.confidence_status != confidence_status(self.confidence_score):
            raise ValueError("text block confidence status does not match its score")
        offsets = (
            self.raw_start_offset,
            self.raw_end_offset,
            self.normalized_start_offset,
            self.normalized_end_offset,
        )
        if any(value is not None for value in offsets):
            if any(value is None for value in offsets):
                raise ValueError("text offsets must be supplied as complete raw/normalized pairs")
            assert self.raw_start_offset is not None and self.raw_end_offset is not None
            assert self.normalized_start_offset is not None
            assert self.normalized_end_offset is not None
            if self.raw_start_offset > self.raw_end_offset:
                raise ValueError("raw offsets are reversed")
            if self.normalized_start_offset > self.normalized_end_offset:
                raise ValueError("normalized offsets are reversed")
            if not self.text_path:
                raise ValueError("textPath is required when offsets are present")
        if self.coordinate is None and not self.text_path:
            raise ValueError("a text block requires a coordinate or textPath")
        return self


class LayoutBlock(ContractModel):
    layout_block_id: str = Field(alias="layoutBlockId", min_length=1)
    file_id: str = Field(alias="fileId", min_length=1)
    page_no: int | None = Field(default=None, alias="pageNo", ge=1)
    layout_type: str = Field(alias="layoutType", min_length=1)
    coordinate: Coordinate | None = None
    related_text_block_ids: list[str] = Field(default_factory=list, alias="relatedTextBlockIds")
    confidence_score: float = Field(alias="confidenceScore", ge=0, le=1)


class Table(ContractModel):
    table_id: str = Field(alias="tableId", min_length=1)
    page_no: int | None = Field(default=None, alias="pageNo", ge=1)
    text_path: str | None = Field(default=None, alias="textPath")
    coordinate: Coordinate | None = None
    cells: list[list[str]]


class Warning(ContractModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    requires_review: bool = Field(alias="requiresReview")


class NormalizedDocument(ContractModel):
    document_id: str = Field(alias="documentId", min_length=1)
    source_file_id: str = Field(alias="sourceFileId", min_length=1)
    review_id: str = Field(alias="reviewId", min_length=1)
    source_file_type: str = Field(alias="sourceFileType", min_length=1)
    parser_name: str = Field(alias="parserName", min_length=1)
    parser_version: str = Field(alias="parserVersion", min_length=1)
    parser_rule_version: str = Field(alias="parserRuleVersion", min_length=1)
    ir_version: str = Field(alias="irVersion", pattern=r"^normalized-document-v1$")
    pages: list[Page]
    text_blocks: list[TextBlock] = Field(alias="textBlocks")
    layout_blocks: list[LayoutBlock] = Field(alias="layoutBlocks")
    tables: list[Table]
    warnings: list[Warning]
    confidence: Confidence
    raw_artifact_ref: str = Field(alias="rawArtifactRef", min_length=1)
    created_at: datetime = Field(alias="createdAt")

    @model_validator(mode="after")
    def block_metadata_matches_document(self) -> "NormalizedDocument":
        for block in self.text_blocks:
            if block.file_id != self.source_file_id:
                raise ValueError("text block source file differs from document source file")
            if (
                block.parser_name,
                block.parser_version,
                block.parser_rule_version,
                block.ir_version,
            ) != (
                self.parser_name,
                self.parser_version,
                self.parser_rule_version,
                self.ir_version,
            ):
                raise ValueError("text block parser metadata differs from document metadata")
        return self
