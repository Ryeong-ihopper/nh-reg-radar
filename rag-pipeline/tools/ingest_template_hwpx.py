"""Ingest an explicitly supplied general template; output is private local data."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rag.templates.catalog import TemplateCatalog  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    catalog = TemplateCatalog.from_hwpx(args.source)
    source, document = catalog.source, catalog.document
    report = {
        "source_sha256": document["source"]["sha256"],
        "tables": len(source["tables"]),
        "physical_cells": sum(len(t["cells"]) for t in source["tables"]),
        "outside_paragraphs": len(source["outside_paragraphs"]),
        "template_sections": len({r["template_section"] for r in document["entries"]}),
        "entries": len(document["entries"]),
        "structure_status": dict(Counter(r["status"] for r in document["entries"])),
        "requirement_modes": dict(Counter(r["requirement_mode"] for r in document["entries"])),
        "entry_issues": dict(Counter(i for r in document["entries"] for i in r["issues"])),
        "source_issues": document["issues"],
        "validation_scope": "XML structure only; visual and semantic review pending",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in [("source.json", source), ("catalog.json", document), ("validation.json", report)]:
        target = args.output_dir / name
        with target.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
