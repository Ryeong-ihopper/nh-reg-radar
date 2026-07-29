# -*- coding: utf-8 -*-
import unittest
from unittest import mock
import http.client
import os
import ssl
import tempfile

import kofia_scraper
import kfb_scraper
import law_scraper
from content_hash import sha256_structure


class ContentHashTests(unittest.TestCase):
    def test_whitespace_changes_are_detected(self):
        self.assertNotEqual(
            sha256_structure({"조문": ["가  나"]}),
            sha256_structure({"조문": ["가\n나"]}),
        )

    def test_parenthesis_whitespace_changes_are_detected(self):
        self.assertNotEqual(
            sha256_structure({"조문": ["( a ) Nutrition information"]}),
            sha256_structure({"조문": ["(a) Nutrition information"]}),
        )

    def test_semantic_changes_are_detected(self):
        self.assertNotEqual(
            sha256_structure({"조문": ["기존 내용"]}),
            sha256_structure({"조문": ["변경 내용"]}),
        )

    def test_law_hash_uses_parsed_content(self):
        body_a = {
            "조문": {"조문단위": {
                "조문여부": "조문", "조문번호": "1",
                "조문내용": "제1조  목적",
            }}
        }
        body_b = {
            "조문": {"조문단위": {
                "조문여부": "조문", "조문번호": "1",
                "조문내용": "제1조\n목적",
            }}
        }
        body_c = {
            "조문": {"조문단위": {
                "조문여부": "조문", "조문번호": "1",
                "조문내용": "제1조 변경",
            }}
        }
        self.assertNotEqual(
            law_scraper._body_content_hash(body_a, "law"),
            law_scraper._body_content_hash(body_b, "law"),
        )
        self.assertNotEqual(
            law_scraper._body_content_hash(body_a, "law"),
            law_scraper._body_content_hash(body_c, "law"),
        )

    def test_kofia_parser_content_can_be_hashed(self):
        html = """
        <div class="JO">
          <div class="article"><table><td>제1조(목적)</td></table></div>
          <div class="hang">① 내용</div>
        </div>
        <div class="addenda">부칙 (2026. 1. 2.)</div><p>시행</p>
        """
        articles, addenda, last_date = kofia_scraper._parse_body(html)
        self.assertEqual(last_date, "20260102")
        self.assertTrue(articles)
        self.assertTrue(
            sha256_structure({"조문": articles, "부칙": addenda})
        )

    def test_kofia_get_retries_incomplete_response(self):
        full = "<html><body>정상</body></html>"
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.side_effect = [
            http.client.IncompleteRead(b"partial"),
            full.encode("utf-8"),
        ]
        with mock.patch("kofia_scraper.urllib.request.urlopen", return_value=response):
            with mock.patch("kofia_scraper.time.sleep"):
                self.assertEqual(kofia_scraper._get("https://example.test"), full)

    def test_kofia_get_retries_when_body_is_cut_off(self):
        """서버가 정상 종료로 끊어도 문서 끝이 없으면 다시 받아야 한다.
        (잘린 본문을 그대로 파싱하면 뒤쪽 조문이 통째로 '삭제'로 오탐된다)"""
        full = "<html><body>전체 조문</body></html>"
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.side_effect = [
            "<html><body>앞부분만".encode("utf-8"),   # </html> 없음 → 잘린 응답
            full.encode("utf-8"),
        ]
        with mock.patch("kofia_scraper.urllib.request.urlopen", return_value=response):
            with mock.patch("kofia_scraper.time.sleep"):
                self.assertEqual(kofia_scraper._get("https://example.test"), full)

    def test_kofia_history_accepts_partial_response(self):
        """연혁 목록은 개정본 번호만 뽑으므로 잘려도 받은 만큼 쓴다."""
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.side_effect = http.client.IncompleteRead(
            b"historySeq=1798 historySeq=1790")
        with mock.patch("kofia_scraper.urllib.request.urlopen", return_value=response):
            self.assertEqual(kofia_scraper.history("136"), ["1798", "1790"])

    def test_law_default_meta_check_does_not_fetch_body(self):
        item = {
            "법령명한글": "테스트법",
            "법령일련번호": "1",
            "법령ID": "2",
            "시행일자": "20260101",
            "공포번호": "3",
        }
        with mock.patch("law_scraper._match", return_value=item):
            with mock.patch("law_scraper.fetch_body") as fetch_body:
                meta = law_scraper.current_meta("테스트법", "law")
        fetch_body.assert_not_called()
        self.assertNotIn("content_hash", meta)

    def test_kofia_default_meta_check_does_not_fetch_body(self):
        with mock.patch(
            "kofia_scraper._find_in_tree",
            return_value=("테스트규정", "10", "20"),
        ):
            with mock.patch("kofia_scraper._get") as get:
                meta = kofia_scraper.current_meta("테스트규정")
        get.assert_not_called()
        self.assertNotIn("content_hash", meta)

    def test_law_download_names_distinguish_table_and_form(self):
        tables = [
            {"구분": "별표", "별표번호": "0001", "별표가지번호": "00",
             "PDF링크": ["https://example.test/a"], "HWP링크": [],
             "PDF파일명": "", "HWP파일명": ""},
            {"구분": "별지", "별표번호": "0001", "별표가지번호": "00",
             "PDF링크": ["https://example.test/b"], "HWP링크": [],
             "PDF파일명": "", "HWP파일명": ""},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(law_scraper, "FILE_DIR", tmp):
                with mock.patch("law_scraper._get", return_value=b"data"):
                    count = law_scraper.download_files(tables, [], "테스트")
            names = sorted(os.listdir(os.path.join(tmp, "테스트")))
        self.assertEqual(count, 2)
        self.assertEqual(names, ["별지0001.pdf", "별표0001.pdf"])

    def test_kfb_get_retries_ssl_error(self):
        opener = mock.MagicMock()
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"ok"
        response.headers = {}
        opener.open.side_effect = [ssl.SSLError("temporary"), response]
        with mock.patch("kfb_scraper.time.sleep"):
            data, _ = kfb_scraper._get(opener, "https://example.test")
        self.assertEqual(data, b"ok")


if __name__ == "__main__":
    unittest.main()
