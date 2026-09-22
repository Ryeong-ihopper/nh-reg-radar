"""Load researcher-authored general decision guides without case answers.

Only workbooks whose names end in ``심의방법.xlsx`` are accepted.  Advertisements
and ``심의정답`` files that may live beside them are intentionally invisible to
this adapter, so they cannot leak into operational prompts.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import openpyxl


SCHEMA = "template-methodology-catalog-v1"
PRESENCE_ONLY_MARKER = "[판정방식: 존재확인]"


def compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def methodology_workbooks(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise ValueError(f"template methodology directory not found: {directory}")
    return sorted(
        path for path in directory.glob("*심의방법.xlsx")
        if path.is_file()
        and not path.name.startswith("~$")
        and "심의정답" not in path.name
    )


def section_from_filename(path: Path) -> str:
    stem = re.sub(r"^\s*\d+\.\s*", "", path.stem)
    stem = re.sub(r"\s*심의방법\s*$", "", stem).strip()
    if stem.startswith("투자성상품-ISA"):
        stem = stem.replace(
            "투자성상품-ISA",
            "투자성상품-개인종합자산관리계좌(ISA)",
            1,
        )
    if not stem:
        raise ValueError(f"cannot derive template section from methodology filename: {path.name}")
    return stem


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def parse_methodology_workbook(path: Path) -> dict[str, Any]:
    """Parse the seven decision-guide columns and retain source provenance."""
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows: list[dict[str, Any]] = []
    try:
        for sheet in book.worksheets:
            values = list(sheet.iter_rows(values_only=True))
            header_index = next(
                (
                    index for index, row in enumerate(values)
                    if "구분" in {compact(value) for value in row}
                    and "예시문구" in {compact(value) for value in row}
                    and "적정판단" in {compact(value) for value in row}
                ),
                None,
            )
            if header_index is None:
                continue
            header = list(values[header_index])
            subheader = list(values[header_index + 1]) if header_index + 1 < len(values) else []

            def column(name: str, source: list[Any], *, start: int = 0) -> int:
                for index in range(start, len(source)):
                    if compact(source[index]) == name:
                        return index
                raise ValueError(f"missing methodology column {name}: {path.name}/{sheet.title}")

            label_col = column("구분", header)
            example_col = column("예시문구", header)
            appropriate_col = column("적정판단", header)
            inappropriate_col = column("부적정", header)
            review_col = column("확인필요", header)
            inappropriate_judgment_col = column("부적정판단", subheader, start=inappropriate_col)
            inappropriate_guide_col = column("안내문구", subheader, start=inappropriate_judgment_col + 1)
            review_judgment_col = column("확인필요판단", subheader, start=review_col)
            review_guide_col = column("안내문구", subheader, start=review_judgment_col + 1)
            current_label = ""
            for row_number, row in enumerate(values[header_index + 2 :], header_index + 3):
                row = list(row)

                def value_at(index: int) -> str:
                    return _text(row[index]) if index < len(row) else ""

                current_label = value_at(label_col) or current_label
                example = value_at(example_col)
                if not example:
                    continue
                rows.append({
                    "template_section": section_from_filename(path),
                    "label": current_label,
                    "example": example,
                    "appropriate_judgment": value_at(appropriate_col),
                    "inappropriate_judgment": value_at(inappropriate_judgment_col),
                    "inappropriate_guidance": value_at(inappropriate_guide_col),
                    "review_needed_judgment": value_at(review_judgment_col),
                    "review_needed_guidance": value_at(review_guide_col),
                    "decision_mode": (
                        "PRESENCE_ONLY"
                        if PRESENCE_ONLY_MARKER in value_at(appropriate_col)
                        else None
                    ),
                    "source": {
                        "filename": path.name,
                        "sha256": source_hash,
                        "sheet": sheet.title,
                        "row": row_number,
                    },
                })
    finally:
        book.close()
    if not rows:
        raise ValueError(f"no methodology rows found: {path.name}")
    return {
        "schema_version": SCHEMA,
        "source": {"filename": path.name, "sha256": source_hash},
        "rows": rows,
    }


def attach_methodology(document: dict[str, Any], directory: Path) -> None:
    """Attach every guide row to the matching source template example.

    An unmatched or duplicate row is a configuration error.  Silently dropping
    one of these rows would recreate the missing-criterion problem this source
    is meant to solve.
    """
    workbooks = methodology_workbooks(directory)
    if not workbooks:
        raise ValueError(f"no *심의방법.xlsx files found: {directory}")
    catalogs = [parse_methodology_workbook(path) for path in workbooks]
    guide_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for catalog in catalogs:
        for row in catalog["rows"]:
            match_key = (compact(row["template_section"]), compact(row["example"]))
            if match_key in guide_by_key:
                raise ValueError(f"duplicate methodology row: {row['source']}")
            guide_by_key[match_key] = row

    matched: set[tuple[str, str]] = set()
    for entry in document["entries"]:
        match_key = (
            compact(entry["template_section"]),
            compact(entry["fields"]["example"]["text"]),
        )
        guide = guide_by_key.get(match_key)
        if guide:
            entry["methodology"] = guide
            matched.add(match_key)
    unmatched = [guide_by_key[key]["source"] for key in guide_by_key.keys() - matched]
    if unmatched:
        raise ValueError(f"methodology rows do not match the template source: {unmatched}")
    document["methodology"] = {
        "schema_version": SCHEMA,
        "directory": str(directory),
        "sources": [catalog["source"] for catalog in catalogs],
        "row_count": len(guide_by_key),
        "matched_count": len(matched),
        "case_answers_loaded": False,
    }


def methodology_prompt(guide: dict[str, Any]) -> str:
    fields = (
        ("적정 판단", "appropriate_judgment"),
        ("부적정 판단", "inappropriate_judgment"),
        ("부적정 시 안내", "inappropriate_guidance"),
        ("확인필요 판단", "review_needed_judgment"),
        ("확인필요 시 안내", "review_needed_guidance"),
    )
    lines = [f"- {label}: {guide[field]}" for label, field in fields if guide.get(field)]
    if guide.get("decision_mode") == "PRESENCE_ONLY":
        lines.append(
            "- 구조화 판정방식: 존재확인(광고에 출처가 정한 표시 사실이 있으면 충족; "
            "출처가 별도로 요구하지 않은 요율·절차를 추가 요건으로 만들지 않음)"
        )
    return "업무 판단 가이드 원문:\n" + "\n".join(lines)
