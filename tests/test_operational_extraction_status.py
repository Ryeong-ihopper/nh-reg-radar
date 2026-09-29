"""Synthetic extraction observations: no gold, provider or source mutation."""
import copy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from operational_locations import extraction_status, saved_workspace


def document():
    return {"diagnostics": {"asset_pages": {"A": {"start": 2, "end": 2}}},
            "pages": [{"page_no": 2, "asset_id": "A", "source_page_no": 1,
                       "parse_status": "ok", "canvas_w": 100, "canvas_h": 100,
                       "regions": [{"region_id": "R", "final_text": "synthetic readable text",
                                    "bbox": [1, 1, 90, 20], "lines": []}]}]}


def test_success_is_extraction_not_accuracy_or_compliance():
    doc = document()
    before = copy.deepcopy(doc)
    result = extraction_status(doc, [{"file_id": "A", "file_name": "synthetic.png"}])
    assert result["status"] == "EXTRACTED" and result["accuracy_verified"] is False
    assert result["files"][0]["pages"][0]["page_no"] == 1
    assert "confidence" not in str(result) and doc == before


def test_coordinate_less_uncertainty_remains_visible_and_scoped():
    doc = document()
    doc["pages"][0]["regions"][0].update(bbox=None, text_selection={"needs_review": True})
    before = copy.deepcopy(doc)
    result = extraction_status(doc, [{"file_id": "A", "file_name": "synthetic.png"}])
    assert result["status"] == "CHECK_REQUIRED"
    assert set(result["files"][0]["pages"][0]["issues"]) == {"UNCERTAIN_LOCAL_READING", "SOURCE_GEOMETRY_MISSING"}
    workspace = saved_workspace({"ads": [{"ad_id": "ADV"}]}, [], doc, "ADV")
    row = next(row for row in workspace["rows"] if row["item_id"] == "LOCAL_READING_REVIEW")
    assert row["verdict"] == "판단불가" and row["review_locations"] == []
    assert row["reading_quality_review"]["issues"] and doc == before


def test_failed_asset_does_not_hide_other_files_or_invent_their_success():
    files = [{"file_id": "A", "file_name": "a.png"}, {"file_id": "B", "file_name": "b.png"}]
    failure = {"failed_assets": [{"file_id": "B", "reason": "private runtime path"}]}
    result = extraction_status({}, files, failure)
    assert [row["status"] for row in result["files"]] == ["UNRECORDED", "FAILED"]
    assert "private runtime path" not in str(result)
    result = extraction_status(document(), files, failure)
    assert [row["status"] for row in result["files"]] == ["EXTRACTED", "FAILED"]


def test_partial_empty_and_unverified_recovery_are_not_missing_disclosures():
    doc = document()
    doc["quality"] = {"complete_document_read": False}
    doc["pages"][0].update(parse_status="partial", unread_regions=["R"])
    doc["pages"][0]["regions"][0]["final_text"] = ""
    doc["unverified_recovery_candidates"] = [{"page_no": 2, "text": "not adopted"}]
    result = extraction_status(doc, [{"file_id": "A", "file_name": "a.png"}])
    assert result["status"] == "CHECK_REQUIRED"
    assert result["files"][0]["issues"] == ["PARTIAL_EXTRACTION"]
    assert set(result["files"][0]["pages"][0]["issues"]) == {"PAGE_STATUS_REVIEW", "UNREAD_REGIONS", "EMPTY_PAGE", "EMPTY_LOCAL_REGION", "UNVERIFIED_RECOVERY_CANDIDATE"}
    assert "VIOLATION" not in str(result)


def test_old_failure_log_cannot_override_available_extraction():
    result = extraction_status(document(), [{"file_id": "A", "file_name": "a.png"}],
                               {"failed_assets": [{"file_id": "A"}]})
    assert result["status"] == "EXTRACTED"
