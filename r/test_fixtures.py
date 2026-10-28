"""Representative bill test fixtures and synthetic image generator for testing and demonstration."""

import io
from typing import Any, Dict, Optional
from PIL import Image, ImageDraw, ImageFilter, ImageFont


def create_synthetic_bill_image(lines: list, is_blurry: bool = False, bg_color=(252, 250, 245)) -> bytes:
    """Generate a clean or blurry synthetic bill image using Pillow."""
    width, height = 650, 800
    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)

    # Draw border simulating paper receipt
    draw.rectangle([10, 10, width - 10, height - 10], outline=(200, 195, 185), width=2)

    y = 40
    for line in lines:
        if line == "---":
            draw.line([30, y, width - 30, y], fill=(180, 180, 180), width=1)
            y += 15
            continue

        # Simple text rendering using default font
        draw.text((35, y), line, fill=(20, 20, 20))
        y += 28

    if is_blurry:
        # Apply gaussian blur filter
        img = img.filter(ImageFilter.GaussianBlur(radius=6))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


# Representative test fixtures
FIXTURES = {
    # 1. Hindi Handwritten Kachha Bill
    "sample_hi_kachha": {
        "filename": "hindi_kachha_bill.jpg",
        "language": "hi",
        "title": "हाथ से लिखा कच्चा बिल (Hindi)",
        "fixture_text": (
            "श्री गणेश किराना स्टोर\n"
            "दिनांक: 25/10/2026\n"
            "बिल नं: 104\n"
            "सामान          मात्रा    दर     रुपये\n"
            "चीनी            2 kg    44     88\n"
            "सरसों तेल       1 ltr   155    155\n"
            "आटा            5 kg    38     190\n"
            "तूर दाल         1 kg    160    160\n"
            "चाय पत्ती       1 pkt   120    120\n"
            "कुल योग: 713\n"
            "धन्यवाद फिर मिलेंगे"
        ),
        "visual_lines": [
            "Shree Ganesh Kirana Store",
            "Date: 25/10/2026   Bill No: 104",
            "---",
            "Item        Qty    Rate   Amount",
            "---",
            "Chini       2 kg   44     88",
            "Sarso Tel   1 ltr  155    155",
            "Atta        5 kg   38     190",
            "Toor Dal    1 kg   160    160",
            "Chai Patti  1 pkt  120    120",
            "---",
            "Total: Rs. 713",
            "---",
            "Thank You Visit Again",
        ],
    },

    # 2. Kannada Bill
    "sample_kn_kachha": {
        "filename": "kannada_kachha_bill.jpg",
        "language": "kn",
        "title": "ಕೈಬರಹದ ಬಿಲ್ (Kannada)",
        "fixture_text": (
            "ಶ್ರೀ ವೆಂಕಟೇಶ್ವರ ಸ್ಟೋರ್ಸ್\n"
            "ದಿನಾಂಕ: 24/10/2026\n"
            "ಬಿಲ್ ನಂ: 85\n"
            "ವಿವರ            ಪ್ರಮಾಣ    ದರ    ಮೊತ್ತ\n"
            "ಸಕ್ಕರೆ          2 kg     44    88\n"
            "ಅಕ್ಕಿ           5 kg     60    300\n"
            "ಹಾಲು           1 ltr    32    32\n"
            "ಎಣ್ಣೆ           1 ltr    150   150\n"
            "ಒಟ್ಟು ಮೊತ್ತ: 570\n"
            "ಧನ್ಯವಾದಗಳು"
        ),
        "visual_lines": [
            "Sri Venkateshwara Stores",
            "Date: 24/10/2026   Bill No: 85",
            "---",
            "Item       Qty    Rate   Amount",
            "---",
            "Sakkare    2 kg   44     88",
            "Akki       5 kg   60     300",
            "Haalu      1 ltr  32     32",
            "Enne       1 ltr  150    150",
            "---",
            "Total: Rs. 570",
            "---",
            "Thank You",
        ],
    },

    # 3. Telugu Bill
    "sample_te_kachha": {
        "filename": "telugu_kachha_bill.jpg",
        "language": "te",
        "title": "చేతిరాత బిల్లు (Telugu)",
        "fixture_text": (
            "లక్ష్మి జనరల్ స్టోర్స్\n"
            "తేదీ: 26/10/2026\n"
            "బిల్ నెం: 210\n"
            "వివరాలు         పరిమాణం   ధర     మొత్తం\n"
            "చక్కెర          2 kg     44     88\n"
            "బియ్యం         5 kg     60     300\n"
            "నూనె           1 ltr    150    150\n"
            "పాలు           2 ltr    32     64\n"
            "మొత్తం: 602\n"
            "ధన్యవాదాలు"
        ),
        "visual_lines": [
            "Lakshmi General Stores",
            "Date: 26/10/2026   Bill No: 210",
            "---",
            "Item       Qty    Rate   Amount",
            "---",
            "Chakkera   2 kg   44     88",
            "Biyyam     5 kg   60     300",
            "Noone      1 ltr  150    150",
            "Paalu      2 ltr  32     64",
            "---",
            "Total: Rs. 602",
            "---",
            "Thank You",
        ],
    },

    # 4. Printed English Bill
    "sample_en_printed": {
        "filename": "printed_english_bill.jpg",
        "language": "en",
        "title": "Printed English Retail Bill",
        "fixture_text": (
            "APEX SUPERMARKET\n"
            "Date: 27/10/2026\n"
            "Bill No: 4502\n"
            "Item Name       Qty   Price   Total\n"
            "Basmati Rice    5 kg  65.00   325.00\n"
            "Sunflower Oil   2 ltr 140.00  280.00\n"
            "Sugar           3 kg  44.00   132.00\n"
            "Bathing Soap    4 pcs 35.00   140.00\n"
            "Sub Total: 877.00\n"
            "Discount: 27.00\n"
            "Grand Total: 850.00\n"
            "Thank You"
        ),
        "visual_lines": [
            "APEX SUPERMARKET",
            "Date: 27/10/2026   Bill No: 4502",
            "---",
            "Item            Qty   Price   Total",
            "---",
            "Basmati Rice    5 kg  65.00   325.00",
            "Sunflower Oil   2 ltr 140.00  280.00",
            "Sugar           3 kg  44.00   132.00",
            "Bathing Soap    4 pcs 35.00   140.00",
            "---",
            "Sub Total: Rs. 877.00",
            "Discount:  Rs.  27.00",
            "Grand Total: Rs. 850.00",
            "---",
            "Thank you for shopping!",
        ],
    },

    # 5. Mixed English + Hindi Bill
    "sample_mixed_hi_en": {
        "filename": "mixed_bill.jpg",
        "language": "auto",
        "title": "Mixed English + Hindi Bill",
        "fixture_text": (
            "KIRANA CASH MEMO\n"
            "Date: 25/10/2026\n"
            "Bill No: 331\n"
            "1. चीनी 2 kg 88\n"
            "2. सरसों तेल 1 ltr 150\n"
            "3. Tata Salt 1 pkt 25\n"
            "4. साबुन 3 pcs 105\n"
            "Total: 368\n"
        ),
        "visual_lines": [
            "KIRANA CASH MEMO",
            "Date: 25/10/2026   Bill No: 331",
            "---",
            "1. Chini    2 kg   88",
            "2. Oil      1 ltr  150",
            "3. Tata Salt 1 pkt 25",
            "4. Sabun    3 pcs  105",
            "---",
            "Total Amount: Rs. 368",
        ],
    },

    # 6. Blurry / Out of Focus Edge Case
    "sample_blurry_bill": {
        "filename": "blurry_bill.jpg",
        "language": "en",
        "title": "Blurry Bill (Edge Case)",
        "is_blurry": True,
        "fixture_text": (
            "KIRANA STORE\n"
            "Bill No: 99\n"
            "Rice 10kg 600\n"
            "Total: 600"
        ),
        "visual_lines": [
            "BLURRY FAINT BILL",
            "Bill No: 99",
            "Rice 10kg 600",
            "Total: 600",
        ],
    },

    # 7. Arithmetic Discrepancy Edge Case
    "sample_math_mismatch": {
        "filename": "arithmetic_mismatch_bill.jpg",
        "language": "en",
        "title": "Arithmetic Discrepancy Bill",
        "fixture_text": (
            "QUICK MART\n"
            "Date: 25/10/2026\n"
            "Bill No: 777\n"
            "Sugar 2 kg @ 50 = 120\n"  # 2 * 50 = 100, but says 120!
            "Rice 5 kg @ 60 = 300\n"
            "Grand Total: 500\n"       # 120 + 300 = 420, but says 500!
        ),
        "visual_lines": [
            "QUICK MART",
            "Date: 25/10/2026   Bill No: 777",
            "---",
            "Sugar 2 kg @ 50 = 120 (Math error: 2x50=100)",
            "Rice  5 kg @ 60 = 300",
            "---",
            "Grand Total: 500 (Mismatch with sum)",
        ],
    },
}


def get_test_fixture(sample_id: str) -> Optional[Dict[str, Any]]:
    """Get fixture data with dynamically rendered image bytes."""
    fixture = FIXTURES.get(sample_id)
    if not fixture:
        return None

    img_bytes = create_synthetic_bill_image(
        fixture.get("visual_lines", ["Sample Bill"]),
        is_blurry=fixture.get("is_blurry", False),
    )

    return {
        "sample_id": sample_id,
        "filename": fixture["filename"],
        "language": fixture["language"],
        "title": fixture["title"],
        "fixture_text": fixture["fixture_text"],
        "bytes": img_bytes,
        "is_blurry": fixture.get("is_blurry", False),
    }
