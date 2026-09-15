"""Open one real saved run in an isolated local UI; never rerun models or alter live state.

Copies only the selected advertisement, its review metadata and checksum-verified
assets. Predictions and requests remain immutable, linked to their original paths.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-state", type=Path, required=True)
    parser.add_argument("--review-id", required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--execution-config", type=Path, required=True)
    parser.add_argument("--port", type=int, default=5181)
    args = parser.parse_args()
    source, target = args.source_state.resolve(), args.state_dir.resolve()
    if target.exists():
        raise ValueError("Verification state must be a new directory; existing data will not be overwritten")
    state = read(source / "execution/web-state.json")
    bundle = next(row for row in state["reviews"] if row["review"]["review_id"] == args.review_id)
    ad_id = bundle["review"]["advertisement_id"]
    ad = next(row for row in state["advertisements"] if row["advertisement_id"] == ad_id)
    result_path = args.result.resolve()
    result = read(result_path)
    if {row["ad_id"] for row in result["ads"]} != {ad_id}:
        raise ValueError("Saved result does not match the selected registered advertisement")
    for file in ad["files"]:
        path = (source / "private" / file["storage_key"]).resolve()
        if path.parent != source / "private" or hashlib.sha256(path.read_bytes()).hexdigest() != file["checksum"]:
            raise ValueError("Original asset path/checksum mismatch")
    spec = importlib.util.spec_from_file_location("operational_viewer", ROOT / "scripts/serve-operational-review.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from operational_locations import saved_workspace
    from operational_web_bridge import parser_layout
    from rag.api.service import write_json_atomic

    selected = copy.deepcopy(bundle)
    selected["review"]["status"] = "REVIEW_COMPLETED"
    failed = result.get("output_failure_pairs", [])
    selected["job"].update(status="COMPLETED_WITH_WARNINGS" if failed else "COMPLETED", progress_rate=100)
    isolated = {"version": state["version"], "advertisements": [ad], "reviews": [selected], "results": [],
                "routing": {ad_id: state["routing"].get(ad_id, {})}, "decisions": {},
                "links": {args.review_id: {"result_file": str(result_path), "output_failure_count": len(failed)}}}
    directory = target / "execution/runs" / args.review_id
    directory.mkdir(parents=True)
    # Generated private workspace, including when a caller chooses another
    # output path: do not accidentally stage customer assets/session tokens.
    (target / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")
    document = read(source / "execution/runs" / args.review_id / "integrated.json")
    write_json_atomic(directory / "integrated.json", document)
    write_json_atomic(directory / "parser-layout.json", parser_layout(document, source="saved_run_verification"))
    (target / "private").mkdir()
    for file in ad["files"]:
        shutil.copy2(source / "private" / file["storage_key"], target / "private" / file["storage_key"])
    write_json_atomic(target / "execution/web-state.json", isolated)
    payloads = [json.loads(json.loads(line)["messages"][1]["content"])
                for line in result_path.with_name("02_judgment_requests.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    workspace = saved_workspace(result, payloads, document, ad_id)
    write_json_atomic(target / "verification.json", {
        "source_result_sha256": hashlib.sha256(result_path.read_bytes()).hexdigest(),
        "review_id": args.review_id, "advertisement_id": ad_id,
        "display_rows": len(workspace["rows"]),
        "rows_with_geometry": sum(bool(row["evidence_locations"]) for row in workspace["rows"]),
        "approximate_region_rows": sum(any(loc["precision"] == "REGION" for loc in row["evidence_locations"]) for row in workspace["rows"]),
        "asset_count": len(ad["files"]), "model_calls": 0,
        "live_state_modified": False,
    })
    app = module.build_operational_server(SimpleNamespace(
        state_dir=target, execution_config=args.execution_config.resolve(),
        static_dir=ROOT / "apps/frontend/dist", port=args.port,
    ))
    # Verification server exposes the same read APIs and frontend but cannot
    # accidentally send a new advertisement to a model or mutate a verdict.
    from fastapi.responses import JSONResponse
    @app.middleware("http")
    async def read_only_verification(request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"} and "/auth/" not in request.url.path:
            return JSONResponse({"message": "Saved-run verification is read-only"}, status_code=409)
        return await call_next(request)
    module.uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
