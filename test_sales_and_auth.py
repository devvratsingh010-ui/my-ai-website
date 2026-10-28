"""Unit tests for Sales Dashboard calculations, multi-tenancy RLS, duplicate prevention, and Auth."""

import tempfile
import unittest
from pathlib import Path
from app.auth import hash_password, verify_password
from app.database import ShopRLS, close_db_connection, get_db_connection, init_db
from app.sales.dashboard import SalesDashboard


class TestSalesAndAuth(unittest.TestCase):
    """Test shop isolation, sales calculations, bill CRUD, and duplicate checking."""

    def setUp(self):
        close_db_connection()
        # Create a fresh isolated SQLite database for each test
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_hisab.db"
        init_db(self.db_path)

        conn = get_db_connection(self.db_path)
        with conn:
            # Create two test shops
            conn.execute(
                "INSERT OR IGNORE INTO shops (id, name, business_category, owner_name) VALUES (?, ?, ?, ?)",
                ("shop_1", "Kirana Store A", "kirana", "Owner A"),
            )
            conn.execute(
                "INSERT OR IGNORE INTO shops (id, name, business_category, owner_name) VALUES (?, ?, ?, ?)",
                ("shop_2", "General Store B", "general_store", "Owner B"),
            )
            # Create users
            conn.execute(
                "INSERT OR IGNORE INTO users (id, shop_id, username, password_hash, full_name) VALUES (?, ?, ?, ?, ?)",
                ("user_1", "shop_1", "user_a", hash_password("passA"), "User A"),
            )
            conn.execute(
                "INSERT OR IGNORE INTO users (id, shop_id, username, password_hash, full_name) VALUES (?, ?, ?, ?, ?)",
                ("user_2", "shop_2", "user_b", hash_password("passB"), "User B"),
            )

        self.rls_shop1 = ShopRLS("shop_1", conn)
        self.rls_shop2 = ShopRLS("shop_2", conn)
        self.dashboard_shop1 = SalesDashboard("shop_1", conn)
        self.dashboard_shop2 = SalesDashboard("shop_2", conn)

    def tearDown(self):
        close_db_connection()
        self.temp_dir.cleanup()

    def test_password_hashing(self):
        pw = "kirana_secure_pwd"
        h = hash_password(pw)
        self.assertTrue(verify_password(h, pw))
        self.assertFalse(verify_password(h, "wrong_password"))

    def test_rls_multi_tenancy_isolation(self):
        """Bills saved in shop_1 must NEVER be visible or aggregated in shop_2."""
        bill_data = {
            "id": "bill_101",
            "user_id": "user_1",
            "bill_number": "001",
            "bill_date": "2026-10-28",
            "subtotal": 500.0,
            "grand_total": 500.0,
            "language_used": "hi",
            "image_hash": "hash_abc_1",
        }
        items = [
            {"id": "item_1", "item_name_original": "चीनी", "item_name_standard": "Sugar", "quantity": 5.0, "unit": "kg", "line_total": 220.0},
            {"id": "item_2", "item_name_original": "आटा", "item_name_standard": "Wheat Flour", "quantity": 7.0, "unit": "kg", "line_total": 280.0},
        ]
        self.rls_shop1.save_bill(bill_data, items)

        # Shop 1 can see it
        self.assertIsNotNone(self.rls_shop1.get_bill("bill_101"))
        self.assertEqual(len(self.rls_shop1.list_bills()), 1)

        # Shop 2 CANNOT see it
        self.assertIsNone(self.rls_shop2.get_bill("bill_101"))
        self.assertEqual(len(self.rls_shop2.list_bills()), 0)

        # Dashboard metrics for Shop 2 must be zero
        m2 = self.dashboard_shop2.get_summary_metrics()
        self.assertEqual(m2["today_sales"], 0.0)
        self.assertEqual(m2["total_bills_count"], 0)

    def test_save_bill_updates_sales_dashboard(self):
        """Saving a bill updates today's sales and item-wise sales."""
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        bill_data = {
            "id": "bill_201",
            "user_id": "user_1",
            "bill_number": "104",
            "bill_date": today,
            "subtotal": 400.0,
            "grand_total": 400.0,
            "language_used": "en",
        }
        items = [
            {"id": "it_1", "item_name_original": "Sugar", "item_name_standard": "Sugar", "quantity": 2.0, "unit": "kg", "line_total": 88.0},
            {"id": "it_2", "item_name_original": "Rice", "item_name_standard": "Rice", "quantity": 5.0, "unit": "kg", "line_total": 312.0},
        ]
        self.rls_shop1.save_bill(bill_data, items)

        metrics = self.dashboard_shop1.get_summary_metrics()
        self.assertEqual(metrics["today_sales"], 400.0)
        self.assertEqual(metrics["today_bills_count"], 1)

        item_sales = self.dashboard_shop1.get_item_wise_sales()
        self.assertEqual(len(item_sales), 2)
        top_item = item_sales[0]
        self.assertEqual(top_item["item_name"], "Rice")
        self.assertEqual(top_item["total_revenue"], 312.0)
        self.assertEqual(top_item["total_quantity"], 5.0)

    def test_update_bill_recalculates_dashboard(self):
        """Editing an existing bill properly updates dashboard metrics."""
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        bill_data = {
            "id": "bill_301",
            "user_id": "user_1",
            "bill_date": today,
            "subtotal": 200.0,
            "grand_total": 200.0,
            "language_used": "hi",
        }
        items = [{"id": "it_1", "item_name_original": "दूध", "quantity": 5.0, "unit": "ltr", "line_total": 200.0}]
        self.rls_shop1.save_bill(bill_data, items)

        # Update: increase quantity to 10 ltr and total to 400
        bill_data["grand_total"] = 400.0
        bill_data["subtotal"] = 400.0
        items[0]["quantity"] = 10.0
        items[0]["line_total"] = 400.0

        updated = self.rls_shop1.update_bill("bill_301", bill_data, items)
        self.assertTrue(updated)

        metrics = self.dashboard_shop1.get_summary_metrics()
        self.assertEqual(metrics["today_sales"], 400.0)
        item_sales = self.dashboard_shop1.get_item_wise_sales()
        self.assertEqual(item_sales[0]["total_quantity"], 10.0)
        self.assertEqual(item_sales[0]["total_revenue"], 400.0)

    def test_delete_bill_recalculates_dashboard(self):
        """Deleting a bill immediately subtracts from dashboard metrics."""
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        bill_data = {
            "id": "bill_401",
            "user_id": "user_1",
            "bill_date": today,
            "grand_total": 350.0,
            "language_used": "kn",
        }
        items = [{"id": "it_1", "item_name_original": "ಸಕ್ಕರೆ", "quantity": 4.0, "unit": "kg", "line_total": 350.0}]
        self.rls_shop1.save_bill(bill_data, items)

        # Before delete
        self.assertEqual(self.dashboard_shop1.get_summary_metrics()["today_sales"], 350.0)

        # Delete bill
        deleted = self.rls_shop1.delete_bill("bill_401")
        self.assertTrue(deleted)

        # After delete
        metrics = self.dashboard_shop1.get_summary_metrics()
        self.assertEqual(metrics["today_sales"], 0.0)
        self.assertEqual(metrics["today_bills_count"], 0)
        self.assertEqual(len(self.dashboard_shop1.get_item_wise_sales()), 0)

    def test_duplicate_submission_prevention(self):
        """Duplicate bill check catches matching image hash or metadata."""
        bill_data = {
            "id": "bill_501",
            "user_id": "user_1",
            "bill_number": "MEMO-99",
            "bill_date": "2026-10-25",
            "grand_total": 500.0,
            "language_used": "te",
            "image_hash": "unique_hash_xyz_99",
        }
        self.rls_shop1.save_bill(bill_data, [{"id": "it_1", "item_name_original": "నూనె", "line_total": 500.0}])

        # Check duplicate by hash
        dup1 = self.rls_shop1.check_duplicate_bill("unique_hash_xyz_99", None, "", 0.0)
        self.assertIsNotNone(dup1)
        self.assertEqual(dup1["type"], "duplicate_image")

        # Check duplicate by bill number + date + total
        dup2 = self.rls_shop1.check_duplicate_bill(None, "MEMO-99", "2026-10-25", 500.0)
        self.assertIsNotNone(dup2)
        self.assertEqual(dup2["type"], "duplicate_metadata")

        # Non-duplicate
        dup3 = self.rls_shop1.check_duplicate_bill("different_hash", "MEMO-100", "2026-10-26", 600.0)
        self.assertIsNone(dup3)


if __name__ == "__main__":
    unittest.main()
