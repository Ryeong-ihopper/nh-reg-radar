"""Canonical NH advertisement compliance pipeline contracts and preparation."""

from .contracts import (
    GEMMA_RESPONSE_VERSION,
    INTEGRATED_INPUT_VERSION,
    OPERATIONAL_RESULT_VERSION,
    SEARCH_DOCUMENT_VERSION,
    ContractError,
    validate_integrated_input,
    validate_operational_result,
    validate_search_document,
)

__all__ = [
    "GEMMA_RESPONSE_VERSION",
    "INTEGRATED_INPUT_VERSION",
    "OPERATIONAL_RESULT_VERSION",
    "SEARCH_DOCUMENT_VERSION",
    "ContractError",
    "validate_integrated_input",
    "validate_operational_result",
    "validate_search_document",
]
