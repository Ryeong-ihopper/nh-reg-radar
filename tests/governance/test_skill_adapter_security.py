from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class SkillAdapterSecurityTest(unittest.TestCase):
    repository: Path = Path(__file__).resolve().parents[2]

    def test_install_rejects_external_adapter_root(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "repository"
            outside = Path(temporary_directory) / "outside"
            skill = root / "skills" / "sample-skill"
            skill.mkdir(parents=True)
            outside.mkdir()
            _ = (skill / "SKILL.md").write_text(
                "---\nname: sample-skill\ndescription: Test skill.\n---\n",
                encoding="utf-8",
            )
            agents_root = root / ".agents"
            agents_root.mkdir()
            (agents_root / "skills").symlink_to(outside, target_is_directory=True)
            environment = os.environ.copy()
            environment["SKILL_ADAPTER_ROOT"] = str(root)
            environment["SKILL_ADAPTER_MODE"] = "copy"

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

            self.assertNotEqual(0, process.returncode)
            self.assertIn("symbolic link", process.stderr)
            self.assertFalse((outside / "sample-skill").exists())

    def test_install_rejects_external_skill_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "repository"
            source_root = root / "skills"
            outside_skill = Path(temporary_directory) / "external-skill"
            source_root.mkdir(parents=True)
            outside_skill.mkdir()
            _ = (outside_skill / "SKILL.md").write_text(
                "---\nname: external-skill\ndescription: External.\n---\n",
                encoding="utf-8",
            )
            (source_root / "external-skill").symlink_to(
                outside_skill,
                target_is_directory=True,
            )
            environment = os.environ.copy()
            environment["SKILL_ADAPTER_ROOT"] = str(root)

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

            self.assertNotEqual(0, process.returncode)
            self.assertIn("skill source must not be a symbolic link", process.stderr)

    def test_install_rejects_nested_source_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "repository"
            skill = root / "skills" / "sample-skill"
            external_file = Path(temporary_directory) / "external.md"
            skill.mkdir(parents=True)
            _ = (skill / "SKILL.md").write_text(
                "---\nname: sample-skill\ndescription: Test skill.\n---\n",
                encoding="utf-8",
            )
            _ = external_file.write_text("external", encoding="utf-8")
            (skill / "reference.md").symlink_to(external_file)
            environment = os.environ.copy()
            environment["SKILL_ADAPTER_ROOT"] = str(root)
            environment["SKILL_ADAPTER_MODE"] = "copy"

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

            self.assertNotEqual(0, process.returncode)
            self.assertIn("skill source contains a symbolic link", process.stderr)

    def test_install_does_not_trust_forged_copy_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            skill = root / "skills" / "sample-skill"
            target = root / ".agents" / "skills" / "sample-skill"
            skill.mkdir(parents=True)
            target.mkdir(parents=True)
            _ = (skill / "SKILL.md").write_text(
                "---\nname: sample-skill\ndescription: Test skill.\n---\n",
                encoding="utf-8",
            )
            protected_file = target / "keep.txt"
            _ = protected_file.write_text("keep", encoding="utf-8")
            _ = (target / ".skill-adapter-source.sha256").write_text(
                "source=skills/sample-skill\nhash=bogus\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["SKILL_ADAPTER_ROOT"] = str(root)
            environment["SKILL_ADAPTER_MODE"] = "copy"

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

            self.assertNotEqual(0, process.returncode)
            self.assertIn("unmanaged adapter collision", process.stderr)
            self.assertTrue(protected_file.exists())

    def test_install_does_not_trust_incomplete_copy_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            skill = root / "skills" / "sample-skill"
            target = root / ".agents" / "skills" / "sample-skill"
            skill.mkdir(parents=True)
            target.mkdir(parents=True)
            _ = (skill / "SKILL.md").write_text(
                "---\nname: sample-skill\ndescription: Test skill.\n---\n",
                encoding="utf-8",
            )
            protected_file = target / "keep.txt"
            _ = protected_file.write_text("keep", encoding="utf-8")
            _ = (target / ".skill-adapter-source.sha256").write_text(
                "source=skills/sample-skill\n",
                encoding="utf-8",
            )
            environment = os.environ.copy()
            environment["SKILL_ADAPTER_ROOT"] = str(root)
            environment["SKILL_ADAPTER_MODE"] = "copy"

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

            self.assertNotEqual(0, process.returncode)
            self.assertIn("unmanaged adapter collision", process.stderr)
            self.assertTrue(protected_file.exists())


if __name__ == "__main__":
    _ = unittest.main()
