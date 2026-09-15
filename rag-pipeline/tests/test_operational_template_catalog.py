from __future__ import annotations

import tempfile
import unittest
import zipfile
import json
import sys
from unittest import mock
from pathlib import Path
from xml.sax.saxutils import escape

from rag.templates.catalog import (
    TemplateCatalog,
    group_explicit_alternatives,
    parse_hwpx,
    required_observation_medium,
)
from tools.run_operational_e2e import model_rule_view
from tools import run_operational_e2e as runner
from test_operational_service import integrated_input
from rag.parsing.prepare_inputs import search_docs
import numpy as np


def p(text):
    return f'<p styleIDRef="2"><run charPrIDRef="3"><t>{escape(text)}</t></run></p>'


def cell(row, col, text="", *, rs=1, cs=1, body=None):
    return (f'<tc><subList>{p(text) if body is None else body}</subList>'
            f'<cellAddr rowAddr="{row}" colAddr="{col}"/>'
            f'<cellSpan rowSpan="{rs}" colSpan="{cs}"/></tc>')


def table(extra="", *, headers=None, mark="O"):
    headers = headers or ["구분", "예 시 문 구", "필 수 여 부", "기 재 요 령"]
    return ('<tbl rowCnt="2" colCnt="4"><tr>' + ''.join(cell(0, i, h) for i, h in enumerate(headers))
            + '</tr><tr>' + cell(1, 0, "일반 항목") + cell(1, 1, body=p("예시") + p("예시") + extra)
            + cell(1, 2, mark) + cell(1, 3, "조건 성립 시 표시") + '</tr></tbl>')


class TemplateCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "general.hwpx"

    def write(self, contents):
        with zipfile.ZipFile(self.path, "w") as z:
            for i, text in enumerate(contents):
                z.writestr(f"Contents/section{i}.xml", '<sec>' + text + '</sec>')

    def test_line_arrangement_guidance_requires_exact_layout_observation(self):
        self.assertEqual(
            required_observation_medium("한 줄에 2개 이상의 문구를 기재할 수 없음"),
            ("광고물+원본형식+레이아웃", "LAYOUT", "레이아웃"),
        )
        self.assertEqual(
            required_observation_medium("상품명 기재"),
            ("광고물", "LLM", "텍스트"),
        )

    def test_only_explicit_method_rows_become_one_any_of_rule(self):
        def rule(item_id, example):
            return {
                "item_id": item_id,
                "product_subtype": "예금성상품-적립식",
                "title": "금리",
                "example_text": example,
                "guide": "",
                "template_basis": {
                    "source_ref": f"source#{item_id}",
                    "legal_basis_refs": [],
                },
            }

        rows = [
            rule("TPL-1", "[방식 ①] 기본금리"),
            rule("TPL-2", "[방식 ②] 최고금리"),
            rule("TPL-3", "[방식 ③] 범위금리"),
            {**rule("TPL-4", "독립 필수 항목"), "title": "유의사항"},
            {**rule("TPL-5", "다른 독립 필수 항목"), "title": "유의사항"},
        ]

        grouped = group_explicit_alternatives(rows)

        self.assertEqual(len(grouped), 3)
        choice = grouped[0]
        self.assertEqual(choice["template_basis"]["alternative_policy"], "ANY_OF")
        self.assertEqual(
            [row["item_id"] for row in choice["template_basis"]["alternative_members"]],
            ["TPL-1", "TPL-2", "TPL-3"],
        )
        self.assertEqual([row["item_id"] for row in grouped[1:]], ["TPL-4", "TPL-5"])

    def test_independent_rules_preserve_repeated_paragraphs_and_style(self):
        self.write([p("[대출성상품-유형]") + '<p><run>' + table() + '</run></p>'])
        catalog = TemplateCatalog.from_hwpx(self.path)
        row = catalog.document["entries"][0]
        self.assertEqual(row["fields"]["example"]["text"], "예시\n예시")
        self.assertEqual(row["requirement_mode"], "REQUIRED")
        self.assertEqual(row["legal_basis_refs"], [])
        self.assertTrue(row["item_id"].startswith("TPL-"))
        self.assertEqual(catalog.select("대출성상품-유형", status="provided")["status"], "SELECTED")
        self.assertEqual(catalog.select("대출성상품-유형", status="inferred")["entries"], [])
        rule = model_rule_view(catalog.operational_rules()[0])
        self.assertEqual(rule["template_basis"]["source_sha256"], catalog.source["source"]["sha256"])
        self.assertFalse(rule["template_basis"]["policy"]["v2_mapping_required"])
        self.assertEqual(catalog.source["tables"][0]["cells"][5]["paragraphs"][0]["runs"][0]["attributes"]["charPrIDRef"], "3")
        self.assertEqual(catalog.document, TemplateCatalog.from_hwpx(self.path).document)

    def test_nested_table_has_one_owner_and_is_not_a_new_rule(self):
        nested = '<tbl rowCnt="1" colCnt="1"><tr>' + cell(0, 0, "내부 표") + '</tr></tbl>'
        self.write([p("[대출성상품-유형]") + '<p><run>' + table(nested) + '</run></p>'])
        catalog = TemplateCatalog.from_hwpx(self.path)
        self.assertEqual([len(t["cells"]) for t in catalog.source["tables"]], [8, 1])
        self.assertEqual(len(catalog.document["entries"]), 1)
        self.assertEqual(catalog.source["tables"][1]["parent_cell_ref"], catalog.source["tables"][0]["cells"][5]["ref"])
        self.assertEqual(catalog.document["entries"][0]["status"], "REVIEW_REQUIRED")

    def test_blank_header_keeps_rows_without_guessing_requirement(self):
        self.write([p("[예금성상품-유형]") + '<p><run>' + table(headers=["구분", "예시문구", "", "기재요령"]) + '</run></p>'])
        row = TemplateCatalog.from_hwpx(self.path).document["entries"][0]
        self.assertIn("INCOMPLETE_HEADER", row["issues"])
        self.assertEqual(row["requirement_mode"], "UNSPECIFIED")
        self.assertEqual(len(row["raw_row_cell_refs"]), 4)

    def test_cases_rejected_even_with_generic_filename(self):
        self.write([p("[대출성상품-유형]") + '<p><run>' + table(headers=["구분", "광고문구", "판단", "판단근거"]) + '</run></p>'])
        with self.assertRaisesRegex(ValueError, "review-case"):
            TemplateCatalog.from_hwpx(self.path)

    def test_all_sections_and_hash_changes_are_retained(self):
        self.write([p("[예금성상품-유형]") + '<p><run>' + table() + '</run></p>',
                    p("[대출성상품-유형]") + '<p><run>' + table(mark="△") + '</run></p>'])
        before = TemplateCatalog.from_hwpx(self.path)
        self.assertEqual(len(before.document["entries"]), 2)
        self.assertEqual(before.document["entries"][1]["requirement_mode"], "CONDITIONAL")
        self.write([p("[예금성상품-유형]") + '<p><run>' + table(mark="?") + '</run></p>'])
        after = TemplateCatalog.from_hwpx(self.path)
        self.assertNotEqual(before.document["entries"][0]["item_id"], after.document["entries"][0]["item_id"])
        self.assertIn("UNRECOGNIZED_REQUIREMENT", after.document["entries"][0]["issues"])

    def test_span_expands_references_without_copying_physical_cells(self):
        content = '<tbl rowCnt="2" colCnt="2"><tr>' + cell(0, 0, "공통", rs=2) + cell(0, 1, "상단")
        content += '</tr><tr>' + cell(1, 1, "하단") + '</tr></tbl>'
        self.write(['<p><run>' + content + '</run></p>'])
        parsed = parse_hwpx(self.path)["tables"][0]
        self.assertEqual(len(parsed["cells"]), 3)
        self.assertEqual(parsed["grid"][0][0], parsed["grid"][1][0])

    def test_overlapping_cells_are_rejected(self):
        content = '<tbl rowCnt="1" colCnt="1"><tr>' + cell(0, 0, "a") + cell(0, 0, "b") + '</tr></tbl>'
        self.write(['<p><run>' + content + '</run></p>'])
        with self.assertRaisesRegex(ValueError, "overlapping"):
            parse_hwpx(self.path)

    def test_runner_builds_template_requests_and_freezes_source_without_v2_mapping(self):
        self.write([p("[예금성상품-유형]") + '<p><run>' + table() + '</run></p>'])
        root = Path(self.tmp.name)
        inputs = root / "inputs"
        inputs.mkdir()
        ad = integrated_input()
        ad["document"]["routing_metadata"] = {
            "product_group": {"value": "예금성", "status": "provided", "source": "intake"},
            "template_id": {"value": "예금성상품-유형", "status": "provided", "source": "intake"}}
        (inputs / "ad.json").write_text(json.dumps(ad), encoding="utf-8")
        coarse, fine = search_docs(ad)
        for name, rows in (("coarse", coarse), ("fine", fine)):
            (root / name).write_text(''.join(json.dumps(row)+'\n' for row in rows), encoding="utf-8")
        regulation = root / "v2.xlsx"
        regulation.write_bytes(b"synthetic workbook; loaders mocked")
        output = root / "run"
        args = ["runner", "--inputs-dir", str(inputs), "--coarse", str(root / "coarse"),
                "--fine", str(root / "fine"), "--regulation", str(regulation),
                "--template-hwpx", str(self.path), "--output-dir", str(output),
                "--es-index", "synthetic", "--vector-cache-dir", str(root / "cache")]

        def encoded(rows, **kwargs):
            return np.ones((len(rows), 2), dtype=np.float32), False, 0.0

        with mock.patch.object(sys, "argv", args), \
             mock.patch.object(runner.v2_source, "set_agent_path"), \
             mock.patch.object(runner.discovery, "load_scope", return_value=([], [])), \
             mock.patch.object(runner.judgment_input, "load_cd_rules", return_value=[]), \
             mock.patch.object(runner.discovery, "load_model"), \
             mock.patch.object(runner.discovery, "load_or_encode", side_effect=encoded), \
             mock.patch.object(runner.discovery, "ensure_rule_index"), \
             mock.patch.object(runner.discovery, "discover_prohibitions", return_value=[]):
            runner.main()
        requests = [json.loads(line) for line in (output / "02_judgment_requests.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(requests), 1)
        payload = json.loads(requests[0]["messages"][1]["content"])
        self.assertEqual(payload["rules"][0]["template_basis"]["basis_type"], "INTERNAL_TEMPLATE")
        freeze = json.loads((output / "FREEZE_BEFORE_PREDICTION.json").read_text(encoding="utf-8"))
        self.assertIn(str(self.path.resolve()), [entry["path"] for entry in freeze["inputs"]])
