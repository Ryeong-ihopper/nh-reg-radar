import importlib.util
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
            self.assertIn("private/nh-parser/run.py", names)
            self.assertIn("private/nh-parser/pyproject.toml", names)
            self.assertIn("private/nh-parser/nh_parser_fin/__init__.py", names)
            self.assertIn("source-manifest.json", names)

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
