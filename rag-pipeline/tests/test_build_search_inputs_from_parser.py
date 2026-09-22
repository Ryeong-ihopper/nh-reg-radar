from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.build_search_inputs_from_parser import confirmed_routing, pair_parser_outputs


class BuildSearchInputsFromParserTests(unittest.TestCase):
    def test_confirmed_routing_replaces_parser_inference_for_audit(self):
        document = {
            "document": {
                "routing_metadata": {
                    "product_group": {
                        "value": "투자성",
                        "source": "parser_classification",
                        "status": "inferred",
                    }
                }
            }
        }
        confirmed_routing(
            document,
            product_group="예금성",
            product_subtype="예금성상품-입출식",
            media_type="WEB_PRODUCT_PAGE",
        )
        routing = document["document"]["routing_metadata"]
        self.assertEqual("예금성", routing["product_group"]["value"])
        self.assertEqual("provided", routing["product_group"]["status"])
        self.assertEqual("예금성상품-입출식", routing["template_id"]["value"])
        self.assertEqual("verified", routing["template_id"]["status"])
        self.assertEqual("WEB_PRODUCT_PAGE", routing["media_type"]["value"])

    def test_unknown_mixed_media_does_not_become_confirmed(self):
        document = {"document": {"routing_metadata": {}}}
        confirmed_routing(
            document,
            product_group="투자성",
            product_subtype="투자성상품-퇴직연금 일반",
            media_type=None,
        )
        self.assertNotIn("media_type", document["document"]["routing_metadata"])

    def test_v3_v6_outputs_pair_in_one_final_directory(self):
        with TemporaryDirectory() as temporary:
            final = Path(temporary)
            (final / "광고_A.p1.json").write_text("{}", encoding="utf-8")
            (final / "광고_A.p3.json").write_text("{}", encoding="utf-8")
            pairs = pair_parser_outputs(final, final)
        self.assertEqual(["광고_A"], [row[0] for row in pairs])
        self.assertEqual("광고_A.p1.json", pairs[0][1].name)
        self.assertEqual("광고_A.p3.json", pairs[0][2].name)

    def test_legacy_same_name_directories_remain_supported(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            p1, p3 = root / "p1", root / "p3"
            p1.mkdir()
            p3.mkdir()
            (p1 / "광고.json").write_text("{}", encoding="utf-8")
            (p3 / "광고.json").write_text("{}", encoding="utf-8")
            pairs = pair_parser_outputs(p1, p3)
        self.assertEqual(["광고"], [row[0] for row in pairs])


if __name__ == "__main__":
    unittest.main()
