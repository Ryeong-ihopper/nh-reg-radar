"""Prevent answer leakage and advertisement-specific behavior in runtime code."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_FILES = (
    ROOT / "rag/operational/contracts.py",
    ROOT / "rag/operational/prepare_inputs.py",
    ROOT / "rag/build_items.py",
    ROOT / "tools/build_ad_evidence_vectors.py",
    ROOT / "tools/build_silver_requests.py",
    ROOT / "tools/dgx_bge_client.py",
    ROOT / "tools/dgx_openai_client.py",
    ROOT / "tools/hybrid_rule_retrieval.py",
    ROOT / "tools/model_result_io.py",
    ROOT / "tools/regulation_v2_catalog.py",
    ROOT / "tools/run_gemma_exhaustive_dgx.py",
    ROOT / "tools/run_operational_e2e.py",
)
ENTRYPOINT_FILES = (
    ROOT / "tools/run_operational_e2e.py",
    ROOT / "tools/hybrid_rule_retrieval.py",
    ROOT / "tools/run_gemma_exhaustive_dgx.py",
)

FORBIDDEN_RUNTIME_REFERENCES = (
    "search_gold19_reviewed_draft",
    "researcher_answer_pilot",
    "researcher_feedback",
    "human_review",
    "case_rule_mapping19",
    "rule_executors_v2",
    "apply_rule_guards_new6",
    "prepare_exhaustive_gold6_0904",
)
LOCAL_ENVIRONMENT = re.compile(
    r"(?:C:\\Users\\babie|babie0511@|10\.90\.0\.103|spark_auto)",
    re.IGNORECASE,
)
ADVERTISEMENT_LITERAL = re.compile(
    r"(?:new_\d{3}_(?:대출성|예금성)|NH농협은행-\d{4}[_-]\d{3})"
)


def source(path: Path) -> str:
    assert path.is_file(), f"canonical runtime file is missing: {path}"
    return path.read_text(encoding="utf-8")


def test_runtime_contains_no_advertisement_specific_literals() -> None:
    leaked = {
        path.name: sorted(set(ADVERTISEMENT_LITERAL.findall(source(path))))
        for path in RUNTIME_FILES
        if ADVERTISEMENT_LITERAL.search(source(path))
    }
    assert not leaked, f"advertisement-specific literals in runtime: {leaked}"


def test_runtime_reads_no_gold_or_feedback_artifact() -> None:
    leaked = {}
    for path in RUNTIME_FILES:
        hits = [value for value in FORBIDDEN_RUNTIME_REFERENCES if value in source(path)]
        if hits:
            leaked[path.name] = hits
    assert not leaked, f"gold/researcher feedback referenced by runtime: {leaked}"


def test_runtime_contains_no_personal_or_internal_default() -> None:
    leaked = [path.name for path in RUNTIME_FILES if LOCAL_ENVIRONMENT.search(source(path))]
    assert not leaked, f"personal/internal defaults in runtime: {leaked}"


def test_runtime_does_not_import_development_answer_builder() -> None:
    forbidden_imports = (
        "build_silver_review_workbook",
        "build_answer10_review_workbook",
        "prepare_answer10_current",
    )
    leaked = {}
    for path in ENTRYPOINT_FILES:
        hits = [value for value in forbidden_imports if value in source(path)]
        if hits:
            leaked[path.name] = hits
    assert not leaked, f"development answer builder imported by runtime: {leaked}"


def test_common_silver_builder_lazy_loads_legacy_converter() -> None:
    text = source(ROOT / "tools/build_silver_requests.py")
    before_main = text.split("def main()", 1)[0]
    assert "from build_review_input_v1 import" not in before_main
