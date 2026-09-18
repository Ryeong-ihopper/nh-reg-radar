"""Saved evidence -> display geometry. Never infer source links from text similarity."""
from __future__ import annotations

import math
import hashlib
import sys
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "rag-pipeline"))
from rag.judgment.reading_quality import project_reading_citations  # noqa: E402
from rag.judgment.source_checks import unresolved_applicability  # noqa: E402
from rag.judgment.arithmetic import calculate_loan_rates, METHOD as ARITHMETIC_METHOD  # noqa: E402
from rag.judgment.grounding import cited_window_text, ungrounded_source_quotes  # noqa: E402


def page_lines(page):
    for region in page.get("regions", []):
        yield from region.get("lines", [])
    yield from page.get("unassigned_lines", [])


def valid_box(box, width, height):
    values = [width, height, *(box if isinstance(box, (list, tuple)) else [])]
    return (
        len(values) == 6
        and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                and math.isfinite(v) for v in values)
        and width > 0 and height > 0
        and 0 <= box[0] < box[2] <= width
        and 0 <= box[1] < box[3] <= height
    )


def page_asset(document, page):
    """Global combined page and original asset-local page are different IDs."""
    number = page["page_no"]
    assets = (document.get("diagnostics") or {}).get("asset_pages") or {}
    matches = [(key, span) for key, span in assets.items()
               if span["start"] <= number <= span["end"]]
    if len(matches) == 1:
        key, span = matches[0]
        return key, number - span["start"] + 1
    return None, number


def resolve_locations(document, judgment, evidence):
    """Exact parser refs or explicitly approximate source regions, never guessed lines."""
    judgment = project_reading_citations(judgment)
    pages = document.get("pages", [])
    index = {line["line_ref"]: (page, line) for page in pages
             for line in page_lines(page) if line.get("line_ref")}
    cited = [evidence[eid] for eid in judgment.get("evidence_ids", []) if eid in evidence]
    refs = list(dict.fromkeys(judgment.get("evidence_line_refs") or []))
    if not refs:
        refs = list(dict.fromkeys(ref for doc in cited
                    if doc.get("span_status") in {"parser_line_exact", "selected_text_line_aligned"}
                    for ref in doc.get("line_refs", [])))
    locations = []

    def append(page, box, key, precision):
        width, height = page.get("canvas_w"), page.get("canvas_h")
        if not valid_box(box, width, height):
            return
        asset, source_page = page_asset(document, page)
        locations.append({"key": key, "pageNo": page["page_no"], "bbox": box,
                          "width": width, "height": height, "asset_id": asset,
                          "source_page_no": source_page, "precision": precision})

    for ref in refs:
        if ref in index:
            page, line = index[ref]
            append(page, line.get("bbox"), ref, "LINE")
    # A selected VLM passage with no proven line alignment can identify its
    # source region, but must not be presented as an exact parser-line quote.
    seen_regions = set()
    for doc in cited:
        if doc.get("span_status") != "region_level_selected_text":
            continue
        key = (doc.get("page_no"), doc.get("region_id"))
        if key in seen_regions:
            continue
        seen_regions.add(key)
        for page in pages:
            if page["page_no"] != key[0]:
                continue
            for region in page.get("regions", []):
                if region.get("region_id") == key[1]:
                    append(page, region.get("bbox"), f"region:{key[0]}:{key[1]}", "REGION")
    return locations


def saved_workspace(raw, requests, document, advertisement_id, discovery=None, reading_audits=None, rule_metadata=None):
    """Single projection shared by the active UI and JSON download."""
    ads = [ad for ad in raw.get("ads", []) if ad["ad_id"] == advertisement_id]
    scoped = {}
    arithmetic = {}
    for request in requests:
        if request.get("ad_id") != advertisement_id and not request.get("ad_id", "").startswith(advertisement_id + "::"):
            continue
        key = request["ad_id"]
        definitions, evidence = scoped.setdefault(key, ({}, {}))
        definitions.update({rule["item_id"]: rule for rule in request["rules"]})
        evidence.update({doc["evidence_id"]: doc for doc in request["documents"]})
        for rule in request['rules']:
            verified = calculate_loan_rates(request, rule)
            if verified:
                arithmetic[(key, rule['item_id'])] = verified
    texts = {line["line_ref"]: line.get("text") or line.get("parser_text") or ""
             for page in document.get("pages", []) for line in page_lines(page)
             if line.get("line_ref")}
    rows, review_rows = [], []
    for ad in ads:
        key = ad.get("scope_id") or ad["ad_id"]
        rules, evidence = scoped.get(key, ({}, {}))
        for candidates, target, kind in ((ad.get("candidates", []), rows, "finding"),
                                         (ad.get("review_candidates", []), review_rows, "review"),
                                         (ad.get("excluded_candidates", []), rows, "scope-review")):
            for number, candidate in enumerate(candidates):
                prediction = project_reading_citations(candidate.get("judgment") or {})
                arithmetic_result = arithmetic.get((key, candidate['item_id']))
                if arithmetic_result and not prediction.get('reading_quality_review'):
                    prediction = arithmetic_result
                applicability_audit = None
                if prediction.get('verdict') in {'COMPLIANT', 'VIOLATION'}:
                    inconsistent = False
                    for check in prediction.get('requirement_checks') or []:
                        if check.get('finding_basis') != 'OBSERVED' or check.get('status') not in {'SATISFIED', 'VIOLATED'}:
                            continue
                        refs = check.get('evidence_line_refs') or []
                        docs = [evidence[eid] for eid in check.get('evidence_ids', []) if eid in evidence]
                        # Legacy E-only citations can be checked against their
                        # saved source text, but never remapped to a guessed L.
                        window = cited_window_text(refs, evidence.values()) if refs else '\n'.join(
                            doc.get('text', '') for doc in docs)
                        if (refs or docs) and ungrounded_source_quotes(check.get('reason', ''), window):
                            inconsistent = True
                    if inconsistent:
                        applicability_audit = {'verdict': prediction['verdict'], 'reason': prediction.get('reason', ''),
                                               'status': 'WITHHELD_BY_GROUNDING_GUARD'}
                        prediction = {**prediction, 'verdict': 'UNDETERMINED',
                                      'evidence_ids': [], 'evidence_line_refs': [], 'requirement_checks': [],
                                      'reason': '판정 설명의 인용 문구와 선택된 원문 줄이 일치하지 않아 자동 확정을 보류했습니다. 실제 원문 근거를 다시 확인해야 합니다.'}
                if unresolved_applicability(prediction):
                    applicability_audit = {'verdict': prediction['verdict'], 'reason': prediction.get('reason', ''),
                                           'status': 'WITHHELD_BY_APPLICABILITY_GUARD'}
                    prediction = {**prediction, 'verdict': 'UNDETERMINED',
                                  'evidence_ids': [], 'evidence_line_refs': [], 'requirement_checks': [],
                                  'reason': '적용 여부를 확인하지 못한 항목이므로 미해당으로 제외하지 않고 사람 검토로 보냅니다. ' + prediction.get('reason', '')}
                if not prediction.get("verdict"):
                    continue  # Processing failures are reported separately, not model abstentions.
                item_id = candidate["item_id"]
                rule = rules.get(item_id, {})
                cited = [evidence[eid] for eid in prediction.get("evidence_ids", []) if eid in evidence]
                text = "\n".join(texts[ref] for ref in prediction.get("evidence_line_refs", []) if ref in texts)
                if not text:
                    text = "\n\n".join(doc.get("text", "") for doc in cited)
                title = rule.get("title") or item_id
                if ad.get("product_name"):
                    title = f"{ad['product_name']} · {title}"
                locations = resolve_locations(document, prediction, evidence)
                location_status = "MAPPED" if locations else "NO_CITATION"
                if not locations and text:
                    location_status = "UNRESOLVED_REFERENCE"
                    if not any(page.get("canvas_w", 0) > 0 and page.get("canvas_h", 0) > 0
                               for page in document.get("pages", [])):
                        location_status = "SOURCE_GEOMETRY_MISSING"
                target.append({
                    "row_id": f"{key}:{kind}:{item_id}:{number}", "scope_id": key, "item_id": item_id,
                    "title": title, "question": rule.get("question", ""),
                    "criterion": rule.get("criterion") or rule.get("guide", ""),
                    "template_example": rule.get("example_text", "") if rule.get("source_sheet") == "HWPX_TEMPLATE" else "",
                    "template_section": (candidate.get("template_basis") or {}).get("template_section"),
                    "template_requirement": (candidate.get("template_basis") or {}).get("requirement_mode"),
                    "requirement_checks": prediction.get("requirement_checks", []),
                    "verdict": {"VIOLATION": "위반", "COMPLIANT": "충족",
                                "UNDETERMINED": "판단불가", "NOT_APPLICABLE": "미해당"}.get(prediction["verdict"], prediction["verdict"]),
                    "reason": prediction.get("reason", ""), "evidence": text,
                    "evidence_ids": prediction.get("evidence_ids", []),
                    "evidence_line_refs": prediction.get("evidence_line_refs", []),
                    "evidence_locations": locations,
                    "evidence_location_status": location_status,
                    "reading_quality_review": prediction.get("reading_quality_review"),
                    "rule_basis": candidate.get("rule_basis"),
                    "decision_trace": ({'decision_source': ARITHMETIC_METHOD,
                        'model_result_source': candidate.get('source'),
                        'evidence_ids': prediction['evidence_ids'],
                        'evidence_line_refs': prediction['evidence_line_refs']}
                        if arithmetic_result and prediction is arithmetic_result else candidate.get("decision_trace")),
                    "judgment_scope": "TEXT_ONLY" if (candidate.get("template_basis") or {}).get("text_facet_only") else "RULE",
                    "model_assessment": applicability_audit or ((reading_audits or {}).get((key, item_id))
                    if prediction.get("reading_quality_review") else None),
                })
    deferred = [dict(row, scope_id=ad.get("scope_id") or ad['ad_id']) for ad in ads
                for row in ad.get("deferred_rules", [])]
    scopes = {ad.get("scope_id") or ad["ad_id"] for ad in ads}
    for scope in (discovery or {}).get("ads", []):
        if scope.get("ad_id") in scopes:
            for source in scope.get('template_scope_deferred', []):
                if not any(row.get('scope_id') == scope['ad_id'] and row.get('item_id') == source.get('item_id')
                           and row.get('reason') == source.get('reason') for row in deferred):
                    deferred.append(dict(source, scope_id=scope['ad_id']))
            deferred.extend({"scope_id": scope["ad_id"], "item_id": item,
                             "reason": "execution_budget_not_inapplicability"}
                            for item in scope.get("candidate_budget", {}).get("deferred_ids", []))
    for row in deferred:
        row["deferred_kind"] = (
            "EXECUTION_BUDGET" if row.get("reason") == "execution_budget_not_inapplicability"
            else "OTHER_TEMPLATE" if row.get("reason") in {"routing did not select this rule's template section",
                                                           "confirmed template does not match this v2 product subtype"}
            else "INPUT_OR_STRUCTURE"
        )
    discoveries = {ad['ad_id']: ad for ad in (discovery or {}).get('ads', [])}
    for entry in deferred:
        metadata = (rule_metadata or {}).get(entry['item_id'], {})
        for field in ('title', 'question', 'rule_basis'):
            if metadata.get(field):
                entry.setdefault(field, metadata[field])
        source = discoveries.get(entry['scope_id'], {})
        for field in ('template_candidates', 'presence_and_style', 'supplemental_v2_candidates', 'prohibition_candidates'):
            match = next((item for item in source.get(field, []) if item.get('item_id') == entry['item_id']), {})
            if match.get('title'):
                entry.setdefault('title', match['title'])
                break
    coverage = [ad.get('template_coverage') or discoveries.get(ad.get('scope_id') or ad['ad_id'], {}).get('template_coverage')
                for ad in ads]
    rows, excluded, omissions = consolidate_review_rows(rows, review_rows, deferred, scoped, coverage)
    return {"rows": rows, "review_candidate_rows": [], "excluded_rows": excluded,
            "execution_omissions": omissions,
            "template_coverage": [value for value in coverage if value],
            "source_ads": ads,
            "output_failure_pairs": [pair for pair in raw.get("output_failure_pairs", [])
                                     if pair.get("ad_id") == advertisement_id],
            "deferred_rules": []}


def consolidate_review_rows(rows, review_rows, deferred, scoped, coverage):
    """One visible disposition per scope/item; source_ads retains raw history."""
    by_pair = {(row['scope_id'], row['item_id']): row for row in rows}
    for row in review_rows:
        row = dict(row, verdict='판단불가')
        by_pair.setdefault((row['scope_id'], row['item_id']), row)
    titles = {item['item_id']: item.get('title', '') for group in coverage if group
              for item in group.get('items', [])}
    omissions = []
    for entry in deferred:
        if entry['deferred_kind'] == 'OTHER_TEMPLATE':
            continue
        key, item = entry['scope_id'], entry['item_id']
        if entry['deferred_kind'] == 'EXECUTION_BUDGET':
            if not any(v['scope_id'] == key and v['item_id'] == item for v in omissions):
                omissions.append({'scope_id': key, 'item_id': item,
                                 'reason': '과거 실행 한도로 판정을 실행하지 못했습니다. 재처리가 필요합니다.'})
            reason = omissions[-1]['reason']
        else:
            reason = entry.get('reason') or '입력 또는 원문을 사람이 확인해야 합니다.'
            if reason == 'template source structure requires review':
                reason = '템플릿 원문 구조를 자동 해석할 수 없어 사람이 확인해야 합니다.'
        pair = (key, item)
        if pair not in by_pair:
            rule = scoped.get(key, ({}, {}))[0].get(item, {})
            basis = entry.get('template_basis') or {}
            by_pair[pair] = {'row_id': f'{key}:manual:{item}', 'scope_id': key, 'item_id': item,
                'title': entry.get('title') or titles.get(item) or rule.get('title') or '사람 확인이 필요한 점검항목',
                'question': entry.get('question') or rule.get('question', ''),
                'criterion': rule.get('criterion', ''), 'verdict': '판단불가', 'reason': '',
                'evidence': '', 'evidence_ids': [], 'evidence_line_refs': [], 'evidence_locations': [],
                'evidence_location_status': 'NO_CITATION', 'requirement_checks': [],
                'template_section': basis.get('template_section'),
                'template_requirement': basis.get('requirement_mode'),
                'rule_basis': entry.get('rule_basis'), 'judgment_scope': 'RULE'}
        row = by_pair[pair]
        reasons = row.setdefault('manual_review_reasons', [])
        if reason in reasons:
            continue
        reasons.append(reason)
        if row['verdict'] != '판단불가' and 'automated_assessment' not in row:
            row['automated_assessment'] = {'verdict': row['verdict'], 'reason': row['reason']}
        # A proven violation survives an unresolved visual facet. A text-only
        # pass is insufficient for an item whose other required facet is unknown.
        if row['verdict'] != '위반':
            row['verdict'] = '판단불가'
        row['reason'] = (row['reason'] + '\n사람 확인 필요: ' + reason).strip()
    return ([r for r in by_pair.values() if r['verdict'] != '미해당'],
            [r for r in by_pair.values() if r['verdict'] == '미해당'], omissions)


def frozen_rule_metadata(path, freeze):
    """Display names only from the exact regulation version frozen by this review."""
    path = Path(path)
    expected = tuple(sorted(item['sha256'] for item in freeze.get('inputs', [])
                            if str(item.get('path', '')).lower().endswith('.xlsx') and item.get('sha256')))
    if not expected or not path.is_file():
        return {}
    stat = path.stat()
    return _rule_metadata(str(path), stat.st_mtime_ns, stat.st_size, expected)


@lru_cache(maxsize=8)
def _rule_metadata(path, _mtime, _size, expected):
    import openpyxl
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    if digest not in expected:
        return {}
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if '실행_점검항목' not in book.sheetnames:
            return {}
        rows = book['실행_점검항목'].iter_rows(values_only=True)
        columns = {name: index for index, name in enumerate(next(rows))}
        result = {}
        for row in rows:
            def field(name):
                return str(row[columns[name]] or '') if name in columns else ''
            item = field('항목ID')
            if item:
                basis = field('근거법령')
                result[item] = {'title': field('약칭'), 'question': field('점검문구'),
                    'rule_basis': {'item_id': item, 'source_type': 'REGULATION_V2',
                        'source_ref': '실행_점검항목:' + item, 'source_sha256': digest,
                        'legal_basis_refs': [basis] if basis else [],
                        'basis_status': 'LEGAL_BASIS_BOUND' if basis else 'LEGAL_BASIS_NOT_PROVIDED'}}
        return result
    finally:
        book.close()
