"""
storage.py — JSON-based persistence for ShelfAI
==================================================
Saves and loads shelf state, stock counts, sales history, and camera
configuration to a JSON file so data survives Streamlit reloads.

Usage:
    from storage import ShelfStorage
    store = ShelfStorage()
    store.save(data_dict)
    data  = store.load()
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# Default persistence file alongside the application
_DEFAULT_PATH = Path(__file__).parent / "shelfai_state.json"


class ShelfStorage:
    """
    JSON file persistence layer.

    Persisted fields
    ----------------
    * camera_config   — type, device index, IP URL, confidence, grid size
    * stock_counts    — {item: count} from last known snapshot
    * sales_history   — list of {item, qty, timestamp} dicts (last 100)
    * grid_state      — last stable grid (2-D list)
    * alerts          — last alert list
    * session_info    — timestamps, frame count, snapshot count
    """

    def __init__(self, path: str = None):
        self.path = Path(path) if path else _DEFAULT_PATH

    # ── Save ──────────────────────────────────────────────────────────
    def save(self, data: Dict[str, Any]) -> bool:
        """Persist *data* to the JSON file. Returns True on success."""
        try:
            payload = {
                "saved_at": datetime.now().isoformat(),
                **data,
            }
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, default=str)
            return True
        except (OSError, TypeError) as e:
            print(f"[storage] Save failed: {e}")
            return False

    # ── Load ──────────────────────────────────────────────────────────
    def load(self) -> Optional[Dict[str, Any]]:
        """Load the previously saved state. Returns None if no file."""
        if not self.path.exists():
            return None
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[storage] Load failed: {e}")
            return None

    # ── Convenience: save camera config ──────────────────────────────
    def save_camera_config(
        self,
        camera_type: str,
        device_index: int,
        ip_url: str,
        confidence: float,
        grid_rows: int,
        grid_cols: int,
    ):
        """Merge camera configuration into the saved state."""
        existing = self.load() or {}
        existing["camera_config"] = {
            "camera_type": camera_type,
            "device_index": device_index,
            "ip_url": ip_url,
            "confidence": confidence,
            "grid_rows": grid_rows,
            "grid_cols": grid_cols,
        }
        self.save(existing)

    # ── Convenience: save shelf snapshot ──────────────────────────────
    def save_shelf_state(
        self,
        stock_counts: Dict[str, int],
        grid_state: Optional[List[List[str]]],
        sales_history: List[Dict],
        alerts: List[Dict],
        frame_count: int = 0,
        snapshot_count: int = 0,
    ):
        """Merge shelf data into the saved state."""
        existing = self.load() or {}
        existing["stock_counts"] = stock_counts
        existing["grid_state"] = grid_state
        existing["alerts"] = alerts
        existing["frame_count"] = frame_count
        existing["snapshot_count"] = snapshot_count

        # Append new sales, keep last 100
        prev_sales = existing.get("sales_history", [])
        merged = prev_sales + sales_history
        existing["sales_history"] = merged[-100:]

        self.save(existing)

    # ── Convenience: load camera config ──────────────────────────────
    def load_camera_config(self) -> Optional[Dict]:
        data = self.load()
        if data:
            return data.get("camera_config")
        return None

    # ── Convenience: load shelf state ────────────────────────────────
    def load_shelf_state(self) -> Optional[Dict]:
        data = self.load()
        if data is None:
            return None
        return {
            "stock_counts":   data.get("stock_counts", {}),
            "grid_state":     data.get("grid_state"),
            "sales_history":  data.get("sales_history", []),
            "alerts":         data.get("alerts", []),
            "frame_count":    data.get("frame_count", 0),
            "snapshot_count": data.get("snapshot_count", 0),
        }

    # ── Clear ─────────────────────────────────────────────────────────
    def clear(self):
        """Delete the persistence file."""
        try:
            if self.path.exists():
                os.remove(self.path)
        except OSError:
            pass
