"""Unit tests for language detection, script analysis, and 4-language constraints."""

import unittest
from app.language.detector import (
    SUPPORTED_LANGUAGE_CODES,
    detect_language,
    get_ocr_language_hints,
    normalize_native_digits,
    validate_selected_language,
)


class TestLanguageSupport(unittest.TestCase):
    """Test strict 4-language support: English, Hindi, Kannada, Telugu."""

    def test_strict_four_languages_allowed(self):
        """Only 'en', 'hi', 'kn', 'te', and 'auto' are allowed."""
        self.assertEqual(SUPPORTED_LANGUAGE_CODES, {"en", "hi", "kn", "te"})
        self.assertTrue(validate_selected_language("en"))
        self.assertTrue(validate_selected_language("hi"))
        self.assertTrue(validate_selected_language("kn"))
        self.assertTrue(validate_selected_language("te"))
        self.assertTrue(validate_selected_language("auto"))

        # Other languages must be rejected
        self.assertFalse(validate_selected_language("fr"))
        self.assertFalse(validate_selected_language("es"))
        self.assertFalse(validate_selected_language("ta"))  # Tamil removed
        self.assertFalse(validate_selected_language("bn"))  # Bengali removed

    def test_hindi_detection(self):
        hindi_text = "श्री गणेश किराना स्टोर\nचीनी 2 kg 88\nआटा 5 kg 190\nकुल योग: 278"
        res = detect_language(hindi_text)
        self.assertEqual(res["primary_language"], "hi")
        self.assertTrue(res["is_supported"])
        self.assertIsNone(res["warning"])

    def test_kannada_detection(self):
        kannada_text = "ಶ್ರೀ ವೆಂಕಟೇಶ್ವರ ಸ್ಟೋರ್ಸ್\nಸಕ್ಕರೆ 2 kg 88\nಅಕ್ಕಿ 5 kg 300\nಒಟ್ಟು: 388"
        res = detect_language(kannada_text)
        self.assertEqual(res["primary_language"], "kn")
        self.assertTrue(res["is_supported"])

    def test_telugu_detection(self):
        telugu_text = "లక్ష్మి జనరల్ స్టోర్స్\nచక్కెర 2 kg 88\nనూనె 1 ltr 150\nమొత్తం: 238"
        res = detect_language(telugu_text)
        self.assertEqual(res["primary_language"], "te")
        self.assertTrue(res["is_supported"])

    def test_english_detection(self):
        en_text = "APEX SUPERMARKET\nSugar 2 kg 88.00\nRice 5 kg 300.00\nTotal: 388.00"
        res = detect_language(en_text)
        self.assertEqual(res["primary_language"], "en")
        self.assertTrue(res["is_supported"])

    def test_mixed_language_detection(self):
        """Bills mixing English headers/numbers with Hindi items."""
        mixed_text = "KIRANA CASH MEMO\nDate: 25/10/2026\nBill No: 104\nचीनी 2 kg 88\nसरसों तेल 1 ltr 155\nTotal: 243"
        res = detect_language(mixed_text)
        self.assertEqual(res["primary_language"], "hi")
        self.assertTrue(res["is_mixed"])
        self.assertIn("en", res["detected_languages"])
        self.assertIn("hi", res["detected_languages"])

    def test_unsupported_language_warning(self):
        """Unsupported languages like Tamil or Bengali should trigger a clear warning."""
        tamil_text = "மளிகை கடை\nஅரிசி 5 கிலோ 250\nமொத்தம்: 250"
        res = detect_language(tamil_text)
        self.assertFalse(res["is_supported"])
        self.assertIn("Unsupported language detected (Tamil)", res["warning"])

    def test_native_digits_normalization(self):
        """Devanagari, Kannada, and Telugu digits normalize to 0-9."""
        devanagari_digits = "२५/१०/२०२६ कुल: ७१३"
        self.assertEqual(normalize_native_digits(devanagari_digits), "25/10/2026 कुल: 713")

        kannada_digits = "೨೪/೧೦/೨೦೨೬ ಒಟ್ಟು: ೫೭೦"
        self.assertEqual(normalize_native_digits(kannada_digits), "24/10/2026 ಒಟ್ಟು: 570")

        telugu_digits = "౨౬/౧౦/౨౦౨౬ మొత్తం: ౬౦౨"
        self.assertEqual(normalize_native_digits(telugu_digits), "26/10/2026 మొత్తం: 602")

    def test_ocr_language_hints(self):
        """Check language hints provided to Google Cloud Vision."""
        self.assertEqual(get_ocr_language_hints("auto"), ["hi", "kn", "te", "en"])
        self.assertEqual(get_ocr_language_hints("hi"), ["hi", "en"])
        self.assertEqual(get_ocr_language_hints("kn"), ["kn", "en"])
        self.assertEqual(get_ocr_language_hints("te"), ["te", "en"])
        self.assertEqual(get_ocr_language_hints("en"), ["en"])


if __name__ == "__main__":
    unittest.main()
