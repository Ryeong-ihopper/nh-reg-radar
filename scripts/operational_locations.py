"""Saved evidence -> display geometry. Never infer source links from text similarity."""
from __future__ import annotations

import math


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


def saved_workspace(raw, requests, document, advertisement_id, discovery=None):
    """Single projection shared by the active UI and JSON download."""
    ads = [ad for ad in raw.get("ads", []) if ad["ad_id"] == advertisement_id]
    scoped = {}
    for request in requests:
        if request.get("ad_id") != advertisement_id and not request.get("ad_id", "").startswith(advertisement_id + "::"):
            continue
        key = request["ad_id"]
        definitions, evidence = scoped.setdefault(key, ({}, {}))
        definitions.update({rule["item_id"]: rule for rule in request["rules"]})
        evidence.update({doc["evidence_id"]: doc for doc in request["documents"]})
    texts = {line["line_ref"]: line.get("text") or line.get("parser_text") or ""
             for page in document.get("pages", []) for line in page_lines(page)
             if line.get("line_ref")}
    rows, review_rows = [], []
    for ad in ads:
        key = ad.get("scope_id") or ad["ad_id"]
        rules, evidence = scoped.get(key, ({}, {}))
        for candidates, target, kind in ((ad.get("candidates", []), rows, "finding"),
                                         (ad.get("review_candidates", []), review_rows, "review")):
            for number, candidate in enumerate(candidates):
                prediction = candidate.get("judgment") or {}
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
                target.append({
                    "row_id": f"{key}:{kind}:{item_id}:{number}", "item_id": item_id,
                    "title": title, "question": rule.get("question", ""),
                    "criterion": rule.get("criterion") or rule.get("guide", ""),
                    "template_example": rule.get("example_text", "") if rule.get("source_sheet") == "HWPX_TEMPLATE" else "",
                    "requirement_checks": prediction.get("requirement_checks", []),
                    "verdict": {"VIOLATION": "위반", "COMPLIANT": "충족",
                                "UNDETERMINED": "판단불가", "NOT_APPLICABLE": "미해당"}.get(prediction["verdict"], prediction["verdict"]),
                    "reason": prediction.get("reason", ""), "evidence": text,
                    "evidence_ids": prediction.get("evidence_ids", []),
                    "evidence_line_refs": prediction.get("evidence_line_refs", []),
                    "evidence_locations": resolve_locations(document, prediction, evidence),
                    "rule_basis": candidate.get("rule_basis"),
                    "decision_trace": candidate.get("decision_trace"),
                })
    deferred = [dict(row, scope_id=ad.get("scope_id")) for ad in ads
                for row in ad.get("deferred_rules", [])]
    scopes = {ad.get("scope_id") or ad["ad_id"] for ad in ads}
    for scope in (discovery or {}).get("ads", []):
        if scope.get("ad_id") in scopes:
            deferred.extend({"scope_id": scope["ad_id"], "item_id": item,
                             "reason": "execution_budget_not_inapplicability"}
                            for item in scope.get("candidate_budget", {}).get("deferred_ids", []))
    for row in deferred:
        row["deferred_kind"] = (
            "EXECUTION_BUDGET" if row.get("reason") == "execution_budget_not_inapplicability"
            else "OTHER_TEMPLATE" if row.get("reason") == "routing did not select this rule's template section"
            else "INPUT_OR_STRUCTURE"
        )
    return {"rows": rows, "review_candidate_rows": review_rows,
            "source_ads": ads,
            "output_failure_pairs": [pair for pair in raw.get("output_failure_pairs", [])
                                     if pair.get("ad_id") == advertisement_id],
            "deferred_rules": deferred}
