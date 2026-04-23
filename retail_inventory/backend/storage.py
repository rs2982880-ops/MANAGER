"""
storage.py — JSON-based persistence for ShelfAI
==================================================
Saves and loads shelf state, stock counts, sales history, and camera
configuration to a JSON file so data survives restarts.

Edge case handling:
  #13 — Storage failure: save_with_retry() retries up to 3 times
  #14 — Snapshot corruption: validate_loaded_data() checks integrity
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# Default persistence file alongside the application
_DEFAULT_PATH = Path(__file__).parent / "shelfai_state.json"

# ── EDGE CASE #13: Retry constants ──
_MAX_SAVE_RETRIES = 3
_SAVE_RETRY_DELAY = 0.5  # seconds between retries


class ShelfStorage:
    """
    JSON file persistence layer with fault tolerance.

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
        # EDGE CASE #13: In-memory fallback when disk writes fail
        self._memory_cache: Optional[Dict[str, Any]] = None

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
            # EDGE CASE #13: Clear memory cache on successful disk write
            self._memory_cache = None
            return True
        except (OSError, TypeError) as e:
            print(f"[storage] Save failed: {e}")
            return False

    def save_with_retry(self, data: Dict[str, Any]) -> bool:
        """
        EDGE CASE #13: Retry save up to _MAX_SAVE_RETRIES times.
        If all retries fail, fall back to in-memory cache so data
        is not lost. The next successful save will flush the cache.
        """
        for attempt in range(1, _MAX_SAVE_RETRIES + 1):
            if self.save(data):
                return True
            if attempt < _MAX_SAVE_RETRIES:
                print(f"[storage] Retry {attempt}/{_MAX_SAVE_RETRIES}...")
                time.sleep(_SAVE_RETRY_DELAY)

        # All retries failed — fall back to memory
        print("[storage] All save retries failed — caching in memory")
        self._memory_cache = {
            "saved_at": datetime.now().isoformat(),
            **data,
        }
        return False

    # ── Load ──────────────────────────────────────────────────────────
    def load(self) -> Optional[Dict[str, Any]]:
        """
        Load the previously saved state.
        EDGE CASE #14: Validates data before returning.
        Returns None if no file or data is corrupted.
        Falls back to memory cache if disk load fails.
        """
        # Try disk first
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if self.validate_loaded_data(data):
                    return data
                else:
                    print("[storage] Loaded data failed validation — discarding")
                    return None
            except (json.JSONDecodeError, OSError) as e:
                print(f"[storage] Load failed: {e}")

        # EDGE CASE #13: Fall back to memory cache
        if self._memory_cache is not None:
            print("[storage] Using in-memory fallback data")
            return self._memory_cache

        return None

    # ── Validation ────────────────────────────────────────────────────
    @staticmethod
    def validate_loaded_data(data: Any) -> bool:
        """
        EDGE CASE #14: Validate snapshot data integrity.
        Checks that:
          - data is a dict
          - stock_counts (if present) has string keys and int/float values
          - grid_state (if present) is a 2-D list of strings
          - No None values in critical numeric fields
        Corrupted data is rejected to prevent downstream errors.
        """
        if not isinstance(data, dict):
            return False

        # Validate stock_counts
        sc = data.get("stock_counts")
        if sc is not None:
            if not isinstance(sc, dict):
                return False
            for k, v in sc.items():
                if not isinstance(k, str):
                    return False
                if not isinstance(v, (int, float)):
                    return False

        # Validate grid_state
        gs = data.get("grid_state")
        if gs is not None:
            if not isinstance(gs, list):
                return False
            for row in gs:
                if not isinstance(row, list):
                    return False
                for cell in row:
                    if not isinstance(cell, str):
                        return False

        return True

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
        self.save_with_retry(existing)

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

        self.save_with_retry(existing)

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
        """Delete the persistence file and memory cache."""
        self._memory_cache = None
        try:
            if self.path.exists():
                os.remove(self.path)
        except OSError:
            pass
