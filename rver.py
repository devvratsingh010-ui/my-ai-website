"""HTTP Server with REST API routes, static file serving, authentication, and OCR processing."""

import email
from email.policy import default
import io
import json
import mimetypes
import os
import re
import shutil
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from app.auth import (
    create_session,
    delete_session,
    hash_password,
    seed_default_data,
    validate_session,
    verify_password,
)
from app.config import (
    BASE_DIR,
    HOST,
    PORT,
    SUPPORTED_LANGUAGES,
    UPLOAD_DIR,
)
from app.database import ShopRLS, get_db_connection, init_db
from app.language.detector import (
    detect_language,
    normalize_native_digits,
    validate_selected_language,
)
from app.ocr.preprocessor import (
    ImageValidationError,
    compute_image_hash,
    preprocess_bill_image,
    validate_image_file,
)
from app.ocr.vision_ocr import (
    CredentialsMissingError,
    GoogleVisionOCR,
    OCRError,
    QuotaExceededError,
    ServiceUnavailableError,
)
from app.parser.bill_parser import BillParser
from app.parser.product_catalog import ProductCatalogMatcher
from app.sales.dashboard import SalesDashboard

STATIC_DIR = BASE_DIR / "app" / "static"


class HisabAPIHandler(SimpleHTTPRequestHandler):
    """Custom HTTP handler with REST endpoints and static file delivery."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    # -------------------------------------------------------------------------
    # Helper utilities
    # -------------------------------------------------------------------------
    def _send_json(self, data: Any, status: int = 200) -> None:
        """Send JSON response."""
        body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, message: str, status: int = 400, code: str = "ERROR", details: Any = None) -> None:
        """Send structured JSON error."""
        self._send_json({"error": True, "code": code, "message": message, "details": details}, status=status)

    def _get_auth_session(self) -> Optional[Dict[str, Any]]:
        """Extract and validate bearer token or cookie session."""
        auth_header = self.headers.get("Authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif "Cookie" in self.headers:
            cookies = urllib.parse.parse_qs(self.headers["Cookie"].replace("; ", "&"))
            token = cookies.get("hisab_session", [""])[0]

        if not token:
            return None
        return validate_session(token)

    def _read_json_body(self) -> Dict[str, Any]:
        """Read and parse JSON request body."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length)
        return json.loads(body.decode("utf-8"))

    # -------------------------------------------------------------------------
    # CORS Preflight
    # -------------------------------------------------------------------------
    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.end_headers()

    # -------------------------------------------------------------------------
    # Route Dispatchers
    # -------------------------------------------------------------------------
    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        # Static files & SPA root
        if path == "/" or path == "/index.html":
            return self._serve_index()
        elif path.startswith("/static/"):
            return super().do_GET()
        elif path.startswith("/uploads/"):
            return self._serve_upload(path[9:])

        # API Routes
        if path == "/api/status":
            return self._handle_get_status()
        elif path == "/api/auth/me":
            return self._handle_get_me()
        elif path == "/api/dashboard":
            return self._handle_get_dashboard()
        elif path == "/api/bills":
            return self._handle_list_bills()
        elif re.match(r"^/api/bills/([A-Za-z0-9_\-]+)$", path):
            bill_id = re.match(r"^/api/bills/([A-Za-z0-9_\-]+)$", path).group(1)
            return self._handle_get_bill(bill_id)
        elif path == "/api/test-samples":
            return self._handle_get_test_samples()

        # Not found fallback
        self._send_error(f"Route '{path}' not found", 404, "NOT_FOUND")

    def do_POST(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/api/auth/login":
            return self._handle_login()
        elif path == "/api/auth/logout":
            return self._handle_logout()
        elif path == "/api/bills/scan":
            return self._handle_scan_bill()
        elif path == "/api/bills/verify-and-save":
            return self._handle_verify_and_save_bill()

        self._send_error(f"Route '{path}' not found", 404, "NOT_FOUND")

    def do_PUT(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        match = re.match(r"^/api/bills/([A-Za-z0-9_\-]+)$", path)
        if match:
            bill_id = match.group(1)
            return self._handle_update_bill(bill_id)

        self._send_error(f"Route '{path}' not found", 404, "NOT_FOUND")

    def do_DELETE(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        match = re.match(r"^/api/bills/([A-Za-z0-9_\-]+)$", path)
        if match:
            bill_id = match.group(1)
            return self._handle_delete_bill(bill_id)

        self._send_error(f"Route '{path}' not found", 404, "NOT_FOUND")

    # -------------------------------------------------------------------------
    # Static & Upload file serving
    # -------------------------------------------------------------------------
    def _serve_index(self) -> None:
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            with open(index_file, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self._send_error("index.html not found", 404)

    def _serve_upload(self, filename: str) -> None:
        # Prevent directory traversal
        safe_name = os.path.basename(filename)
        file_path = UPLOAD_DIR / safe_name
        if not file_path.exists():
            self._send_error("Image not found", 404)
            return

        mime_type, _ = mimetypes.guess_type(str(file_path))
        mime_type = mime_type or "image/jpeg"

        with open(file_path, "rb") as f:
            content = f.read()

        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "public, max-age=86400")
        self.end_headers()
        self.wfile.write(content)

    # -------------------------------------------------------------------------
    # API Handlers
    # -------------------------------------------------------------------------
    def _handle_get_status(self) -> None:
        ocr = GoogleVisionOCR()
        cred_status = ocr.get_credential_status()
        session = self._get_auth_session()

        self._send_json({
            "app_name": "HisabAI",
            "version": "1.0.0",
            "supported_languages": SUPPORTED_LANGUAGES,
            "ocr_status": cred_status,
            "current_user": {
                "user_id": session["user_id"],
                "username": session["username"],
                "full_name": session["full_name"],
                "shop_id": session["shop_id"],
                "shop_name": session["shop_name"],
                "business_category": session["business_category"],
            } if session else None,
        })

    def _handle_login(self) -> None:
        data = self._read_json_body()
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()

        if not username or not password:
            self._send_error("Username and password are required", 400, "MISSING_CREDENTIALS")
            return

        conn = get_db_connection()
        cur = conn.execute(
            """
            SELECT u.*, s.name as shop_name, s.business_category
            FROM users u
            JOIN shops s ON u.shop_id = s.id
            WHERE u.username = ?
            """,
            (username,),
        )
        user = cur.fetchone()
        if not user or not verify_password(user["password_hash"], password):
            self._send_error("Invalid username or password", 401, "INVALID_LOGIN")
            return

        token = create_session(user["id"], user["shop_id"])
        self._send_json({
            "token": token,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "full_name": user["full_name"],
                "role": user["role"],
                "shop_id": user["shop_id"],
                "shop_name": user["shop_name"],
                "business_category": user["business_category"],
            },
        })

    def _handle_logout(self) -> None:
        session = self._get_auth_session()
        if session:
            delete_session(session["token"])
        self._send_json({"success": True, "message": "Logged out successfully"})

    def _handle_get_me(self) -> None:
        session = self._get_auth_session()
        if not session:
            self._send_error("Not authenticated", 401, "UNAUTHORIZED")
            return
        self._send_json({"user": session})

    def _handle_get_dashboard(self) -> None:
        session = self._get_auth_session()
        if not session:
            self._send_error("Not authenticated", 401, "UNAUTHORIZED")
            return

        dashboard = SalesDashboard(session["shop_id"])
        metrics = dashboard.get_summary_metrics()
        items = dashboard.get_item_wise_sales(limit=15)
        trend = dashboard.get_daily_sales_trend(days=7)

        rls = ShopRLS(session["shop_id"])
        recent_bills = rls.list_bills(limit=10)

        self._send_json({
            "metrics": metrics,
            "item_wise_sales": items,
            "sales_trend": trend,
            "recent_bills": recent_bills,
            "shop": {
                "id": session["shop_id"],
                "name": session["shop_name"],
                "category": session["business_category"],
            },
        })

    def _handle_list_bills(self) -> None:
        session = self._get_auth_session()
        if not session:
            self._send_error("Not authenticated", 401, "UNAUTHORIZED")
            return

        rls = ShopRLS(session["shop_id"])
        bills = rls.list_bills(limit=50)
        self._send_json({"bills": bills})

    def _handle_get_bill(self, bill_id: str) -> None:
        session = self._get_auth_session()
        if not session:
            self._send_error("Not authenticated", 401, "UNAUTHORIZED")
            return

        rls = ShopRLS(session["shop_id"])
        bill = rls.get_bill(bill_id)
        if not bill:
            self._send_error(f"Bill '{bill_id}' not found in this shop", 404, "NOT_FOUND")
            return
        self._send_json({"bill": bill})

    def _handle_delete_bill(self, bill_id: str) -> None:
        session = self._get_auth_session()
        if not session:
            self._send_error("Not authenticated", 401, "UNAUTHORIZED")
            return

        rls = ShopRLS(session["shop_id"])
        success = rls.delete_bill(bill_id)
        if not success:
            self._send_error(f"Bill '{bill_id}' not found or unauthorized", 404, "NOT_FOUND")
            return

        # Return updated dashboard metrics immediately
        dashboard = SalesDashboard(session["shop_id"])
        self._send_json({
            "success": True,
            "message": "Bill deleted successfully.",
            "metrics": dashboard.get_summary_metrics(),
        })

    def _handle_update_bill(self, bill_id: str) -> None:
        session = self._get_auth_session()
        if not session:
            self._send_error("Not authenticated", 401, "UNAUTHORIZED")
            return

        data = self._read_json_body()
        bill_data = data.get("bill", {})
        items = data.get("items", [])

        if not bill_data.get("bill_date") or bill_data.get("grand_total") is None:
            self._send_error("Bill date and grand total are required", 400, "INVALID_DATA")
            return

        rls = ShopRLS(session["shop_id"])
        success = rls.update_bill(bill_id, bill_data, items)
        if not success:
            self._send_error(f"Bill '{bill_id}' not found or unauthorized", 404, "NOT_FOUND")
            return

        dashboard = SalesDashboard(session["shop_id"])
        self._send_json({
            "success": True,
            "message": "Bill updated successfully.",
            "updated_bill": rls.get_bill(bill_id),
            "metrics": dashboard.get_summary_metrics(),
        })

    def _handle_scan_bill(self) -> None:
        """Process bill scan: upload validation, preprocessing, OCR, language detection, structured parsing."""
        session = self._get_auth_session()
        if not session:
            self._send_error("Authentication required to scan bills", 401, "UNAUTHORIZED")
            return

        # Check content type: JSON base64 or multipart
        content_type = self.headers.get("Content-Type", "")
        image_bytes: Optional[bytes] = None
        filename: str = "bill.jpg"
        selected_language: str = "auto"
        sample_id: Optional[str] = None

        if "multipart/form-data" in content_type:
            # Parse multipart form using standard library email module
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length)
            msg = email.message_from_bytes(
                b"Content-Type: " + content_type.encode("latin-1") + b"\r\n\r\n" + raw_body,
                policy=default,
            )
            for part in msg.iter_parts():
                disp = part.get("Content-Disposition", "")
                if 'name="image"' in disp:
                    image_bytes = part.get_payload(decode=True)
                    filename = part.get_filename() or "bill.jpg"
                elif 'name="language"' in disp:
                    val = part.get_payload()
                    if isinstance(val, str):
                        selected_language = val.strip()
        elif "application/json" in content_type:
            data = self._read_json_body()
            selected_language = data.get("language", "auto")
            sample_id = data.get("sample_id")

            if sample_id:
                # Load built-in test sample
                sample_info = self._get_sample_by_id(sample_id)
                if not sample_info:
                    self._send_error(f"Sample '{sample_id}' not found", 404)
                    return
                image_bytes = sample_info["bytes"]
                filename = sample_info["filename"]
                if "language" not in data or data["language"] == "auto":
                    selected_language = sample_info.get("language", "auto")
            elif "image_base64" in data:
                b64_data = data["image_base64"]
                if "," in b64_data:
                    b64_data = b64_data.split(",")[1]
                try:
                    import base64
                    image_bytes = base64.b64decode(b64_data)
                    filename = data.get("filename", "bill.jpg")
                except Exception as e:
                    self._send_error(f"Invalid base64 image data: {str(e)}", 400)
                    return

        if not image_bytes:
            self._send_error("No image provided in request.", 400, "MISSING_IMAGE")
            return

        # Validate language selection: strictly 'auto', 'en', 'hi', 'kn', 'te'
        if not validate_selected_language(selected_language):
            self._send_error(
                f"Unsupported language selection '{selected_language}'. HisabAI supports strictly: auto, en, hi, kn, te.",
                400,
                "UNSUPPORTED_LANGUAGE_PARAM",
            )
            return

        # Step 1: Validate image format and integrity
        try:
            validate_image_file(image_bytes, filename)
        except ImageValidationError as e:
            self._send_error(str(e), 400, "IMAGE_VALIDATION_FAILED")
            return

        # Step 2: Preprocess image (EXIF orientation, blur check, contrast)
        processed_bytes, img_meta = preprocess_bill_image(image_bytes)
        img_hash = compute_image_hash(processed_bytes)

        # Save processed image to uploads directory
        ext = Path(filename).suffix.lower() or ".jpg"
        saved_filename = f"{img_hash[:16]}{ext}"
        saved_path = UPLOAD_DIR / saved_filename
        with open(saved_path, "wb") as f:
            f.write(processed_bytes)

        image_url = f"/uploads/{saved_filename}"

        # Step 3: Check for duplicate submissions in this shop
        rls = ShopRLS(session["shop_id"])
        duplicate_check = rls.check_duplicate_bill(image_hash=img_hash, bill_number=None, bill_date="", grand_total=0.0)

        # Step 4: Run OCR (Google Cloud Vision)
        ocr = GoogleVisionOCR()
        ocr_result: Dict[str, Any]
        is_live_ocr = True

        try:
            ocr_result = ocr.recognize_bill(
                image_bytes=processed_bytes,
                selected_language=selected_language,
                allow_demo_fallback=True,
            )
        except OCRError as e:
            self._send_error(e.message, e.status_code, e.error_code, e.details)
            return
        except Exception as e:
            self._send_error(f"OCR processing failed: {str(e)}", 500, "OCR_FAILED")
            return

        raw_text = ocr_result.get("raw_text", "")

        # If credentials were missing and sample_id was used, retrieve fixture OCR text for realistic test
        if ocr_result.get("status") == "CREDENTIALS_MISSING" and sample_id:
            sample_info = self._get_sample_by_id(sample_id)
            if sample_info and sample_info.get("fixture_text"):
                raw_text = sample_info["fixture_text"]
                ocr_result["raw_text"] = raw_text
                ocr_result["is_sample_fixture"] = True
                ocr_result["confidence"] = 0.88

        # Step 5: Language Detection and Script Validation
        lang_info = detect_language(raw_text)

        # Step 6: Structured Bill Parsing
        aliases = rls.get_product_aliases()
        catalog_matcher = ProductCatalogMatcher(aliases)
        parser = BillParser(catalog_matcher)
        parsed_bill = parser.parse(raw_text)

        # Attach image and metadata
        parsed_bill["image_path"] = image_url
        parsed_bill["image_hash"] = img_hash
        parsed_bill["ocr_raw_text"] = raw_text
        parsed_bill["selected_language"] = selected_language
        parsed_bill["detected_language"] = lang_info["primary_language"]
        parsed_bill["detected_languages"] = lang_info["detected_languages"]
        parsed_bill["is_mixed_language"] = lang_info["is_mixed"]
        parsed_bill["language_warning"] = lang_info.get("warning")
        parsed_bill["ocr_provider"] = ocr_result.get("provider", "Google Cloud Vision OCR")
        parsed_bill["ocr_status"] = ocr_result.get("status")
        parsed_bill["is_live_ocr"] = ocr.has_credentials()
        parsed_bill["image_quality"] = img_meta["quality"]
        parsed_bill["duplicate_warning"] = duplicate_check

        # If blur detected, add to review reasons
        if img_meta["quality"]["is_blurry"]:
            parsed_bill["needs_review"] = True
            parsed_bill["review_reasons"].append(img_meta["quality"]["warning"])

        # If language is unsupported, flag for review
        if not lang_info["is_supported"]:
            parsed_bill["needs_review"] = True
            parsed_bill["review_reasons"].append(lang_info["warning"])

        # Never silently save uncertain OCR output as verified data:
        # Shopkeeper MUST confirm on the verification screen!
        self._send_json({
            "success": True,
            "verification_required": True,
            "bill": parsed_bill,
            "ocr_summary": {
                "confidence": ocr_result.get("confidence", 0.0),
                "is_live_ocr": ocr.has_credentials(),
                "status": ocr_result.get("status"),
                "duration_ms": ocr_result.get("duration_ms", 0),
            },
        })

    def _handle_verify_and_save_bill(self) -> None:
        """Confirm and save a verified bill after shopkeeper review."""
        session = self._get_auth_session()
        if not session:
            self._send_error("Authentication required to save bills", 401, "UNAUTHORIZED")
            return

        data = self._read_json_body()
        bill_data = data.get("bill", {})
        items = data.get("items", [])

        if not bill_data.get("bill_date"):
            self._send_error("Bill date is required", 400, "MISSING_DATE")
            return

        if bill_data.get("grand_total") is None:
            self._send_error("Grand total is required", 400, "MISSING_TOTAL")
            return

        if not items:
            self._send_error("Bill must contain at least one item", 400, "EMPTY_ITEMS")
            return

        rls = ShopRLS(session["shop_id"])

        # Prevent duplicate submission if requested
        force_save = data.get("force_save", False)
        if not force_save:
            dup = rls.check_duplicate_bill(
                image_hash=bill_data.get("image_hash"),
                bill_number=bill_data.get("bill_number"),
                bill_date=bill_data["bill_date"],
                grand_total=float(bill_data["grand_total"]),
            )
            if dup:
                self._send_error(
                    "Duplicate bill detected. A bill with identical details or image was already saved.",
                    409,
                    "DUPLICATE_BILL",
                    details=dup,
                )
                return

        bill_data["user_id"] = session["user_id"]
        bill_data["status"] = "verified"

        # Save to database
        saved_id = rls.save_bill(bill_data, items)

        # Return saved bill & updated dashboard metrics immediately
        dashboard = SalesDashboard(session["shop_id"])
        self._send_json({
            "success": True,
            "message": "Bill confirmed and saved successfully! Sales dashboard has been updated.",
            "bill_id": saved_id,
            "dashboard_metrics": dashboard.get_summary_metrics(),
        })

    def _handle_get_test_samples(self) -> None:
        """List representative bill samples across English, Hindi, Kannada, Telugu, mixed, and edge cases."""
        samples = [
            {
                "id": "sample_hi_kachha",
                "title": "हाथ से लिखा कच्चा बिल (Hindi)",
                "language": "hi",
                "description": "Handwritten Hindi kirana bill with items (चीनी, तेल, आटा, दाल), quantities, and rates.",
                "type": "handwritten",
            },
            {
                "id": "sample_kn_kachha",
                "title": "ಕೈಬರಹದ ಬಿಲ್ (Kannada)",
                "language": "kn",
                "description": "Kannada kirana bill with items (ಸಕ್ಕರೆ, ಅಕ್ಕಿ, ಹಾಲು, ಎಣ್ಣೆ) and quantities in Kannada script.",
                "type": "handwritten",
            },
            {
                "id": "sample_te_kachha",
                "title": "చేతిరాత బిల్లు (Telugu)",
                "language": "te",
                "description": "Telugu general store bill with items (చక్కెర, బియ్యం, పాలు, నూనె) and rates.",
                "type": "handwritten",
            },
            {
                "id": "sample_en_printed",
                "title": "Printed English Bill",
                "language": "en",
                "description": "Standard printed retail receipt with Item, Qty, Rate, and Amount columns.",
                "type": "printed",
            },
            {
                "id": "sample_mixed_hi_en",
                "title": "Mixed English + Hindi Bill",
                "language": "auto",
                "description": "Mixed script bill with English header/numbers and Hindi item names.",
                "type": "mixed",
            },
            {
                "id": "sample_blurry_bill",
                "title": "Blurry / Poor Light Bill (Edge Case)",
                "language": "en",
                "description": "Edge case test: blurry image requiring manual review warning.",
                "type": "edge_case_blurry",
            },
            {
                "id": "sample_math_mismatch",
                "title": "Arithmetic Discrepancy Bill (Edge Case)",
                "language": "en",
                "description": "Edge case test: item total does not match Qty x Rate.",
                "type": "edge_case_math",
            },
        ]
        self._send_json({"samples": samples})

    def _get_sample_by_id(self, sample_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve synthetic test image bytes and fixture text for testing."""
        from app.ocr.test_fixtures import get_test_fixture
        return get_test_fixture(sample_id)


def run_server(host: str = HOST, port: int = PORT) -> None:
    """Initialize DB and run HTTP server."""
    init_db()
    seed_default_data()
    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, HisabAPIHandler)
    print(f"HisabAI server running at http://{host}:{port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.server_close()


if __name__ == "__main__":
    run_server()
