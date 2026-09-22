"""Build integrated/coarse/fine audit inputs from nh-ad-parser P1/P3 output."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from rag.contracts.validation import validate_search_collections
from rag.parsing.prepare_inputs import combine, search_docs, write_json, write_jsonl


def parser_output_key(path: Path, kind: str) -> str:
    """Return one document key for legacy same-name and v3/v6 suffixed files."""
    suffix = f".{kind}.json"
    if path.name.endswith(suffix):
        return path.name.removesuffix(suffix)
    if path.suffix == ".json":
        return path.stem
    raise ValueError(f"unsupported {kind.upper()} output filename: {path.name}")


def pair_parser_outputs(p1_dir: Path, p3_dir: Path) -> list[tuple[str, Path, Path]]:
    """Pair P1/P3 without assuming the two schema generations name files alike."""
    def keyed(directory: Path, kind: str) -> dict[str, Path]:
        output: dict[str, Path] = {}
        for path in sorted(directory.glob("*.json")):
            # A shared v3/v6 final directory contains both kinds.
            if path.name.endswith((".p1.json", ".p3.json")) and not path.name.endswith(f".{kind}.json"):
                continue
            key = parser_output_key(path, kind)
            if key in output:
                raise ValueError(f"duplicate {kind.upper()} output key: {key}")
            output[key] = path
        return output

    p1 = keyed(p1_dir, "p1")
    p3 = keyed(p3_dir, "p3")
    if not p1:
        raise ValueError("P1 directory contains no JSON files")
    if set(p1) != set(p3):
        raise ValueError("P1/P3 output document keys differ")
    return [(key, p1[key], p3[key]) for key in sorted(p1)]


def confirmed_routing(
    document: dict,
    *,
    product_group: str,
    product_subtype: str,
    media_type: str | None,
) -> None:
    routing = document["document"].setdefault("routing_metadata", {})
    routing.update({
        "product_group": {
            "value": product_group,
            "source": "audit_manifest",
            "status": "provided",
        },
        "product_subtype": {
            "value": product_subtype,
            "source": "audit_manifest",
            "status": "provided",
        },
        "template_id": {
            "value": product_subtype,
            "source": "audit_manifest",
            "status": "verified",
        },
    })
    if media_type:
        routing["media_type"] = {
            "value": media_type,
            "source": "audit_manifest",
            "status": "provided",
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--p1-dir", type=Path, required=True)
    parser.add_argument("--p3-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--product-group", required=True)
    parser.add_argument("--product-subtype", required=True)
    parser.add_argument(
        "--media-type",
        help="confirmed common media type; omit when files use mixed or unknown media",
    )
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("output directory already exists")

    pairs = pair_parser_outputs(args.p1_dir, args.p3_dir)

    integrated_documents = []
    coarse_documents = []
    fine_documents = []
    manifest_rows = []
    for document_key, p1_path, p3_path in pairs:
        document = combine(p1_path, p3_path)
        confirmed_routing(
            document,
            product_group=args.product_group,
            product_subtype=args.product_subtype,
            media_type=args.media_type,
        )
        coarse, fine = search_docs(document)
        integrated_documents.append(document)
        coarse_documents.extend(coarse)
        fine_documents.extend(fine)
        target = args.output_dir / "integrated" / f"{document_key}.json"
        write_json(target, document)
        manifest_rows.append({
            "source_file": document["document"]["source_file"],
            "p1": str(p1_path.resolve()),
            "p3": str(p3_path.resolve()),
            "integrated": str(target.resolve()),
            "coarse_documents": len(coarse),
            "fine_documents": len(fine),
        })

    validate_search_collections(
        integrated_documents, coarse_documents, fine_documents
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "evidence_coarse.jsonl", coarse_documents)
    write_jsonl(args.output_dir / "evidence_fine.jsonl", fine_documents)
    manifest = {
        "schema_version": "parser-output-search-audit-input-v1",
        "scope": "chunking and retrieval audit only",
        "routing": {
            "product_group": args.product_group,
            "product_subtype": args.product_subtype,
            "media_type": args.media_type,
        },
        "counts": {
            "advertisements": len(integrated_documents),
            "coarse_documents": len(coarse_documents),
            "fine_documents": len(fine_documents),
        },
        "documents": manifest_rows,
    }
    write_json(args.output_dir / "manifest.json", manifest)
    print(json.dumps(manifest["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
