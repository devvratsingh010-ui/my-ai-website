"""Authentication, session management, and database seeding."""

import hashlib
import hmac
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
from app.database import get_db_connection

SALT_LENGTH = 16
ITERATIONS = 100_000


def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256."""
    salt = os.urandom(SALT_LENGTH)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return f"{salt.hex()}${key.hex()}"


def verify_password(stored_hash: str, password: str) -> bool:
    """Verify password against stored hash."""
    try:
        salt_hex, key_hex = stored_hash.split("$")
        salt = bytes.fromhex(salt_hex)
        expected_key = bytes.fromhex(key_hex)
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
        return hmac.compare_digest(key, expected_key)
    except Exception:
        return False


def create_session(user_id: str, shop_id: str, duration_days: int = 7) -> str:
    """Generate and store a new session token."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=duration_days)
    conn = get_db_connection()
    with conn:
        conn.execute(
            """
            INSERT INTO sessions (token, user_id, shop_id, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (token, user_id, shop_id, expires_at.isoformat()),
        )
    return token


def validate_session(token: str) -> Optional[Dict[str, Any]]:
    """Validate token and return user & shop info, or None if invalid/expired."""
    if not token:
        return None
    conn = get_db_connection()
    cur = conn.execute(
        """
        SELECT s.token, s.user_id, s.shop_id, s.expires_at,
               u.username, u.full_name, u.role,
               sh.name as shop_name, sh.business_category
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        JOIN shops sh ON s.shop_id = sh.id
        WHERE s.token = ?
        """,
        (token,),
    )
    row = cur.fetchone()
    if not row:
        return None

    # Check expiration
    expires_at_str = row["expires_at"]
    try:
        expires_at = datetime.fromisoformat(expires_at_str)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            # Expired
            delete_session(token)
            return None
    except Exception:
        return None

    return dict(row)


def delete_session(token: str) -> None:
    """Delete a session token on logout."""
    conn = get_db_connection()
    with conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def seed_default_data() -> None:
    """Seed initial shops, shopkeeper users, and product catalog aliases."""
    conn = get_db_connection()

    # Check if already seeded
    cur = conn.execute("SELECT COUNT(*) as cnt FROM shops")
    if cur.fetchone()["cnt"] > 0:
        return

    with conn:
        # Shop 1: Ramesh Gupta Kirana Store
        shop1_id = "shop_ramesh_kirana"
        conn.execute(
            """
            INSERT OR IGNORE INTO shops (id, name, business_category, owner_name, phone, address)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (shop1_id, "Shree Ganesh Kirana Store", "kirana", "Ramesh Gupta", "+91 98765 43210", "Main Market, Kanpur"),
        )
        user1_id = "user_ramesh"
        conn.execute(
            """
            INSERT OR IGNORE INTO users (id, shop_id, username, password_hash, full_name, role)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user1_id, shop1_id, "ramesh", hash_password("kirana123"), "Ramesh Gupta", "owner"),
        )

        # Shop 2: Suresh Rao General Store (for multi-tenancy verification)
        shop2_id = "shop_suresh_general"
        conn.execute(
            """
            INSERT OR IGNORE INTO shops (id, name, business_category, owner_name, phone, address)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (shop2_id, "Sri Venkateshwara Stores", "general_store", "Suresh Rao", "+91 91234 56789", "Gandhi Circle, Bengaluru"),
        )
        user2_id = "user_suresh"
        conn.execute(
            """
            INSERT OR IGNORE INTO users (id, shop_id, username, password_hash, full_name, role)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user2_id, shop2_id, "suresh", hash_password("kirana123"), "Suresh Rao", "owner"),
        )

        # Seed product aliases for Shop 1 (Hindi & English)
        aliases_data = [
            # Standard name, Alias name, Language, default unit, default price
            ("Sugar", "चीनी", "hi", "kg", 44.0),
            ("Sugar", "शक्कर", "hi", "kg", 44.0),
            ("Sugar", "Sugar", "en", "kg", 44.0),
            ("Basmati Rice", "चावल", "hi", "kg", 65.0),
            ("Basmati Rice", "Rice", "en", "kg", 65.0),
            ("Wheat Flour", "आटा", "hi", "kg", 38.0),
            ("Wheat Flour", "Atta", "en", "kg", 38.0),
            ("Cooking Oil", "सरसों तेल", "hi", "ltr", 155.0),
            ("Cooking Oil", "तेल", "hi", "ltr", 150.0),
            ("Cooking Oil", "Oil", "en", "ltr", 150.0),
            ("Toor Dal", "तूर दाल", "hi", "kg", 160.0),
            ("Toor Dal", "अरहर दाल", "hi", "kg", 160.0),
            ("Toor Dal", "दाल", "hi", "kg", 150.0),
            ("Milk", "दूध", "hi", "ltr", 32.0),
            ("Milk", "Milk", "en", "ltr", 32.0),
            ("Tea Powder", "चाय पत्ती", "hi", "packet", 120.0),
            ("Tea Powder", "चाय", "hi", "packet", 120.0),
            ("Tea Powder", "Tea", "en", "packet", 120.0),
            ("Bathing Soap", "साबुन", "hi", "pcs", 35.0),
            ("Bathing Soap", "Soap", "en", "pcs", 35.0),
            ("Salt", "नमक", "hi", "packet", 25.0),
            ("Salt", "Salt", "en", "packet", 25.0),
            ("Turmeric", "हल्दी", "hi", "packet", 40.0),
            ("Chilli Powder", "मिर्च पाउडर", "hi", "packet", 45.0),
            # Kannada Aliases
            ("Sugar", "ಸಕ್ಕರೆ", "kn", "kg", 44.0),
            ("Rice", "ಅಕ್ಕಿ", "kn", "kg", 60.0),
            ("Cooking Oil", "ಎಣ್ಣೆ", "kn", "ltr", 150.0),
            ("Toor Dal", "ತೊಗರಿ ಬೇಳೆ", "kn", "kg", 160.0),
            ("Toor Dal", "ಬೇಳೆ", "kn", "kg", 160.0),
            ("Milk", "ಹಾಲು", "kn", "ltr", 32.0),
            ("Tea Powder", "ಚಹಾ ಪುಡಿ", "kn", "packet", 120.0),
            ("Soap", "ಸಾಬೂನು", "kn", "pcs", 35.0),
            ("Salt", "ಉಪ್ಪು", "kn", "packet", 25.0),
            # Telugu Aliases
            ("Sugar", "చక్కెర", "te", "kg", 44.0),
            ("Rice", "బియ్యం", "te", "kg", 60.0),
            ("Cooking Oil", "నూనె", "te", "ltr", 150.0),
            ("Toor Dal", "కంది పప్పు", "te", "kg", 160.0),
            ("Toor Dal", "పప్పు", "te", "kg", 160.0),
            ("Milk", "పాలు", "te", "ltr", 32.0),
            ("Tea Powder", "టీ పొడి", "te", "packet", 120.0),
            ("Soap", "సబ్బు", "te", "pcs", 35.0),
            ("Salt", "ఉప్పు", "te", "packet", 25.0),
        ]

        for std_name, alias, lang, def_unit, def_price in aliases_data:
            alias_id = f"alias_{shop1_id}_{lang}_{secrets.token_hex(4)}"
            conn.execute(
                """
                INSERT INTO product_aliases (id, shop_id, standard_name, alias_name, language_code, default_unit, default_price)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (alias_id, shop1_id, std_name, alias, lang, def_unit, def_price),
            )
            # Also add to shop 2
            alias_id2 = f"alias_{shop2_id}_{lang}_{secrets.token_hex(4)}"
            conn.execute(
                """
                INSERT INTO product_aliases (id, shop_id, standard_name, alias_name, language_code, default_unit, default_price)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (alias_id2, shop2_id, std_name, alias, lang, def_unit, def_price),
            )
