"""Configuration settings for HisabAI application."""

import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "hisab_ai.db"

# Server configuration
HOST = os.environ.get("HISAB_HOST", "127.0.0.1")
PORT = int(os.environ.get("HISAB_PORT", "8000"))
DEBUG = os.environ.get("HISAB_DEBUG", "True").lower() in ("true", "1", "yes")

# Upload limits
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/tiff",
}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".tiff"}

# Exactly four supported languages
SUPPORTED_LANGUAGES = {
    "en": {"name": "English", "native": "English", "script": "Latin"},
    "hi": {"name": "Hindi", "native": "हिंदी", "script": "Devanagari"},
    "kn": {"name": "Kannada", "native": "ಕನ್ನಡ", "script": "Kannada"},
    "te": {"name": "Telugu", "native": "తెలుగు", "script": "Telugu"},
}

DEFAULT_LANGUAGE = "auto"  # Auto-detect is the default

# Google Cloud Vision configuration
# Can use GOOGLE_VISION_API_KEY (REST API) or GOOGLE_APPLICATION_CREDENTIALS (Service Account JSON)
GOOGLE_VISION_API_KEY = os.environ.get("GOOGLE_VISION_API_KEY", "").strip()
GOOGLE_APPLICATION_CREDENTIALS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
VISION_API_ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"
OCR_TIMEOUT_SECONDS = int(os.environ.get("OCR_TIMEOUT_SECONDS", "15"))

# Secret key for session tokens
SECRET_KEY = os.environ.get("HISAB_SECRET_KEY", "hisabai-secret-kirana-key-2026")
