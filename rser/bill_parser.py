"""Structured Bill Parser for Kachha Bills in English, Hindi, Kannada, and Telugu."""

import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from app.language.detector import normalize_native_digits
from app.parser.product_catalog import ProductCatalogMatcher

# Recognized unit synonyms across all 4 supported languages
UNITS_REGEX = (
    r"(?:\b|(?<=\d))(?:kg|kgs|kilo|g|gm|gms|gram|grams|ltr|lt|liter|litre|litres|ml|packet|packets|pkt|pkts|"
    r"piece|pieces|pcs|pc|box|boxes|bag|bags|bottle|bottles|dozen|dz|"
    r"किलो|किग्रा|ग्राम|लीटर|ली|पैकेट|पैक|पीस|नग|बोरी|डिब्बा|दर्जन|"
    r"ಕೆಜಿ|ಕಿಲೋಗ್ರಾಂ|ಗ್ರಾಂ|ಲೀಟರ್|ಲೀ|ಪ್ಯಾಕೆಟ್|ಪೀಸ್|ಬಾಕ್ಸ್|ಚೀಲ|ಡಜನ್|"
    r"కేజీ|కిలో|గ్రాములు|లీటరు|లీ|ప్యాకెట్|పీస్|బాక్స్|సంచి|డజను)(?:\b|(?=\s))"
)

# Canonical mapping for recognized units
UNIT_CANONICAL = {
    # English
    "kg": "kg", "kgs": "kg", "kilo": "kg", "g": "g", "gm": "g", "gms": "g", "gram": "g", "grams": "g",
    "ltr": "ltr", "lt": "ltr", "liter": "ltr", "litre": "ltr", "litres": "ltr", "ml": "ml",
    "packet": "packet", "packets": "packet", "pkt": "packet", "pkts": "packet",
    "piece": "pcs", "pieces": "pcs", "pcs": "pcs", "pc": "pcs",
    "box": "box", "boxes": "box", "bag": "bag", "bags": "bag",
    "bottle": "bottle", "bottles": "bottle", "dozen": "dozen", "dz": "dozen",
    # Hindi
    "किलो": "kg", "किग्रा": "kg", "ग्राम": "g", "लीटर": "ltr", "ली": "ltr",
    "पैकेट": "packet", "पैक": "packet", "पीस": "pcs", "नग": "pcs",
    "बोरी": "bag", "डिब्बा": "box", "दर्जन": "dozen",
    # Kannada
    "ಕೆಜಿ": "kg", "ಕಿಲೋಗ್ರಾಂ": "kg", "ಗ್ರಾಂ": "g", "ಲೀಟರ್": "ltr", "ಲೀ": "ltr",
    "ಪ್ಯಾಕೆಟ್": "packet", "ಪೀಸ್": "pcs", "ಬಾಕ್ಸ್": "box", "ಚೀಲ": "bag", "ಡಜನ್": "dozen",
    # Telugu
    "కేజీ": "kg", "కిలో": "kg", "గ్రాములు": "g", "లీటరు": "ltr", "లీ": "ltr",
    "ప్యాకెట్": "packet", "పీస్": "pcs", "బాక్స్": "box", "సంచి": "bag", "డజను": "dozen",
}

# Bill Number keywords across 4 languages
BILL_NO_KEYWORDS = [
    r"bill\s*no\.?", r"bill\s*#", r"invoice\s*no\.?", r"cash\s*memo", r"memo\s*no\.?",
    r"बिल\s*नं\.?", r"बिल\s*नंबर", r"रसीद\s*नं\.?",
    r"ಬಿಲ್\s*ನಂ\.?", r"ಬಿಲ್\s*ಸಂಖ್ಯೆ",
    r"బిల్\s*నెం\.?", r"బిల్\s*సంఖ్య",
]

# Date keywords across 4 languages
DATE_KEYWORDS = [
    r"date", r"dt\.?", r"दिनांक", r"तारीख", r"ದಿನಾಂಕ", r"తేదీ",
]

# Total keywords across 4 languages
TOTAL_KEYWORDS = [
    r"grand\s*total", r"g\.?\s*total", r"net\s*total", r"total\s*amount", r"(?<!sub\s)(?<!sub-)total",
    r"कुल\s*योग", r"कुल\s*राशि", r"कुल",
    r"ಒಟ್ಟು\s*ಮೊತ್ತ", r"ಒಟ್ಟು",
    r"మొత్తం\s*రూ\.?", r"మొత్తం",
]

# Subtotal keywords
SUBTOTAL_KEYWORDS = [
    r"sub\s*total", r"sub-total", r"उप\s*योग", r"उपकुल", r"ಉಪ\s*ಮೊತ್ತ", r"ఉప\s*మొత్తం",
]

# Discount keywords
DISCOUNT_KEYWORDS = [
    r"discount", r"disc\.?", r"छूट", r"कटौती", r"ರಿಯಾಯಿತಿ", r"ತಗ್ಗಿంపు",
]

# Tax keywords
TAX_KEYWORDS = [
    r"tax", r"gst", r"cgst", r"sgst", r"vat", r"कर", r"ತೆರಿಗೆ", r"పన్ను",
]


class BillParser:
    """Parses raw OCR text into structured bill metadata and line items."""

    def __init__(self, catalog_matcher: Optional[ProductCatalogMatcher] = None):
        self.catalog = catalog_matcher or ProductCatalogMatcher([])

    def parse(self, raw_text: str, default_date: Optional[str] = None) -> Dict[str, Any]:
        """Convert OCR text into a structured bill document."""
        if not raw_text or not raw_text.strip():
            return self._empty_bill(default_date)

        # Normalize native digits (Devanagari, Kannada, Telugu) to Arabic 0-9
        normalized_text = normalize_native_digits(raw_text)
        lines = [line.strip() for line in normalized_text.splitlines() if line.strip()]

        bill_number: Optional[str] = None
        bill_date: Optional[str] = None
        grand_total: Optional[float] = None
        subtotal: Optional[float] = None
        discount: Optional[float] = None
        tax: Optional[float] = None

        extracted_items: List[Dict[str, Any]] = []
        item_lines: List[str] = []

        # Step 1: Scan lines for header and footer metadata
        for line in lines:
            # Check for bill number
            if not bill_number:
                b_no = self._extract_bill_number(line)
                if b_no:
                    bill_number = b_no
                    continue

            # Check for date
            if not bill_date:
                b_date = self._extract_date(line)
                if b_date:
                    bill_date = b_date
                    continue

            # Check for Subtotal
            s_tot = self._extract_amount_with_keywords(line, SUBTOTAL_KEYWORDS)
            if s_tot is not None:
                subtotal = s_tot
                continue

            # Check for Grand Total
            g_tot = self._extract_amount_with_keywords(line, TOTAL_KEYWORDS)
            if g_tot is not None:
                grand_total = g_tot
                continue

            # Check for Discount
            d_amt = self._extract_amount_with_keywords(line, DISCOUNT_KEYWORDS)
            if d_amt is not None:
                discount = d_amt
                continue

            # Check for Tax
            t_amt = self._extract_amount_with_keywords(line, TAX_KEYWORDS)
            if t_amt is not None:
                tax = t_amt
                continue

            # Skip table header lines (e.g. "Item Qty Rate Amount")
            if self._is_table_header(line):
                continue

            # Skip pure shop title / greeting / footer lines
            if self._is_ignorable_non_item_line(line):
                continue

            item_lines.append(line)

        # Step 2: Parse line items
        for line in item_lines:
            item = self._parse_item_line(line)
            if item:
                extracted_items.append(item)

        # Step 3: Validate arithmetic and cross-check totals
        validation = self._validate_and_reconcile(
            items=extracted_items,
            subtotal=subtotal,
            discount=discount,
            tax=tax,
            grand_total=grand_total,
        )

        final_bill_date = bill_date or default_date or datetime.utcnow().strftime("%Y-%m-%d")

        return {
            "id": f"bill_{uuid.uuid4().hex[:12]}",
            "bill_number": bill_number,
            "bill_date": final_bill_date,
            "subtotal": validation["subtotal"],
            "discount": validation["discount"],
            "tax": validation["tax"],
            "grand_total": validation["grand_total"],
            "items": extracted_items,
            "validation": validation,
            "needs_review": validation["needs_review"] or any(item.get("needs_review") for item in extracted_items),
            "review_reasons": validation["review_reasons"],
        }

    def _extract_bill_number(self, line: str) -> Optional[str]:
        for kw in BILL_NO_KEYWORDS:
            match = re.search(rf"{kw}\s*[:\-#]?\s*([A-Za-z0-9\-_]+)", line, re.IGNORECASE)
            if match:
                val = match.group(1).strip()
                # Exclude purely alphabetic words that are false positives like 'no' or 'bill'
                if val.lower() not in ("no", "bill", "memo"):
                    return val
        return None

    def _extract_date(self, line: str) -> Optional[str]:
        # Indian formats: DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY, DD/MM/YY
        date_patterns = [
            r"\b(0?[1-9]|[12][0-9]|3[01])[\/\-\.](0?[1-9]|1[012])[\/\-\.](20\d\d|\d{2})\b",
            r"\b(20\d\d)[\/\-\.](0?[1-9]|1[012])[\/\-\.](0?[1-9]|[12][0-9]|3[01])\b",
        ]
        for pat in date_patterns:
            m = re.search(pat, line)
            if m:
                p1, p2, p3 = m.group(1), m.group(2), m.group(3)
                try:
                    if len(p1) == 4:  # YYYY-MM-DD
                        year, month, day = int(p1), int(p2), int(p3)
                    else:  # DD-MM-YYYY or DD-MM-YY
                        day, month = int(p1), int(p2)
                        year = int(p3)
                        if year < 100:
                            year += 2000
                    return f"{year:04d}-{month:02d}-{day:02d}"
                except ValueError:
                    continue
        return None

    def _extract_amount_with_keywords(self, line: str, keywords: List[str]) -> Optional[float]:
        for kw in keywords:
            pat = rf"{kw}\s*[:\-]?\s*(?:rs\.?|inr|₹)?\s*([0-9]+(?:\.[0-9]{1,2})?)"
            m = re.search(pat, line, re.IGNORECASE)
            if m:
                try:
                    return float(m.group(1))
                except ValueError:
                    pass
        return None

    def _is_table_header(self, line: str) -> bool:
        low = line.lower()
        header_words = [
            "item", "items", "particulars", "description", "qty", "quantity", "rate", "price", "amount", "s.no", "sl.no",
            # Hindi
            "सामान", "विवरण", "मात्रा", "दर", "भाव", "रुपये", "रुपया", "कीमत",
            # Kannada
            "ವಿವರ", "ಪ್ರಮಾಣ", "ದರ", "ಮೊತ್ತ", "ವಸ್ತು", "ಬೆಲೆ",
            # Telugu
            "వివరాలు", "పరిమాణం", "ధర", "మొత్తం", "వస్తువు", "రేటు",
        ]
        matches = sum(1 for w in header_words if w in low)
        return matches >= 2

    def _is_ignorable_non_item_line(self, line: str) -> bool:
        low = line.lower()
        ignore_words = [
            "thank you", "visit again", "धन्यवाद", "फिर मिलेंगे", "ಧನ್ಯವಾದಗಳು", "ಧನ್ಯವಾದ", "ధన్యవాదాలు", "ధన్యవాదం",
            "terms & conditions", "gstin", "ph:", "phone:", "mob:", "mobile:", "cash memo",
            "store", "stores", "स्टोर", "दुकान", "ಸ್ಟೋರ್ಸ್", "ಸ್ಟೋರ್", "స్టోర్స్", "స్టోర్",
            "supermarket", "mart", "kirana", "किराना",
        ]
        return any(w in low for w in ignore_words)

    def _parse_item_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse a single item row preserving original script and detecting quantity, unit, price, and line total."""
        # Clean line of leading serial numbers like "1.", "1)", "1 - "
        clean_line = re.sub(r"^\s*\d+[\.\)\-]\s*", "", line).strip()
        if not clean_line:
            return None

        # Detect unit if present
        unit_match = re.search(UNITS_REGEX, clean_line, re.IGNORECASE)
        unit: Optional[str] = None
        canonical_unit: Optional[str] = None
        if unit_match:
            unit = unit_match.group(0).strip().lower()
            canonical_unit = UNIT_CANONICAL.get(unit, unit)

        # Extract all numeric values
        # Match standalone numbers or decimals (e.g. 2, 2.5, 44, 150.00)
        number_tokens = []
        for m in re.finditer(r"\b([0-9]+(?:\.[0-9]{1,2})?)\b", clean_line):
            number_tokens.append({
                "value": float(m.group(1)),
                "raw": m.group(1),
                "start": m.start(),
                "end": m.end(),
            })

        if not number_tokens:
            # If line has no numbers, only treat as item if a unit is present or catalog alias matches
            matched = self.catalog.find_match(clean_line)
            if not matched and not unit:
                return None

            item_name = clean_line
            return {
                "id": f"item_{uuid.uuid4().hex[:8]}",
                "item_name_original": item_name,
                "item_name_standard": matched["standard_name"] if matched else None,
                "quantity": None,
                "unit": canonical_unit,
                "unit_price": None,
                "line_total": None,
                "needs_review": True,
                "confidence_flags": "missing_price_and_qty",
                "review_reason": "No price or quantity recognized on this line.",
            }

        # Identify item name text: usually everything before the first number or around numbers
        first_num = number_tokens[0]
        last_num = number_tokens[-1]

        # Extract item text by removing numbers and units
        name_candidate = clean_line[:first_num["start"]].strip()
        # If empty before first number (e.g. "2 kg Sugar 88"), extract text after unit
        if len(name_candidate) < 2:
            # Check after last number or between
            remaining = re.sub(r"\b[0-9]+(?:\.[0-9]{1,2})?\b", "", clean_line)
            if unit:
                remaining = re.sub(rf"\b{re.escape(unit)}\b", "", remaining, flags=re.IGNORECASE)
            remaining = re.sub(r"[@xX=₹\-\:]", "", remaining).strip()
            name_candidate = remaining

        # Clean trailing symbols
        name_candidate = re.sub(r"[@xX=₹\-\:]+$", "", name_candidate).strip()

        # If name is still empty or too short, set placeholder
        if len(name_candidate) < 1:
            name_candidate = "Item"

        # Determine quantity, unit price, and line total from number tokens
        quantity: Optional[float] = None
        unit_price: Optional[float] = None
        line_total: Optional[float] = None
        needs_review = False
        review_reasons = []

        if len(number_tokens) == 1:
            # Only one number on the line: could be price/total or quantity
            val = number_tokens[0]["value"]
            if unit_match and unit_match.start() >= number_tokens[0]["end"]:
                # Number immediately preceding a unit -> Quantity
                quantity = val
                needs_review = True
                review_reasons.append("Missing price; only quantity detected.")
            else:
                # Typically line total
                line_total = val
                quantity = 1.0  # default assumption if only total present
                needs_review = True
                review_reasons.append("Unit price not specified; verified line total.")

        elif len(number_tokens) == 2:
            # Two numbers: typically [Qty, Total] or [Rate, Total] or [Qty, Rate]
            n1 = number_tokens[0]["value"]
            n2 = number_tokens[1]["value"]

            # If "@ rate" or "x rate" pattern exists:
            if re.search(r"[@xX]\s*" + re.escape(number_tokens[1]["raw"]), clean_line):
                quantity = n1
                unit_price = n2
                line_total = round(quantity * unit_price, 2)
            elif unit_match and unit_match.start() >= number_tokens[0]["end"]:
                # n1 is adjacent to unit -> quantity
                quantity = n1
                line_total = n2
                if quantity > 0:
                    unit_price = round(line_total / quantity, 2)
            else:
                # Default: smaller integer as quantity, larger as line_total
                if n1 <= n2 and (n1 < 50):
                    quantity = n1
                    line_total = n2
                    if quantity > 0:
                        unit_price = round(line_total / quantity, 2)
                else:
                    quantity = 1.0
                    unit_price = n1
                    line_total = n2

        elif len(number_tokens) >= 3:
            # Three numbers: [Qty, Rate, Total]
            n1 = number_tokens[0]["value"]
            n2 = number_tokens[1]["value"]
            n3 = number_tokens[2]["value"]

            quantity = n1
            unit_price = n2
            line_total = n3

            # Validate arithmetic: quantity * unit_price == line_total
            expected_total = round(quantity * unit_price, 2)
            if abs(expected_total - line_total) > 0.05:
                needs_review = True
                review_reasons.append(
                    f"Arithmetic mismatch: {quantity} x ₹{unit_price} = ₹{expected_total}, but line total is ₹{line_total}."
                )

        # Look up standard catalog item
        matched_catalog = self.catalog.find_match(name_candidate)

        flags = []
        if needs_review:
            flags.extend(review_reasons)

        return {
            "id": f"item_{uuid.uuid4().hex[:8]}",
            "item_name_original": name_candidate,  # Preserved in original script!
            "item_name_standard": matched_catalog["standard_name"] if matched_catalog else None,
            "quantity": quantity,
            "unit": canonical_unit,
            "unit_price": unit_price,
            "line_total": line_total,
            "needs_review": needs_review,
            "confidence_flags": "; ".join(flags) if flags else "verified",
            "review_reason": "; ".join(review_reasons) if review_reasons else None,
        }

    def _validate_and_reconcile(
        self,
        items: List[Dict[str, Any]],
        subtotal: Optional[float],
        discount: Optional[float],
        tax: Optional[float],
        grand_total: Optional[float],
    ) -> Dict[str, Any]:
        """Validate mathematical consistency across line totals, taxes, discounts, and grand total."""
        needs_review = False
        reasons = []

        # Sum up valid line totals
        valid_line_totals = [it["line_total"] for it in items if it.get("line_total") is not None]
        calculated_subtotal = round(sum(valid_line_totals), 2) if valid_line_totals else 0.0

        disc = discount or 0.0
        tx = tax or 0.0

        expected_grand_total = round(calculated_subtotal - disc + tx, 2)

        final_subtotal = subtotal if subtotal is not None else calculated_subtotal

        final_grand_total: float
        if grand_total is not None:
            final_grand_total = grand_total
            if abs(final_grand_total - expected_grand_total) > 0.5 and valid_line_totals:
                needs_review = True
                reasons.append(
                    f"Grand total mismatch: Extracted total is ₹{final_grand_total}, "
                    f"but sum of items (₹{calculated_subtotal}) - discount (₹{disc}) + tax (₹{tx}) = ₹{expected_grand_total}."
                )
        else:
            final_grand_total = expected_grand_total
            if not valid_line_totals:
                needs_review = True
                reasons.append("Grand total could not be determined automatically.")

        if any(item.get("needs_review") for item in items):
            needs_review = True

        return {
            "subtotal": final_subtotal,
            "discount": disc,
            "tax": tx,
            "grand_total": final_grand_total,
            "calculated_total": expected_grand_total,
            "needs_review": needs_review,
            "review_reasons": reasons,
        }

    def _empty_bill(self, default_date: Optional[str]) -> Dict[str, Any]:
        return {
            "id": f"bill_{uuid.uuid4().hex[:12]}",
            "bill_number": None,
            "bill_date": default_date or datetime.utcnow().strftime("%Y-%m-%d"),
            "subtotal": 0.0,
            "discount": 0.0,
            "tax": 0.0,
            "grand_total": 0.0,
            "items": [],
            "validation": {
                "subtotal": 0.0,
                "discount": 0.0,
                "tax": 0.0,
                "grand_total": 0.0,
                "calculated_total": 0.0,
                "needs_review": True,
                "review_reasons": ["No bill text provided."],
            },
            "needs_review": True,
            "review_reasons": ["No bill text provided."],
        }
