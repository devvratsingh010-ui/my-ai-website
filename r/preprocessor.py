"""Image preprocessing, EXIF orientation correction, validation, and blur detection."""

import hashlib
import io
import math
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from app.config import ALLOWED_EXTENSIONS, ALLOWED_MIME_TYPES, MAX_UPLOAD_SIZE_BYTES


class ImageValidationError(Exception):
    """Raised when an uploaded image fails validation."""
    pass


def compute_image_hash(image_bytes: bytes) -> str:
    """Compute SHA-256 hash of image bytes for duplicate detection."""
    return hashlib.sha256(image_bytes).hexdigest()


def validate_image_file(image_bytes: bytes, filename: str) -> None:
    """Validate image file size, extension, and integrity."""
    if not image_bytes:
        raise ImageValidationError("Empty image file received.")

    if len(image_bytes) > MAX_UPLOAD_SIZE_BYTES:
        max_mb = MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
        raise ImageValidationError(f"File size exceeds maximum allowed size of {max_mb} MB.")

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(ALLOWED_EXTENSIONS)
        raise ImageValidationError(f"Unsupported file format '{ext}'. Allowed formats: {allowed}")

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img.verify()
    except Exception as e:
        raise ImageValidationError(f"Invalid or corrupted image file: {str(e)}")


def detect_blur_and_quality(img: Image.Image) -> Dict[str, Any]:
    """Detect if an image is blurry or has poor lighting/contrast using edge variance."""
    # Convert to grayscale for analysis
    gray = img.convert("L")
    # Resize small for fast analysis
    gray_thumb = gray.copy()
    gray_thumb.thumbnail((400, 400))

    # Calculate edge variance using FIND_EDGES filter
    edges = gray_thumb.filter(ImageFilter.FIND_EDGES)
    stat = list(edges.tobytes())

    # Average edge gradient indicates sharpness (sharp > 3.0, blurry < 2.5)
    mean_edge = sum(stat) / max(len(stat), 1)
    variance = sum((x - mean_edge) ** 2 for x in stat) / max(len(stat), 1)
    std_dev = math.sqrt(variance)

    # Luminance / brightness check
    orig_stat = list(gray_thumb.tobytes())
    avg_brightness = sum(orig_stat) / max(len(orig_stat), 1)

    is_blurry = mean_edge < 3.5  # Threshold for blurry text
    is_poorly_lit = avg_brightness < 30 or avg_brightness > 253

    warning = None
    if is_blurry:
        warning = "The photo appears blurry or out of focus. Text extraction might be incomplete or inaccurate."
    elif is_poorly_lit:
        warning = "The photo lighting is very dim or overexposed. Readable text might be missed."

    return {
        "sharpness_score": round(mean_edge, 2),
        "std_dev": round(std_dev, 2),
        "is_blurry": is_blurry,
        "brightness_score": round(avg_brightness, 2),
        "is_poorly_lit": is_poorly_lit,
        "warning": warning,
    }


def preprocess_bill_image(
    image_bytes: bytes,
    enhance_contrast: bool = True,
    max_dimension: int = 2400,
) -> Tuple[bytes, Dict[str, Any]]:
    """Correct orientation, enhance readability, and normalize image."""
    img = Image.open(io.BytesIO(image_bytes))

    # 1. Correct orientation via EXIF
    original_format = img.format or "JPEG"
    orientation_corrected = False
    try:
        transposed = ImageOps.exif_transpose(img)
        if transposed is not None:
            orientation_corrected = True
            img = transposed
    except Exception:
        pass

    # Ensure RGB
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    elif img.mode == "L":
        img = img.convert("RGB")

    # 2. Check blur and lighting
    quality = detect_blur_and_quality(img)

    # 3. Resize if too massive for OCR (maintaining aspect ratio)
    w, h = img.size
    resized = False
    if max(w, h) > max_dimension:
        ratio = max_dimension / max(w, h)
        new_w = int(w * ratio)
        new_h = int(h * ratio)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        resized = True

    # 4. Readability enhancement: slight contrast boost for pencil/faint ink
    if enhance_contrast:
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.25)
        sharpener = ImageEnhance.Sharpness(img)
        img = sharpener.enhance(1.15)

    # Save processed image to JPEG bytes
    out_buf = io.BytesIO()
    img.save(out_buf, format="JPEG", quality=90, optimize=True)
    processed_bytes = out_buf.getvalue()

    metadata = {
        "original_width": w,
        "original_height": h,
        "final_width": img.size[0],
        "final_height": img.size[1],
        "orientation_corrected": orientation_corrected,
        "resized": resized,
        "quality": quality,
    }

    return processed_bytes, metadata
