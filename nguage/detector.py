"""Language detection, script analysis, and validation for exactly four languages:
1. English (en)
2. Hindi (hi)
3. Kannada (kn)
4. Telugu (te)
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple

# Unicode script ranges
SCRIPT_RANGES = {
    "hi": (0x0900, 0x097F),  # Devanagari (Hindi)
    "kn": (0x0C80, 0x0CFF),  # Kannada
    "te": (0x0C00, 0x0C7F),  # Telugu
    "en": (0x0041, 0x007A),  # Basic Latin alphabets
}

# Known unsupported Indian and foreign scripts to explicitly catch and flag
UNSUPPORTED_SCRIPTS = {
    "ta": ("Tamil", (0x0B80, 0x0BFF)),
    "ml": ("Malayalam", (0x0D00, 0x0D7F)),
    "bn": ("Bengali", (0x0980, 0x09FF)),
    "gu": ("Gujarati", (0x0A80, 0x0AFF)),
    "pa": ("Punjabi/Gurmukhi", (0x0A00, 0x0A7F)),
    "or": ("Odia", (0x0B00, 0x0B7F)),
    "ur": ("Urdu/Arabic", (0x0600, 0x06FF)),
}

SUPPORTED_LANGUAGE_CODES = {"en", "hi", "kn", "te"}

# Native digits mapping to standard Arabic digits
NATIVE_DIGITS = {
    # Devanagari ०-९
    "\u0966": "0", "\u0967": "1", "\u0968": "2", "\u0969": "3", "\u096a": "4",
    "\u096b": "5", "\u096c": "6", "\u096d": "7", "\u096e": "8", "\u096f": "9",
    # Kannada ೦-೯
    "\u0ce6": "0", "\u0ce7": "1", "\u0ce8": "2", "\u0ce9": "3", "\u0cea": "4",
    "\u0ceb": "5", "\u0cec": "6", "\u0ced": "7", "\u0cee": "8", "\u0cef": "9",
    # Telugu ౦-౯
    "\u0c66": "0", "\u0c67": "1", "\u0c68": "2", "\u0c69": "3", "\u0c6a": "4",
    "\u0c6b": "5", "\u0c6c": "6", "\u0c6d": "7", "\u0c6e": "8", "\u0c6f": "9",
}


def normalize_native_digits(text: str) -> str:
    """Convert native Devanagari, Kannada, and Telugu digits to standard Arabic digits."""
    return "".join(NATIVE_DIGITS.get(ch, ch) for ch in text)


def analyze_text_scripts(text: str) -> Dict[str, Any]:
    """Count character frequencies across supported and unsupported scripts."""
    counts: Dict[str, int] = {"en": 0, "hi": 0, "kn": 0, "te": 0}
    unsupported_counts: Dict[str, int] = {}

    for ch in text:
        cp = ord(ch)
        # Check supported scripts
        if (0x0041 <= cp <= 0x005A) or (0x0061 <= cp <= 0x007A):
            counts["en"] += 1
        elif 0x0900 <= cp <= 0x097F:
            counts["hi"] += 1
        elif 0x0C80 <= cp <= 0x0CFF:
            counts["kn"] += 1
        elif 0x0C00 <= cp <= 0x0C7F:
            counts["te"] += 1
        else:
            # Check unsupported scripts
            for code, (name, (start, end)) in UNSUPPORTED_SCRIPTS.items():
                if start <= cp <= end:
                    unsupported_counts[name] = unsupported_counts.get(name, 0) + 1
                    break

    return {"supported_counts": counts, "unsupported_counts": unsupported_counts}


def detect_language(text: str) -> Dict[str, Any]:
    """Detect language of bill text, supporting mixed scripts and warning for unsupported languages."""
    if not text or not text.strip():
        return {
            "primary_language": "unknown",
            "detected_languages": [],
            "is_mixed": False,
            "confidence": 0.0,
            "warning": "No readable text detected",
            "is_supported": False,
        }

    script_analysis = analyze_text_scripts(text)
    counts = script_analysis["supported_counts"]
    unsupported = script_analysis["unsupported_counts"]

    # Check if unsupported scripts dominate or are significant
    if unsupported:
        max_unsupported_name = max(unsupported, key=unsupported.get)
        max_unsupported_count = unsupported[max_unsupported_name]
        total_supported = sum(counts.values())
        if max_unsupported_count > 0 and (total_supported == 0 or max_unsupported_count > total_supported * 0.3):
            return {
                "primary_language": "unsupported",
                "unsupported_name": max_unsupported_name,
                "detected_languages": [],
                "is_mixed": False,
                "confidence": 0.0,
                "warning": f"Unsupported language detected ({max_unsupported_name}). HisabAI only supports English, Hindi, Kannada, and Telugu. You can enter or correct the text manually.",
                "is_supported": False,
            }

    # Find present supported languages (with at least 2 characters or >5% of text)
    total_chars = sum(counts.values())
    if total_chars == 0:
        # Might only be digits or symbols
        return {
            "primary_language": "en",  # Default digits/symbols to English
            "detected_languages": ["en"],
            "is_mixed": False,
            "confidence": 0.5,
            "warning": "Text consists mostly of digits or symbols; defaulted to English.",
            "is_supported": True,
        }

    detected_langs = [lang for lang, cnt in counts.items() if cnt >= 2 and (cnt / total_chars) >= 0.05]

    # Sort by character count descending
    detected_langs.sort(key=lambda l: counts[l], reverse=True)

    if not detected_langs:
        detected_langs = [max(counts, key=counts.get)]

    # If both a regional language (hi/kn/te) and English are present, prioritize the regional language as primary
    # because kachha bills often have English headers/digits but regional item names
    regional_langs = [l for l in detected_langs if l in ("hi", "kn", "te")]
    if regional_langs and "en" in detected_langs:
        primary = regional_langs[0]
        is_mixed = True
    else:
        primary = detected_langs[0]
        is_mixed = len(detected_langs) > 1

    primary_ratio = counts[primary] / max(total_chars, 1)
    confidence = round(min(0.99, max(0.5, primary_ratio)), 2)

    return {
        "primary_language": primary,
        "detected_languages": detected_langs,
        "is_mixed": is_mixed,
        "confidence": confidence,
        "warning": None,
        "is_supported": True,
    }


def get_ocr_language_hints(selected_language: str) -> List[str]:
    """Get Google Cloud Vision language hints for a given selection.
    Selection can be 'auto', 'en', 'hi', 'kn', 'te'.
    Always only uses the 4 supported language codes.
    """
    if selected_language == "auto":
        return ["hi", "kn", "te", "en"]
    if selected_language in SUPPORTED_LANGUAGE_CODES:
        # Include English as secondary hint for numbers/symbols
        if selected_language == "en":
            return ["en"]
        return [selected_language, "en"]
    # Fallback
    return ["hi", "kn", "te", "en"]


def validate_selected_language(lang_code: str) -> bool:
    """Validate that language code is strictly in the 4 supported languages or 'auto'."""
    return lang_code in ("auto", "en", "hi", "kn", "te")
