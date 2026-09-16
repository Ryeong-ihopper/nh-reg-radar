"""Saved evidence -> display geometry. Never infer source links from text similarity."""
from __future__ import annotations

import math
import sys
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


def saved_workspace(raw, requests, document, advertisement_id, discovery=None, reading_audits=None):
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
                                         ([c for c in ad.get("excluded_candidates", [])
                                           if unresolved_applicability(c.get("judgment") or {})], rows, "scope-review")):
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
                    "row_id": f"{key}:{kind}:{item_id}:{number}", "item_id": item_id,
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
    deferred = [dict(row, scope_id=ad.get("scope_id")) for ad in ads
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
            else "OTHER_TEMPLATE" if row.get("reason") == "routing did not select this rule's template section"
            else "INPUT_OR_STRUCTURE"
        )
    discoveries = {ad['ad_id']: ad for ad in (discovery or {}).get('ads', [])}
    coverage = [ad.get('template_coverage') or discoveries.get(ad.get('scope_id') or ad['ad_id'], {}).get('template_coverage')
                for ad in ads]
    return {"rows": rows, "review_candidate_rows": review_rows,
            "template_coverage": [value for value in coverage if value],
            "source_ads": ads,
            "output_failure_pairs": [pair for pair in raw.get("output_failure_pairs", [])
                                     if pair.get("ad_id") == advertisement_id],
            "deferred_rules": deferred}
