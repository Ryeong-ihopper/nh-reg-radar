from __future__ import annotations

import re
import unittest
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]
TEST_CASES = REPOSITORY / "docs" / "test-cases.md"

# 테스트케이스 표는 첫 열 머리글이 `TC ID`다. `연결 TC`처럼 여러 케이스를 묶어 참조하는
# 매핑 표는 케이스를 정의하지 않으므로 세지 않는다. 첫 열 값을 형식으로 걸러 모으면
# 잘못된 식별자가 수집 단계에서 버려져 형식 검사를 우회하므로, 표 위치로 판별한다.
IDENTIFIER_COLUMN = "TC ID"
# `TC-NFR-DOC-001`처럼 영역이 여러 단계인 식별자도 있다.
IDENTIFIER_PATTERN = re.compile(r"^TC-(?:[A-Z]+-)+\d{3}$")


def split_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_delimiter(cell: str) -> bool:
    return bool(cell) and set(cell) <= set("-:")


def collect_rows(text: str) -> dict[str, list[tuple[int, str]]]:
    """`TC ID` 표의 식별자별 행 위치와 항목명을 모은다.

    표 판별은 머리글로 하고 첫 열 값은 형식을 따지지 않고 그대로 담는다. 그래야 잘못된
    식별자도 수집돼 형식 검사가 볼 수 있다. 표 바깥에서 식별자를 언급하는 문장이나 다른
    열의 참조는 담지 않는다.
    """
    rows: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for number, cells, header in walk_table_rows(text):
        if header == IDENTIFIER_COLUMN:
            rows[cells[0]].append((number, cells[1] if len(cells) > 1 else ""))
    return dict(rows)


def walk_table_rows(text: str) -> Iterator[tuple[int, list[str], str | None]]:
    """표 행을 (행 번호, 셀, 그 표의 첫 열 머리글)로 훑는다.

    표를 여는 행 자체는 머리글이 `None`으로 나온다. 빈 줄이나 문단이 표를 끊으면 뒤따르는
    행이 새 표를 여는 것으로 보이므로, 소속 표를 함께 돌려주어 구조 결함을 판별할 수 있다.
    """
    header: str | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.startswith("|"):
            header = None
            continue
        cells = split_row(line)
        if not cells or not cells[0]:
            continue
        if is_delimiter(cells[0]):
            continue
        if header is None:
            # 표의 첫 행은 머리글이다.
            header = cells[0]
            yield number, cells, None
            continue
        yield number, cells, header


def collect_orphan_rows(text: str) -> list[tuple[int, str]]:
    """표에서 떨어져 나와 스스로 머리행이 된 식별자 행을 찾는다.

    표 중간에 빈 줄이 들어가면 뒤따르는 케이스 행이 별도 표의 머리행이 되어 고유성 검사
    범위에서 조용히 빠진다. 실제로 그렇게 새어나간 행이 있었으므로(#30) 함께 막는다.
    """
    return [
        (number, cells[0])
        for number, cells, header in walk_table_rows(text)
        if header is None and cells[0].startswith("TC-")
    ]


def document_rows() -> dict[str, list[tuple[int, str]]]:
    return collect_rows(TEST_CASES.read_text(encoding="utf-8"))


class TestCaseIdentifierTest(unittest.TestCase):
    """테스트케이스 식별자의 고유성과 형식을 고정한다.

    같은 ID를 서로 다른 케이스가 나눠 쓰면 목표 manifest, 커밋, PR에서 `TC-xxx-nnn`으로
    참조할 때 어떤 케이스인지 특정할 수 없다. 표 중간에 행을 끼워 넣으면서 이미 쓰인
    번호를 재사용하는 실수가 실제로 반복됐으므로(#30) 자동으로 막는다.

    검사 범위는 현재 문서 안의 중복과 형식까지다. `docs/project-rules.md` §5.2의 "기존
    식별자 보존"과 "다음 번호 부여"는 이전 버전과의 비교가 필요하므로 자동 검증하지
    않는다. 그 판단은 변경 이력과 리뷰가 담당한다.
    """

    def test_document_declares_test_case_rows(self) -> None:
        self.assertGreater(len(document_rows()), 300, "테스트케이스 표를 읽지 못했습니다")

    def test_identifiers_are_unique(self) -> None:
        rows = document_rows()
        duplicates = {
            identifier: entries for identifier, entries in rows.items() if len(entries) > 1
        }
        if duplicates:
            report = "\n".join(
                f"  {identifier}: " + " / ".join(f"{number}행 {name}" for number, name in entries)
                for identifier, entries in sorted(duplicates.items())
            )
            message = (
                "같은 테스트케이스 식별자를 여러 행이 사용합니다. 기존 식별자는 보존하고 "
                "나중에 추가한 행에 해당 접두어의 다음 번호를 부여하세요."
            )
            self.fail(f"{message}\n{report}")

    def test_identifiers_use_the_documented_shape(self) -> None:
        for identifier, entries in sorted(document_rows().items()):
            with self.subTest(identifier=identifier):
                self.assertRegex(
                    identifier,
                    IDENTIFIER_PATTERN,
                    f"{entries[0][0]}행: 식별자는 TC-<영역>-<3자리> 형식을 사용합니다",
                )

    def test_no_identifier_row_floats_outside_a_table(self) -> None:
        orphans = collect_orphan_rows(TEST_CASES.read_text(encoding="utf-8"))
        if orphans:
            report = "\n".join(f"  {number}행: {identifier}" for number, identifier in orphans)
            message = (
                "표에서 떨어져 나온 케이스 행이 있습니다. 앞의 빈 줄을 없애 원래 표에 붙이거나 "
                "해당 영역의 표로 옮기세요. 떠 있는 행은 고유성 검사에서 빠집니다."
            )
            self.fail(f"{message}\n{report}")

    def test_orphan_detection_catches_a_blank_line_inside_a_table(self) -> None:
        """표 중간 빈 줄로 행이 이탈하는 구조 결함을 실제로 잡는지 확인한다."""
        broken = "\n".join(
            (
                "| TC ID | 테스트 항목 | 기대 결과 |",
                "| --- | --- | --- |",
                "| TC-ABC-001 | 첫 케이스 | 기대 |",
                "",
                "| TC-ABC-002 | 이탈한 케이스 | 기대 |",
            )
        )
        self.assertEqual(collect_orphan_rows(broken), [(5, "TC-ABC-002")])
        # 이탈한 행은 고유성 검사에서 빠지므로 중복이어도 통과해 버린다.
        self.assertNotIn("TC-ABC-002", collect_rows(broken))

        fixed = broken.replace("| 기대 |\n\n", "| 기대 |\n")
        self.assertEqual(collect_orphan_rows(fixed), [])
        self.assertIn("TC-ABC-002", collect_rows(fixed))

    def test_compound_area_identifiers_are_covered(self) -> None:
        """`TC-NFR-*` 같은 복합 영역 식별자도 검사 범위에 들어와야 한다."""
        rows = document_rows()
        compound = [identifier for identifier in rows if identifier.count("-") > 2]
        self.assertGreater(len(compound), 50, "복합 영역 식별자가 수집되지 않았습니다")
        self.assertIn("TC-NFR-DOC-001", rows)
        self.assertIn("TC-NFR-SEC-001", rows)

    def test_collector_detects_duplicated_single_and_compound_identifiers(self) -> None:
        """검사 자체가 단일·복합 식별자 중복을 모두 잡는지 확인한다."""
        sample = "\n".join(
            (
                "| TC ID | 테스트 항목 | 기대 결과 |",
                "| --- | --- | --- |",
                "| TC-XYZ-001 | 첫 케이스 | 기대 |",
                "| TC-XYZ-001 | 다른 케이스 | 기대 |",
                "| TC-NFR-XYZ-001 | 복합 첫 케이스 | 기대 |",
                "| TC-NFR-XYZ-001 | 복합 다른 케이스 | 기대 |",
                "| TC-XYZ-002 | 세 번째 | 기대 |",
            )
        )
        rows = collect_rows(sample)
        self.assertEqual([name for _, name in rows["TC-XYZ-001"]], ["첫 케이스", "다른 케이스"])
        self.assertEqual(
            [name for _, name in rows["TC-NFR-XYZ-001"]], ["복합 첫 케이스", "복합 다른 케이스"]
        )
        self.assertEqual(len(rows["TC-XYZ-002"]), 1)

    def test_collector_keeps_malformed_identifiers_for_the_shape_check(self) -> None:
        """형식이 틀린 식별자를 버리지 않아야 형식 검사가 걸러낼 수 있다."""
        sample = "\n".join(
            (
                "| TC ID | 테스트 항목 | 기대 결과 |",
                "| --- | --- | --- |",
                "| TC-abc-001 | 소문자 영역 | 기대 |",
                "| TC-ABC-18 | 두 자리 번호 | 기대 |",
                "| TC-ABC-001/002 | 묶음 표기 | 기대 |",
            )
        )
        rows = collect_rows(sample)
        for malformed in ("TC-abc-001", "TC-ABC-18", "TC-ABC-001/002"):
            self.assertIn(malformed, rows)
            self.assertNotRegex(malformed, IDENTIFIER_PATTERN)

    def test_collector_ignores_rows_outside_identifier_tables(self) -> None:
        """매핑 표(`연결 TC`)와 본문 언급은 케이스 행으로 세지 않는다."""
        sample = "\n".join(
            (
                "TC-ABC-001은 문장 안에서 언급될 수 있다.",
                "",
                "| 연결 TC | 화면 검증 |",
                "| --- | --- |",
                "| TC-ABC-001/002/003 | 묶음 참조 |",
                "",
                "| TC ID | 테스트 항목 | 기대 결과 |",
                "| --- | --- | --- |",
                "| TC-ABC-001 | 실제 케이스 | 기대 |",
            )
        )
        rows = collect_rows(sample)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows["TC-ABC-001"][0][1], "실제 케이스")


if __name__ == "__main__":
    _ = unittest.main()
