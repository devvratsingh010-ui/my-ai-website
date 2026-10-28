"""Unit tests for Structured Bill Parser across all 4 supported languages."""

import unittest
from app.ocr.test_fixtures import FIXTURES
from app.parser.bill_parser import BillParser
from app.parser.product_catalog import ProductCatalogMatcher

# Sample shop product aliases
SAMPLE_ALIASES = [
    {"standard_name": "Sugar", "alias_name": "चीनी", "language_code": "hi"},
    {"standard_name": "Sugar", "alias_name": "ಸಕ್ಕರೆ", "language_code": "kn"},
    {"standard_name": "Sugar", "alias_name": "చక్కెర", "language_code": "te"},
    {"standard_name": "Basmati Rice", "alias_name": "चावल", "language_code": "hi"},
    {"standard_name": "Rice", "alias_name": "ಅಕ್ಕಿ", "language_code": "kn"},
    {"standard_name": "Rice", "alias_name": "బియ్యం", "language_code": "te"},
    {"standard_name": "Cooking Oil", "alias_name": "सरसों तेल", "language_code": "hi"},
    {"standard_name": "Cooking Oil", "alias_name": "ಎಣ್ಣೆ", "language_code": "kn"},
    {"standard_name": "Cooking Oil", "alias_name": "నూనె", "language_code": "te"},
]


class TestBillParser(unittest.TestCase):
    """Test parsing kachha bills in English, Hindi, Kannada, Telugu, and edge cases."""

    def setUp(self):
        matcher = ProductCatalogMatcher(SAMPLE_ALIASES)
        self.parser = BillParser(matcher)

    def test_parse_hindi_kachha_bill(self):
        """Parse Hindi handwritten kachha bill."""
        fixture = FIXTURES["sample_hi_kachha"]
        bill = self.parser.parse(fixture["fixture_text"])

        self.assertEqual(bill["bill_number"], "104")
        self.assertEqual(bill["bill_date"], "2026-10-25")
        self.assertEqual(bill["grand_total"], 713.0)
        self.assertEqual(len(bill["items"]), 5)

        # Check item 1: चीनी 2 kg 44 = 88
        item1 = bill["items"][0]
        # Must preserve original script!
        self.assertEqual(item1["item_name_original"], "चीनी")
        # Standardized name mapped separately
        self.assertEqual(item1["item_name_standard"], "Sugar")
        self.assertEqual(item1["quantity"], 2.0)
        self.assertEqual(item1["unit"], "kg")
        self.assertEqual(item1["unit_price"], 44.0)
        self.assertEqual(item1["line_total"], 88.0)

        # Check item 2: सरसों तेल 1 ltr 155 = 155
        item2 = bill["items"][1]
        self.assertEqual(item2["item_name_original"], "सरसों तेल")
        self.assertEqual(item2["item_name_standard"], "Cooking Oil")
        self.assertEqual(item2["quantity"], 1.0)
        self.assertEqual(item2["unit"], "ltr")
        self.assertEqual(item2["line_total"], 155.0)

    def test_parse_kannada_bill(self):
        """Parse Kannada bill preserving Kannada script."""
        fixture = FIXTURES["sample_kn_kachha"]
        bill = self.parser.parse(fixture["fixture_text"])

        self.assertEqual(bill["bill_number"], "85")
        self.assertEqual(bill["bill_date"], "2026-10-24")
        self.assertEqual(bill["grand_total"], 570.0)
        self.assertEqual(len(bill["items"]), 4)

        # Item 1: ಸಕ್ಕರೆ 2 kg 44 = 88
        item1 = bill["items"][0]
        self.assertEqual(item1["item_name_original"], "ಸಕ್ಕರೆ")
        self.assertEqual(item1["item_name_standard"], "Sugar")
        self.assertEqual(item1["quantity"], 2.0)
        self.assertEqual(item1["unit"], "kg")
        self.assertEqual(item1["line_total"], 88.0)

        # Item 2: ಅಕ್ಕಿ 5 kg 60 = 300
        item2 = bill["items"][1]
        self.assertEqual(item2["item_name_original"], "ಅಕ್ಕಿ")
        self.assertEqual(item2["item_name_standard"], "Rice")
        self.assertEqual(item2["quantity"], 5.0)

    def test_parse_telugu_bill(self):
        """Parse Telugu bill preserving Telugu script."""
        fixture = FIXTURES["sample_te_kachha"]
        bill = self.parser.parse(fixture["fixture_text"])

        self.assertEqual(bill["bill_number"], "210")
        self.assertEqual(bill["bill_date"], "2026-10-26")
        self.assertEqual(bill["grand_total"], 602.0)
        self.assertEqual(len(bill["items"]), 4)

        # Item 1: చక్కెర 2 kg 44 = 88
        item1 = bill["items"][0]
        self.assertEqual(item1["item_name_original"], "చక్కెర")
        self.assertEqual(item1["item_name_standard"], "Sugar")
        self.assertEqual(item1["quantity"], 2.0)
        self.assertEqual(item1["unit"], "kg")

        # Item 3: నూనె 1 ltr 150 = 150
        item3 = bill["items"][2]
        self.assertEqual(item3["item_name_original"], "నూనె")
        self.assertEqual(item3["item_name_standard"], "Cooking Oil")

    def test_parse_printed_english_bill(self):
        """Parse printed English bill with subtotal, discount, and grand total."""
        fixture = FIXTURES["sample_en_printed"]
        bill = self.parser.parse(fixture["fixture_text"])

        self.assertEqual(bill["bill_number"], "4502")
        self.assertEqual(bill["bill_date"], "2026-10-27")
        self.assertEqual(bill["subtotal"], 877.0)
        self.assertEqual(bill["discount"], 27.0)
        self.assertEqual(bill["grand_total"], 850.0)
        self.assertEqual(len(bill["items"]), 4)

    def test_arithmetic_mismatch_flagged(self):
        """Flag arithmetic discrepancies without silently modifying values."""
        fixture = FIXTURES["sample_math_mismatch"]
        bill = self.parser.parse(fixture["fixture_text"])

        self.assertTrue(bill["needs_review"])
        # Should flag that Sugar line total (120) differs from 2 x 50 = 100
        sugar_item = [it for it in bill["items"] if "Sugar" in it["item_name_original"]][0]
        self.assertTrue(sugar_item["needs_review"])
        self.assertIn("Arithmetic mismatch", sugar_item["review_reason"])
        # Values preserved, not silently altered
        self.assertEqual(sugar_item["quantity"], 2.0)
        self.assertEqual(sugar_item["unit_price"], 50.0)
        self.assertEqual(sugar_item["line_total"], 120.0)

    def test_missing_prices_flagged(self):
        """Lines with missing prices must be flagged for review, not invented."""
        text = "Date: 25/10/2026\n1. Basmati Rice 5 kg\nTotal: 300"
        bill = self.parser.parse(text)

        item = bill["items"][0]
        self.assertEqual(item["item_name_original"], "Basmati Rice")
        self.assertEqual(item["quantity"], 5.0)
        self.assertIsNone(item["unit_price"])
        self.assertTrue(item["needs_review"])


if __name__ == "__main__":
    unittest.main()
