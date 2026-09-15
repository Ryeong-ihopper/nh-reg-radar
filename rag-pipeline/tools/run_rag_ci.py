# -*- coding: utf-8 -*-
"""One-command offline CI gate for the active RAG/search/judgment code."""
from __future__ import annotations

import importlib.util
import inspect
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
UNIT_PATTERNS = (
    "test_retrieval_separation.py",
    "test_judge_output_contract.py",
    "test_parser_contract_adapter.py",
    "test_reading_quality.py",
    "test_operational_condition_contracts.py",
    "test_blind_evaluation.py",
    "test_operational_template_catalog.py",
    "test_operational_rag_contracts.py",
    "test_operational_grounding.py",
    "test_operational_chunking.py",
    "test_operational_schema_contracts.py",
    "test_gold_v2_binding.py",
    "test_operational_recovery.py",
    "test_operational_policy.py",
    "test_operational_service.py",
    "test_operational_decision_guides.py",
    "test_operational_reranking.py",
    "test_operational_search_integrity.py",
    "test_runtime_call_metrics.py",
)
FUNCTION_MODULES = (
    "test_operational_applicability.py",
    "test_operational_acceleration.py",
    "test_operational_no_leakage.py",
    "test_operational_codebase_structure.py",
)


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"테스트 모듈을 읽을 수 없음: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for pattern in UNIT_PATTERNS:
        suite.addTests(loader.discover(str(TESTS), pattern=pattern, top_level_dir=str(TESTS)))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1

    function_count = 0
    for filename in FUNCTION_MODULES:
        module = load_module(TESTS / filename)
        for name, function in inspect.getmembers(module, inspect.isfunction):
            if not name.startswith("test_"):
                continue
            function()
            function_count += 1
            print(f"ok: {filename}::{name}")
    print(f"RAG CI PASS: unittest={result.testsRun}, function_checks={function_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
