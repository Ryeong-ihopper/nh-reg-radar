import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "operational_runtime", ROOT / "scripts/operational_runtime.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class OperationalRuntimeTests(unittest.TestCase):
    def fixture(self, root, names):
        manifest = root / MODULE.MANIFEST
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({"schema": "nh-operational-runtime-files-v1",
                                       "entrypoints": [], "files": names}), encoding="utf-8")

    def test_missing_runtime_file_fails_before_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root, ["scripts/missing.py"])
            with self.assertRaisesRegex(ValueError, "missing runtime file"):
                MODULE.stage(root / "output", root)
            self.assertFalse((root / "output").exists())

    def test_traversal_absolute_and_duplicate_paths_are_rejected(self):
        for names in (["../outside.py"], ["/outside.py"], ["C:/outside.py"],
                      ["scripts\\outside.py"], ["scripts/main.py", "scripts/main.py"]):
            with self.subTest(names=names), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.fixture(root, names)
                with self.assertRaisesRegex(ValueError, "unsafe|duplicate"):
                    MODULE.runtime_files(root)

    def test_added_import_or_subprocess_dependency_requires_manifest_update(self):
        for body in ("import extra\n", "command = ['python', 'extra.py']\n"):
            with self.subTest(body=body), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.fixture(root, ["scripts/main.py"])
                (root / "scripts").mkdir()
                (root / "scripts/main.py").write_text(body, encoding="utf-8")
                (root / "scripts/extra.py").write_text("", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "omitted runtime dependencies"):
                    MODULE.runtime_files(root)

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            marker = output / "existing.txt"
            marker.write_text("preserve", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "empty directory"):
                MODULE.stage(output)
            self.assertEqual(marker.read_text(), "preserve")

    def test_runtime_stage_hashes_and_repository_tooling_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "runtime"
            receipt = MODULE.stage(output)
            actual = {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}
            self.assertEqual(actual, set(receipt["sha256"]) | {"runtime-files-manifest.json"})
            for name, digest in receipt["sha256"].items():
                self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest)
                self.assertEqual(hashlib.sha256((output / name).read_bytes()).hexdigest(), digest)
            required = {"rag-pipeline/tools/build_silver_requests.py",
                        "rag-pipeline/tools/recover_operational_judgments.py",
                        "scripts/parse_hwp_native.py", "scripts/render_hwp_review_html.py"}
            self.assertTrue(required.issubset(actual))
            for name in ("rag-pipeline/tools/ingest_template_hwpx.py",
                         "rag-pipeline/tools/compile_current_execution_plans.py",
                         "rag-pipeline/tools/evaluate_structured_plan.py",
                         "scripts/doc_guard.py", "apps/backend/migrations/env.py",
                         "scripts/package_operational_server.py"):
                self.assertTrue((ROOT / name).is_file(), name)
                self.assertNotIn(name, actual)
            self.assertFalse(any("/tests/" in n or "/legacy/" in n for n in actual))

    def test_staged_web_runner_recovery_and_parser_entrypoints_load_in_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "runtime"
            MODULE.stage(output)
            environment = dict(os.environ, PYTHONPATH="", PYTHONDONTWRITEBYTECODE="1",
                               PYTHONIOENCODING="utf-8")
            code = '''import importlib.util, pathlib, sys
root = pathlib.Path.cwd()
for name in ("scripts/serve-operational-review.py", "rag-pipeline/tools/serve_operational_api.py",
             "rag-pipeline/tools/run_operational_e2e.py", "rag-pipeline/tools/run_gemma_exhaustive_dgx.py",
             "rag-pipeline/tools/recover_operational_judgments.py", "scripts/parse_hwp_native.py",
             "scripts/render_hwp_review_html.py"):
    spec = importlib.util.spec_from_file_location(pathlib.Path(name).stem.replace("-", "_"), root / name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
for module in tuple(sys.modules.values()):
    name = getattr(module, "__name__", "")
    if name.startswith(("rag.", "nh_ad_backend.", "nh_ai_providers.", "nh_parser_contracts.")):
        assert pathlib.Path(module.__file__).resolve().is_relative_to(root), name
print("isolated operational imports passed")
'''
            result = subprocess.run([sys.executable, "-c", code], cwd=output, env=environment,
                                    encoding="utf-8", capture_output=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for name in ("rag-pipeline/tools/run_operational_e2e.py",
                         "rag-pipeline/tools/recover_operational_judgments.py",
                         "scripts/serve-operational-review.py"):
                result = subprocess.run([sys.executable, name, "--help"], cwd=output, env=environment,
                                        encoding="utf-8", capture_output=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
