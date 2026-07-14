from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class GovernanceIntegrationTest(unittest.TestCase):
    repository: Path = Path(__file__).resolve().parents[2]

    def test_pre_push_validates_upstream_commit_range(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            binary_directory = root / "bin"
            scripts_directory = root / "scripts"
            binary_directory.mkdir()
            scripts_directory.mkdir()
            call_log = root / "python-calls.log"

            git_script = "\n".join(
                (
                    "#!/bin/sh",
                    'if [ "$1" = "rev-parse" ] && [ "$2" = "--show-toplevel" ]; then',
                    f"  printf '%s\\n' '{root}'",
                    'elif [ "$1" = "rev-parse" ] && [ "$2" = "--abbrev-ref" ]; then',
                    "  printf '%s\\n' 'origin/main'",
                    "else",
                    "  exit 1",
                    "fi",
                    "",
                )
            )
            python_script = "\n".join(
                (
                    "#!/bin/sh",
                    'printf \'%s\\n\' "$*" >> "$CALL_LOG"',
                    "",
                )
            )
            consistency_script = "#!/bin/sh\nexit 0\n"
            skill_adapter_script = "#!/bin/sh\nexit 0\n"

            git_path = binary_directory / "git"
            python_path = binary_directory / "python3"
            consistency_path = scripts_directory / "check-doc-consistency.sh"
            skill_adapter_path = scripts_directory / "manage-skill-adapters.sh"
            _ = git_path.write_text(git_script, encoding="utf-8")
            _ = python_path.write_text(python_script, encoding="utf-8")
            _ = consistency_path.write_text(consistency_script, encoding="utf-8")
            _ = skill_adapter_path.write_text(skill_adapter_script, encoding="utf-8")
            git_path.chmod(0o755)
            python_path.chmod(0o755)
            consistency_path.chmod(0o755)
            skill_adapter_path.chmod(0o755)

            environment = os.environ.copy()
            environment["PATH"] = f"{binary_directory}:{environment['PATH']}"
            environment["CALL_LOG"] = str(call_log)
            process = subprocess.run(
                [str(self.repository / ".githooks" / "pre-push")],
                cwd=root,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

            calls = call_log.read_text(encoding="utf-8")

        self.assertEqual(0, process.returncode, process.stderr)
        self.assertIn(
            "-m scripts.doc_guard validate --scope diff --base-ref origin/main",
            calls,
        )

    def test_push_workflow_uses_event_before_and_quality_gates(self) -> None:
        workflow = (
            self.repository / ".github" / "workflows" / "document-governance.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("github.event.before", workflow)
        self.assertIn("uvx ruff check", workflow)
        self.assertIn(
            "uvx basedpyright --project governance/pyrightconfig.json", workflow
        )
        self.assertNotIn("--base-ref HEAD~1", workflow)

    def test_pre_commit_tracks_governance_entrypoints(self) -> None:
        hook = (self.repository / ".githooks" / "pre-commit").read_text(
            encoding="utf-8"
        )

        self.assertIn("setup-dev-tools", hook)
        self.assertIn("skill-adapters/", hook)
        self.assertIn("\\.githooks/", hook)
        self.assertIn("manage-skill-adapters.sh validate", hook)

    def test_pre_commit_runs_governance_checks_for_staged_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "repository"
            scripts = root / "scripts"
            hooks = root / ".githooks"
            docs = root / "docs"
            binary_directory = root / "bin"
            scripts.mkdir(parents=True)
            hooks.mkdir()
            docs.mkdir()
            binary_directory.mkdir()
            call_log = root / "calls.log"
            _ = shutil.copy2(
                self.repository / ".githooks" / "pre-commit",
                hooks / "pre-commit",
            )
            for script_name in (
                "manage-skill-adapters.sh",
                "check-doc-consistency.sh",
            ):
                script = scripts / script_name
                _ = script.write_text(
                    '#!/bin/sh\nprintf \'%s\\n\' "$0 $*" >> "$CALL_LOG"\n',
                    encoding="utf-8",
                )
                script.chmod(0o755)
            python = binary_directory / "python3"
            _ = python.write_text(
                '#!/bin/sh\nprintf \'%s\\n\' "python3 $*" >> "$CALL_LOG"\n',
                encoding="utf-8",
            )
            python.chmod(0o755)
            project_rules = docs / "project-rules.md"
            _ = project_rules.write_text("# Project rules\n", encoding="utf-8")
            environment = os.environ.copy()
            environment["PATH"] = f"{binary_directory}:{environment['PATH']}"
            environment["CALL_LOG"] = str(call_log)
            commands = (
                ["git", "init", "--quiet"],
                ["git", "config", "user.email", "test@example.com"],
                ["git", "config", "user.name", "Test"],
                ["git", "add", "."],
                ["git", "commit", "--quiet", "-m", "fixture"],
            )
            for command in commands:
                setup = subprocess.run(
                    command,
                    cwd=root,
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(0, setup.returncode, setup.stderr)
            project_rules.unlink()
            stage = subprocess.run(
                ["git", "add", "--update"],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )

            process = subprocess.run(
                [str(hooks / "pre-commit")],
                cwd=root,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            calls = call_log.read_text(encoding="utf-8")

            self.assertEqual(0, stage.returncode, stage.stderr)
            self.assertEqual(0, process.returncode, process.stderr)
            self.assertIn("check-doc-consistency.sh", calls)
            self.assertIn("doc_guard validate --scope staged", calls)

    def test_setup_installs_only_project_local_skill_adapters(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "repository"
            scripts = root / "scripts"
            hooks = root / ".githooks"
            tests = root / "tests" / "governance"
            skill = root / "skills" / "sample-skill"
            scripts.mkdir(parents=True)
            hooks.mkdir()
            tests.mkdir(parents=True)
            skill.mkdir(parents=True)
            _ = shutil.copy2(
                self.repository / "scripts" / "setup-dev-tools.sh",
                scripts / "setup-dev-tools.sh",
            )
            _ = shutil.copy2(
                self.repository / "scripts" / "manage-skill-adapters.sh",
                scripts / "manage-skill-adapters.sh",
            )
            _ = shutil.copytree(
                self.repository / "scripts" / "skill-adapters",
                scripts / "skill-adapters",
            )
            _ = (scripts / "__init__.py").write_text("", encoding="utf-8")
            _ = (scripts / "doc_guard.py").write_text("", encoding="utf-8")
            consistency = scripts / "check-doc-consistency.sh"
            _ = consistency.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            consistency.chmod(0o755)
            for hook_name in ("pre-commit", "pre-push"):
                hook = hooks / hook_name
                _ = hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                hook.chmod(0o755)
            _ = (skill / "SKILL.md").write_text(
                "---\nname: sample-skill\ndescription: Test skill.\n---\n",
                encoding="utf-8",
            )
            git_init = subprocess.run(
                ["git", "init", "--quiet", str(root)],
                check=False,
                capture_output=True,
                text=True,
            )
            home = Path(temporary_directory) / "home"
            environment = os.environ.copy()
            environment["HOME"] = str(home)
            environment["SKILL_ADAPTER_MODE"] = "symlink"

            process = subprocess.run(
                [str(scripts / "setup-dev-tools.sh")],
                cwd=root,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            hooks_path = subprocess.run(
                ["git", "config", "--get", "core.hooksPath"],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, git_init.returncode, git_init.stderr)
            self.assertEqual(0, process.returncode, process.stderr)
            self.assertTrue((root / ".agents" / "skills" / "sample-skill").is_symlink())
            self.assertTrue((root / ".claude" / "skills" / "sample-skill").is_symlink())
            self.assertFalse((home / ".codex").exists())
            self.assertFalse((home / ".claude").exists())
            self.assertEqual(".githooks", hooks_path.stdout.strip())


if __name__ == "__main__":
    _ = unittest.main()
