# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import json
import tempfile
import unittest

import collect_safety as CS


class IsCollapseTests(unittest.TestCase):
    def test_first_collection_always_allowed(self):
        self.assertFalse(CS.is_collapse(None, 0))
        self.assertFalse(CS.is_collapse(None, 50))

    def test_small_baseline_not_treated_as_collapse(self):
        # 원래 2~3개뿐인 규정은 1개만 줄어도 비율로는 급감처럼 보인다 — 무시해야 한다
        self.assertFalse(CS.is_collapse(2, 1))
        self.assertFalse(CS.is_collapse(3, 0))

    def test_drop_to_zero_always_blocked(self):
        # 실측 사례: 금투협 규정 개정 후 첨부 50개 → 0개
        self.assertTrue(CS.is_collapse(50, 0))
        self.assertTrue(CS.is_collapse(4, 0))

    def test_drop_below_half_blocked(self):
        self.assertTrue(CS.is_collapse(50, 20))
        self.assertTrue(CS.is_collapse(50, 24))

    def test_drop_above_half_allowed(self):
        self.assertFalse(CS.is_collapse(50, 26))
        self.assertFalse(CS.is_collapse(50, 49))

    def test_increase_allowed(self):
        self.assertFalse(CS.is_collapse(50, 93))


class LoadOldCountTests(unittest.TestCase):
    def test_missing_file_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(CS.load_old_count(d, "없는규정", "별표"))

    def test_reads_list_length(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "규정.json")
            json.dump({"별표": [1, 2, 3]}, open(p, "w", encoding="utf-8"))
            self.assertEqual(CS.load_old_count(d, "규정", "별표"), 3)

    def test_reads_string_length(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "규정.json")
            json.dump({"본문": "가나다라마"}, open(p, "w", encoding="utf-8"))
            self.assertEqual(CS.load_old_count(d, "규정", "본문"), 5)

    def test_corrupt_json_treated_as_no_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "규정.json")
            open(p, "w", encoding="utf-8").write("{안깨진 json 아님")
            self.assertIsNone(CS.load_old_count(d, "규정", "별표"))


class CheckAndMaybeBlockTests(unittest.TestCase):
    def test_blocks_and_preserves_existing_file(self):
        """실측 사례 재현: 첨부 50개짜리 기존 파일이 있는 상태에서, 새로 수집한
        결과가 0개면 저장을 막고 기존 파일은 그대로 남아야 한다."""
        with tempfile.TemporaryDirectory() as d:
            old_path = os.path.join(d, "규정.json")
            old_record = {"별표": list(range(50)), "표시": "기존 데이터"}
            json.dump(old_record, open(old_path, "w", encoding="utf-8"))

            new_record = {"별표": [], "표시": "새 데이터(비어있음)"}
            ok, reason = CS.check_and_maybe_block(
                d, "규정", "별표", 0, new_record, "새 본문", verbose=False)

            self.assertFalse(ok)
            self.assertIn("50", reason)
            self.assertIn("0", reason)

            # 기존 output/규정.json 은 손대지 않았어야 한다
            untouched = json.load(open(old_path, encoding="utf-8"))
            self.assertEqual(untouched, old_record)

            # 검토용 사본은 _quarantine/ 에 남는다
            qpath = os.path.join(d, "_quarantine", "규정.json")
            self.assertTrue(os.path.exists(qpath))
            saved = json.load(open(qpath, encoding="utf-8"))
            self.assertEqual(saved["레코드"], new_record)
            self.assertIn("사유", saved)

    def test_allows_normal_update(self):
        with tempfile.TemporaryDirectory() as d:
            old_path = os.path.join(d, "규정.json")
            json.dump({"별표": list(range(50))}, open(old_path, "w", encoding="utf-8"))

            new_record = {"별표": list(range(51))}
            ok, reason = CS.check_and_maybe_block(
                d, "규정", "별표", 51, new_record, "본문", verbose=False)

            self.assertTrue(ok)
            self.assertIsNone(reason)
            # 정상 통과는 quarantine 파일을 만들지 않는다
            self.assertFalse(os.path.exists(os.path.join(d, "_quarantine", "규정.json")))

    def test_first_collection_allowed_even_with_zero(self):
        with tempfile.TemporaryDirectory() as d:
            ok, reason = CS.check_and_maybe_block(
                d, "신규규정", "별표", 0, {"별표": []}, "본문", verbose=False)
            self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
