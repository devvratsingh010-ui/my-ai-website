"""End-to-End workflow tests: upload/scan -> parse -> verify -> confirm & save -> dashboard update."""

import json
import tempfile
import unittest
from pathlib import Path
from app.auth import hash_password
from app.database import ShopRLS, close_db_connection, get_db_connection, init_db
from app.language.detector import detect_language
from app.ocr.preprocessor import preprocess_bill_image, validate_image_file
from app.ocr.test_fixtures import FIXTURES, get_test_fixture
from app.parser.bill_parser import BillParser
from app.parser.product_catalog import ProductCatalogMatcher
from app.sales.dashboard import SalesDashboard


class TestEndToEndWorkflow(unittest.TestCase):
    """Test full flow: bill scan -> structured parse -> verify -> save -> sales dashboard."""

    def setUp(self):
        close_db_connection()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "e2e_hisab.db"
        init_db(self.db_path)

        conn = get_db_connection(self.db_path)
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO shops (id, name, business_category, owner_name) VALUES (?, ?, ?, ?)",
                ("shop_kirana", "Shree Ganesh Kirana", "kirana", "Ramesh Gupta"),
            )
            conn.execute(
                "INSERT OR IGNORE INTO users (id, shop_id, username, password_hash, full_name) VALUES (?, ?, ?, ?, ?)",
                ("user_ramesh", "shop_kirana", "ramesh", hash_password("kirana123"), "Ramesh Gupta"),
            )
            # Add product alias for Hindi
            conn.execute(
                "INSERT OR IGNORE INTO product_aliases (id, shop_id, standard_name, alias_name, language_code) VALUES (?, ?, ?, ?, ?)",
                ("al_1", "shop_kirana", "Sugar", "चीनी", "hi"),
            )

        self.rls = ShopRLS("shop_kirana", conn)
        self.dashboard = SalesDashboard("shop_kirana", conn)

    def tearDown(self):
        close_db_connection()
        self.temp_dir.cleanup()

    def test_complete_hindi_bill_workflow(self):
        """End-to-end test with Hindi kachha bill:
        1. Process bill image
        2. Recognize text & detect language
        3. Parse into structured items
        4. Edit/correct field in verification step
        5. Confirm & save
        6. Verify dashboard metrics
        """
        # Step 1: Image Processing
        fixture = get_test_fixture("sample_hi_kachha")
        self.assertIsNotNone(fixture)
        validate_image_file(fixture["bytes"], fixture["filename"])
        processed_bytes, img_meta = preprocess_bill_image(fixture["bytes"])
        self.assertFalse(img_meta["quality"]["is_blurry"])

        # Step 2: Language Detection
        raw_text = fixture["fixture_text"]
        lang_res = detect_language(raw_text)
        self.assertEqual(lang_res["primary_language"], "hi")
        self.assertTrue(lang_res["is_supported"])

        # Step 3: Structured Bill Parsing
        matcher = ProductCatalogMatcher(self.rls.get_product_aliases())
        parser = BillParser(matcher)
        bill = parser.parse(raw_text)

        self.assertEqual(bill["bill_number"], "104")
        self.assertEqual(bill["bill_date"], "2026-10-25")
        self.assertEqual(len(bill["items"]), 5)

        # Verify original script is preserved
        self.assertEqual(bill["items"][0]["item_name_original"], "चीनी")
        self.assertEqual(bill["items"][0]["item_name_standard"], "Sugar")

        # Step 4: Verification Simulation
        # Shopkeeper edits quantity of item 0 from 2 to 3 and recalculates
        items = bill["items"]
        items[0]["quantity"] = 3.0
        items[0]["line_total"] = 3.0 * 44.0  # 132.0

        # Recalculate grand total: 132 + 155 + 190 + 160 + 120 = 757.0
        updated_grand_total = sum(it["line_total"] for it in items)
        self.assertEqual(updated_grand_total, 757.0)

        # Step 5: Confirm & Save to Database
        bill_data = {
            "id": bill["id"],
            "user_id": "user_ramesh",
            "bill_number": bill["bill_number"],
            "bill_date": bill["bill_date"],
            "subtotal": updated_grand_total,
            "discount": 0.0,
            "tax": 0.0,
            "grand_total": updated_grand_total,
            "detected_language": lang_res["primary_language"],
            "language_used": "hi",
            "image_hash": "e2e_hash_1",
            "status": "verified",
        }
        saved_id = self.rls.save_bill(bill_data, items)
        self.assertEqual(saved_id, bill["id"])

        # Step 6: Verify Sales Dashboard Reflection
        saved_bill = self.rls.get_bill(saved_id)
        self.assertIsNotNone(saved_bill)
        self.assertEqual(saved_bill["grand_total"], 757.0)
        self.assertEqual(len(saved_bill["items"]), 5)

        # Dashboard metrics
        metrics = self.dashboard.get_summary_metrics()
        self.assertEqual(metrics["all_time_sales"], 757.0)
        self.assertEqual(metrics["total_bills_count"], 1)

        # Item-wise sales
        item_sales = self.dashboard.get_item_wise_sales()
        self.assertEqual(len(item_sales), 5)
        sugar_stat = [it for it in item_sales if it["item_name"] == "Sugar"][0]
        self.assertEqual(sugar_stat["total_quantity"], 3.0)
        self.assertEqual(sugar_stat["total_revenue"], 132.0)
        # Original name preserved
        self.assertEqual(sugar_stat["original_name"], "चीनी")


if __name__ == "__main__":
    unittest.main()
