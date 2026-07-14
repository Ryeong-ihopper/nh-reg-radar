from __future__ import annotations

import tempfile
import unittest
import unicodedata
from pathlib import Path

from scripts.doc_governance.config import load_config
from scripts.doc_governance.git_changes import GitCommandError, changed_files
from scripts.doc_governance.impact import filter_changed_paths, validate_change_impact
from scripts.doc_governance.models import GovernanceConfig
from scripts.doc_governance.validators import validate_repository


class DocumentGovernanceTest(unittest.TestCase):
    repository: Path = Path(__file__).resolve().parents[2]
    config: GovernanceConfig = load_config(repository / "governance" / "document-policy.json")

    def test_current_documents_satisfy_repository_policy(self) -> None:
        findings = validate_repository(self.repository, self.config)

        errors = [finding for finding in findings if finding.severity == "error"]
        self.assertEqual([], errors)

    def test_missing_document_metadata_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            document = root / "docs" / "sample.md"
            document.parent.mkdir(parents=True)
            _ = document.write_text("# Sample\n", encoding="utf-8")

            findings = validate_repository(
                root,
                self.config.with_required_documents(("docs/sample.md",)),
            )

        codes = {finding.code for finding in findings}
        self.assertIn("DOC_CURRENT_INFO", codes)
        self.assertIn("DOC_CHANGELOG", codes)

    def test_non_english_document_filename_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            document = root / "docs" / "문서.md"
            document.parent.mkdir(parents=True)
            document_text = "\n".join(
                (
                    "# 문서",
                    "",
                    "## 문서 현행 정보",
                    "",
                    "| 항목 | 내용 |",
                    "| --- | --- |",
                    "| 현행 버전 | v1.0 |",
                    "| 기준일 | 2026-07-13 |",
                    "",
                    "## 변경 이력",
                    "",
                    "| 버전 | 기준일 | 변경 내용 |",
                    "| --- | --- | --- |",
                    "| v1.0 | 2026-07-13 | 최초 작성 |",
                    "",
                )
            )
            _ = document.write_text(
                document_text,
                encoding="utf-8",
            )

            findings = validate_repository(
                root,
                self.config.with_required_documents(("docs/문서.md",)),
            )

        codes = {finding.code for finding in findings}
        self.assertIn("DOC_FILENAME", codes)

    def test_current_changelog_entry_must_be_first(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            document = root / "docs" / "sample.md"
            document.parent.mkdir(parents=True)
            document_text = "\n".join(
                (
                    "# Sample",
                    "",
                    "## 문서 현행 정보",
                    "",
                    "| 항목 | 내용 |",
                    "| --- | --- |",
                    "| 현행 버전 | v1.1 |",
                    "| 기준일 | 2026-07-13 |",
                    "",
                    "## 변경 이력",
                    "",
                    "| 버전 | 기준일 | 변경 내용 |",
                    "| --- | --- | --- |",
                    "| v1.0 | 2026-07-01 | 최초 작성 |",
                    "| v1.1 | 2026-07-13 | 변경 |",
                    "",
                )
            )
            _ = document.write_text(
                document_text,
                encoding="utf-8",
            )

            findings = validate_repository(
                root,
                self.config.with_required_documents(("docs/sample.md",)),
            )

        codes = {finding.code for finding in findings}
        self.assertIn("DOC_CHANGELOG_CURRENT", codes)

    def test_adr_missing_from_index_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            adr_dir = root / "docs" / "adr"
            adr_dir.mkdir(parents=True)
            _ = (adr_dir / "README.md").write_text("# ADR 목록\n", encoding="utf-8")
            adr_text = "\n\n".join(
                (
                    "# ADR-0001: Example",
                    "## 상태\n\nAccepted",
                    "## 배경\n\nContext",
                    "## 결정\n\nDecision",
                    "## 대안\n\nAlternative",
                    "## 영향\n\nImpact",
                    "## 후속 조치\n\nAction",
                    "## 관련 문서\n\nNone\n",
                )
            )
            _ = (adr_dir / "ADR-0001-example.md").write_text(
                adr_text,
                encoding="utf-8",
            )

            findings = validate_repository(
                root,
                self.config.with_required_documents(()),
            )

        codes = {finding.code for finding in findings}
        self.assertIn("ADR_INDEX_MISSING", codes)

    def test_contract_change_requires_specification_and_tests(self) -> None:
        changed = ["apps/backend/api/reviews.py"]

        findings = validate_change_impact(changed, self.config)

        codes = {finding.code for finding in findings}
        self.assertIn("CHANGE_IMPACT", codes)
        self.assertIn("TEST_IMPACT", codes)

    def test_contract_change_passes_with_required_documents_and_test(self) -> None:
        changed = [
            "apps/backend/api/reviews.py",
            "docs/api-specification.md",
            "docs/test-cases.md",
            "tests/api/test_reviews.py",
        ]

        findings = validate_change_impact(changed, self.config)

        errors = [finding for finding in findings if finding.severity == "error"]
        self.assertEqual([], errors)

    def test_test_case_document_does_not_replace_automated_tests(self) -> None:
        changed = [
            "apps/backend/services/reviews.py",
            "docs/test-cases.md",
        ]

        findings = validate_change_impact(changed, self.config)

        codes = {finding.code for finding in findings}
        self.assertIn("TEST_IMPACT", codes)

    def test_sensitive_source_paths_are_excluded_from_impact_output(self) -> None:
        sensitive_path = unicodedata.normalize(
            "NFD",
            "docs/광고예시/customer-source.pdf",
        )

        changed = filter_changed_paths(
            [sensitive_path, "docs/project-rules.md"],
            self.config,
        )

        self.assertEqual(["docs/project-rules.md"], changed)

    def test_protected_source_markdown_is_not_an_active_document(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            protected_document = root / "docs" / "광고예시" / "고객원본.md"
            protected_document.parent.mkdir(parents=True)
            _ = protected_document.write_text("# 원본\n", encoding="utf-8")

            findings = validate_repository(
                root,
                self.config.with_required_documents(()),
            )

        protected_paths = [finding.path for finding in findings if "광고예시" in finding.path]
        self.assertEqual([], protected_paths)

    def test_invalid_diff_base_is_an_error(self) -> None:
        with self.assertRaises(GitCommandError):
            _ = changed_files(
                self.repository,
                "diff",
                "refs/heads/__document_governance_missing_base__",
            )


if __name__ == "__main__":
    _ = unittest.main()
