"""Synthetic provenance boundaries, not advertisement-specific verdict fixtures."""
import sys
import copy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from operational_locations import resolve_locations, saved_workspace, valid_box


def source():
    return {"diagnostics": {"asset_pages": {"FILE-b": {"start": 2, "end": 2}}},
            "pages": [{"page_no": 2, "canvas_w": 100, "canvas_h": 200,
                       "regions": [{"region_id": "R", "bbox": [0, 0, 100, 100],
                                    "lines": [{"line_ref": "FILE-b::L1", "text": "repeated text", "bbox": [1, 2, 80, 20]}]}],
                       "unassigned_lines": [{"line_ref": "FILE-b::U1", "text": "unassigned", "bbox": [1, 30, 80, 40]}]}]}


def test_manual_rule_names_require_matching_frozen_source_hash(tmp_path):
    import hashlib
    import openpyxl
    from operational_locations import frozen_rule_metadata
    path = tmp_path / 'source.xlsx'
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = '실행_점검항목'
    sheet.append(['항목ID', '약칭', '점검문구', '근거법령'])
    sheet.append(['SYN', '합성 항목', '사람 확인 질문', '합성 기준 제2조'])
    book.save(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    frozen = {'inputs': [{'path': 'old-location/source.xlsx', 'sha256': digest}]}
    metadata = frozen_rule_metadata(path, frozen)
    assert metadata['SYN']['title'] == '합성 항목'
    assert metadata['SYN']['rule_basis']['source_sha256'] == digest
    assert frozen_rule_metadata(path, {'inputs': [{'path': 'other.xlsx', 'sha256': 'wrong'}]}) == {}
    raw = {'ads': [{'ad_id': 'ADV', 'deferred_rules': [{'item_id': 'SYN', 'reason': '사람 확인'}]}]}
    row = saved_workspace(raw, [], source(), 'ADV', rule_metadata=metadata)['rows'][0]
    assert row['title'] == '합성 항목' and row['question'] == '사람 확인 질문'
    assert row['verdict'] == '판단불가'


def test_unresolved_exclusion_is_visible_without_rewriting_saved_prediction():
    judgment = {'verdict': 'NOT_APPLICABLE', 'reason': '자료가 없어 의무 적용 여부를 판단할 수 없습니다.',
                'evidence_ids': ['E'], 'evidence_line_refs': ['FILE-b::L1']}
    raw = {'ads': [{'ad_id': 'ADV', 'excluded_candidates': [{'item_id': 'SYN', 'judgment': judgment}]}]}
    before = copy.deepcopy(raw)
    workspace = saved_workspace(raw, [], source(), 'ADV')
    row = workspace['rows'][0]
    assert row['verdict'] == '판단불가'
    assert row['model_assessment']['verdict'] == 'NOT_APPLICABLE'
    assert row['evidence_locations'] == [] and row['evidence_ids'] == []
    assert raw == before and workspace['source_ads'] == raw['ads']
    judgment['reason'] = '대상 상품군이 달라 적용 대상이 아닙니다.'
    assert saved_workspace(raw, [], source(), 'ADV')['rows'] == []


def test_saved_wrong_phrase_citation_is_withheld_without_changing_raw_or_guessing_location():
    for refs in ([], ['FILE-b::L1']):
        judgment = {'verdict': 'COMPLIANT', 'reason': '상품명이 확인됩니다.',
                    'evidence_ids': ['E'], 'evidence_line_refs': refs,
                    'requirement_checks': [{'status': 'SATISFIED', 'finding_basis': 'OBSERVED',
                        'evidence_ids': ['E'], 'evidence_line_refs': refs,
                        'reason': "광고 내에 '가상통장'이라는 상품명이 명시되어 있습니다."}]}
        raw = {'ads': [{'ad_id': 'ADV', 'candidates': [{'item_id': 'SYN', 'judgment': judgment}]}]}
        requests = [{'ad_id': 'ADV', 'rules': [{'item_id': 'SYN'}], 'documents': [
            {'evidence_id': 'E', 'text': '세부 조건 참고', 'line_refs': ['FILE-b::L1'],
             'line_texts': {'FILE-b::L1': '세부 조건 참고'}, 'span_status': 'parser_line_exact'}]}]
        before = copy.deepcopy(raw)
        row = saved_workspace(raw, requests, source(), 'ADV')['rows'][0]
        assert row['verdict'] == '판단불가'
        assert row['model_assessment']['status'] == 'WITHHELD_BY_GROUNDING_GUARD'
        assert row['evidence_locations'] == [] and row['evidence_line_refs'] == []
        assert raw == before
        doc = requests[0]['documents'][0]
        doc.update(text='가상통장', line_texts={'FILE-b::L1': '가상통장'})
        row = saved_workspace(raw, requests, source(), 'ADV')['rows'][0]
        assert row['verdict'] == '충족' and len(row['evidence_locations']) == 1


def test_unassigned_and_asset_local_page_are_preserved():
    value = resolve_locations(source(), {"evidence_line_refs": ["FILE-b::U1"]}, {})
    assert len(value) == 1
    assert (value[0]["pageNo"], value[0]["asset_id"], value[0]["source_page_no"]) == (2, "FILE-b", 1)
    assert value[0]["precision"] == "LINE"


def test_revoked_gate_does_not_expand_old_chunk_or_explicit_line_citations():
    for refs in ([], ["FILE-b::L1"]):
        judgment = {"verdict": "UNDETERMINED", "evidence_ids": ["E"], "evidence_line_refs": refs,
                    "reading_quality_review": {"policy": "reading-quality-gate-v1", "issues": [
                        {"location": "applicability", "code": "UNCERTAIN_READING_EVIDENCE"}]}}
        evidence = {"E": {"span_status": "parser_line_exact", "line_refs": ["FILE-b::L1"]}}
        before = copy.deepcopy(judgment)
        assert resolve_locations(source(), judgment, evidence) == []
        assert judgment == before
        judgment.pop("reading_quality_review")
        assert len(resolve_locations(source(), judgment, evidence)) == 1


def test_guarded_workspace_uses_active_evidence_but_preserves_raw_audit():
    prediction = {"verdict": "UNDETERMINED", "evidence_ids": ["E"], "evidence_line_refs": [],
                  "reading_quality_review": {"policy": "reading-quality-gate-v1", "issues": [
                      {"location": "applicability", "code": "UNCERTAIN_READING_EVIDENCE"}]}}
    raw = {"ads": [{"ad_id": "ADV", "candidates": [{"item_id": "R1", "judgment": prediction}]}]}
    requests = [{"ad_id": "ADV", "rules": [{"item_id": "R1"}], "documents": [
        {"evidence_id": "E", "text": "candidate text", "span_status": "parser_line_exact", "line_refs": ["FILE-b::L1"]}]}]
    before = copy.deepcopy(raw)
    workspace = saved_workspace(raw, requests, source(), "ADV")
    row = workspace['rows'][0]
    assert row['verdict'] == '판단불가'
    assert row['evidence'] == '' and row['evidence_locations'] == [] and row['evidence_ids'] == []
    assert row['reading_quality_review'] == prediction['reading_quality_review']
    assert raw == before and workspace['source_ads'] == raw['ads']


def test_coordinate_free_source_is_not_presented_as_whole_ad_judgment():
    raw = {"ads": [{"ad_id": "ADV", "candidates": [{"item_id": "R1", "judgment": {
        "verdict": "COMPLIANT", "evidence_ids": ["E"], "evidence_line_refs": []}}]}]}
    requests = [{"ad_id": "ADV", "rules": [{"item_id": "R1"}], "documents": [
        {"evidence_id": "E", "text": "specific source", "span_status": "parser_line_exact", "line_refs": ["L1"]}]}]
    document = {"pages": [{"page_no": 1, "canvas_w": 0, "canvas_h": 0,
                           "regions": [{"lines": [{"line_ref": "L1", "text": "specific source", "bbox": None}]}]}]}
    row = saved_workspace(raw, requests, document, "ADV")["rows"][0]
    assert row["evidence_location_status"] == "SOURCE_GEOMETRY_MISSING"
    assert row["evidence_locations"] == [] and row["evidence"] == "specific source"
    row = saved_workspace(raw, requests, source(), "ADV")["rows"][0]
    assert row["evidence_location_status"] == "UNRESOLVED_REFERENCE"


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


def test_manual_facets_merge_without_hiding_violations_or_counting_twice():
    candidates = [{'item_id': item, 'judgment': {'verdict': verdict, 'reason': 'text finding'}}
                  for item, verdict in [('PASS', 'COMPLIANT'), ('FAIL', 'VIOLATION')]]
    deferred = [{'item_id': item, 'reason': '사람 시각 확인 필요'} for item in ['PASS', 'FAIL', 'NEW', 'NEW']]
    deferred += [{'item_id': 'OTHER', 'reason': "routing did not select this rule's template section"},
                 {'item_id': 'OTHER-V2', 'reason': 'confirmed template does not match this v2 product subtype'}]
    raw = {'ads': [{'ad_id': 'ADV', 'candidates': candidates, 'deferred_rules': deferred,
                   'excluded_candidates': [{'item_id': 'EX', 'judgment': {'verdict': 'NOT_APPLICABLE', 'reason': '대상 상품 아님'}}],
                   'review_candidates': [{'item_id': 'PENDING', 'judgment': {'verdict': 'UNDETERMINED', 'reason': '적용성 확인 필요'}}]}]}
    before = copy.deepcopy(raw)
    value = saved_workspace(raw, [], source(), 'ADV')
    rows = {r['item_id']: r for r in value['rows']}
    assert set(rows) == {'PASS', 'FAIL', 'NEW', 'PENDING'}
    assert rows['PASS']['verdict'] == rows['NEW']['verdict'] == rows['PENDING']['verdict'] == '판단불가'
    assert rows['PASS']['automated_assessment']['verdict'] == '충족'
    assert rows['FAIL']['verdict'] == '위반'
    assert rows['NEW']['evidence_locations'] == []
    assert len(rows['NEW']['manual_review_reasons']) == 1
    assert [r['item_id'] for r in value['excluded_rows']] == ['EX']
    assert value['deferred_rules'] == value['review_candidate_rows'] == []
    assert raw == before


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
    assert value['rows'] == []
    assert [r["title"] for r in value["excluded_rows"]] == ["a", "b"]
    assert all(r["verdict"] == "미해당" for r in value["excluded_rows"])
    assert len(value["output_failure_pairs"]) == 1
    assert value["output_failure_pairs"][0]["reason"] == "invalid JSON"


def test_legacy_budget_omission_is_unknown_and_explicitly_incomplete():
    raw = {"ads": [{"ad_id": "ADV", "scope_id": "S", "candidates": [],
                    "deferred_rules": [{"item_id": "R1", "reason": "routing did not select this rule's template section"}]}]}
    discovery = {"ads": [{"ad_id": "S", "candidate_budget": {"deferred_ids": ["R2"]}},
                         {"ad_id": "OTHER", "candidate_budget": {"deferred_ids": ["R3"]}}]}
    value = saved_workspace(raw, [], source(), "ADV", discovery)
    assert value['deferred_rules'] == []
    assert len(value['execution_omissions']) == 1
    assert all(row['verdict'] == '판단불가' for row in value['rows'])
    assert [row['item_id'] for row in value['rows']] == ['R2']


def test_recovered_legacy_result_uses_its_frozen_scope_coverage_without_mutation():
    import copy
    raw = {'ads': [{'ad_id': 'ADV', 'scope_id': 'scope-a', 'candidates': []}]}
    frozen = copy.deepcopy(raw)
    coverage = {'missing_count': 0, 'requested_count': 5}
    discovery = {'ads': [{'ad_id': 'scope-a', 'template_coverage': coverage},
                         {'ad_id': 'other-scope', 'template_coverage': {'missing_count': 10}}]}
    value = saved_workspace(raw, [], source(), 'ADV', discovery)
    assert value['template_coverage'] == [coverage]
    assert raw == frozen
    assert saved_workspace(raw, [], source(), 'ADV', {'ads': discovery['ads'][1:]})['template_coverage'] == []


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
