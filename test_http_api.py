"""Integration test for HTTP REST API and web endpoints."""

import threading
import time
import unittest
import requests
from app.config import HOST
from app.server import HisabAPIHandler, ThreadingHTTPServer, init_db, seed_default_data

TEST_PORT = 8011
BASE_URL = f"http://{HOST}:{TEST_PORT}"


class TestLiveHttpServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        seed_default_data()
        cls.httpd = ThreadingHTTPServer((HOST, TEST_PORT), HisabAPIHandler)
        cls.server_thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def test_get_index_html(self):
        resp = requests.get(f"{BASE_URL}/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("HisabAI", resp.text)
        self.assertIn("Supported: EN, HI, KN, TE", resp.text)

    def test_api_status(self):
        resp = requests.get(f"{BASE_URL}/api/status")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["app_name"], "HisabAI")
        self.assertIn("hi", data["supported_languages"])
        self.assertIn("kn", data["supported_languages"])
        self.assertIn("te", data["supported_languages"])
        self.assertIn("en", data["supported_languages"])

    def test_api_login_and_dashboard_flow(self):
        # 1. Login
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": "ramesh", "password": "kirana123"},
        )
        self.assertEqual(login_resp.status_code, 200)
        token = login_resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Check dashboard initially
        dash_resp = requests.get(f"{BASE_URL}/api/dashboard", headers=headers)
        self.assertEqual(dash_resp.status_code, 200)

        # 3. Scan a sample Hindi bill
        scan_resp = requests.post(
            f"{BASE_URL}/api/bills/scan",
            headers=headers,
            json={"sample_id": "sample_hi_kachha", "language": "hi"},
        )
        self.assertEqual(scan_resp.status_code, 200)
        scan_data = scan_resp.json()
        self.assertTrue(scan_data["verification_required"])
        bill = scan_data["bill"]
        self.assertEqual(bill["detected_language"], "hi")

        # 4. Verify and save the bill (using force_save=True to allow repeat test runs)
        save_resp = requests.post(
            f"{BASE_URL}/api/bills/verify-and-save",
            headers=headers,
            json={"bill": bill, "items": bill["items"], "force_save": True},
        )
        self.assertEqual(save_resp.status_code, 200)
        self.assertTrue(save_resp.json()["success"])

        # 5. Check dashboard updated
        dash_after = requests.get(f"{BASE_URL}/api/dashboard", headers=headers).json()
        self.assertGreater(dash_after["metrics"]["all_time_sales"], 0.0)


if __name__ == "__main__":
    unittest.main()
