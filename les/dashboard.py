"""Sales metrics, item-wise sales reporting, and dashboard analytics."""

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from app.database import get_db_connection


class SalesDashboard:
    """Computes sales aggregates and item-wise statistics scoped to a shop."""

    def __init__(self, shop_id: str, db_conn: Optional[sqlite3.Connection] = None):
        if not shop_id:
            raise ValueError("shop_id is required for sales dashboard")
        self.shop_id = shop_id
        self.conn = db_conn or get_db_connection()

    def get_summary_metrics(self) -> Dict[str, Any]:
        """Calculate today's sales, this week, this month, and total bills."""
        conn = self.conn
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        first_of_month = now.strftime("%Y-%m-01")

        # Today's sales
        cur = conn.execute(
            """
            SELECT COALESCE(SUM(grand_total), 0.0) as total,
                   COUNT(*) as bill_count
            FROM bills
            WHERE shop_id = ? AND bill_date = ?
            """,
            (self.shop_id, today),
        )
        today_row = cur.fetchone()
        today_sales = float(today_row["total"])
        today_count = int(today_row["bill_count"])

        # This week's sales (last 7 days)
        cur = conn.execute(
            """
            SELECT COALESCE(SUM(grand_total), 0.0) as total,
                   COUNT(*) as bill_count
            FROM bills
            WHERE shop_id = ? AND bill_date >= ?
            """,
            (self.shop_id, week_ago),
        )
        week_row = cur.fetchone()
        week_sales = float(week_row["total"])

        # This month's sales
        cur = conn.execute(
            """
            SELECT COALESCE(SUM(grand_total), 0.0) as total,
                   COUNT(*) as bill_count
            FROM bills
            WHERE shop_id = ? AND bill_date >= ?
            """,
            (self.shop_id, first_of_month),
        )
        month_row = cur.fetchone()
        month_sales = float(month_row["total"])

        # All-time sales
        cur = conn.execute(
            """
            SELECT COALESCE(SUM(grand_total), 0.0) as total,
                   COUNT(*) as bill_count
            FROM bills
            WHERE shop_id = ?
            """,
            (self.shop_id,),
        )
        all_time_row = cur.fetchone()
        all_time_sales = float(all_time_row["total"])
        all_time_count = int(all_time_row["bill_count"])

        avg_bill = round(today_sales / today_count, 2) if today_count > 0 else (
            round(all_time_sales / all_time_count, 2) if all_time_count > 0 else 0.0
        )

        return {
            "today_sales": round(today_sales, 2),
            "today_bills_count": today_count,
            "this_week_sales": round(week_sales, 2),
            "this_month_sales": round(month_sales, 2),
            "all_time_sales": round(all_time_sales, 2),
            "total_bills_count": all_time_count,
            "avg_bill_value": avg_bill,
            "currency": "INR",
            "currency_symbol": "₹",
        }

    def get_item_wise_sales(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Item-wise sales ranking by revenue and quantity sold."""
        conn = self.conn
        cur = conn.execute(
            """
            SELECT 
                COALESCE(bi.item_name_standard, bi.item_name_original) as display_name,
                bi.item_name_original,
                bi.unit,
                SUM(COALESCE(bi.quantity, 1.0)) as total_quantity,
                SUM(COALESCE(bi.line_total, 0.0)) as total_revenue,
                COUNT(bi.id) as times_sold
            FROM bill_items bi
            JOIN bills b ON bi.bill_id = b.id
            WHERE bi.shop_id = ?
            GROUP BY display_name, bi.unit
            ORDER BY total_revenue DESC, total_quantity DESC
            LIMIT ?
            """,
            (self.shop_id, limit),
        )
        rows = cur.fetchall()
        result = []
        for r in rows:
            qty = round(float(r["total_quantity"]), 2)
            rev = round(float(r["total_revenue"]), 2)
            avg_rate = round(rev / qty, 2) if qty > 0 else 0.0
            result.append({
                "item_name": r["display_name"],
                "original_name": r["item_name_original"],
                "unit": r["unit"] or "pcs",
                "total_quantity": qty,
                "total_revenue": rev,
                "times_sold": int(r["times_sold"]),
                "avg_price": avg_rate,
            })
        return result

    def get_daily_sales_trend(self, days: int = 7) -> List[Dict[str, Any]]:
        """Daily sales trend for charts."""
        conn = self.conn
        now = datetime.now(timezone.utc)
        start_date = (now - timedelta(days=days - 1)).strftime("%Y-%m-%d")

        cur = conn.execute(
            """
            SELECT bill_date,
                   COALESCE(SUM(grand_total), 0.0) as total,
                   COUNT(*) as bill_count
            FROM bills
            WHERE shop_id = ? AND bill_date >= ?
            GROUP BY bill_date
            ORDER BY bill_date ASC
            """,
            (self.shop_id, start_date),
        )
        data_by_date = {row["bill_date"]: {"total": float(row["total"]), "count": int(row["bill_count"])} for row in cur.fetchall()}

        # Fill in missing days
        trend = []
        curr = now - timedelta(days=days - 1)
        for _ in range(days):
            ds = curr.strftime("%Y-%m-%d")
            entry = data_by_date.get(ds, {"total": 0.0, "count": 0})
            trend.append({
                "date": ds,
                "formatted_date": curr.strftime("%d %b"),
                "total": round(entry["total"], 2),
                "count": entry["count"],
            })
            curr += timedelta(days=1)

        return trend
