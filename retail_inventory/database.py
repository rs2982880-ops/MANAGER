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
