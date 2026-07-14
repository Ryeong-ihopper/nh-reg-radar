from __future__ import annotations

import json
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path

from scripts.validate_goal_manifest import JsonValue, Manifest, validate_manifest


class GoalManifestValidatorTest(unittest.TestCase):
    repository: Path = Path(__file__).resolve().parents[2]

    def _fixture(self, root: Path) -> Manifest:
        documents = {
            "docs/requirements-definition.md": "## FR-001 Advertisement upload\n",
            "docs/functional-specification.md": "| F-001 | Advertisement upload |\n",
            "docs/screen-specification.md": "| S-003 | Advertisement upload |\n",
            "docs/api-specification.md": (
                "| Method | POST |\n| URI | `/api/v1/advertisements` |\n"
            ),
            "docs/database-specification.md": "## 5.1 advertisements\n",
            "docs/test-cases.md": "| TC-ADV-001 | Advertisement upload |\n",
            "tests/api/test_advertisements.py": ("def test_create_advertisement():\n    pass\n"),
        }
        for relative, contents in documents.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            _ = path.write_text(contents, encoding="utf-8")
        return {
            "schema_version": 1,
            "goal_id": "G001-example",
            "capability": "Advertisement upload",
            "trace": {
                "requirements": ["FR-001"],
                "functions": ["F-001"],
                "screens": ["S-003"],
                "api_operations": ["POST /api/v1/advertisements"],
                "db_objects": ["app.advertisements"],
            },
            "test_cases": [
                {
                    "id": "TC-ADV-001",
                    "nodes": ["tests/api/test_advertisements.py::test_create_advertisement"],
                }
            ],
            "changed_paths": ["openapi/openapi.yaml"],
            "synchronized_documents": [
                "docs/api-specification.md",
                "docs/test-cases.md",
            ],
        }

    @staticmethod
    def _mapping(manifest: Manifest, field: str) -> dict[str, JsonValue]:
        value = manifest[field]
        if not isinstance(value, dict):
            raise AssertionError(f"{field} is not a mapping")
        return value

    @staticmethod
    def _list(manifest: Manifest, field: str) -> list[JsonValue]:
        value = manifest[field]
        if not isinstance(value, list):
            raise AssertionError(f"{field} is not a list")
        return value

    def _validate(self, update: Callable[[Manifest], None] | None = None) -> set[str]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            manifest = self._fixture(root)
            if update is not None:
                update(manifest)
            manifest_path = root / "governance" / "goal-manifests" / "goal.json"
            manifest_path.parent.mkdir(parents=True)
            _ = manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            findings = validate_manifest(root, manifest_path)
        return {finding.code for finding in findings}

    def test_valid_manifest_maps_all_trace_dimensions(self) -> None:
        self.assertEqual(set(), self._validate())

    def test_repository_manifest_is_valid(self) -> None:
        manifest = self.repository / "governance" / "goal-manifests" / "G001-m0.json"
        findings = validate_manifest(self.repository, manifest)

        self.assertEqual([], findings)

    def test_g005_m4_repository_manifest_is_valid_and_complete(self) -> None:
        manifest = self.repository / "governance" / "goal-manifests" / "G005-m4-parser-ocr-job.json"
        findings = validate_manifest(self.repository, manifest)
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        identifiers = {item["id"] for item in payload["test_cases"]}

        self.assertEqual([], findings)
        self.assertEqual(
            {
                *(f"TC-REV-{number:03d}" for number in range(1, 15)),
                *(f"TC-OCR-{number:03d}" for number in range(1, 25)),
            },
            identifiers,
        )

    def test_missing_trace_dimension_is_rejected(self) -> None:
        def remove_screens(manifest: Manifest) -> None:
            _ = self._mapping(manifest, "trace").pop("screens")

        codes = self._validate(remove_screens)

        self.assertIn("MANIFEST_FIELD_MISSING", codes)

    def test_unknown_source_id_is_rejected(self) -> None:
        def use_unknown_id(manifest: Manifest) -> None:
            self._mapping(manifest, "trace")["requirements"] = ["FR-999"]

        codes = self._validate(use_unknown_id)

        self.assertIn("TRACE_UNKNOWN_ID", codes)

    def test_duplicate_trace_id_is_rejected(self) -> None:
        def duplicate_function(manifest: Manifest) -> None:
            self._mapping(manifest, "trace")["functions"] = ["F-001", "F-001"]

        codes = self._validate(duplicate_function)

        self.assertIn("TRACE_DUPLICATE", codes)

    def test_duplicate_test_case_id_is_rejected(self) -> None:
        def duplicate(manifest: Manifest) -> None:
            test_cases = self._list(manifest, "test_cases")
            first = test_cases[0]
            if not isinstance(first, dict):
                raise AssertionError("test case is not a mapping")
            test_cases.append(dict(first))

        self.assertIn("TRACE_DUPLICATE", self._validate(duplicate))

    def test_test_case_must_exist_in_document(self) -> None:
        def unknown(manifest: Manifest) -> None:
            test_cases = self._list(manifest, "test_cases")
            first = test_cases[0]
            if not isinstance(first, dict):
                raise AssertionError("test case is not a mapping")
            first["id"] = "TC-ADV-999"

        self.assertIn("TRACE_UNKNOWN_ID", self._validate(unknown))

    def test_manifest_requires_at_least_one_test_case(self) -> None:
        def remove_test_cases(manifest: Manifest) -> None:
            manifest["test_cases"] = []

        self.assertIn("TEST_CASE_MISSING", self._validate(remove_test_cases))

    def test_test_case_requires_execution_or_manual_mapping(self) -> None:
        def unmap(manifest: Manifest) -> None:
            test_cases = self._list(manifest, "test_cases")
            first = test_cases[0]
            if not isinstance(first, dict):
                raise AssertionError("test case is not a mapping")
            _ = first.pop("nodes")

        self.assertIn("TEST_CASE_UNMAPPED", self._validate(unmap))

    def test_missing_test_node_is_rejected(self) -> None:
        def missing_node(manifest: Manifest) -> None:
            test_cases = self._list(manifest, "test_cases")
            first = test_cases[0]
            if not isinstance(first, dict):
                raise AssertionError("test case is not a mapping")
            first["nodes"] = ["tests/api/test_missing.py::test_missing"]

        self.assertIn("TEST_NODE_MISSING", self._validate(missing_node))

    def test_api_change_requires_api_and_test_document_sync(self) -> None:
        def omit_sync(manifest: Manifest) -> None:
            manifest["synchronized_documents"] = []

        self.assertIn("API_DOC_SYNC_MISSING", self._validate(omit_sync))

    def test_non_api_change_does_not_require_api_document_sync(self) -> None:
        def governance_only(manifest: Manifest) -> None:
            manifest["changed_paths"] = ["scripts/validate_goal_manifest.py"]
            manifest["synchronized_documents"] = []

        self.assertNotIn("API_DOC_SYNC_MISSING", self._validate(governance_only))


if __name__ == "__main__":
    _ = unittest.main()
