"""Legacy: export the supplied NH advertisement template HWPX into a review workbook.

The HWPX is a source template, not a regulation source.  This tool preserves
its four source columns verbatim and optionally cross-references only the
``신규규칙후보`` sheet in regulation-list v2.  It deliberately leaves the
compliant/violation/review guidance columns empty: those judgments require an
approved general guide and must not be invented from individual advertisements.
"""
from __future__ import annotations

import argparse
import re
import zipfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

import openpyxl
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


def local_name(node: ET.Element) -> str:
    return node.tag.rsplit("}", 1)[-1]


def clean(value: object) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def key(value: object) -> str:
    return re.sub(r"\s+", "", clean(value)).replace("[", "").replace("]", "")


def cell_text(cell: ET.Element) -> str:
    paragraphs = []
    for paragraph in cell.iter():
        if local_name(paragraph) != "p":
            continue
        text = clean("".join(paragraph.itertext()))
        if text:
            paragraphs.append(text)
    return "\n".join(dict.fromkeys(paragraphs))


def table_rows(table: ET.Element) -> tuple[list[str], list[list[str]], list[str]]:
    """Read an HWPX table, including cells carried by row/column spans."""
    cells: list[tuple[int, int, int, int, str]] = []
    for cell in table.iter():
        if local_name(cell) != "tc":
            continue
        address = next((x for x in cell if local_name(x) == "cellAddr"), None)
        span = next((x for x in cell if local_name(x) == "cellSpan"), None)
        if address is None:
            continue
        row = int(address.get("rowAddr", "0"))
        col = int(address.get("colAddr", "0"))
        row_span = int(span.get("rowSpan", "1")) if span is not None else 1
        col_span = int(span.get("colSpan", "1")) if span is not None else 1
        cells.append((row, col, row_span, col_span, cell_text(cell)))

    row_count = int(table.get("rowCnt", "0"))
    col_count = int(table.get("colCnt", "0"))

    def value_at(row: int, col: int) -> str:
        for start_row, start_col, row_span, col_span, text in cells:
            if start_row <= row < start_row + row_span and start_col <= col < start_col + col_span:
                return text
        return ""

    matrix = [[value_at(row, col) for col in range(col_count)] for row in range(row_count)]
    headers = [clean(value) for value in (matrix[0] if matrix else [])]
    issues = []
    required = {"구분", "예시문구", "필수여부", "기재요령"}
    found = {key(header) for header in headers}
    missing = sorted(required - found)
    if missing:
        issues.append(f"원본 표 헤더 누락 또는 변형: {', '.join(missing)}")
    return headers, matrix[1:], issues


def find_column(headers: Iterable[str], name: str) -> int | None:
    target = key(name)
    for index, header in enumerate(headers):
        if key(header) == target:
            return index
    return None


def extract_templates(hwpx_path: Path) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    with zipfile.ZipFile(hwpx_path) as archive:
        root = ET.fromstring(archive.read("Contents/section0.xml"))

    rows: list[dict[str, object]] = []
    issues: list[dict[str, str]] = []
    section = ""
    table_number = 0
    for paragraph in list(root):
        if local_name(paragraph) != "p":
            continue
        direct_text = clean("".join(
            node.text or "" for node in paragraph.iter() if local_name(node) == "t"
        ))
        tables = [node for node in paragraph.iter() if local_name(node) == "tbl"]
        if not tables:
            if re.fullmatch(r"\[[^\]]+\]", direct_text):
                section = direct_text[1:-1].strip()
            continue
        for table in tables:
            table_number += 1
            headers, source_rows, table_issues = table_rows(table)
            for message in table_issues:
                issues.append({
                    "원본표번호": str(table_number),
                    "템플릿섹션": section,
                    "검토사유": message,
                })
            label_index = find_column(headers, "구분")
            example_index = find_column(headers, "예시문구")
            required_index = find_column(headers, "필수여부")
            guidance_index = find_column(headers, "기재요령")
            for source_row, values in enumerate(source_rows, start=1):
                def column(index: int | None) -> str:
                    return clean(values[index]) if index is not None and index < len(values) else ""

                label = column(label_index)
                example = column(example_index)
                mandatory = column(required_index)
                guidance = column(guidance_index)
                if not any((label, example, mandatory, guidance)):
                    continue
                rows.append({
                    "원본표번호": table_number,
                    "원본행번호": source_row,
                    "템플릿_원본ID": f"HWPX-T{table_number:02d}-R{source_row:03d}",
                    "템플릿섹션": section,
                    "구분": label,
                    "예시문구": example,
                    "필수여부": mandatory,
                    "기재요령": guidance,
                    "이미지_대체문구포함": "Y" if "그림입니다" in example else "N",
                })
    return rows, issues


def load_v2_template_rows(path: Path) -> dict[tuple[str, str], list[dict[str, str]]]:
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = book["신규규칙후보"]
    values = sheet.iter_rows(values_only=True)
    headers = [clean(value) for value in next(values)]
    index = {name: position for position, name in enumerate(headers)}
    by_key: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in values:
        record = {name: clean(row[position]) if position < len(row) else "" for name, position in index.items()}
        item_id = record.get("템플릿_셀ID", "")
        section = record.get("섹션", "")
        label = record.get("구분", "")
        if item_id and section and label:
            by_key[(key(section), key(label))].append({
                "T항목ID": item_id,
                "T필수여부": record.get("필수여부", ""),
                "T예시문구": record.get("예시문구", ""),
                "T기재요령": record.get("기재요령", ""),
            })
    book.close()
    return by_key


def map_v2(rows: list[dict[str, object]], v2_rows: dict[tuple[str, str], list[dict[str, str]]]) -> list[dict[str, object]]:
    mapped = []
    for row in rows:
        candidates = v2_rows.get((key(row["템플릿섹션"]), key(row["구분"])), [])
        item_ids = [candidate["T항목ID"] for candidate in candidates]
        output = dict(row)
        output["v2_T항목ID_후보"] = "\n".join(item_ids)
        output["v2_매핑상태"] = "정확일치" if len(candidates) == 1 else ("복수후보" if candidates else "미매핑")
        output["판정가이드_적합조건"] = ""
        output["판정가이드_부적정조건"] = ""
        output["판정가이드_확인필요조건"] = ""
        output["판정가이드_안내문구"] = ""
        mapped.append(output)
    return mapped


def style_sheet(sheet, widths: dict[str, int]) -> None:
    header_fill = PatternFill("solid", fgColor="1F4E78")
    for cell in sheet[1]:
        cell.font = Font(color="FFFFFF", bold=True)
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)


def build_workbook(
    output_path: Path,
    *,
    source_path: Path,
    rows: list[dict[str, object]],
    issues: list[dict[str, str]],
) -> None:
    book = Workbook()
    readme = book.active
    readme.title = "README"
    readme.append(["항목", "내용"])
    readme.append(["원본", str(source_path)])
    readme.append(["생성일", date.today().isoformat()])
    readme.append(["추출 범위", "HWPX의 20개 표에서 구분·예시문구·필수여부·기재요령을 행 단위로 보존"])
    readme.append(["판정 가이드", "적합·부적정·확인필요 열은 원문에 없는 값이므로 비워 둠. 준법감시부 승인 일반 기준으로만 기입"])
    readme.append(["v2 매핑", "규제목록 v2 신규규칙후보의 섹션+구분 정확일치만 후보로 표시. 미매핑은 오류가 아니라 추가 검토 대상"])
    style_sheet(readme, {"A": 22, "B": 120})

    source = book.create_sheet("템플릿_원문정리")
    columns = [
        "원본표번호", "원본행번호", "템플릿_원본ID", "템플릿섹션", "구분", "예시문구",
        "필수여부", "기재요령", "이미지_대체문구포함", "v2_T항목ID_후보", "v2_매핑상태",
        "판정가이드_적합조건", "판정가이드_부적정조건", "판정가이드_확인필요조건", "판정가이드_안내문구",
    ]
    source.append(columns)
    for row in rows:
        source.append([row.get(column, "") for column in columns])
    style_sheet(source, {
        "A": 11, "B": 11, "C": 20, "D": 36, "E": 20, "F": 70, "G": 12,
        "H": 55, "I": 15, "J": 20, "K": 14, "L": 45, "M": 45, "N": 45, "O": 45,
    })

    summary = book.create_sheet("템플릿_요약")
    summary.append(["템플릿섹션", "항목수", "O", "△", "필수여부 미기재", "v2 정확일치", "v2 미매핑"])
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["템플릿섹션"])].append(row)
    for section, section_rows in sorted(grouped.items()):
        status = Counter(str(row["v2_매핑상태"]) for row in section_rows)
        mandatory = Counter(clean(row["필수여부"]) for row in section_rows)
        summary.append([
            section, len(section_rows), mandatory.get("O", 0), mandatory.get("△", 0),
            len(section_rows) - mandatory.get("O", 0) - mandatory.get("△", 0),
            status.get("정확일치", 0), status.get("미매핑", 0),
        ])
    style_sheet(summary, {"A": 48, "B": 10, "C": 9, "D": 9, "E": 15, "F": 13, "G": 12})

    review = book.create_sheet("추출_검토필요")
    review.append(["원본표번호", "템플릿섹션", "검토사유"])
    for issue in issues:
        review.append([issue["원본표번호"], issue["템플릿섹션"], issue["검토사유"]])
    for row in rows:
        if str(row["v2_매핑상태"]) != "정확일치":
            review.append([row["원본표번호"], row["템플릿섹션"], f"{row['템플릿_원본ID']}: v2 {row['v2_매핑상태']}"])
    style_sheet(review, {"A": 13, "B": 48, "C": 80})

    output_path.parent.mkdir(parents=True, exist_ok=True)
    book.save(output_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template-hwpx", type=Path, required=True)
    parser.add_argument("--regulation-v2", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows, issues = extract_templates(args.template_hwpx)
    v2_rows = load_v2_template_rows(args.regulation_v2)
    mapped = map_v2(rows, v2_rows)
    build_workbook(args.output, source_path=args.template_hwpx, rows=mapped, issues=issues)
    print(f"template rows={len(mapped)} tables={len(set(row['원본표번호'] for row in mapped))} output={args.output}")


if __name__ == "__main__":
    main()
