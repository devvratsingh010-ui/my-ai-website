"""Google Cloud Vision OCR integration with document-oriented text detection,
language hints, error handling, and offline verification support.
"""

import base64
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple
import requests
from app.config import (
    GOOGLE_APPLICATION_CREDENTIALS,
    GOOGLE_VISION_API_KEY,
    OCR_TIMEOUT_SECONDS,
    VISION_API_ENDPOINT,
)
from app.language.detector import detect_language, get_ocr_language_hints


class OCRError(Exception):
    """Base exception for OCR errors."""
    def __init__(self, message: str, error_code: str, status_code: int = 400, details: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details


class CredentialsMissingError(OCRError):
    """Raised when Google Cloud Vision credentials are not configured."""
    def __init__(self):
        super().__init__(
            message="Google Cloud Vision credentials are not configured.",
            error_code="CREDENTIALS_MISSING",
            status_code=503,
            details=(
                "To enable live OCR, set the GOOGLE_VISION_API_KEY environment variable "
                "or set GOOGLE_APPLICATION_CREDENTIALS to a Google Cloud Service Account JSON file. "
                "You can continue by entering bill details manually or using sample test bills."
            ),
        )


class QuotaExceededError(OCRError):
    def __init__(self):
        super().__init__(
            message="Google Cloud Vision API quota or rate limit exceeded.",
            error_code="QUOTA_EXCEEDED",
            status_code=429,
            details="The API request limit was reached. Please wait a few moments or enter bill details manually.",
        )


class ServiceUnavailableError(OCRError):
    def __init__(self, details: Optional[str] = None):
        super().__init__(
            message="OCR service is currently unavailable or timed out.",
            error_code="SERVICE_UNAVAILABLE",
            status_code=503,
            details=details or "Could not connect to Google Cloud Vision API. Please check your network or enter bill manually.",
        )


class GoogleVisionOCR:
    """Client for Google Cloud Vision Document Text Detection."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        credentials_file: Optional[str] = None,
        timeout: int = OCR_TIMEOUT_SECONDS,
    ):
        self.api_key = (api_key or GOOGLE_VISION_API_KEY).strip()
        self.credentials_file = (credentials_file or GOOGLE_APPLICATION_CREDENTIALS).strip()
        self.timeout = timeout

    def has_credentials(self) -> bool:
        """Check if any valid credential is configured."""
        if self.api_key:
            return True
        if self.credentials_file and os.path.exists(self.credentials_file):
            return True
        return False

    def get_credential_status(self) -> Dict[str, Any]:
        """Return diagnostic info on credential status without exposing secrets."""
        has_key = bool(self.api_key)
        has_file = bool(self.credentials_file and os.path.exists(self.credentials_file))
        return {
            "is_configured": has_key or has_file,
            "provider": "Google Cloud Vision OCR",
            "feature": "DOCUMENT_TEXT_DETECTION",
            "auth_method": "API_KEY" if has_key else ("SERVICE_ACCOUNT" if has_file else "NONE"),
            "supported_languages": ["en", "hi", "kn", "te"],
            "setup_instructions": (
                "Configure GOOGLE_VISION_API_KEY in your environment or .env file, "
                "or set GOOGLE_APPLICATION_CREDENTIALS to your Google Cloud service account JSON path."
            ),
        }

    def _get_auth_headers_and_url(self) -> Tuple[str, Dict[str, str]]:
        """Determine endpoint URL and authentication headers."""
        if self.api_key:
            url = f"{VISION_API_ENDPOINT}?key={self.api_key}"
            headers = {"Content-Type": "application/json"}
            return url, headers

        if self.credentials_file and os.path.exists(self.credentials_file):
            # Try to get OAuth2 token using google-auth if installed, or service account JWT
            try:
                from google.oauth2 import service_account
                import google.auth.transport.requests

                creds = service_account.Credentials.from_service_account_file(
                    self.credentials_file,
                    scopes=["https://www.googleapis.com/auth/cloud-vision"],
                )
                auth_req = google.auth.transport.requests.Request()
                creds.refresh(auth_req)
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {creds.token}",
                }
                return VISION_API_ENDPOINT, headers
            except ImportError:
                # If google-auth is not installed, prompt user to use API key
                raise OCRError(
                    message="google-auth library not installed for Service Account JSON.",
                    error_code="LIBRARY_MISSING",
                    status_code=500,
                    details="Install google-auth or use GOOGLE_VISION_API_KEY directly.",
                )

        raise CredentialsMissingError()

    def recognize_bill(
        self,
        image_bytes: bytes,
        selected_language: str = "auto",
        allow_demo_fallback: bool = True,
    ) -> Dict[str, Any]:
        """Perform OCR using Google Cloud Vision DOCUMENT_TEXT_DETECTION.

        Language hints are constructed strictly from the 4 supported languages.
        """
        # Validate credentials first
        if not self.has_credentials():
            if allow_demo_fallback:
                # Return explicit missing credentials state with fallback demo guidance
                return self._build_credentials_missing_response(selected_language)
            raise CredentialsMissingError()

        # Build request payload
        encoded_image = base64.b64encode(image_bytes).decode("utf-8")
        lang_hints = get_ocr_language_hints(selected_language)

        payload = {
            "requests": [
                {
                    "image": {"content": encoded_image},
                    "features": [
                        {"type": "DOCUMENT_TEXT_DETECTION", "maxResults": 1}
                    ],
                    "imageContext": {
                        "languageHints": lang_hints
                    },
                }
            ]
        }

        try:
            url, headers = self._get_auth_headers_and_url()
            start_time = time.time()
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            duration_ms = int((time.time() - start_time) * 1000)
        except requests.exceptions.Timeout:
            raise ServiceUnavailableError("OCR request timed out. Please try again or enter bill manually.")
        except requests.exceptions.ConnectionError:
            raise ServiceUnavailableError("Unable to reach Google Cloud Vision servers. Check network connection.")
        except Exception as e:
            if isinstance(e, OCRError):
                raise
            raise ServiceUnavailableError(f"Unexpected connection error: {str(e)}")

        # Handle HTTP status codes
        if response.status_code == 429:
            raise QuotaExceededError()
        elif response.status_code == 403:
            err_data = response.json().get("error", {})
            msg = err_data.get("message", "Permission denied / Invalid API key")
            raise OCRError(f"Google Cloud Vision authentication failed: {msg}", "AUTH_FAILED", 403)
        elif response.status_code != 200:
            err_data = response.json().get("error", {})
            msg = err_data.get("message", f"HTTP {response.status_code}")
            raise OCRError(f"Vision API error: {msg}", "API_ERROR", response.status_code)

        result_json = response.json()
        return self._parse_vision_response(result_json, duration_ms, selected_language)

    def _parse_vision_response(
        self, response_json: Dict[str, Any], duration_ms: int, selected_language: str
    ) -> Dict[str, Any]:
        """Extract fullTextAnnotation, block confidence, and detect language."""
        responses = response_json.get("responses", [])
        if not responses:
            return {
                "success": False,
                "status": "NO_TEXT",
                "raw_text": "",
                "blocks": [],
                "confidence": 0.0,
                "error_message": "No text detected in the image. Please take a clearer photo or enter manually.",
                "duration_ms": duration_ms,
            }

        first_resp = responses[0]

        # Check for API-level error inside the response object
        if "error" in first_resp:
            err = first_resp["error"]
            raise OCRError(
                f"Vision API returned error: {err.get('message')}",
                "API_INTERNAL_ERROR",
                details=err.get("details"),
            )

        full_text_annotation = first_resp.get("fullTextAnnotation")
        if not full_text_annotation or not full_text_annotation.get("text", "").strip():
            return {
                "success": False,
                "status": "NO_TEXT",
                "raw_text": "",
                "blocks": [],
                "confidence": 0.0,
                "warning": "No readable text could be recognized. The image might be empty, blurry, or blank.",
                "duration_ms": duration_ms,
            }

        raw_text = full_text_annotation["text"]

        # Calculate average confidence across blocks/pages
        confidences: List[float] = []
        blocks_data = []
        for page in full_text_annotation.get("pages", []):
            conf = page.get("confidence")
            if conf is not None:
                confidences.append(float(conf))
            for block in page.get("blocks", []):
                b_conf = block.get("confidence")
                if b_conf is not None:
                    confidences.append(float(b_conf))
                # Collect block text
                block_words = []
                for paragraph in block.get("paragraphs", []):
                    for word in paragraph.get("words", []):
                        word_text = "".join(symbol.get("text", "") for symbol in word.get("symbols", []))
                        block_words.append(word_text)
                blocks_data.append({
                    "text": " ".join(block_words),
                    "confidence": b_conf,
                })

        overall_confidence = round(sum(confidences) / len(confidences), 3) if confidences else 0.80

        # Language detection and validation
        lang_detection = detect_language(raw_text)

        status = "SUCCESS"
        if not lang_detection["is_supported"]:
            status = "UNSUPPORTED_LANGUAGE"
        elif overall_confidence < 0.65:
            status = "LOW_CONFIDENCE"

        return {
            "success": True,
            "status": status,
            "provider": "Google Cloud Vision OCR",
            "raw_text": raw_text,
            "blocks": blocks_data,
            "confidence": overall_confidence,
            "detected_language": lang_detection["primary_language"],
            "detected_languages": lang_detection["detected_languages"],
            "is_mixed_language": lang_detection["is_mixed"],
            "language_warning": lang_detection.get("warning"),
            "is_supported_language": lang_detection["is_supported"],
            "raw_vision_response": full_text_annotation,
            "duration_ms": duration_ms,
        }

    def _build_credentials_missing_response(self, selected_language: str) -> Dict[str, Any]:
        """Informative response returned when API credentials are not set."""
        return {
            "success": False,
            "status": "CREDENTIALS_MISSING",
            "provider": "Google Cloud Vision OCR",
            "is_live_ocr": False,
            "raw_text": "",
            "confidence": 0.0,
            "error_code": "CREDENTIALS_MISSING",
            "error_message": (
                "Google Cloud Vision API key is not configured. "
                "Please configure GOOGLE_VISION_API_KEY or GOOGLE_APPLICATION_CREDENTIALS in your environment. "
                "You can still enter or correct bill details manually, or test with sample bills."
            ),
            "configuration_guide": {
                "environment_variable": "GOOGLE_VISION_API_KEY",
                "service_account_variable": "GOOGLE_APPLICATION_CREDENTIALS",
                "documentation_url": "https://cloud.google.com/vision/docs/ocr",
            },
        }
