from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class SkillAdapterTransactionTest(unittest.TestCase):
    repository: Path = Path(__file__).resolve().parents[2]

    def test_partial_backup_cleanup_keeps_committed_adapter_roots_consistent(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            skill = root / "skills" / "sample-skill"
            skill.mkdir(parents=True)
            skill_file = skill / "SKILL.md"
            original = "---\nname: sample-skill\ndescription: Original.\n---\n"
            updated = "---\nname: sample-skill\ndescription: Updated.\n---\n"
            _ = skill_file.write_text(original, encoding="utf-8")
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
            _ = skill_file.write_text(updated, encoding="utf-8")
            binary_directory = root / "bin"
            binary_directory.mkdir()
            remove = binary_directory / "rm"
            _ = remove.write_text(
                "".join(
                    (
                        "#!/bin/sh\n",
                        "for target do :; done\n",
                        '"$REAL_RM" -f "$target/SKILL.md"\n',
                        "exit 1\n",
                    )
                ),
                encoding="utf-8",
            )
            remove.chmod(0o755)
            real_remove = shutil.which("rm")
            if real_remove is None:
                self.fail("rm command not found")
            environment["PATH"] = f"{binary_directory}:{environment['PATH']}"
            environment["REAL_RM"] = real_remove

            reinstall = subprocess.run(
                [str(script), "install"],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            validate = subprocess.run(
                [str(script), "validate"],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(0, install.returncode, install.stderr)
            self.assertEqual(0, reinstall.returncode, reinstall.stderr)
            self.assertEqual(0, validate.returncode, validate.stderr)
            for tool_directory in (".agents", ".claude"):
                target = root / tool_directory / "skills" / "sample-skill" / "SKILL.md"
                self.assertEqual(updated, target.read_text(encoding="utf-8"))
            backups = [
                backup
                for tool_directory in (".agents", ".claude")
                for backup in (root / tool_directory / "skills").glob(".*.backup.*")
            ]
            self.assertEqual(2, len(backups))


if __name__ == "__main__":
    _ = unittest.main()
