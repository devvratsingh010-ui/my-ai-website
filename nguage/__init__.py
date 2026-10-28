"""Language detection and script handling module."""
from app.language.detector import (
    SUPPORTED_LANGUAGE_CODES,
    detect_language,
    get_ocr_language_hints,
    normalize_native_digits,
    validate_selected_language,
)

__all__ = [
    "detect_language",
    "get_ocr_language_hints",
    "normalize_native_digits",
    "validate_selected_language",
    "SUPPORTED_LANGUAGE_CODES",
]
