from __future__ import annotations

import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.run_governance_tests import write_snapshot


class GovernanceRuntimeTest(unittest.TestCase):
    def test_snapshot_preserves_working_bytes_and_modes_without_ignored_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            root = parent / "repository"
            root.mkdir()
            command = ["git", "-c", "core.autocrlf=false", "-C", str(root)]
            _ = subprocess.run([*command, "init", "--quiet"], check=True)
            _ = (root / ".gitignore").write_bytes(b"*.key\ndocs/private.md\n")
            _ = (root / "run.sh").write_bytes(b"#!/bin/sh\necho original\n")
            _ = (root / "removed.txt").write_bytes(b"remove from working tree")
            _ = subprocess.run([*command, "add", "."], check=True)
            _ = subprocess.run([*command, "update-index", "--chmod=+x", "run.sh"], check=True)
            changed = b"#!/bin/sh\necho working\n"
            _ = (root / "run.sh").write_bytes(changed)
            (root / "removed.txt").unlink()
            _ = (root / "private.key").write_bytes(b"fixture secret must not leave source")
            _ = (root / "untracked-config.json").write_bytes(b"{}")
            (root / "docs").mkdir()
            _ = (root / "docs/work-log.md").write_bytes(b"# Local document\n")
            _ = (root / "docs/private.md").write_bytes(b"ignored document")
            destination = parent / "snapshot.tar"
            self.assertEqual(3, write_snapshot(root, destination))
            with tarfile.open(destination) as archive:
                self.assertEqual(
                    {".gitignore", "run.sh", "docs/work-log.md"}, set(archive.getnames())
                )
                self.assertEqual(0o755, archive.getmember("run.sh").mode)
                script = archive.extractfile("run.sh")
                assert script is not None
                self.assertEqual(changed, script.read())

    def test_snapshot_rejects_parent_path_without_reading_external_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            index = b"100644 " + b"0" * 40 + b" 0\t../private.key\0"
            with patch("scripts.run_governance_tests._git", side_effect=[index, b""]):
                with self.assertRaisesRegex(ValueError, "Unsafe snapshot path"):
                    _ = write_snapshot(root, root / "snapshot.tar")
