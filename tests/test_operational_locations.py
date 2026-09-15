"""Synthetic provenance boundaries, not advertisement-specific verdict fixtures."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from operational_locations import resolve_locations, saved_workspace, valid_box


def source():
    return {"diagnostics": {"asset_pages": {"FILE-b": {"start": 2, "end": 2}}},
            "pages": [{"page_no": 2, "canvas_w": 100, "canvas_h": 200,
                       "regions": [{"region_id": "R", "bbox": [0, 0, 100, 100],
                                    "lines": [{"line_ref": "FILE-b::L1", "text": "repeated text", "bbox": [1, 2, 80, 20]}]}],
                       "unassigned_lines": [{"line_ref": "FILE-b::U1", "text": "unassigned", "bbox": [1, 30, 80, 40]}]}]}


def test_unassigned_and_asset_local_page_are_preserved():
    value = resolve_locations(source(), {"evidence_line_refs": ["FILE-b::U1"]}, {})
    assert len(value) == 1
    assert (value[0]["pageNo"], value[0]["asset_id"], value[0]["source_page_no"]) == (2, "FILE-b", 1)
    assert value[0]["precision"] == "LINE"


def test_region_selected_text_never_becomes_exact_line_fallback():
    doc = {"region_id": "R", "page_no": 2, "span_status": "region_level_selected_text", "line_refs": ["FILE-b::L1"]}
    value = resolve_locations(source(), {"evidence_ids": ["E"]}, {"E": doc})
    assert len(value) == 1 and value[0]["precision"] == "REGION"
    doc["span_status"] = "selected_text_line_aligned"
    assert resolve_locations(source(), {"evidence_ids": ["E"]}, {"E": doc})[0]["precision"] == "LINE"
    doc.pop("span_status")
    assert resolve_locations(source(), {"evidence_ids": ["E"]}, {"E": doc}) == []


def test_invalid_geometry_and_unknown_refs_fail_closed():
    for box in ([0, 0, 101, 10], [1, 1, 0, 2], [0, 0, float("nan"), 10], [0, 1], None):
        assert not valid_box(box, 100, 200)
    assert not valid_box([0, 0, 10, 10], 0, 200)
    assert resolve_locations(source(), {"evidence_line_refs": ["another-product::L1"]}, {}) == []


def test_workspace_scopes_rules_and_preserves_failure_distinction():
    ads, requests = [], []
    for suffix in ("a", "b"):
        scope = f"ADV::product:{suffix}"
        ads.append({"ad_id": "ADV", "scope_id": scope, "candidates": [
            {"item_id": "R1", "judgment": {"verdict": "NOT_APPLICABLE", "reason": suffix}},
            {"item_id": "FAILED", "status": "output_failure"}], "deferred_rules": []})
        requests.append({"ad_id": scope, "rules": [{"item_id": "R1", "title": suffix}], "documents": []})
    raw = {"ads": ads, "output_failure_pairs": [{"ad_id": "ADV", "item_id": "FAILED", "reason": "invalid JSON"}, {"ad_id": "OTHER"}]}
    value = saved_workspace(raw, requests, source(), "ADV")
    assert [r["title"] for r in value["rows"]] == ["a", "b"]
    assert all(r["verdict"] == "미해당" for r in value["rows"])
    assert len(value["output_failure_pairs"]) == 1
    assert value["output_failure_pairs"][0]["reason"] == "invalid JSON"


def test_budget_deferral_is_visible_but_not_a_verdict_or_input_failure():
    raw = {"ads": [{"ad_id": "ADV", "scope_id": "S", "candidates": [],
                    "deferred_rules": [{"item_id": "R1", "reason": "routing did not select this rule's template section"}]}]}
    discovery = {"ads": [{"ad_id": "S", "candidate_budget": {"deferred_ids": ["R2"]}},
                         {"ad_id": "OTHER", "candidate_budget": {"deferred_ids": ["R3"]}}]}
    value = saved_workspace(raw, [], source(), "ADV", discovery)
    assert [r["deferred_kind"] for r in value["deferred_rules"]] == ["OTHER_TEMPLATE", "EXECUTION_BUDGET"]
    assert value["rows"] == []


def test_same_template_title_keeps_distinct_source_examples_and_missing_checks():
    checks = [{"status": "MISSING", "finding_basis": "ABSENCE"}]
    raw = {"ads": [{"ad_id": "ADV", "scope_id": "ADV::product:p", "candidates": [
        {"item_id": key, "judgment": {"verdict": "VIOLATION", "requirement_checks": checks}}
        for key in ("TPL-A", "TPL-B")]}]}
    requests = [{"ad_id": "ADV::product:p", "documents": [], "rules": [
        {"item_id": key, "title": "Shared heading", "source_sheet": "HWPX_TEMPLATE", "example_text": example}
        for key, example in (("TPL-A", "First source meaning"), ("TPL-B", "Second source meaning"))]}]
    rows = saved_workspace(raw, requests, source(), "ADV")["rows"]
    assert [row["template_example"] for row in rows] == ["First source meaning", "Second source meaning"]
    assert all(row["requirement_checks"] == checks for row in rows)
    assert all(row["verdict"] == "위반" for row in rows)
