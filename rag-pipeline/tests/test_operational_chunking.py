# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]

from rag.parsing.prepare_inputs import (  # noqa: E402
    BULLET_START,
    _fine_views,
    _is_table_region,
    _label_groups,
    page_source_roles,
    _selected_text_line_refs,
    compact,
    search_docs,
)
from rag.retrieval.context import expand_source_context  # noqa: E402


ASSET = "FILE-AAAA"


def line(index, text, *, top, bottom, left=260, right=520):
    return {
        "line_ref": f"{ASSET}::p1/p1_r004/L{index:03d}",
        "text": text,
        "bbox": [left, top, right, bottom],
        "text_source": "ocr",
        "confidence": 0.9,
        "style": None,
        "labels": [],
    }


def label(name, indexes):
    return {
        "label_id": f"예금성상품-적립식:{name}",
        "label": name,
        "spans": [{
            "line_refs": [f"p1/p1_r004/L{i:03d}" for i in indexes],
            "sources": ["semantic_vlm"],
            "confidence": 1.0,
        }],
    }


def region(lines, *, labels=None, layout="table"):
    text = "".join(row["text"] for row in lines)
    return {
        "evidence_id": f"AD#asset:{ASSET}:p1:p1_r004",
        "region_id": f"{ASSET}:p1_r004",
        "bbox": [250, 0, 900, 2000],
        "layout": {"label": layout, "score": 0.7},
        "final_text": text,
        "line_refs": [row["line_ref"] for row in lines],
        "lines": lines,
        "labels": labels or [],
    }


class SelectedTextAlignmentTests(unittest.TestCase):
    def search(self, source):
        source["assignment_status"] = "assigned"
        return search_docs({"document": {"ad_id": "AD", "source_file": "test.png", "routing_metadata": {}},
                            "pages": [{"page_no": 1, "regions": [source]}]})

    def test_selected_subset_keeps_per_chunk_spans_and_labels(self):
        source = self.make_region(["메뉴", "- 회사 안내", "- 비용 안내", "푸터"], "- 회사 안내\n- 비용 안내")
        source["lines"][0]["labels"] = [{"label": "상품명"}]
        source["lines"][1]["labels"] = [{"label": "회사명"}]
        source["lines"][2]["labels"] = [{"label": "부대비용"}]
        coarse, fine = self.search(source)
        self.assertEqual(fine[0]["line_refs"], source["line_refs"][1:2])
        self.assertEqual(fine[1]["line_refs"], source["line_refs"][2:3])
        self.assertEqual(fine[0]["labels"], [{"label": "회사명"}])
        self.assertEqual(fine[1]["labels"], [{"label": "부대비용"}])
        self.assertNotIn({"label": "상품명"}, coarse[0]["labels"])
        self.assertTrue(all(view["line_spans"] for view in fine))

    def test_parser_header_and_footer_roles_survive_search_projection(self):
        for layout, expected in [("header", "PAGE_CHROME"), ("footer", "PAGE_CHROME"),
                                 ("text", "ADVERTISEMENT_CONTENT")]:
            with self.subTest(layout=layout):
                source = self.make_region(["공통 또는 본문 문구"], "공통 또는 본문 문구")
                source["layout"] = {"label": layout, "score": 0.9}
                coarse, fine = self.search(source)
                self.assertEqual(coarse[0]["source_role"], expected)
                self.assertEqual(fine[0]["source_role"], expected)

    def test_edge_position_alone_never_demotes_advertisement_content(self):
        """A hero banner row is not navigation because it sits near an edge.

        Full-page web captures place the product name and the principal-loss
        notice inside the top fifth of the image. Only a parser layout label
        may assign page chrome, because that evidence is removed from
        body-rule retrieval.
        """
        banner = []
        for index, (left, text) in enumerate(
                ((100, "일임형ISA"), (350, "원금 비보장 상품"), (600, "일임형 ISA란?")), 1):
            item = self.make_region([text], text)
            item["region_id"] = f"banner-{index}"
            item["bbox"] = [left, 200, left + 140, 300]
            banner.append(item)
        menu = []
        for index, left in enumerate((100, 350, 600), 1):
            item = self.make_region([f"메뉴 {index}"], f"메뉴 {index}")
            item["region_id"] = f"menu-{index}"
            item["bbox"] = [left, 820, left + 140, 845]
            menu.append(item)
        footer = self.make_region(["하단 안내"], "하단 안내")
        footer["region_id"], footer["bbox"] = "footer", [100, 900, 300, 930]
        footer["layout"] = {"label": "footer", "score": 0.9}
        roles = page_source_roles({
            "canvas_w": 1000, "canvas_h": 1000,
            "regions": [*banner, *menu, footer],
        })
        for index in range(1, 4):
            self.assertEqual(roles[f"banner-{index}"][0], "ADVERTISEMENT_CONTENT")
            self.assertEqual(roles[f"menu-{index}"][0], "ADVERTISEMENT_CONTENT")
        self.assertEqual(roles["footer"], ("PAGE_CHROME", "parser_layout:footer"))

    def test_changed_text_and_duplicate_text_do_not_inherit_original_labels(self):
        for texts, selected in [(["금리 3%"], "금리 4%"), (["같은 문장", "같은 문장"], "같은 문장")]:
            source = self.make_region(texts, selected)
            source["lines"][0]["labels"] = [{"label": "대출금리"}]
            source["text_selection"] = {"needs_review": False}
            coarse, fine = self.search(source)
            for view in [*coarse, *fine]:
                self.assertEqual(view["labels"], [])
                self.assertTrue(view["text_selection"]["needs_review"])
                self.assertEqual(view["text_canonical"], selected)
            self.assertEqual(source["lines"][0]["text"], texts[0])

    def test_selected_table_subset_keeps_visual_rows(self):
        lines = [line(0, "메뉴", top=0, bottom=8),
                 line(1, "가입기간", top=20, bottom=28),
                 line(2, "6개월", top=20, bottom=28, left=540),
                 line(3, "가입금액", top=40, bottom=48),
                 line(4, "월 20만원", top=40, bottom=48, left=540)]
        source = region(lines)
        source["final_text"] = "가입기간 6개월\n가입금액 월 20만원"
        views = _fine_views(source)
        self.assertEqual(len(views), 2)
        self.assertEqual(views[0]["line_refs"], source["line_refs"][1:3])
        self.assertEqual(views[1]["line_refs"], source["line_refs"][3:5])
        self.assertTrue(all(v["line_spans"] for v in views))

    def test_one_corrected_part_does_not_hide_exact_other_chunk(self):
        source = self.make_region(["- 조건 안내", "- 금리 3%"], "- 조건 안내\n- 금리 4%")
        views = _fine_views(source)
        self.assertEqual(views[0]["span_status"], "selected_text_line_aligned")
        self.assertEqual(views[0]["line_refs"], source["line_refs"][:1])
        self.assertEqual(views[1]["span_status"], "region_level_selected_text")

    def test_confident_vlm_and_unique_ocr_line_agreement_is_locally_trusted(self):
        source = self.make_region(
            ["※ 원금손실은 투자자에게 귀속됩니다", "※ 다른 줄 오씨알 오류"],
            "※ 원금손실은 투자자에게 귀속됩니다.\n※ 다른 줄 OCR 오류",
        )
        source["text_selection"] = {
            "selection_status": "judge_selected_vlm_requires_review",
            "needs_review": True,
            "confidence": 1.0,
            "reason": "다른 줄 보정 확인 필요",
        }

        _, fine = self.search(source)

        first, second = fine
        self.assertEqual(first["line_refs"], source["line_refs"][:1])
        self.assertEqual(first["text_selection"]["selection_status"], "independent_line_agreement")
        self.assertFalse(first["text_selection"]["needs_review"])
        self.assertEqual(second["span_status"], "region_level_selected_text")
        self.assertTrue(second["text_selection"]["needs_review"])

    def test_explanation_duty_sentence_isolated_from_an_uncertain_neighbor(self):
        wording = (
            "※ 당행은 이 계좌에 관하여 충분히 설명할 의무가 있으며, 투자자는 투자에 앞서 "
            "상품 등에 대한 충분한 설명을 들으신 후 신중하게 투자결정을 내리시기 바랍니다"
        )
        source = self.make_region(
            [wording.replace(" ", ""), "※ 다른 줄 오씨알 오류"],
            f"{wording}.\n※ 다른 줄 OCR 오류",
        )
        source["text_selection"] = {
            "selection_status": "judge_selected_vlm_requires_review",
            "needs_review": True,
            "confidence": 1.0,
            "reason": "다른 줄 보정 확인 필요",
        }

        _, fine = self.search(source)

        explanation, uncertain = fine
        self.assertEqual(explanation["line_refs"], source["line_refs"][:1])
        self.assertEqual(
            explanation["text_selection"]["selection_status"],
            "independent_line_agreement",
        )
        self.assertFalse(explanation["text_selection"]["needs_review"])
        self.assertTrue(uncertain["text_selection"]["needs_review"])

    def test_line_agreement_does_not_clear_low_confidence_or_ambiguous_text(self):
        for confidence, texts in ((0.9, ["같은 문장"]), (1.0, ["같은 문장", "같은 문장"])):
            with self.subTest(confidence=confidence, texts=texts):
                source = self.make_region(texts, "같은 문장.")
                source["text_selection"] = {
                    "selection_status": "judge_selected_vlm_requires_review",
                    "needs_review": True,
                    "confidence": confidence,
                }
                _, fine = self.search(source)
                self.assertTrue(fine[0]["text_selection"]["needs_review"])

    def make_region(self, texts, selected):
        result = region([line(i, text, top=i * 10, bottom=i * 10 + 8)
                         for i, text in enumerate(texts)], layout="text")
        result["final_text"] = selected
        return result

    def test_unique_full_line_alignment_keeps_exact_source_refs(self):
        source = self.make_region(["메뉴", "필수 문구", "관련 조건", "푸터"], "필수문구 관련조건")
        self.assertEqual(_selected_text_line_refs(source), source["line_refs"][1:3])

    def test_repeated_text_is_not_assigned_to_first_identical_line(self):
        source = self.make_region(["동일 안내", "다른 조건", "동일 안내"], "동일 안내")
        self.assertIsNone(_selected_text_line_refs(source))
        self.assertEqual(_fine_views(source)[0]["span_status"], "region_level_selected_text")

    def test_alternative_line_segmentations_are_ambiguous(self):
        self.assertIsNone(_selected_text_line_refs(self.make_region(["A", "AB", "B"], "AB")))

    def test_changed_number_and_partial_source_line_are_not_exact(self):
        for source in (self.make_region(["금리 3%"], "금리 4%"),
                       self.make_region(["기본 안내와 조건"], "기본 안내")):
            self.assertIsNone(_selected_text_line_refs(source))


class SourceContextTests(unittest.TestCase):
    def linked_rows(self):
        rows = self.rows()
        for i, row in enumerate(rows):
            row['line_refs'] = [f'L{i}']
        rows[3].update(page_no=2, parent_doc_id='footnote-region')
        rows[2]['source_relations'] = [{'type': 'footnote_for', 'status': 'observed',
            'from_line_ids': ['L3'], 'to_line_ids': ['L2']}]
        return rows

    def test_explicit_observed_footnote_across_pages_is_included(self):
        selected, audit = expand_source_context(['2'], self.linked_rows())
        self.assertIn('3', selected)
        self.assertIn('3', audit['relation_added_ids'])

    def test_relation_must_not_cross_product_or_ad(self):
        for key in ('ad_id', 'product_id'):
            rows = self.linked_rows()
            rows[3][key] = 'other'
            selected, audit = expand_source_context(['2'], rows)
            self.assertNotIn('3', selected)
            self.assertEqual(audit['deferred_groups'][-1]['reason'], 'relation_target_missing_or_outside_scope')

    def test_inferred_relation_and_missing_target_are_deferred(self):
        for mutation in ('inferred', 'missing'):
            rows = self.linked_rows()
            relation = rows[2]['source_relations'][0]
            if mutation == 'inferred':
                relation['status'] = 'inferred'
            else:
                relation['from_line_ids'] = ['unknown-line']
            selected, audit = expand_source_context(['2'], rows)
            self.assertNotIn('3', selected)
            self.assertTrue(audit['deferred_groups'])

    def test_explicit_relation_budget_preserves_seed_and_defers_whole_target(self):
        selected, audit = expand_source_context(['2'], self.linked_rows(), char_budget=1)
        self.assertEqual(selected, ['2'])
        self.assertTrue(any(group['reason'] == 'source_relation_budget' for group in audit['deferred_groups']))

    def rows(self):
        return [{"doc_id": str(i), "ad_id": "ad", "product_id": "product",
                 "page_no": 1, "source_file": "file", "parent_doc_id": "region",
                 "text_canonical": text} for i, text in enumerate([
                     "조건 충족 시 우대", "구분 / 금리", "우대금리 1%", "※ 적용 제외 조건"])]

    def test_condition_header_value_and_footnote_retrieved_together(self):
        selected, audit = expand_source_context(["2"], self.rows())
        self.assertEqual(set(selected), {"0", "1", "2", "3"})
        self.assertEqual(selected[0], "2")
        self.assertFalse(audit["semantic_dependencies_complete"])

    def test_never_crosses_ad_product_file_or_page(self):
        for key in ("ad_id", "product_id", "source_file", "page_no"):
            rows = self.rows()
            rows[0][key] = "other"
            self.assertNotIn("0", expand_source_context(["2"], rows)[0])

    def test_budget_defers_whole_group_without_losing_trigger(self):
        selected, audit = expand_source_context(["2"], self.rows(), char_budget=1)
        self.assertEqual(selected, ["2"])
        self.assertEqual(set(audit["deferred_groups"][0]["evidence_ids"]), {"0", "1", "3"})

    def test_no_semantic_link_inferred_across_regions(self):
        rows = self.rows()
        rows[3]["parent_doc_id"] = "different_region"
        self.assertNotIn("3", expand_source_context(["2"], rows)[0])


class ChainedSourceRelationTests(unittest.TestCase):
    """Observed condition/footnote chains keep source scope and budget boundaries."""

    def rows(self):
        rows = [
            {"doc_id": name, "ad_id": "ad", "product_id": "product",
             "source_file": "source.pdf", "page_no": i + 1,
             "parent_doc_id": f"region-{name}", "line_refs": [name],
             "text_canonical": name * 4}
            for i, name in enumerate(("a", "b", "c"))
        ]
        rows[0]["source_relations"] = [
            {"type": "condition_context", "status": "observed",
             "from_line_ids": ["a"], "to_line_ids": ["b"]}]
        rows[1]["source_relations"] = [
            {"type": "footnote_for", "status": "observed",
             "from_line_ids": ["b"], "to_line_ids": ["c"]}]
        return rows

    def test_observed_two_step_chain_includes_terminal_footnote(self):
        selected, audit = expand_source_context(["a"], self.rows())
        self.assertEqual(selected, ["a", "b", "c"])
        self.assertEqual(audit["relation_added_ids"], ["b", "c"])
        self.assertEqual(audit["added_chars"], 8)
        self.assertFalse(audit["semantic_dependencies_complete"])

    def test_second_step_over_budget_is_explicitly_deferred(self):
        selected, audit = expand_source_context(["a"], self.rows(), char_budget=4)
        self.assertEqual(selected, ["a", "b"])
        self.assertEqual(audit["deferred_groups"][0]["reason"], "source_relation_budget")
        self.assertEqual(audit["deferred_groups"][0]["evidence_ids"], ["c"])

    def test_exact_budget_and_zero_budget(self):
        self.assertEqual(expand_source_context(["a"], self.rows(), char_budget=8)[0], ["a", "b", "c"])
        self.assertEqual(expand_source_context(["a"], self.rows(), char_budget=0)[0], ["a"])

    def test_second_step_inferred_link_is_not_followed(self):
        rows = self.rows()
        rows[1]["source_relations"][0]["status"] = "inferred"
        selected, audit = expand_source_context(["a"], rows)
        self.assertEqual(selected, ["a", "b"])
        self.assertEqual(audit["deferred_groups"][0]["reason"], "unverified_source_relation")

    def test_second_step_cannot_cross_advertisement_or_product(self):
        for field in ("ad_id", "product_id"):
            with self.subTest(field=field):
                rows = self.rows()
                rows[2][field] = "other"
                selected, audit = expand_source_context(["a"], rows)
                self.assertEqual(selected, ["a", "b"])
                self.assertEqual(audit["deferred_groups"][0]["reason"], "relation_target_missing_or_outside_scope")

    def test_cycle_finishes_without_duplicate_or_double_charge(self):
        rows = self.rows()
        rows[2]["source_relations"] = [
            {"type": "continuation_of", "status": "observed",
             "from_line_ids": ["c"], "to_line_ids": ["a"]}]
        selected, audit = expand_source_context(["a"], rows)
        self.assertEqual(selected, ["a", "b", "c"])
        self.assertEqual(audit["added_chars"], 8)

    def test_unrelated_metadata_does_not_consume_relation_before_valid_seed(self):
        rows = self.rows()
        rows[0]["source_relations"].insert(0, dict(rows[1]["source_relations"][0]))
        self.assertEqual(expand_source_context(["a"], rows)[0], ["a", "b", "c"])


class BulletBoundaryTests(unittest.TestCase):
    """소수와 날짜는 번호 매기기 말머리가 아니다."""

    def test_decimal_values_are_not_bullets(self):
        for value in ("1.0", "0.7", "3.0%p", "2026.6.22."):
            self.assertIsNone(BULLET_START.match(value), value)

    def test_real_ordered_markers_still_split(self):
        for value in ("1. 첫째", "2) 둘째", "① 항목", "※ 항목", "- 항목"):
            self.assertIsNotNone(BULLET_START.match(value), value)

    def test_middle_dot_is_not_a_bullet(self):
        """가운뎃점은 표에서 값의 일부로 쓰여 말머리로 보지 않는다."""
        self.assertIsNone(BULLET_START.match("·최대연3.0%p"))


class TableRowTests(unittest.TestCase):
    """표는 라벨 셀과 값 셀이 한 청크에 있어야 한다."""

    def setUp(self):
        self.lines = [
            line(21, "우대금리", top=1012, bottom=1031, left=267, right=313),
            line(22, "·최대연3.0%p", top=1014, bottom=1032, left=380, right=610),
            line(25, "①[소득]급여이체", top=1084, bottom=1098, left=391, right=792),
            line(26, "1.0", top=1082, bottom=1099, left=874, right=897),
            line(27, "②[카드]이용실적", top=1110, bottom=1129, left=388, right=759),
            line(28, "0.7", top=1111, bottom=1130, left=874, right=898),
        ]

    def test_row_values_stay_with_their_condition(self):
        views = _fine_views(region(self.lines))
        self.assertEqual(len(views), 1)
        text = views[0]["text_canonical"]
        for value in ("3.0%p", "1.0", "0.7", "①[소득]급여이체", "②[카드]이용실적"):
            self.assertIn(value, text)

    def test_no_characters_are_lost(self):
        reg = region(self.lines)
        views = _fine_views(reg)
        self.assertEqual(
            compact("".join(view["text_canonical"] for view in views)),
            compact(reg["final_text"]),
        )


class LabelBoundaryTests(unittest.TestCase):
    """파서 라벨이 항목 경계를 정하고, 없으면 좌표로 돌아간다."""

    def setUp(self):
        self.lines = [
            line(13, "가입기간", top=860, bottom=880, left=264, right=315),
            line(14, "36개월", top=861, bottom=879, left=378, right=424),
            line(21, "우대금리", top=1012, bottom=1031, left=267, right=313),
            line(22, "·최대연3.0%p", top=1014, bottom=1032, left=380, right=610),
            line(23, "주1) 급여이체 기준 준용", top=1050, bottom=1068, left=383, right=726),
        ]

    def test_label_change_starts_a_new_chunk(self):
        reg = region(self.lines, labels=[
            label("가입기간", [13, 14]),
            label("우대금리", [21, 22]),
        ])
        views = _fine_views(reg)
        self.assertEqual(len(views), 2)
        self.assertIn("36개월", views[0]["text_canonical"])
        self.assertIn("최대연3.0%p", views[1]["text_canonical"])

    def test_asset_namespaced_labels_preserve_same_chunk_boundaries(self):
        from rag.parsing.source_structure import namespace_structure
        labels = [label("가입기간", [13, 14]), label("우대금리", [21, 22])]
        original = _fine_views(region(self.lines, labels=labels))
        merged = _fine_views(region(self.lines, labels=namespace_structure(labels, ASSET)))
        self.assertEqual([v["text_canonical"] for v in merged],
                         [v["text_canonical"] for v in original])
        self.assertEqual([v["line_refs"] for v in merged], [v["line_refs"] for v in original])
        self.assertEqual(len(merged), 2)

    def test_labels_from_another_asset_never_match_by_suffix(self):
        from rag.parsing.source_structure import namespace_structure
        rows = [[part] for part in self.lines]
        labels = namespace_structure([label("가입기간", [13, 14]), label("우대금리", [21, 22])], "OTHER")
        self.assertIsNone(_label_groups(rows, region=region(self.lines, labels=labels)))

    def test_ambiguous_legacy_suffix_is_not_assigned(self):
        import copy
        lines = copy.deepcopy(self.lines)
        lines.extend([{**part, "line_ref": part["line_ref"].replace(ASSET, "OTHER")} for part in self.lines])
        labels = [label("가입기간", [13, 14]), label("우대금리", [21, 22])]
        self.assertIsNone(_label_groups([[part] for part in lines], region=region(lines, labels=labels)))

    def test_unlabeled_rows_attach_to_the_preceding_item(self):
        """주석은 앞 항목에 딸린 내용이므로 떨어져 나가지 않는다."""
        reg = region(self.lines, labels=[
            label("가입기간", [13, 14]),
            label("우대금리", [21, 22]),
        ])
        views = _fine_views(reg)
        self.assertIn("주1) 급여이체 기준 준용", views[-1]["text_canonical"])

    def test_single_label_falls_back_to_coordinates(self):
        """라벨이 한 종류뿐이면 경계 정보가 없으므로 좌표 방식을 쓴다."""
        rows = [[line(13, "가입기간", top=860, bottom=880)]]
        self.assertIsNone(
            _label_groups(rows, region=region(self.lines, labels=[label("가입기간", [13])]))
        )

    def test_labels_are_ignored_outside_table_regions(self):
        """이미지 영역은 항목이 가로로 배치돼 라벨이 교대로 나타난다."""
        reg = region(self.lines, labels=[
            label("가입기간", [13, 14]),
            label("우대금리", [21, 22]),
        ], layout="image")
        self.assertFalse(_is_table_region(reg))
        self.assertEqual(len(_fine_views(reg)), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
