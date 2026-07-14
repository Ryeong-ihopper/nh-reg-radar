from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class SkillAdapterBehaviorTest(unittest.TestCase):
    repository: Path = Path(__file__).resolve().parents[2]

    def test_skill_adapters_install_only_in_project_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            skill = root / "skills" / "sample-skill"
            skill.mkdir(parents=True)
            _ = (skill / "SKILL.md").write_text(
                "---\nname: sample-skill\ndescription: Test skill.\n---\n",
                encoding="utf-8",
            )
            home = root / "home"
            environment = os.environ.copy()
            environment["HOME"] = str(home)
            environment["SKILL_ADAPTER_ROOT"] = str(root)
            environment["SKILL_ADAPTER_MODE"] = "symlink"

            process = subprocess.run(
                [
                    str(self.repository / "scripts" / "manage-skill-adapters.sh"),
                    "install",
                ],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

            codex_adapter = root / ".agents" / "skills" / "sample-skill"
            claude_adapter = root / ".claude" / "skills" / "sample-skill"

            self.assertEqual(0, process.returncode, process.stderr)
            self.assertTrue(codex_adapter.is_symlink())
            self.assertTrue(claude_adapter.is_symlink())
            self.assertEqual(
                Path("../../skills/sample-skill"),
                codex_adapter.readlink(),
            )
            self.assertEqual(
                Path("../../skills/sample-skill"),
                claude_adapter.readlink(),
            )
            self.assertFalse((home / ".codex").exists())
            self.assertFalse((home / ".claude").exists())

    def test_copy_skill_adapter_detects_source_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            skill_file = root / "skills" / "sample-skill" / "SKILL.md"
            skill_file.parent.mkdir(parents=True)
            _ = skill_file.write_text(
                "---\nname: sample-skill\ndescription: Test skill.\n---\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["SKILL_ADAPTER_ROOT"] = str(root)
            environment["SKILL_ADAPTER_MODE"] = "copy"
            script = self.repository / "scripts" / "manage-skill-adapters.sh"

            install = subprocess.run(
                [str(script), "install"],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            _ = skill_file.write_text(
                "---\nname: sample-skill\ndescription: Changed.\n---\n",
                encoding="utf-8",
            )
            validate = subprocess.run(
                [str(script), "validate"],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, install.returncode, install.stderr)
            self.assertNotEqual(0, validate.returncode)
            self.assertIn("source drift", validate.stderr)

    def test_skill_adapter_validation_detects_deleted_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            skill_file = root / "skills" / "sample-skill" / "SKILL.md"
            skill_file.parent.mkdir(parents=True)
            _ = skill_file.write_text(
                "---\nname: sample-skill\ndescription: Test skill.\n---\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["SKILL_ADAPTER_ROOT"] = str(root)
            environment["SKILL_ADAPTER_MODE"] = "symlink"
            script = self.repository / "scripts" / "manage-skill-adapters.sh"
            install = subprocess.run(
                [str(script), "install"],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            skill_file.unlink()
            skill_file.parent.rmdir()

            validate = subprocess.run(
                [str(script), "validate"],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, install.returncode, install.stderr)
            self.assertNotEqual(0, validate.returncode)
            self.assertIn("stale skill adapter", validate.stderr)

    def test_copy_skill_adapter_detects_source_mode_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            skill_file = root / "skills" / "sample-skill" / "SKILL.md"
            helper = skill_file.parent / "helper.sh"
            skill_file.parent.mkdir(parents=True)
            _ = skill_file.write_text(
                "---\nname: sample-skill\ndescription: Test skill.\n---\n",
                encoding="utf-8",
            )
            _ = helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            helper.chmod(0o644)
            environment = os.environ.copy()
            environment["SKILL_ADAPTER_ROOT"] = str(root)
            environment["SKILL_ADAPTER_MODE"] = "copy"
            script = self.repository / "scripts" / "manage-skill-adapters.sh"
            install = subprocess.run(
                [str(script), "install"],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            helper.chmod(0o755)

            validate = subprocess.run(
                [str(script), "validate"],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, install.returncode, install.stderr)
            self.assertNotEqual(0, validate.returncode)
            self.assertIn("source drift", validate.stderr)

    def test_copy_skill_adapter_detects_content_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            skill_file = root / "skills" / "sample-skill" / "SKILL.md"
            skill_file.parent.mkdir(parents=True)
            _ = skill_file.write_text(
                "---\nname: sample-skill\ndescription: Test skill.\n---\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["SKILL_ADAPTER_ROOT"] = str(root)
            environment["SKILL_ADAPTER_MODE"] = "copy"
            script = self.repository / "scripts" / "manage-skill-adapters.sh"
            install = subprocess.run(
                [str(script), "install"],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            adapter_file = root / ".agents" / "skills" / "sample-skill" / "SKILL.md"
            _ = adapter_file.write_text("modified\n", encoding="utf-8")

            validate = subprocess.run(
                [str(script), "validate"],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, install.returncode, install.stderr)
            self.assertNotEqual(0, validate.returncode)
            self.assertIn("content drift", validate.stderr)


if __name__ == "__main__":
    _ = unittest.main()
