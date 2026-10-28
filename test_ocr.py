"""Unit tests for Image Preprocessing and Google Cloud Vision OCR integration."""

import io
import unittest
from PIL import Image
from app.ocr.preprocessor import (
    ImageValidationError,
    compute_image_hash,
    detect_blur_and_quality,
    preprocess_bill_image,
    validate_image_file,
)
from app.ocr.test_fixtures import create_synthetic_bill_image
from app.ocr.vision_ocr import (
    CredentialsMissingError,
    GoogleVisionOCR,
    OCRError,
    QuotaExceededError,
    ServiceUnavailableError,
)


class TestOCRAndPreprocessing(unittest.TestCase):
    """Test image preprocessing, validation, and Google Vision OCR client."""

    def test_image_validation_valid(self):
        """Valid JPEG image passes validation."""
        img_bytes = create_synthetic_bill_image(["Test Bill", "Sugar 2kg 88"])
        # Should not raise
        validate_image_file(img_bytes, "bill.jpg")

    def test_image_validation_invalid_extension(self):
        """Disallowed extensions must fail."""
        img_bytes = create_synthetic_bill_image(["Test Bill"])
        with self.assertRaises(ImageValidationError):
            validate_image_file(img_bytes, "bill.exe")

    def test_image_validation_corrupted_file(self):
        """Corrupted byte content must fail."""
        corrupted_bytes = b"not an image file content"
        with self.assertRaises(ImageValidationError):
            validate_image_file(corrupted_bytes, "bill.png")

    def test_image_hash_consistency(self):
        """Image SHA-256 hash is consistent for identical image bytes."""
        img_bytes = create_synthetic_bill_image(["Bill 1", "Total 100"])
        hash1 = compute_image_hash(img_bytes)
        hash2 = compute_image_hash(img_bytes)
        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 64)

    def test_blur_detection_sharp_vs_blurry(self):
        """Sharp image vs blurred image detection."""
        sharp_bytes = create_synthetic_bill_image(["Clear Line 1", "Clear Line 2"], is_blurry=False)
        blurry_bytes = create_synthetic_bill_image(["Blurry Line 1", "Blurry Line 2"], is_blurry=True)

        sharp_img = Image.open(io.BytesIO(sharp_bytes))
        blurry_img = Image.open(io.BytesIO(blurry_bytes))

        sharp_qual = detect_blur_and_quality(sharp_img)
        blurry_qual = detect_blur_and_quality(blurry_img)

        self.assertFalse(sharp_qual["is_blurry"])
        self.assertTrue(blurry_qual["is_blurry"])
        self.assertIn("blurry", blurry_qual["warning"].lower())

    def test_preprocess_bill_image(self):
        """Preprocessing handles normalization, dimensions, and metadata."""
        raw_bytes = create_synthetic_bill_image(["Store Name", "Rice 5kg 300"])
        processed_bytes, meta = preprocess_bill_image(raw_bytes)
        self.assertIsInstance(processed_bytes, bytes)
        self.assertIn("original_width", meta)
        self.assertIn("quality", meta)

    def test_vision_ocr_status_when_no_credentials(self):
        """Vision OCR correctly reports credentials status without leaking secrets."""
        ocr = GoogleVisionOCR(api_key="", credentials_file="")
        self.assertFalse(ocr.has_credentials())

        status = ocr.get_credential_status()
        self.assertFalse(status["is_configured"])
        self.assertEqual(status["provider"], "Google Cloud Vision OCR")
        self.assertEqual(status["feature"], "DOCUMENT_TEXT_DETECTION")
        self.assertEqual(status["supported_languages"], ["en", "hi", "kn", "te"])

    def test_vision_ocr_raises_when_credentials_missing_and_fallback_disabled(self):
        """Calling recognize_bill with no credentials and fallback disabled raises CredentialsMissingError."""
        ocr = GoogleVisionOCR(api_key="", credentials_file="")
        img_bytes = create_synthetic_bill_image(["Bill 1"])
        with self.assertRaises(CredentialsMissingError):
            ocr.recognize_bill(img_bytes, selected_language="auto", allow_demo_fallback=False)

    def test_vision_ocr_informative_response_when_fallback_enabled(self):
        """Calling recognize_bill with fallback enabled returns explicit CREDENTIALS_MISSING status."""
        ocr = GoogleVisionOCR(api_key="", credentials_file="")
        img_bytes = create_synthetic_bill_image(["Bill 1"])
        res = ocr.recognize_bill(img_bytes, selected_language="auto", allow_demo_fallback=True)
        self.assertEqual(res["status"], "CREDENTIALS_MISSING")
        self.assertIn("GOOGLE_VISION_API_KEY", res["error_message"])


if __name__ == "__main__":
    unittest.main()
