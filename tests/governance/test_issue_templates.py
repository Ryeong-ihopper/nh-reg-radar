from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import cast

ALLOWED_TYPES = ("feat", "fix", "hotfix", "refactor", "docs", "test", "chore", "ci")
REQUIRED_KEYS = ("name", "about", "title", "labels", "assignees")
KEY_PATTERN = re.compile(r"^(?P<key>[a-z][a-z0-9_]*):(?P<rest>.*)$")


class FrontMatterError(ValueError):
    """Raised when issue-template front matter violates the accepted grammar."""


def parse_front_matter(text: str) -> dict[str, str]:
    """Validate and parse issue-template front matter.

    GitHub silently drops a template from the chooser when its front matter is
    malformed. To catch that without a YAML dependency, this accepts only the
    narrowest shape the templates need: a flat mapping of the documented keys whose
    values are JSON-compatible double-quoted strings, each validated with
    `json.loads`. Flow sequences and bare scalars are rejected outright, so
    unbalanced brackets, bad escapes and non-string types cannot slip through.
    Comma-separated labels are written as one quoted string (`labels: "bug, ui"`).

    PyYAML is deliberately not used: the governance suite runs under the bare
    `setup-python` interpreter in CI, where PyYAML is not guaranteed to exist.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise FrontMatterError("front matter must open with '---'")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise FrontMatterError("front matter must close with '---'") from error

    parsed: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        if line != line.lstrip():
            raise FrontMatterError(f"nested or indented mapping is not allowed: {line!r}")
        match = KEY_PATTERN.match(line)
        if match is None:
            raise FrontMatterError(f"line is not a top-level 'key: value' pair: {line!r}")
        key = match.group("key")
        rest = match.group("rest")
        if not rest.startswith(" "):
            raise FrontMatterError(f"'{key}' must be followed by a space before its value")
        if key in parsed:
            raise FrontMatterError(f"duplicate key: {key}")
        parsed[key] = _string_value(key, rest.strip())
    if not parsed:
        raise FrontMatterError("front matter is empty")
    return parsed


def _string_value(key: str, raw: str) -> str:
    """Require a JSON-compatible double-quoted string and return its value."""
    if not raw.startswith('"'):
        raise FrontMatterError(f"'{key}' must be a double-quoted string: {raw!r}")
    try:
        decoded = cast(object, json.loads(raw))
    except ValueError as error:
        raise FrontMatterError(f"'{key}' is not a valid quoted string: {raw!r}") from error
    if not isinstance(decoded, str):
        raise FrontMatterError(f"'{key}' must be a string, got {type(decoded).__name__}")
    return decoded


class FrontMatterGrammarTest(unittest.TestCase):
    """Prove the parser rejects the malformations it is meant to catch."""

    def test_rejects_malformed_front_matter(self) -> None:
        cases = {
            "unclosed flow sequence": '---\nname: "a"\nlabels: [broken\n---\n',
            "unbalanced nested brackets": '---\nname: "a"\nlabels: [a, [b]\n---\n',
            "flow sequence value": '---\nname: "a"\nlabels: [bug, ui]\n---\n',
            "single quoted value": "---\nname: 'a'\n---\n",
            "bare scalar value": "---\nname: a\n---\n",
            "numeric value": "---\nname: 123\n---\n",
            "boolean value": "---\nname: true\n---\n",
            "unterminated quote": '---\nname: "broken\n---\n',
            "invalid escape": '---\nname: "a\\qb"\n---\n',
            "duplicate key": '---\nname: "a"\nname: "b"\n---\n',
            "missing opening delimiter": 'name: "a"\n---\n',
            "missing closing delimiter": '---\nname: "a"\n',
            "indented mapping": '---\nname: "a"\n  nested: "b"\n---\n',
            "not a mapping": "---\n- item\n---\n",
            "inline map": '---\nname: {inline: "map"}\n---\n',
        }
        for label, text in cases.items():
            with self.subTest(case=label):
                with self.assertRaises(FrontMatterError):
                    _ = parse_front_matter(text)

    def test_accepts_the_documented_shape(self) -> None:
        text = (
            "---\n"
            'name: "결함 신고"\n'
            'about: "제목은 `fix: <요약>` 형식"\n'
            'title: "fix: "\n'
            'labels: ""\n'
            'assignees: ""\n'
            "---\n"
        )
        parsed = parse_front_matter(text)
        self.assertEqual(parsed["name"], "결함 신고")
        self.assertEqual(parsed["title"], "fix: ")
        self.assertEqual(parsed["labels"], "")

    def test_accepts_comma_separated_labels_as_one_string(self) -> None:
        text = '---\nname: "a"\nabout: "b"\ntitle: "c"\nlabels: "bug, ui"\nassignees: ""\n---\n'
        self.assertEqual(parse_front_matter(text)["labels"], "bug, ui")


class IssueTemplateTest(unittest.TestCase):
    """Guard the repository's GitHub issue templates and the documented convention."""

    repository: Path = Path(__file__).resolve().parents[2]

    @property
    def template_directory(self) -> Path:
        return self.repository / ".github" / "ISSUE_TEMPLATE"

    def _templates(self) -> list[Path]:
        return sorted(self.template_directory.glob("*.md"))

    def test_issue_templates_exist(self) -> None:
        self.assertTrue(self.template_directory.is_dir(), ".github/ISSUE_TEMPLATE must exist")
        names = {path.name for path in self._templates()}
        self.assertIn("bug_report.md", names)
        self.assertIn("task.md", names)

    def test_front_matter_is_valid_and_complete(self) -> None:
        for path in self._templates():
            with self.subTest(template=path.name):
                parsed = parse_front_matter(path.read_text(encoding="utf-8"))
                self.assertEqual(
                    sorted(parsed),
                    sorted(REQUIRED_KEYS),
                    f"{path.name} key set must match GitHub's",
                )
                self.assertTrue(parsed["name"], f"{path.name} needs a non-empty name")

    def test_bug_template_defaults_to_conventional_fix_title(self) -> None:
        parsed = parse_front_matter(
            (self.template_directory / "bug_report.md").read_text(encoding="utf-8")
        )
        self.assertTrue(
            parsed["title"].startswith("fix:"),
            "bug report template must default to the 'fix: ' Conventional title",
        )

    def test_templates_reference_the_documented_convention(self) -> None:
        for path in self._templates():
            with self.subTest(template=path.name):
                body = path.read_text(encoding="utf-8")
                self.assertIn("§11.3", body, f"{path.name} must cite the naming rule section")
                self.assertIn("<type>: <한글 요약>", body)

    def test_project_rules_document_the_issue_title_convention(self) -> None:
        rules = (self.repository / "docs" / "project-rules.md").read_text(encoding="utf-8")
        self.assertIn("## 11.3 이슈·브랜치 및 커밋 명명", rules)
        self.assertIn("이슈 제목은 커밋·PR과 동일한 Conventional 형식", rules)
        for issue_type in ALLOWED_TYPES:
            self.assertIn(f"`{issue_type}`", rules)

    def test_pull_request_template_links_issues(self) -> None:
        template = (self.repository / ".github" / "pull_request_template.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("## 관련 이슈", template)
        self.assertIn("#<issue-number>", template)

    def test_kanban_wording_is_conditional_everywhere(self) -> None:
        """The Notion kanban link is only required when a kanban is in operation."""
        sources = [self.repository / "README.md", self.repository / "docs" / "project-rules.md"]
        sources.extend(self._templates())
        for path in sources:
            with self.subTest(document=path.name):
                body = path.read_text(encoding="utf-8")
                if "칸반" not in body:
                    continue
                self.assertIn(
                    "칸반을 운영하는 경우",
                    body,
                    f"{path.name} must state the kanban link requirement conditionally",
                )


if __name__ == "__main__":
    _ = unittest.main()
