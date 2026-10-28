"""Database models, migrations, and Row-Level Security helpers for SQLite."""

import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from app.config import DB_PATH

_thread_local = threading.local()


def get_db_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Get a thread-local SQLite connection with foreign keys and WAL enabled."""
    conn = getattr(_thread_local, "connection", None)
    current_path = getattr(_thread_local, "db_path", None)
    if conn is None or current_path != str(db_path):
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        _thread_local.connection = conn
        _thread_local.db_path = str(db_path)
    return conn


def close_db_connection() -> None:
    """Close the thread-local database connection if open."""
    conn = getattr(_thread_local, "connection", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        _thread_local.connection = None
        _thread_local.db_path = None


def init_db(db_path: Path = DB_PATH) -> None:
    """Initialize database schema with tables and indexes."""
    conn = get_db_connection(db_path)
    with conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS shops (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            business_category TEXT NOT NULL DEFAULT 'kirana',
            owner_name TEXT NOT NULL,
            phone TEXT,
            address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            shop_id TEXT NOT NULL,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'owner',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (shop_id) REFERENCES shops (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            shop_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
            FOREIGN KEY (shop_id) REFERENCES shops (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS product_aliases (
            id TEXT PRIMARY KEY,
            shop_id TEXT NOT NULL,
            standard_name TEXT NOT NULL,
            alias_name TEXT NOT NULL,
            language_code TEXT NOT NULL,
            default_unit TEXT,
            default_price REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (shop_id) REFERENCES shops (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS bills (
            id TEXT PRIMARY KEY,
            shop_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            bill_number TEXT,
            bill_date TEXT NOT NULL,
            subtotal REAL,
            tax REAL DEFAULT 0.0,
            discount REAL DEFAULT 0.0,
            grand_total REAL NOT NULL,
            detected_language TEXT,
            language_used TEXT NOT NULL,
            image_path TEXT,
            image_hash TEXT,
            ocr_raw_text TEXT,
            status TEXT NOT NULL DEFAULT 'verified',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (shop_id) REFERENCES shops (id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS bill_items (
            id TEXT PRIMARY KEY,
            bill_id TEXT NOT NULL,
            shop_id TEXT NOT NULL,
            item_name_original TEXT NOT NULL,
            item_name_standard TEXT,
            quantity REAL,
            unit TEXT,
            unit_price REAL,
            line_total REAL,
            confidence_flags TEXT,
            line_order INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (bill_id) REFERENCES bills (id) ON DELETE CASCADE,
            FOREIGN KEY (shop_id) REFERENCES shops (id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_bills_shop_date ON bills (shop_id, bill_date);
        CREATE INDEX IF NOT EXISTS idx_bills_image_hash ON bills (shop_id, image_hash);
        CREATE INDEX IF NOT EXISTS idx_bill_items_bill_id ON bill_items (bill_id);
        CREATE INDEX IF NOT EXISTS idx_bill_items_shop_standard ON bill_items (shop_id, item_name_standard);
        CREATE INDEX IF NOT EXISTS idx_product_aliases_shop ON product_aliases (shop_id, alias_name);
        """)


class ShopRLS:
    """Row-Level Security wrapper to enforce tenant boundaries by shop_id."""

    def __init__(self, shop_id: str, db_conn: Optional[sqlite3.Connection] = None):
        if not shop_id:
            raise ValueError("shop_id must be provided for RLS context")
        self.shop_id = shop_id
        self.conn = db_conn or get_db_connection()

    def get_shop(self) -> Optional[Dict[str, Any]]:
        cur = self.conn.execute("SELECT * FROM shops WHERE id = ?", (self.shop_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def list_bills(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        cur = self.conn.execute(
            """
            SELECT b.*, u.full_name as created_by_name,
                   (SELECT COUNT(*) FROM bill_items bi WHERE bi.bill_id = b.id) as item_count
            FROM bills b
            LEFT JOIN users u ON b.user_id = u.id
            WHERE b.shop_id = ?
            ORDER BY b.bill_date DESC, b.created_at DESC
            LIMIT ? OFFSET ?
            """,
            (self.shop_id, limit, offset),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_bill(self, bill_id: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.execute(
            """
            SELECT b.*, u.full_name as created_by_name
            FROM bills b
            LEFT JOIN users u ON b.user_id = u.id
            WHERE b.id = ? AND b.shop_id = ?
            """,
            (bill_id, self.shop_id),
        )
        row = cur.fetchone()
        if not row:
            return None
        bill = dict(row)
        # Fetch items
        items_cur = self.conn.execute(
            """
            SELECT * FROM bill_items
            WHERE bill_id = ? AND shop_id = ?
            ORDER BY line_order ASC
            """,
            (bill_id, self.shop_id),
        )
        bill["items"] = [dict(item) for item in items_cur.fetchall()]
        return bill

    def check_duplicate_bill(
        self, image_hash: Optional[str], bill_number: Optional[str], bill_date: str, grand_total: float
    ) -> Optional[Dict[str, Any]]:
        """Check if a bill with the same image hash or same number/date/total already exists in this shop."""
        if image_hash:
            cur = self.conn.execute(
                "SELECT id, bill_number, bill_date, grand_total, created_at FROM bills WHERE shop_id = ? AND image_hash = ?",
                (self.shop_id, image_hash),
            )
            row = cur.fetchone()
            if row:
                return {"type": "duplicate_image", "existing_bill": dict(row)}

        if bill_number:
            cur = self.conn.execute(
                "SELECT id, bill_number, bill_date, grand_total, created_at FROM bills WHERE shop_id = ? AND bill_number = ? AND bill_date = ? AND ABS(grand_total - ?) < 0.01",
                (self.shop_id, bill_number, bill_date, grand_total),
            )
            row = cur.fetchone()
            if row:
                return {"type": "duplicate_metadata", "existing_bill": dict(row)}

        return None

    def save_bill(self, bill_data: Dict[str, Any], items: List[Dict[str, Any]]) -> str:
        """Insert a verified bill and its items transactionally."""
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO bills (
                    id, shop_id, user_id, bill_number, bill_date, subtotal, tax,
                    discount, grand_total, detected_language, language_used,
                    image_path, image_hash, ocr_raw_text, status, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    bill_data["id"],
                    self.shop_id,
                    bill_data["user_id"],
                    bill_data.get("bill_number"),
                    bill_data["bill_date"],
                    bill_data.get("subtotal"),
                    bill_data.get("tax", 0.0),
                    bill_data.get("discount", 0.0),
                    bill_data["grand_total"],
                    bill_data.get("detected_language"),
                    bill_data.get("language_used", bill_data.get("selected_language", "auto")),
                    bill_data.get("image_path"),
                    bill_data.get("image_hash"),
                    bill_data.get("ocr_raw_text"),
                    bill_data.get("status", "verified"),
                    bill_data.get("notes"),
                ),
            )
            for order, item in enumerate(items):
                self.conn.execute(
                    """
                    INSERT INTO bill_items (
                        id, bill_id, shop_id, item_name_original, item_name_standard,
                        quantity, unit, unit_price, line_total, confidence_flags, line_order
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["id"],
                        bill_data["id"],
                        self.shop_id,
                        item["item_name_original"],
                        item.get("item_name_standard"),
                        item.get("quantity"),
                        item.get("unit"),
                        item.get("unit_price"),
                        item.get("line_total"),
                        item.get("confidence_flags"),
                        order,
                    ),
                )
        return bill_data["id"]

    def update_bill(self, bill_id: str, bill_data: Dict[str, Any], items: List[Dict[str, Any]]) -> bool:
        """Update an existing bill and replace its items."""
        # Check ownership
        existing = self.get_bill(bill_id)
        if not existing:
            return False

        with self.conn:
            self.conn.execute(
                """
                UPDATE bills SET
                    bill_number = ?,
                    bill_date = ?,
                    subtotal = ?,
                    tax = ?,
                    discount = ?,
                    grand_total = ?,
                    notes = ?,
                    status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND shop_id = ?
                """,
                (
                    bill_data.get("bill_number"),
                    bill_data["bill_date"],
                    bill_data.get("subtotal"),
                    bill_data.get("tax", 0.0),
                    bill_data.get("discount", 0.0),
                    bill_data["grand_total"],
                    bill_data.get("notes"),
                    bill_data.get("status", "verified"),
                    bill_id,
                    self.shop_id,
                ),
            )
            # Delete old items and insert updated ones
            self.conn.execute("DELETE FROM bill_items WHERE bill_id = ? AND shop_id = ?", (bill_id, self.shop_id))
            for order, item in enumerate(items):
                self.conn.execute(
                    """
                    INSERT INTO bill_items (
                        id, bill_id, shop_id, item_name_original, item_name_standard,
                        quantity, unit, unit_price, line_total, confidence_flags, line_order
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["id"],
                        bill_id,
                        self.shop_id,
                        item["item_name_original"],
                        item.get("item_name_standard"),
                        item.get("quantity"),
                        item.get("unit"),
                        item.get("unit_price"),
                        item.get("line_total"),
                        item.get("confidence_flags"),
                        order,
                    ),
                )
        return True

    def delete_bill(self, bill_id: str) -> bool:
        """Delete a bill owned by this shop."""
        with self.conn:
            cur = self.conn.execute("DELETE FROM bills WHERE id = ? AND shop_id = ?", (bill_id, self.shop_id))
            return cur.rowcount > 0

    def get_product_aliases(self) -> List[Dict[str, Any]]:
        """Get product aliases registered for this shop."""
        cur = self.conn.execute(
            "SELECT * FROM product_aliases WHERE shop_id = ? ORDER BY alias_name ASC", (self.shop_id,)
        )
        return [dict(row) for row in cur.fetchall()]
