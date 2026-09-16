"""Deterministic HWPX source adapter and independent template checklist catalog.

No regulation workbook, advertisement, gold, or model is used during ingestion.
Raw XML is retained alongside the projection so unsupported structures remain
auditable. Structural completeness is not a claim of rendered-page fidelity.
"""
from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

SCHEMA = "review-template-catalog-v1"
PARSER_VERSION = "hwpx-template-1"
HEADERS = {"구분": "label", "예시문구": "example", "필수여부": "requirement", "기재요령": "guidance"}
CASE_HEADERS = {"판단", "판단근거", "광고문구"}
ALTERNATIVE_METHOD = re.compile(r"^\s*\[방식\s*([^]]+)\]")


def required_observation_medium(guidance: str) -> tuple[str, str, str]:
    """Choose the observation contract stated by a template row.

    This does not interpret an advertisement or add a rule.  It only prevents
    a text-only model from treating a navigation/section label as proof for a
    template instruction that is explicitly about line arrangement or visual
    presentation.
    """
    normalized = re.sub(r"\s+", "", guidance or "")
    layout_tokens = (
        "한줄", "같은줄", "줄바꿈", "줄로", "나란히", "배치", "위치",
        "글자크기", "글씨크기", "폰트", "글꼴", "서체", "로고", "색상", "시인성", "가독성",
        "인식하기", "분리하여",
    )
    # Contrast requires visual context: the syllables also occur in costs
    # (부대비용) and ordinary numerical comparisons (전년 대비).
    visual_contrast = "대비" in normalized and any(
        token in normalized for token in ("배경", "명암", "명도", "전경", "색채")
    )
    if visual_contrast or any(token in normalized for token in layout_tokens):
        return "광고물+원본형식+레이아웃", "LAYOUT", "레이아웃"
    return "광고물", "LLM", "텍스트"


def local(node):
    return node.tag.rsplit("}", 1)[-1]


def key(text):
    return re.sub(r"\s+", "", text)


def owned(node, tag, boundary):
    """Descendants belonging to this object, excluding nested objects."""
    for child in node:
        if local(child) in boundary:
            continue
        if local(child) == tag:
            yield child
        else:
            yield from owned(child, tag, boundary)


def text_content(node):
    parts = []
    for child in node:
        tag = local(child)
        if tag in {"tbl", "pic", "shapeComment"}:
            continue
        if tag == "t":
            parts.append("".join(child.itertext()))
        elif tag in {"lineBreak", "br"}:
            parts.append("\n")
        elif tag == "tab":
            parts.append("\t")
        else:
            parts.append(text_content(child))
    return "".join(parts)


def parse_hwpx(path: Path) -> dict:
    """Preserve every section, physical cell, duplicate paragraph and XML part."""
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    tables, outside, issues, xml_parts, objects = [], [], [], {}, []
    cell_refs_by_node = {}
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("duplicate ZIP member")
        sections = sorted((n for n in names if re.fullmatch(r"Contents/section\d+\.xml", n)),
                          key=lambda n: int(re.search(r"section(\d+)", n).group(1)))
        if not sections:
            raise ValueError("HWPX has no section XML")
        for name in names:
            if name.endswith((".xml", ".hpf")):
                raw = archive.read(name)
                if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
                    raise ValueError("XML entity declarations are unsupported")
                xml_parts[name] = raw.decode("utf-8-sig")
        for name in names:
            if name.startswith("BinData/"):
                raw = archive.read(name)
                objects.append({"member": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})

        # Physical sections are separate: never carry a template heading across
        # an unknown section boundary merely because the prior section had one.
        for member in sections:
            root = ET.fromstring(xml_parts[member])
            parent = {child: node for node in root.iter() for child in node}

            def ancestor(node, tag):
                node = parent.get(node)
                while node is not None:
                    if local(node) == tag:
                        return node
                    node = parent.get(node)
                return None

            title = ""
            table_number = 0
            for node in root.iter():
                if local(node) == "p" and ancestor(node, "tc") is None:
                    text = text_content(node)
                    if text.strip():
                        ref = f"{member}#p{len(outside)+1}"
                        outside.append({"ref": ref, "text": text, "attributes": dict(node.attrib)})
                        match = re.fullmatch(r"\s*\[([^\]]+)\]\s*", text)
                        if match:
                            title = match.group(1).strip()
                if local(node) != "tbl":
                    continue
                table_number += 1
                ref = f"{member}#table{table_number}"
                rows, cols = int(node.get("rowCnt", "0")), int(node.get("colCnt", "0"))
                if rows <= 0 or cols <= 0 or rows * cols > 100000:
                    raise ValueError(f"invalid table dimensions: {ref}")
                grid = [[None for _ in range(cols)] for _ in range(rows)]
                cells = []
                for cell in owned(node, "tc", {"tbl"}):
                    address = next((n for n in cell if local(n) == "cellAddr"), None)
                    span = next((n for n in cell if local(n) == "cellSpan"), None)
                    if address is None:
                        raise ValueError(f"cell without address: {ref}")
                    row, col = int(address.get("rowAddr", "-1")), int(address.get("colAddr", "-1"))
                    rs = int(span.get("rowSpan", "1")) if span is not None else 1
                    cs = int(span.get("colSpan", "1")) if span is not None else 1
                    if min(row, col) < 0 or min(rs, cs) < 1 or row+rs > rows or col+cs > cols:
                        raise ValueError(f"cell outside table: {ref}/{row}/{col}")
                    cell_ref = f"{ref}/r{row}c{col}"
                    cell_refs_by_node[cell] = cell_ref
                    paragraphs = []
                    for index, p in enumerate(owned(cell, "p", {"tbl", "tc"})):
                        paragraphs.append({
                            "ref": f"{cell_ref}/p{index}", "text": text_content(p),
                            "attributes": dict(p.attrib),
                            "runs": [{"attributes": dict(r.attrib), "text": text_content(r)}
                                     for r in p if local(r) == "run"],
                        })
                    media = [dict(n.attrib) for n in cell.iter() if local(n) == "img"]
                    nested = any(local(n) == "tbl" for n in cell.iter())
                    value = {"ref": cell_ref, "row": row, "col": col, "row_span": rs, "col_span": cs,
                             "paragraphs": paragraphs, "text": "\n".join(p["text"] for p in paragraphs),
                             "attributes": dict(cell.attrib), "images": media, "nested_table": nested}
                    cells.append(value)
                    for y in range(row, row+rs):
                        for x in range(col, col+cs):
                            if grid[y][x] is not None:
                                raise ValueError(f"overlapping cells: {cell_ref}")
                            grid[y][x] = cell_ref
                gaps = sum(v is None for row in grid for v in row)
                if gaps:
                    issues.append({"ref": ref, "code": "UNCOVERED_TABLE_SLOTS", "count": gaps})
                tables.append({"ref": ref, "title": title, "rows": rows, "cols": cols,
                               "nested": ancestor(node, "tbl") is not None,
                               "parent_cell_ref": cell_refs_by_node.get(ancestor(node, "tc")),
                               "cells": cells, "grid": grid, "uncovered_slots": gaps})
    return {"schema_version": "hwpx-template-source-v1", "parser_version": PARSER_VERSION,
            "source": {"filename": path.name, "sha256": source_hash},
            "xml_parts": xml_parts, "binary_objects": objects, "tables": tables,
            "outside_paragraphs": outside, "issues": issues}


def compile_catalog(source: dict) -> dict:
    """Project source rows; never invent conditions from examples or cases."""
    entries, issues, omitted = [], list(source["issues"]), []
    source_hash = source["source"]["sha256"]
    for table in source["tables"]:
        cells = {c["ref"]: c for c in table["cells"]}
        header = [key(cells[r]["text"]) if r else "" for r in table["grid"][0]]
        if set(header) & CASE_HEADERS:
            raise ValueError("review-case columns cannot be loaded as a general template")
        # Recognize a partial header without silently inferring the blank
        # column's meaning. Keep its raw cells and mark every affected row.
        recognized = set(header) & set(HEADERS)
        if table["nested"] or "구분" not in recognized or len(recognized) < 3:
            omitted.append(table["ref"])
            issues.append({"ref": table["ref"], "code": "NON_CHECKLIST_TABLE_RETAINED"})
            continue
        columns = {field: [i for i, h in enumerate(header) if h == name] for name, field in HEADERS.items()}
        for y, row in enumerate(table["grid"][1:], start=1):
            fields = {}
            row_issues = ["INCOMPLETE_HEADER"] if len(recognized) < len(HEADERS) else []
            for field, positions in columns.items():
                refs = list(dict.fromkeys(row[x] for x in positions if row[x]))
                fields[field] = {"cell_refs": refs, "text": "\n".join(cells[r]["text"] for r in refs)}
                if any(row[x] is None for x in positions):
                    row_issues.append("MISSING_PHYSICAL_CELL")
                if any(cells[r]["images"] or cells[r]["nested_table"] for r in refs):
                    row_issues.append("VISUAL_OR_NESTED_CONTENT")
                    fields[field]["requires_structure_review"] = True
            if not any(f["text"].strip() for f in fields.values()) and not row_issues:
                continue
            if all(key(fields[field]["text"]) == name for name, field in HEADERS.items()):
                continue  # repeated header, retained in source
            # A horizontal merge between semantically distinct columns cannot
            # be interpreted as separate conditions even if text is readable.
            field_refs = [set(f["cell_refs"]) for f in fields.values()]
            if any(a & b for i, a in enumerate(field_refs) for b in field_refs[i+1:]):
                row_issues.append("CROSS_FIELD_MERGE")
            raw_mark = fields["requirement"]["text"].strip()
            mode = {"O": "REQUIRED", "○": "REQUIRED", "〇": "REQUIRED", "△": "CONDITIONAL"}.get(raw_mark, "UNSPECIFIED")
            if raw_mark and mode == "UNSPECIFIED":
                row_issues.append("UNRECOGNIZED_REQUIREMENT")
            if not table["title"] or not fields["label"]["text"].strip():
                row_issues.append("MISSING_SECTION_OR_LABEL")
            if mode == "CONDITIONAL" and not fields["guidance"]["text"].strip():
                row_issues.append("CONDITIONAL_GUIDANCE_MISSING")
            ref = f"{table['ref']}/row{y}"
            digest = hashlib.sha256(f"{source_hash}:{ref}".encode()).hexdigest()[:24]
            entries.append({"item_id": f"TPL-{digest}", "source_ref": ref,
                            "template_section": table["title"], "fields": fields,
                            "raw_row_cell_refs": list(dict.fromkeys(r for r in row if r)),
                            "requirement_mode": mode, "issues": sorted(set(row_issues)),
                            "status": "REVIEW_REQUIRED" if row_issues else "STRUCTURED",
                            "legal_basis_refs": []})
    if not entries:
        raise ValueError("no general template checklist found")
    return {"schema_version": SCHEMA, "parser_version": PARSER_VERSION,
            "source": source["source"], "entries": entries, "issues": issues,
            "non_checklist_table_refs": omitted,
            "policy": {"basis": "INTERNAL_TEMPLATE", "v2_mapping_required": False,
                       "examples_are_exact_requirements": False,
                       "conditional_requires_applicability_evidence": True}}


class TemplateCatalog:
    def __init__(self, source: dict):
        self.source = source
        self.document = compile_catalog(source)
        self.by_id = {row["item_id"]: row for row in self.document["entries"]}

    @classmethod
    def from_hwpx(cls, path: Path):
        return cls(parse_hwpx(path))

    def select(self, classification: str, *, status: str) -> dict:
        """Exact confirmed classification selects a checklist, not a verdict."""
        if status not in {"confirmed", "provided", "verified"}:
            return {"status": "CLASSIFICATION_REQUIRED", "entries": []}
        entries = [r for r in self.document["entries"] if key(r["template_section"]) == key(classification)]
        return {"status": "SELECTED" if entries else "TEMPLATE_NOT_FOUND", "entries": entries}

    def judgment_basis(self, item_id: str) -> dict:
        row = self.by_id[item_id]
        return {"item_id": item_id, "basis_type": "INTERNAL_TEMPLATE",
                "source_sha256": self.document["source"]["sha256"], "source_ref": row["source_ref"],
                "template_section": row["template_section"], "fields": row["fields"],
                "requirement_mode": row["requirement_mode"], "structure_status": row["status"],
                "structure_issues": row["issues"], "legal_basis_refs": row["legal_basis_refs"],
                "policy": self.document["policy"]}

    def operational_rules(self) -> list[dict]:
        """Adapt independent source items to the shared evidence/rule contract."""
        rules = []
        for row in self.document["entries"]:
            section, fields = row["template_section"], row["fields"]
            input_requirement, judgment_type, required_medium = required_observation_medium(
                fields["guidance"]["text"]
            )
            # Ingest all families; the current advertised PoC supports these
            # two only. This is a product-scope boundary, not source omission.
            groups = [g for g in ("대출성", "예금성") if section.startswith(g)]
            if not groups:
                continue
            basis = self.judgment_basis(row["item_id"])
            # Keep the original structure status. Readable obligations remain
            # independently checkable when only an example contains an image or
            # nested table; unknown headers/marks/merged fields never qualify.
            text_ready = (
                not (set(row["issues"]) - {"VISUAL_OR_NESTED_CONTENT"})
                and not any(fields[name].get("requires_structure_review")
                            for name in ("label", "requirement", "guidance"))
                and row["requirement_mode"] in {"REQUIRED", "CONDITIONAL"}
                and bool(fields["example"]["text"].strip() or
                         (required_medium == "텍스트" and fields["guidance"]["text"].strip()))
            )
            partial = text_ready and (
                required_medium == "레이아웃" or "VISUAL_OR_NESTED_CONTENT" in row["issues"]
            )
            basis["text_review_ready"] = text_ready
            basis["text_facet_only"] = partial
            basis["manual_review_required"] = partial
            criterion = fields["guidance"]["text"]
            if not partial:
                criterion = (f"{fields['label']['text']}의 필수 의미요소를 확인한다. "
                             "예시의 숫자·상품명·문구 완전일치는 의무가 아니다.\n"
                             f"예시: {fields['example']['text']}\n기재요령 원문: {criterion}")
            if partial:
                # Keep visual source paragraphs in the source-bound manual
                # facet, not as obligations in the text-only model contract.
                # Mixed paragraphs are conservatively deferred in full.
                text_guidance = "\n".join(
                    line for line in criterion.splitlines()
                    if required_observation_medium(line)[2] == "텍스트"
                )
                basis["manual_guidance"] = criterion
                criterion = (
                    "원문의 텍스트 기재 의무만 판정한다. 예시의 필수 의미를 확인하되 "
                    "예시 숫자·상품명·문자열의 완전일치를 요구하지 않는다.\n"
                    f"텍스트 예시: {fields['example']['text']}\n텍스트 기재요령: {text_guidance}"
                )
                input_requirement, judgment_type, required_medium = "광고물", "LLM", "텍스트"
            rules.append({
                "item_id": row["item_id"], "source_sheet": "HWPX_TEMPLATE",
                "category": "PRESENCE", "category_label": "템플릿 점검",
                "product_groups": groups, "product_subtype": section,
                "template_required": fields["requirement"]["text"],
                "title": fields["label"]["text"], "question": fields["label"]["text"],
                "criterion": criterion, "guide": fields["guidance"]["text"],
                "example_text": fields["example"]["text"],
                "example_policy": "의미상 예시이며 숫자·상품명·문자열 완전일치 의무가 아님",
                "input_requirement": input_requirement,
                "judgment_type": judgment_type, "required_medium": required_medium,
                "template_basis": basis,
            })
        return group_explicit_alternatives(rules)


def group_explicit_alternatives(rules: list[dict]) -> list[dict]:
    """Compile source-marked ``[방식 N]`` rows into one ANY_OF obligation.

    The marker is an explicit structure in the authoritative template.  It is
    not inferred from duplicate labels, because most duplicate labels are
    independent requirements.  Physical source rows and their IDs remain in
    ``template_basis.alternative_members`` for audit.
    """
    grouped: dict[tuple[str, str], list[tuple[str, dict]]] = {}
    for rule in rules:
        match = ALTERNATIVE_METHOD.match(str(rule.get("example_text") or ""))
        if match:
            grouped.setdefault(
                (str(rule.get("product_subtype") or ""), str(rule.get("title") or "")), []
            ).append((match.group(1).strip(), rule))

    valid_groups = {key: values for key, values in grouped.items() if len(values) > 1}
    emitted: set[tuple[str, str]] = set()
    output: list[dict] = []
    for rule in rules:
        key = (str(rule.get("product_subtype") or ""), str(rule.get("title") or ""))
        members = valid_groups.get(key)
        if not members:
            output.append(rule)
            continue
        if key in emitted:
            continue
        emitted.add(key)
        member_ids = [member["item_id"] for _, member in members]
        digest = hashlib.sha256(
            ("template-any-of\0" + "\0".join(member_ids)).encode("utf-8")
        ).hexdigest()[:24]
        alternatives = [
            {
                "method": method,
                "item_id": member["item_id"],
                "source_ref": member["template_basis"]["source_ref"],
                "example_text": ALTERNATIVE_METHOD.sub(
                    "", str(member.get("example_text") or ""), count=1
                ).strip(),
                "guide": member.get("guide") or "",
            }
            for method, member in members
        ]
        composite = dict(members[0][1])
        composite.update({
            "item_id": f"TPL-{digest}",
            "title": f"{key[1]}(표시 방식 택일)",
            "question": f"{key[1]}를 템플릿에서 허용한 방식 중 하나로 표시했는가?",
            "criterion": (
                "아래 표시 방식 중 광고가 선택한 한 방식의 필수 의미요소를 "
                "모두 확인한다. 예시 숫자·상품명·문구의 완전일치는 요구하지 않는다.\n"
                + "\n".join(
                    f"[방식 {value['method']}] {value['example_text']}"
                    + (f"\n기재요령: {value['guide']}" if value["guide"] else "")
                    for value in alternatives
                )
            ),
            "guide": "템플릿 원문의 [방식 N] 항목 중 하나를 택일",
            "example_text": "\n".join(value["example_text"] for value in alternatives),
        })
        basis = dict(composite["template_basis"])
        member_bases = [member["template_basis"] for _, member in members]
        if any("structure_status" in value for value in member_bases):
            basis["structure_status"] = "STRUCTURED" if all(
                value.get("structure_status") == "STRUCTURED" for value in member_bases
            ) else "REVIEW_REQUIRED"
            basis["text_review_ready"] = all(value.get("text_review_ready") for value in member_bases)
            basis["manual_review_required"] = any(value.get("manual_review_required") for value in member_bases)
            basis["text_facet_only"] = basis["manual_review_required"] and basis["text_review_ready"]
        basis.update({
            "item_id": composite["item_id"],
            "source_ref": ";".join(value["source_ref"] for value in alternatives),
            "alternative_policy": "ANY_OF",
            "alternative_members": alternatives,
        })
        composite["template_basis"] = basis
        output.append(composite)
    return output
