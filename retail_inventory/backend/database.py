"""
Database module — SQLite + JSON persistence for grid-based tracking.
====================================================================
Stores grid snapshots (as JSON blobs), position-based sales events,
and alerts.
"""

import json
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple


DB_FILE = "inventory.db"
STOCK_JSON = "stock.json"


class Database:
    """SQLite + JSON persistence for the grid-based inventory system."""

    def __init__(self, db_path: str = DB_FILE, stock_json: str = STOCK_JSON):
        self.db_path = db_path
        self.stock_json = stock_json
        self._init_db()

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------
    def _init_db(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS grid_snapshots (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT    NOT NULL,
                    grid_json TEXT    NOT NULL,
                    stock_json TEXT   NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sales_events (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp  TEXT    NOT NULL,
                    item_name  TEXT    NOT NULL,
                    quantity   INTEGER NOT NULL,
                    event_type TEXT    NOT NULL
                );
                CREATE TABLE IF NOT EXISTS alerts_log (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp  TEXT    NOT NULL,
                    item_name  TEXT    NOT NULL,
                    alert_type TEXT    NOT NULL,
                    message    TEXT    NOT NULL
                );
                CREATE TABLE IF NOT EXISTS daily_sales (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    date       TEXT    NOT NULL,
                    item_name  TEXT    NOT NULL,
                    quantity   INTEGER NOT NULL DEFAULT 0,
                    notes      TEXT    DEFAULT '',
                    created_at TEXT    DEFAULT (datetime('now')),
                    updated_at TEXT,
                    UNIQUE(date, item_name)
                );
            """)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    # ------------------------------------------------------------------
    # Grid snapshots
    # ------------------------------------------------------------------
    def save_grid_snapshot(
        self,
        grid: List[List[str]],
        stock: Dict[str, int],
    ):
        """Persist a grid snapshot to SQLite and the JSON sidecar."""
        ts = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO grid_snapshots (timestamp, grid_json, stock_json) "
                "VALUES (?, ?, ?)",
                (ts, json.dumps(grid), json.dumps(stock)),
            )
        self._save_stock_json(stock, grid)

    def _save_stock_json(self, stock: Dict[str, int], grid: List[List[str]]):
        data = {
            "timestamp": datetime.now().isoformat(),
            "stock": stock,
            "grid": grid,
        }
        try:
            with open(self.stock_json, "w") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass

    def load_previous_stock(self) -> Dict[str, int]:
        if os.path.exists(self.stock_json):
            try:
                with open(self.stock_json, "r") as f:
                    return json.load(f).get("stock", {})
            except (json.JSONDecodeError, KeyError):
                pass
        return {}

    def load_previous_grid(self) -> Optional[List[List[str]]]:
        if os.path.exists(self.stock_json):
            try:
                with open(self.stock_json, "r") as f:
                    return json.load(f).get("grid")
            except (json.JSONDecodeError, KeyError):
                pass
        return None

    # ------------------------------------------------------------------
    # Sales / restock events
    # ------------------------------------------------------------------
    def log_sales(self, sales: Dict[str, int]):
        ts = datetime.now().isoformat()
        rows = [(ts, item, qty, "sale") for item, qty in sales.items() if qty > 0]
        if rows:
            with self._connect() as conn:
                conn.executemany(
                    "INSERT INTO sales_events (timestamp, item_name, quantity, event_type) "
                    "VALUES (?, ?, ?, ?)", rows,
                )

    def log_restocks(self, restocks: Dict[str, int]):
        ts = datetime.now().isoformat()
        rows = [(ts, item, qty, "restock") for item, qty in restocks.items() if qty > 0]
        if rows:
            with self._connect() as conn:
                conn.executemany(
                    "INSERT INTO sales_events (timestamp, item_name, quantity, event_type) "
                    "VALUES (?, ?, ?, ?)", rows,
                )

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------
    def log_alert(self, item: str, alert_type: str, message: str):
        ts = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO alerts_log (timestamp, item_name, alert_type, message) "
                "VALUES (?, ?, ?, ?)", (ts, item, alert_type, message),
            )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def get_snapshot_history(self, limit: int = 50) -> List[Tuple]:
        """Returns [(timestamp, grid_json, stock_json), …] newest first."""
        with self._connect() as conn:
            return conn.execute(
                "SELECT timestamp, grid_json, stock_json FROM grid_snapshots "
                "ORDER BY id DESC LIMIT ?", (limit,),
            ).fetchall()

    def get_sales_history(self, limit: int = 100) -> List[Tuple]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT timestamp, item_name, quantity, event_type "
                "FROM sales_events ORDER BY id DESC LIMIT ?", (limit,),
            ).fetchall()

    def get_recent_alerts(self, limit: int = 30) -> List[Tuple]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT timestamp, item_name, alert_type, message "
                "FROM alerts_log ORDER BY id DESC LIMIT ?", (limit,),
            ).fetchall()

    # ------------------------------------------------------------------
    # Sales aggregation (for charts)
    # ------------------------------------------------------------------

    def get_daily_sales(self, days: int = 30) -> List[Dict]:
        """
        Daily sales totals per product for the last N days.

        Returns list of dicts:
            [{"date": "2026-04-21", "item": "bottle", "qty": 5}, ...]
        """
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT DATE(timestamp) AS day,
                       item_name,
                       SUM(quantity) AS total_qty
                FROM   sales_events
                WHERE  event_type = 'sale'
                  AND  timestamp >= DATE('now', ?)
                GROUP BY day, item_name
                ORDER BY day ASC, item_name ASC
            """, (f"-{days} days",)).fetchall()
        return [{"date": r[0], "item": r[1], "qty": r[2]} for r in rows]

    def get_weekly_sales(self, weeks: int = 12) -> List[Dict]:
        """
        Weekly sales totals per product for the last N weeks.

        Returns list of dicts:
            [{"week": "2026-W16", "item": "bottle", "qty": 12}, ...]
        """
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT strftime('%Y-W%W', timestamp) AS week,
                       item_name,
                       SUM(quantity) AS total_qty
                FROM   sales_events
                WHERE  event_type = 'sale'
                  AND  timestamp >= DATE('now', ?)
                GROUP BY week, item_name
                ORDER BY week ASC, item_name ASC
            """, (f"-{weeks * 7} days",)).fetchall()
        return [{"week": r[0], "item": r[1], "qty": r[2]} for r in rows]

    def get_monthly_sales(self, months: int = 12) -> List[Dict]:
        """
        Monthly sales totals per product for the last N months.

        Returns list of dicts:
            [{"month": "2026-04", "item": "bottle", "qty": 30}, ...]
        """
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT strftime('%Y-%m', timestamp) AS month,
                       item_name,
                       SUM(quantity) AS total_qty
                FROM   sales_events
                WHERE  event_type = 'sale'
                  AND  timestamp >= DATE('now', ?)
                GROUP BY month, item_name
                ORDER BY month ASC, item_name ASC
            """, (f"-{months} months",)).fetchall()
        return [{"month": r[0], "item": r[1], "qty": r[2]} for r in rows]

    def get_yearly_sales(self) -> List[Dict]:
        """
        Yearly sales totals per product (all time).

        Returns list of dicts:
            [{"year": "2026", "item": "bottle", "qty": 120}, ...]
        """
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT strftime('%Y', timestamp) AS year,
                       item_name,
                       SUM(quantity) AS total_qty
                FROM   sales_events
                WHERE  event_type = 'sale'
                GROUP BY year, item_name
                ORDER BY year ASC, item_name ASC
            """).fetchall()
        return [{"year": r[0], "item": r[1], "qty": r[2]} for r in rows]

    def get_sales_summary_today(self) -> List[Dict]:
        """
        Today's sales per product.

        Returns: [{"item": "bottle", "qty": 3}, ...]
        """
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT item_name, SUM(quantity) AS total_qty
                FROM   sales_events
                WHERE  event_type = 'sale'
                  AND  DATE(timestamp) = DATE('now')
                GROUP BY item_name
                ORDER BY total_qty DESC
            """).fetchall()
        return [{"item": r[0], "qty": r[1]} for r in rows]

    def get_total_sales_all_time(self) -> int:
        """Total units sold all time."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(quantity), 0) FROM sales_events "
                "WHERE event_type = 'sale'"
            ).fetchone()
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # Daily Sales Log — Human-corrected, editable sales layer
    # ------------------------------------------------------------------

    def upsert_daily_sale(
        self, date: str, item_name: str, quantity: int, notes: str = ""
    ) -> int:
        """
        Insert or update a daily sale record.
        If (date, item_name) already exists, update quantity and notes.
        Returns the row id.
        """
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO daily_sales (date, item_name, quantity, notes, updated_at)
                VALUES (?, ?, ?, ?, datetime('now'))
                ON CONFLICT(date, item_name) DO UPDATE SET
                    quantity   = excluded.quantity,
                    notes      = excluded.notes,
                    updated_at = datetime('now')
            """, (date, item_name, quantity, notes))
            row = conn.execute(
                "SELECT id FROM daily_sales WHERE date = ? AND item_name = ?",
                (date, item_name),
            ).fetchone()
        return row[0] if row else 0

    def update_daily_sale(self, sale_id: int, quantity: int, notes: str = "") -> bool:
        """Update an existing daily sale record by ID."""
        with self._connect() as conn:
            cur = conn.execute("""
                UPDATE daily_sales
                SET quantity = ?, notes = ?, updated_at = datetime('now')
                WHERE id = ?
            """, (quantity, notes, sale_id))
        return cur.rowcount > 0

    def delete_daily_sale(self, sale_id: int) -> bool:
        """Delete a daily sale record by ID."""
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM daily_sales WHERE id = ?", (sale_id,))
        return cur.rowcount > 0

    def get_daily_sales_log(self, days: int = 30) -> List[Dict]:
        """
        Fetch the daily sales log for the last N days.
        Returns list of dicts sorted by date DESC, then item ASC.
        """
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT id, date, item_name, quantity, notes, created_at, updated_at
                FROM   daily_sales
                WHERE  date >= DATE('now', ?)
                ORDER BY date DESC, item_name ASC
            """, (f"-{days} days",)).fetchall()
        return [
            {
                "id": r[0], "date": r[1], "item": r[2],
                "quantity": r[3], "notes": r[4] or "",
                "created_at": r[5], "updated_at": r[6],
            }
            for r in rows
        ]

    def get_daily_sales_summary(self) -> Dict:
        """Aggregated daily sales summary for KPI cards."""
        with self._connect() as conn:
            today = conn.execute("""
                SELECT COALESCE(SUM(quantity), 0) FROM daily_sales
                WHERE date = DATE('now')
            """).fetchone()[0]

            week = conn.execute("""
                SELECT COALESCE(SUM(quantity), 0) FROM daily_sales
                WHERE date >= DATE('now', '-7 days')
            """).fetchone()[0]

            month = conn.execute("""
                SELECT COALESCE(SUM(quantity), 0) FROM daily_sales
                WHERE date >= DATE('now', '-30 days')
            """).fetchone()[0]

            total = conn.execute("""
                SELECT COALESCE(SUM(quantity), 0) FROM daily_sales
            """).fetchone()[0]

        return {
            "today": today,
            "week": week,
            "month": month,
            "total": total,
        }

