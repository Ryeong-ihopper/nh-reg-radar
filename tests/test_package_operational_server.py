import importlib.util
import hashlib
import json
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "package_operational_server", ROOT / "scripts/package_operational_server.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class OperationalPackageTests(unittest.TestCase):
    def test_parser_fin_bundle_keeps_executable_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parser = root / "parser"
            (parser / "nh_parser_fin").mkdir(parents=True)
            (parser / "run.py").write_text("", encoding="utf-8")
            (parser / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
            (parser / "nh_parser_fin/__init__.py").write_text("", encoding="utf-8")
            document = root / "document-processor/src/document_processor"
            document.mkdir(parents=True)
            (document / "__init__.py").write_text("", encoding="utf-8")
            output = root / "bundle.tgz"

            MODULE.package(output, parser, root / "document-processor")

            with tarfile.open(output, "r:gz") as archive:
                names = set(archive.getnames())
                manifest = json.load(archive.extractfile("source-manifest.json"))["sha256"]
                self.assertEqual(names, set(manifest) | {"source-manifest.json"})
                for name, digest in manifest.items():
                    self.assertEqual(hashlib.sha256(archive.extractfile(name).read()).hexdigest(), digest)
            self.assertIn("private/nh-parser/run.py", names)
            self.assertIn("private/nh-parser/pyproject.toml", names)
            self.assertIn("private/nh-parser/nh_parser_fin/__init__.py", names)
            self.assertIn("source-manifest.json", names)
            for name in ("canonical-execution-plans-v2.json", "operational-catalog-migration-v1.json",
                         "operational-rule-dispositions-v1.json"):
                self.assertIn("rag-pipeline/config/" + name, names)
            for name in ("scripts/operational_runtime.py", "infra/operational/runtime-files.json",
                         "rag-pipeline/tools/build_silver_requests.py",
                         "rag-pipeline/tools/recover_operational_judgments.py"):
                self.assertIn(name, names)
            for name in ("scripts/doc_guard.py", "scripts/package_operational_server.py",
                         "rag-pipeline/tools/ingest_template_hwpx.py",
                         "rag-pipeline/tools/compile_current_execution_plans.py",
                         "apps/backend/migrations/env.py"):
                self.assertNotIn(name, names)

    def test_legacy_parser_layout_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parser = root / "parser"
            (parser / "tools").mkdir(parents=True)
            (parser / "tools/parse.py").write_text("", encoding="utf-8")
            document = root / "document-processor/src/document_processor"
            document.mkdir(parents=True)
            (document / "__init__.py").write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "nh-parser-fin"):
                MODULE.package(root / "bundle.tgz", parser, root / "document-processor")


if __name__ == "__main__":
    unittest.main()
