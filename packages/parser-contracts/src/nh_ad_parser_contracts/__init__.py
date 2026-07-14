"""Public M4 parser/OCR contract surface."""

from nh_ad_parser_contracts.artifacts import (
    ArtifactAccessDenied,
    ArtifactChecksumMismatch,
    ArtifactMetadata,
    ArtifactStore,
    InMemoryArtifactMetadataRepository,
    InMemoryArtifactStorage,
)
from nh_ad_parser_contracts.models import (
    Confidence,
    ConfidenceStatus,
    Coordinate,
    LayoutBlock,
    NormalizedDocument,
    Page,
    Table,
    TextBlock,
    Warning,
    confidence_status,
)
from nh_ad_parser_contracts.routing import (
    AdapterNotConfigured,
    DocumentInput,
    ParserAdapter,
    ParserAttempt,
    ParserRoute,
    ParserRouter,
    ParserSelection,
)

__all__ = [
    "AdapterNotConfigured",
    "ArtifactAccessDenied",
    "ArtifactChecksumMismatch",
    "ArtifactMetadata",
    "ArtifactStore",
    "Confidence",
    "ConfidenceStatus",
    "Coordinate",
    "DocumentInput",
    "InMemoryArtifactMetadataRepository",
    "InMemoryArtifactStorage",
    "LayoutBlock",
    "NormalizedDocument",
    "Page",
    "ParserAdapter",
    "ParserAttempt",
    "ParserRoute",
    "ParserRouter",
    "ParserSelection",
    "Table",
    "TextBlock",
    "Warning",
    "confidence_status",
]
