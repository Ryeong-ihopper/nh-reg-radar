"""Synthetic provenance boundaries, not advertisement-specific verdict fixtures."""
import sys
import copy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from operational_locations import (load_template_appropriate_judgments, resolve_locations,
                                   local_reading_review, resolve_review_locations,
                                   resolve_chunk_locations, saved_workspace, valid_box, with_rendered_line_locations,
                                   verified_separate_notice_lines)
from operational_locations import display_condition_checks


def test_display_checks_use_frozen_wording_and_do_not_invent_missing_verdicts():
    rule = {'condition_contract': {'obligation_checks': [
        {'obligation_id': 'O1', 'text': 'Synthetic disclosure'},
        {'obligation_id': 'O2', 'text': 'Synthetic eligibility'}]}}
    prediction = {'requirement_checks': [
        {'obligation_ref': 'O1', 'status': 'SATISFIED', 'reason': 'Synthetic cited text'}]}
    original = copy.deepcopy((rule, prediction))
    assert display_condition_checks(rule, prediction) == [
        {'text': 'Synthetic disclosure', 'status': 'SATISFIED', 'reason': 'Synthetic cited text'},
        {'text': 'Synthetic eligibility', 'status': 'UNRECORDED', 'reason': ''}]
    assert (rule, prediction) == original


def test_display_checks_preserve_legacy_recorded_wording_without_current_rule_lookup():
    assert display_condition_checks({}, {'requirement_checks': [
        {'requirement': 'Legacy wording', 'status': 'UNDETERMINED'}]}) == [
        {'text': 'Legacy wording', 'status': 'UNDETERMINED', 'reason': ''}]


def test_display_source_fields_remain_bound_to_the_saved_request():
    raw = {'ads': [{'ad_id': 'ADV', 'product_name': 'Synthetic package', 'candidates': [
        {'item_id': 'SYNTHETIC', 'judgment': {'verdict': 'UNDETERMINED', 'reason': 'Synthetic uncertainty',
            'evidence_ids': [], 'evidence_line_refs': [], 'requirement_checks': []}}]}]}
    requests = [{'ad_id': 'ADV', 'documents': [], 'rules': [{'item_id': 'SYNTHETIC', 'title': 'Criterion label',
        'canonical_execution_plan': {'source': {'source_fields': {'violated': 'Frozen source guidance'}}}}]}]
    original = copy.deepcopy((raw, requests))
    row = saved_workspace(raw, requests, source(), 'ADV')['rows'][0]
    assert row['item_title'] == 'Criterion label'
    assert row['source_product'] == 'Synthetic package'
    assert row['template_guidance'] == 'Frozen source guidance'
    assert row['title'] == 'Synthetic package · Criterion label'
    assert (raw, requests) == original


def rendered_fixture():
    doc = source()
    doc['pages'][0]['regions'][0]['lines'][0].update(text='alpha beta', bbox=None)
    layout = {'source': 'HWP 200-DPI render + parser visual projection', 'pages': [
        {'page_no': 3, 'source_page_no': 3, 'canvas_w': 100, 'canvas_h': 200,
         'regions': [{'lines': [{'text': 'alpha', 'bbox': [1, 2, 80, 20]},
                               {'text': 'beta', 'bbox': [1, 22, 80, 40]}]}]}]}
    return doc, layout


def test_rendered_wrapped_line_preserves_source_and_uses_actual_page():
    doc, layout = rendered_fixture()
    original = copy.deepcopy((doc, layout))
    linked = with_rendered_line_locations(doc, layout, 'FILE-b')
    locations = resolve_locations(linked, {'evidence_line_refs': ['FILE-b::L1']}, {})
    assert len(locations) == 2
    assert all(x['pageNo'] == x['source_page_no'] == 3 for x in locations)
    assert all(x['asset_id'] == 'FILE-b' for x in locations)
    assert locations[0]['bbox'] == [1, 2, 80, 20]
    assert (doc, layout) == original
    assert linked['pages'] == doc['pages']


def test_rendered_repeated_text_different_text_and_cross_asset_fail_closed():
    doc, layout = rendered_fixture()
    page = layout['pages'][0]
    page['regions'].append(copy.deepcopy(page['regions'][0]))
    assert not with_rendered_line_locations(doc, layout, 'FILE-b')['display_line_locations']
    page['regions'].pop()
    page['regions'][0]['lines'][1]['text'] = 'betA'
    assert not with_rendered_line_locations(doc, layout, 'FILE-b')['display_line_locations']
    page['regions'][0]['lines'][1]['text'] = 'beta'
    page['asset_id'] = 'FILE-other'
    assert not with_rendered_line_locations(doc, layout, 'FILE-b')['display_line_locations']
    assert with_rendered_line_locations(doc, layout, 'FILE-other') == doc


def test_rendered_semantic_duplicates_invalid_boxes_and_existing_geometry():
    doc, layout = rendered_fixture()
    line = doc['pages'][0]['regions'][0]['lines'][0]
    duplicate = {**line, 'line_ref': 'duplicate'}
    doc['pages'][0]['unassigned_lines'].append(duplicate)
    assert not with_rendered_line_locations(doc, layout, 'FILE-b')['display_line_locations']
    doc['pages'][0]['unassigned_lines'].pop()
    layout['pages'][0]['regions'][0]['lines'][1]['bbox'] = [0, 0, 101, 200]
    assert not with_rendered_line_locations(doc, layout, 'FILE-b')['display_line_locations']
    line['bbox'] = [1, 2, 80, 20]
    linked = with_rendered_line_locations(doc, layout, 'FILE-b')
    assert resolve_locations(linked, {'evidence_line_refs': ['FILE-b::L1']}, {})[0]['pageNo'] == 2


def test_same_line_notice_guidance_uses_exact_rendered_lines_without_visual_guessing():
    document = source()
    region = document['pages'][0]['regions'][0]
    region['lines'] = [
        {'line_ref': 'FILE-b::N1', 'text': '※ 금융소비자는 설명을 받을 권리가 있습니다.', 'bbox': None},
        {'line_ref': 'FILE-b::N2', 'text': '※ 계약 전 상품설명서를 읽어보시기 바랍니다.', 'bbox': None},
    ]
    region['line_refs'] = ['FILE-b::N1', 'FILE-b::N2']
    document['pages'][0]['unassigned_lines'] = []
    document['display_line_locations'] = {
        'FILE-b::N1': [{'pageNo': 2, 'bbox': [1, 10, 90, 20]}],
        'FILE-b::N2': [{'pageNo': 2, 'bbox': [1, 30, 90, 40]}],
    }
    entry = {'template_basis': {
        'manual_guidance': '한 줄에 2개 이상의 유의사항 문구 기재 불가능(은행연합회 지도사항)'
    }}
    assessment = verified_separate_notice_lines(document, entry)
    assert assessment['notice_line_count'] == 2

    raw = {'ads': [{'ad_id': 'ADV', 'candidates': [{'item_id': 'TPL-NOTICE', 'judgment': {
        'verdict': 'COMPLIANT', 'reason': '유의사항 문구가 있습니다.', 'evidence_ids': [],
        'evidence_line_refs': ['FILE-b::N1'], 'requirement_checks': []}}],
        'deferred_rules': [{'item_id': 'TPL-NOTICE', 'title': '유의사항',
            'facet': 'VISUAL_OR_STRUCTURE',
            'reason': '텍스트 의무는 별도 판정하며 배치·로고·중첩 원문 구조는 사람 확인 필요',
            **entry}]}]}
    requests = [{'ad_id': 'ADV', 'rules': [{'item_id': 'TPL-NOTICE',
        'source_sheet': 'HWPX_TEMPLATE', 'title': '유의사항', 'question': '유의사항'}],
        'documents': []}]
    row = saved_workspace(raw, requests, document, 'ADV')['rows'][0]
    assert row['verdict'] == '충족'
    assert row['judgment_scope'] == 'RULE'
    assert '각 유의사항이 서로 다른 줄' in row['reason']

    document['display_line_locations']['FILE-b::N2'][0]['bbox'] = [1, 12, 90, 22]
    assert verified_separate_notice_lines(document, entry) is None
    assert saved_workspace(raw, requests, document, 'ADV')['rows'][0]['verdict'] == '판단불가'


def source():
    return {"diagnostics": {"asset_pages": {"FILE-b": {"start": 2, "end": 2}}},
            "pages": [{"page_no": 2, "canvas_w": 100, "canvas_h": 200,
                       "regions": [{"region_id": "R", "bbox": [0, 0, 100, 100],
                                    "lines": [{"line_ref": "FILE-b::L1", "text": "repeated text", "bbox": [1, 2, 80, 20]}]}],
                       "unassigned_lines": [{"line_ref": "FILE-b::U1", "text": "unassigned", "bbox": [1, 30, 80, 40]}]}]}


def test_saved_absence_disguised_as_observed_is_projected_without_mutating_original():
    prediction = {'item_id': 'SYNTHETIC', 'verdict': 'VIOLATION', 'reason': '필수 안내의 누락으로 판단됩니다.',
        'evidence_ids': ['E'], 'evidence_line_refs': ['FILE-b::L1'], 'requirement_checks': [{
            'status': 'VIOLATED', 'finding_basis': 'OBSERVED', 'reason': '안내 문구가 확인되지 않습니다.',
            'evidence_ids': ['E'], 'evidence_line_refs': ['FILE-b::L1']}]}
    raw = {'ads': [{'ad_id': 'ADV', 'candidates': [{'item_id': 'SYNTHETIC', 'judgment': prediction}]}]}
    request = {'ad_id': 'ADV', 'parser_coverage': 'PARTIAL', 'rules': [{'item_id': 'SYNTHETIC'}],
        'documents': [{'evidence_id': 'E', 'line_refs': ['FILE-b::L1'], 'text': 'repeated text'}],
        'evidence_scope': {'SYNTHETIC': {'evidence_ids': ['E'], 'complete_ad_scan': False}}}
    frozen = copy.deepcopy((raw, request))
    row = saved_workspace(raw, [request], source(), 'ADV')['rows'][0]
    assert row['verdict'] == '판단불가'
    assert row['evidence_locations'] == []
    assert row['model_assessment']['verdict'] == 'VIOLATION'
    assert (raw, request) == frozen
    request['parser_coverage'] = 'FULL'
    request['evidence_scope']['SYNTHETIC']['complete_ad_scan'] = True
    # A complete scan does not make unrelated OBSERVED evidence a valid
    # absence finding. The source contract still requires MISSING + ABSENCE.
    complete = copy.deepcopy((raw, request))
    row = saved_workspace(raw, [request], source(), 'ADV')['rows'][0]
    assert row['verdict'] == '판단불가'
    assert row['evidence_locations'] == []
    assert row['model_assessment']['verdict'] == 'VIOLATION'
    assert (raw, request) == complete


def test_template_appropriate_judgment_guide_is_exact_and_display_only(tmp_path):
    import openpyxl
    path = tmp_path / "1. 대출성상품-상품명 노출.xlsx"
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["안내"])
    sheet.append(["구분", "예시문구", "적정 판단"])
    sheet.append(["상품명", "예시", "상품명 언급 시 적정"])
    book.save(path)
    values = load_template_appropriate_judgments(path)
    assert values == {("대출성상품-상품명 노출", "상품명"): "상품명 언급 시 적정"}

    raw = {"ads": [{"ad_id": "ADV", "candidates": [{"item_id": "TPL-1", "judgment": {
        "verdict": "COMPLIANT", "reason": "확인", "evidence_ids": [], "evidence_line_refs": []}}]}]}
    requests = [{"ad_id": "ADV", "rules": [{"item_id": "TPL-1", "source_sheet": "HWPX_TEMPLATE"}],
                 "documents": []}]
    metadata = {"TPL-1": {"appropriate_judgment": values[("대출성상품-상품명 노출", "상품명")]}}
    row = saved_workspace(raw, requests, source(), "ADV", rule_metadata=metadata)["rows"][0]
    assert row["template_appropriate_judgment"] == "상품명 언급 시 적정"


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
    assert len(row['review_locations']) == 1
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


def test_chunk_projection_unions_cited_window_without_replacing_exact_line():
    document = source()
    document["pages"][0]["regions"][0]["lines"].append(
        {"line_ref": "FILE-b::L2", "text": "context", "bbox": [2, 22, 90, 44]}
    )
    evidence = {"E": {"evidence_id": "E", "span_status": "parser_line_exact",
                       "line_refs": ["FILE-b::L1", "FILE-b::L2"]}}
    judgment = {"evidence_ids": ["E"], "evidence_line_refs": ["FILE-b::L1"]}

    assert resolve_locations(document, judgment, evidence)[0]["bbox"] == [1, 2, 80, 20]
    assert resolve_chunk_locations(document, judgment, evidence) == [{
        "key": "chunk:E:2:0", "pageNo": 2, "bbox": [1, 2, 90, 44],
        "width": 100, "height": 200, "asset_id": "FILE-b", "source_page_no": 1,
        "precision": "CHUNK", "evidence_id": "E",
    }]


def test_conditional_template_title_exposes_the_actual_condition():
    raw = {"ads": [{"ad_id": "ADV", "product_name": "예금성05", "candidates": [{
        "item_id": "TPL-CONDITIONAL",
        "template_basis": {
            "requirement_mode": "CONDITIONAL",
            "fields": {"guidance": {"text": "생성형 AI 활용 시 필수\n추가 설명"}},
        },
        "judgment": {"verdict": "UNDETERMINED", "reason": "외부 조건 확인 필요",
                     "evidence_ids": [], "evidence_line_refs": []},
    }]}]}
    requests = [{"ad_id": "ADV", "rules": [{
        "item_id": "TPL-CONDITIONAL", "source_sheet": "HWPX_TEMPLATE",
        "title": "유의사항", "question": "유의사항",
    }], "documents": []}]

    row = saved_workspace(raw, requests, source(), "ADV")["rows"][0]

    assert row["title"] == "예금성05 · 유의사항 (생성형 AI 활용 시 필수)"


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
    document['pages'][0].update(canvas_w=None, canvas_h=None)
    row = saved_workspace(raw, requests, document, "ADV")["rows"][0]
    assert row["evidence_location_status"] == "SOURCE_GEOMETRY_MISSING"
    assert row["evidence_locations"] == [] and row["evidence"] == "specific source"
    row = saved_workspace(raw, requests, source(), "ADV")["rows"][0]
    assert row["evidence_location_status"] == "UNRESOLVED_REFERENCE"


def test_heading_only_saved_compliance_is_withheld_without_rewriting_prediction():
    judgment = {'verdict':'COMPLIANT','reason':'본문 기재 확인','requirement_checks':[
        {'status':'SATISFIED','finding_basis':'OBSERVED','evidence_line_refs':['L'],'reason':'본문 기재 확인'}]}
    raw = {'ads':[{'ad_id':'ADV','candidates':[{'item_id':'TPL-synthetic','judgment':judgment}]}]}
    requests = [{'ad_id':'ADV','rules':[{'item_id':'TPL-synthetic','source_sheet':'HWPX_TEMPLATE',
        'title':'해약 안내','example_text':'해약 후에는 혜택이 더 이상 제공되지 않습니다.'}],
        'documents':[{'line_refs':['L'],'evidence_id':'E','line_texts':{'L':'상품 해약 안내'}}]}]
    before = copy.deepcopy(raw)
    row = saved_workspace(raw, requests, source(), 'ADV')['rows'][0]
    assert row['verdict'] == '판단불가'
    assert row['model_assessment']['verdict'] == 'COMPLIANT'
    assert raw == before


def test_region_selected_text_never_becomes_exact_line_fallback():
    doc = {"region_id": "R", "page_no": 2, "span_status": "region_level_selected_text", "line_refs": ["FILE-b::L1"]}
    value = resolve_locations(source(), {"evidence_ids": ["E"]}, {"E": doc})
    assert len(value) == 1 and value[0]["precision"] == "REGION"
    doc["span_status"] = "selected_text_line_aligned"
    assert resolve_locations(source(), {"evidence_ids": ["E"]}, {"E": doc})[0]["precision"] == "LINE"
    doc.pop("span_status")
    assert resolve_locations(source(), {"evidence_ids": ["E"]}, {"E": doc}) == []


def test_multi_line_chunk_without_explicit_ref_is_not_drawn_as_a_wide_range():
    document = source()
    document['pages'][0]['regions'][0]['lines'].append(
        {'line_ref': 'FILE-b::L2', 'text': 'second', 'bbox': [1, 22, 80, 28]})
    doc = {'span_status': 'parser_line_exact', 'line_refs': ['FILE-b::L1', 'FILE-b::L2']}
    assert resolve_locations(document, {'evidence_ids': ['E']}, {'E': doc}) == []
    exact = resolve_locations(document, {'evidence_line_refs': ['FILE-b::L2']}, {})
    assert [value['bbox'] for value in exact] == [[1, 22, 80, 28]]


def test_uncertain_refs_are_exposed_as_review_locations_not_judgment_evidence():
    judgment = {'verdict': 'UNDETERMINED', 'evidence_ids': [], 'evidence_line_refs': [],
                'reading_quality_review': {'issues': [{
                    'code': 'INCOMPLETE_READING_ABSENCE', 'location': 'requirement_checks:0',
                    'evidence_ids': ['E'], 'line_refs': ['FILE-b::L1']} ]}}
    evidence = {'E': {'span_status': 'parser_line_exact', 'line_refs': ['FILE-b::L1']}}
    assert resolve_locations(source(), judgment, evidence) == []
    review = resolve_review_locations(source(), judgment, evidence)
    assert len(review) == 1 and review[0]['bbox'] == [1, 2, 80, 20]


def test_local_uncertain_and_empty_regions_are_one_scoped_review_row():
    document = source()
    region = document['pages'][0]['regions'][0]
    region.update(final_text='', text_selection={'needs_review': True})
    line = document['pages'][0]['unassigned_lines'][0]
    line['text_selection'] = {'selection_status': 'unassigned_parser_text'}
    locations, issues = local_reading_review(document)
    assert len(locations) == 2
    assert {value['precision'] for value in locations} == {'LINE', 'REGION'}
    assert {value['code'] for value in issues} == {'UNCERTAIN_LOCAL_READING', 'EMPTY_LOCAL_REGION'}

    workspace = saved_workspace({'ads': [{'ad_id': 'ADV'}]}, [], document, 'ADV')
    rows = [row for row in workspace['rows'] if row['item_id'] == 'LOCAL_READING_REVIEW']
    assert len(rows) == 1 and rows[0]['verdict'] == '판단불가'
    assert rows[0]['evidence_locations'] == []
    assert len(rows[0]['review_locations']) == 2


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


def test_visual_deferred_rule_projects_retrieval_trigger_as_review_location():
    deferred = [{
        'item_id': 'VISUAL',
        'title': '배경 대비',
        'reason': '시인성은 사람 검토 대상입니다.',
        'trigger_evidence': [{
            'trigger': {
                'doc_id': 'chunk-1',
                'line_refs': ['FILE-b::L1'],
                'text': '원금손실 위험 고지',
            },
        }],
    }]
    raw = {'ads': [{'ad_id': 'ADV', 'deferred_rules': deferred}]}
    row = saved_workspace(raw, [], source(), 'ADV')['rows'][0]
    assert row['item_id'] == 'VISUAL'
    assert row['evidence_locations'] == []
    assert row['evidence_location_status'] == 'NO_CITATION'
    assert row['evidence'] == '원금손실 위험 고지'
    assert row['evidence_line_refs'] == ['FILE-b::L1']
    assert len(row['review_locations']) == 1
    assert row['review_locations'][0]['bbox'] == [1, 2, 80, 20]


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


def test_discovery_audit_only_rows_do_not_become_workspace_judgments():
    raw = {"ads": [{"ad_id": "ADV", "scope_id": "S", "candidates": []}]}
    discovery = {"ads": [{"ad_id": "S", "candidate_budget": {
        "method": "discovery_audit_only_v1",
        "deferred_reason": "outside_formal_execution_scope",
        "deferred_ids": ["HOLD", "UNCLASSIFIED"],
    }}]}
    value = saved_workspace(raw, [], source(), "ADV", discovery)
    assert value["rows"] == []
    assert value["execution_omissions"] == []


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


def test_canonical_appropriate_criterion_uses_frozen_request_without_legacy_catalog():
    raw = {"ads": [{"ad_id": "ADV", "candidates": [{"item_id": "CANON", "judgment": {
        "verdict": "UNDETERMINED", "reason": "확인 필요", "evidence_ids": [], "evidence_line_refs": []}}]}]}
    rule = {"item_id": "CANON", "source_sheet": "HWPX_TEMPLATE", "canonical_execution_plan": {
        "source_criteria": {"satisfied": "해당 사항 표시 시 적정", "review": "외부 확인 필요"}}}
    requests = [{"ad_id": "ADV", "rules": [rule], "documents": []}]
    row = saved_workspace(raw, requests, source(), "ADV")["rows"][0]
    assert row["template_appropriate_judgment"] == "해당 사항 표시 시 적정"
    assert row["verdict"] == "판단불가"
    assert raw["ads"][0]["candidates"][0]["judgment"]["verdict"] == "UNDETERMINED"
