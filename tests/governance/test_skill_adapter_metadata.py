from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class SkillAdapterMetadataTest(unittest.TestCase):
    repository: Path = Path(__file__).resolve().parents[2]

    def test_copy_adapter_rejects_extra_marker_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            skill = root / "skills" / "sample-skill"
            skill.mkdir(parents=True)
            _ = (skill / "SKILL.md").write_text(
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
            marker = (
                root
                / ".agents"
                / "skills"
                / "sample-skill"
                / ".skill-adapter-source.sha256"
            )
            with marker.open("a", encoding="utf-8") as marker_file:
                _ = marker_file.write("extra=value\n")

            validate = subprocess.run(
                [str(script), "validate"],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, install.returncode, install.stderr)
            self.assertNotEqual(0, validate.returncode)
            self.assertIn("unmanaged skill adapter", validate.stderr)

    def test_copy_adapter_rejects_unterminated_extra_marker_record(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            skill = root / "skills" / "sample-skill"
            skill.mkdir(parents=True)
            _ = (skill / "SKILL.md").write_text(
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
            marker = (
                root
                / ".agents"
                / "skills"
                / "sample-skill"
                / ".skill-adapter-source.sha256"
            )
            with marker.open("a", encoding="utf-8") as marker_file:
                _ = marker_file.write("extra=value")

            validate = subprocess.run(
                [str(script), "validate"],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, install.returncode, install.stderr)
            self.assertNotEqual(0, validate.returncode)
            self.assertIn("unmanaged skill adapter", validate.stderr)

    def test_copy_adapter_detects_empty_directory_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            skill = root / "skills" / "sample-skill"
            skill.mkdir(parents=True)
            _ = (skill / "SKILL.md").write_text(
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
            adapter = root / ".agents" / "skills" / "sample-skill"
            (adapter / "empty").mkdir()

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

    def test_skill_source_rejects_special_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            skill = root / "skills" / "sample-skill"
            skill.mkdir(parents=True)
            _ = (skill / "SKILL.md").write_text(
                "---\nname: sample-skill\ndescription: Test skill.\n---\n",
                encoding="utf-8",
            )
            os.mkfifo(skill / "unsupported.fifo")
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
            self.assertIn("unsupported file type", process.stderr)


if __name__ == "__main__":
    _ = unittest.main()
