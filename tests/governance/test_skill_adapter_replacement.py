from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class SkillAdapterReplacementTest(unittest.TestCase):
    repository: Path = Path(__file__).resolve().parents[2]

    def test_failed_reinstall_preserves_existing_adapter(self) -> None:
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
            environment["SKILL_ADAPTER_MODE"] = "symlink"
            script = self.repository / "scripts" / "manage-skill-adapters.sh"
            install = subprocess.run(
                [str(script), "install"],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            binary_directory = root / "bin"
            binary_directory.mkdir()
            failing_link = binary_directory / "ln"
            _ = failing_link.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            failing_link.chmod(0o755)
            environment["PATH"] = f"{binary_directory}:{environment['PATH']}"

            reinstall = subprocess.run(
                [str(script), "install"],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            target = root / ".agents" / "skills" / "sample-skill"

            self.assertEqual(0, install.returncode, install.stderr)
            self.assertNotEqual(0, reinstall.returncode)
            self.assertTrue(target.is_symlink())
            self.assertEqual(Path("../../skills/sample-skill"), target.readlink())

    def test_install_rejects_symbolic_link_adapter_parent(self) -> None:
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
            (root / ".agents").symlink_to(outside, target_is_directory=True)
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
            self.assertIn("symbolic link", process.stderr)
            self.assertEqual([], list(outside.iterdir()))

    def test_install_does_not_replace_modified_copy(self) -> None:
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
            target_file = root / ".agents" / "skills" / "sample-skill" / "SKILL.md"
            _ = target_file.write_text("modified\n", encoding="utf-8")

            reinstall = subprocess.run(
                [str(script), "install"],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, install.returncode, install.stderr)
            self.assertNotEqual(0, reinstall.returncode)
            self.assertEqual("modified\n", target_file.read_text(encoding="utf-8"))

    def test_install_removes_valid_stale_copy(self) -> None:
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
            target = root / ".agents" / "skills" / "sample-skill"
            shutil.rmtree(skill)

            cleanup = subprocess.run(
                [str(script), "install"],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, install.returncode, install.stderr)
            self.assertEqual(0, cleanup.returncode, cleanup.stderr)
            self.assertFalse(target.exists())

    def test_activation_failure_restores_previous_adapter(self) -> None:
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
            environment["SKILL_ADAPTER_MODE"] = "symlink"
            script = self.repository / "scripts" / "manage-skill-adapters.sh"
            install = subprocess.run(
                [str(script), "install"],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            binary_directory = root / "bin"
            binary_directory.mkdir()
            move = binary_directory / "mv"
            remove = binary_directory / "rm"
            _ = move.write_text(
                "".join(
                    (
                        "#!/bin/sh\n",
                        'count="$(cat "$MV_COUNT_FILE" 2>/dev/null || printf 0)"\n',
                        "count=$((count + 1))\n",
                        'printf \'%s\n\' "$count" > "$MV_COUNT_FILE"\n',
                        '[ "$count" -eq 2 ] && exit 1\n',
                        'exec "$REAL_MV" "$@"\n',
                    )
                ),
                encoding="utf-8",
            )
            _ = remove.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
            move.chmod(0o755)
            remove.chmod(0o755)
            real_move = shutil.which("mv")
            if real_move is None:
                self.fail("mv command not found")
            environment["PATH"] = f"{binary_directory}:{environment['PATH']}"
            environment["REAL_MV"] = real_move
            environment["MV_COUNT_FILE"] = str(root / "mv-count")

            reinstall = subprocess.run(
                [str(script), "install"],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            target = root / ".agents" / "skills" / "sample-skill"

            self.assertEqual(0, install.returncode, install.stderr)
            self.assertNotEqual(0, reinstall.returncode)
            self.assertTrue(target.is_symlink())
            self.assertEqual(Path("../../skills/sample-skill"), target.readlink())
            self.assertEqual([], list((root / ".agents" / "skills").glob("*.backup.*")))

    def test_invalid_copy_candidate_preserves_previous_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            skill = root / "skills" / "sample-skill"
            skill.mkdir(parents=True)
            source_text = "---\nname: sample-skill\ndescription: Test skill.\n---\n"
            _ = (skill / "SKILL.md").write_text(source_text, encoding="utf-8")
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
            binary_directory = root / "bin"
            binary_directory.mkdir()
            copy = binary_directory / "cp"
            _ = copy.write_text(
                "".join(
                    (
                        "#!/bin/sh\n",
                        '"$REAL_CP" "$@" || exit $?\n',
                        "for destination do :; done\n",
                        "printf 'corrupted\\n' > \"$destination/SKILL.md\"\n",
                    )
                ),
                encoding="utf-8",
            )
            copy.chmod(0o755)
            real_copy = shutil.which("cp")
            if real_copy is None:
                self.fail("cp command not found")
            environment["PATH"] = f"{binary_directory}:{environment['PATH']}"
            environment["REAL_CP"] = real_copy

            reinstall = subprocess.run(
                [str(script), "install"],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            target_file = root / ".agents" / "skills" / "sample-skill" / "SKILL.md"

            self.assertEqual(0, install.returncode, install.stderr)
            self.assertNotEqual(0, reinstall.returncode)
            self.assertEqual(source_text, target_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    _ = unittest.main()
