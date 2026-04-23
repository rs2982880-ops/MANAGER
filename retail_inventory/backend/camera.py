"""
camera.py — Camera lifecycle management for FastAPI backend
=============================================================
Thin wrapper around ShelfCamera providing a centralized interface
for the FastAPI routes and WebSocket handler.

Edge case handling:
  #13 — Storage failure: persist with retry + in-memory fallback
  #14 — Snapshot corruption: validate before using loaded state
"""

import base64
import threading
import time
from typing import Dict, List, Optional, Tuple

import cv2

from camera_manager import ShelfCamera
from database import Database
from detector import ProductDetector
from storage import ShelfStorage


class CameraService:
    """
    Singleton-style camera service managing:
      - YOLO detector (shared)
      - Active ShelfCamera instance
      - Frame encoding for WebSocket
      - Persistence to JSON + SQLite
      - System health monitoring
    """

    def __init__(self):
        self._detector: Optional[ProductDetector] = None
        self._shelf: Optional[ShelfCamera] = None
        self._storage = ShelfStorage()
        self._db = Database()
        self._lock = threading.Lock()

        # Settings (defaults)
        self.confidence: float = 0.45
        self.detection_on: bool = True
        self.grid_rows: int = 3
        self.grid_cols: int = 5
        self.region: Tuple[int, int, int, int] = (50, 30, 590, 440)
        self.snap_interval: float = 30.0
        self.buffer_size: int = 5
        self.stock_threshold: int = 5

        # FPS tracking
        self._frame_times: list = []
        self._fps: float = 0.0

        # Load persisted config
        self._restore_config()

    # ── Detector ──────────────────────────────────────────────────────
    def get_detector(self) -> ProductDetector:
        if self._detector is None:
            print("[camera] Loading YOLOv8 model...")
            self._detector = ProductDetector(confidence=self.confidence)
            print("[camera] Model loaded successfully")
        return self._detector

    # ── Restore from persistence ──────────────────────────────────────
    def _restore_config(self):
        """
        EDGE CASE #14: Validate loaded config before using it.
        Corrupted JSON is silently discarded.
        """
        cfg = self._storage.load_camera_config()
        if cfg:
            self.confidence = cfg.get("confidence", 0.45)
            self.grid_rows = cfg.get("grid_rows", 3)
            self.grid_cols = cfg.get("grid_cols", 5)
            print(f"[camera] Restored config: conf={self.confidence}, grid={self.grid_rows}x{self.grid_cols}")

    def _persist_config(self, camera_type: str = "Device", device_index: int = 0, ip_url: str = ""):
        self._storage.save_camera_config(
            camera_type=camera_type,
            device_index=device_index,
            ip_url=ip_url,
            confidence=self.confidence,
            grid_rows=self.grid_rows,
            grid_cols=self.grid_cols,
        )

    def _persist_shelf_state(self):
        """
        Save current shelf state to JSON + log sales to SQLite.
        EDGE CASE #13: Uses save_with_retry for fault tolerance.
        If disk write fails, data is cached in memory.
        """
        if self._shelf is None:
            return
        try:
            state = self._shelf.get_state()
            latest_sales = state.get("latest_sales", {})

            # Log sales to SQLite
            if latest_sales:
                try:
                    self._db.log_sales(latest_sales)
                except Exception as e:
                    print(f"[camera] SQLite log_sales failed: {e}")

            # EDGE CASE #13: save_with_retry handles retries + memory fallback
            self._storage.save_shelf_state(
                stock_counts={p["name"]: p["stock"] for p in state.get("products", [])},
                grid_state=state.get("grid_map"),
                sales_history=[
                    {"item": k, "qty": v, "time": ""}
                    for k, v in latest_sales.items()
                ],
                alerts=state.get("alerts", []),
                frame_count=state.get("frame_count", 0),
                snapshot_count=state.get("snapshot_count", 0),
            )
        except Exception as e:
            print(f"[camera] Persist error: {e}")

    # ── Camera lifecycle ─────────────────────────────────────────────
    def start(self, source) -> dict:
        """Start camera with given source (int index or URL string)."""
        detector = self.get_detector()
        detector.set_confidence(self.confidence)

        # Determine camera type for persistence
        camera_type = "Device" if isinstance(source, int) else "IP Camera"
        device_index = source if isinstance(source, int) else 0
        ip_url = source if isinstance(source, str) else ""

        self._shelf = ShelfCamera(
            name="Main Shelf",
            source=source,
            detector=detector,
            region=self.region,
            rows=self.grid_rows,
            cols=self.grid_cols,
            snap_interval=self.snap_interval,
            buffer_size=self.buffer_size,
            stock_threshold=self.stock_threshold,
        )

        ok = self._shelf.start_camera()
        if ok:
            self._persist_config(camera_type, device_index, ip_url)
            return {"ok": True, "status": "streaming", "message": "Camera started"}
        else:
            err = self._shelf.error_msg or "Camera failed to open"
            return {"ok": False, "status": "error", "message": err}

    def stop(self) -> dict:
        """Stop the active camera and persist final state."""
        if self._shelf is not None:
            self._persist_shelf_state()
            self._shelf.stop_camera()
        return {"ok": True, "status": "idle", "message": "Camera stopped"}

    @property
    def is_running(self) -> bool:
        return self._shelf is not None and self._shelf.running

    # ── Frame access ─────────────────────────────────────────────────
    def get_latest_frame_base64(self) -> Optional[str]:
        """Get the latest annotated frame as a base64-encoded JPEG string."""
        if self._shelf is None:
            return None
        with self._shelf.lock:
            jpg = self._shelf.latest_jpg
        if jpg is None:
            return None
        return base64.b64encode(jpg).decode("ascii")

    def get_latest_frame_bytes(self) -> Optional[bytes]:
        """Get the latest annotated frame as raw JPEG bytes."""
        if self._shelf is None:
            return None
        with self._shelf.lock:
            return self._shelf.latest_jpg

    # ── FPS calculation ──────────────────────────────────────────────
    def update_fps(self):
        now = time.time()
        self._frame_times.append(now)
        # Keep last 30 timestamps
        self._frame_times = self._frame_times[-30:]
        if len(self._frame_times) >= 2:
            span = self._frame_times[-1] - self._frame_times[0]
            if span > 0:
                self._fps = (len(self._frame_times) - 1) / span

    @property
    def fps(self) -> float:
        return round(self._fps, 1)

    # ── State ────────────────────────────────────────────────────────
    def get_state(self) -> dict:
        """Full shelf state for REST or WebSocket."""
        if self._shelf is None:
            # Return saved state if available
            saved = self._storage.load_shelf_state()
            if saved and saved.get("stock_counts"):
                return {
                    "ok": True,
                    "status": "idle",
                    "running": False,
                    "total_stock": sum(saved["stock_counts"].values()),
                    "detected_stock": sum(saved["stock_counts"].values()),
                    "total_sold": 0,
                    "num_classes": len(saved["stock_counts"]),
                    "low_count": 0,
                    "empty_count": 0,
                    "products": [
                        {"name": k, "stock": v, "max": max(v * 2, 20), "rate": 0, "status": "ok"}
                        for k, v in saved["stock_counts"].items()
                    ],
                    "grid": [],
                    "grid_map": saved.get("grid_state"),
                    "grid_rows": self.grid_rows,
                    "grid_cols": self.grid_cols,
                    "alerts": saved.get("alerts", []),
                    "recommendations": [],
                    "latest_sales": {},
                    "frame_count": saved.get("frame_count", 0),
                    "snapshot_count": saved.get("snapshot_count", 0),
                    "fps": 0,
                    "saved_data": True,
                    "system_state": None,
                }
            return {
                "ok": True,
                "status": "idle",
                "running": False,
                "total_stock": 0,
                "detected_stock": 0,
                "total_sold": 0,
                "num_classes": 0,
                "low_count": 0,
                "empty_count": 0,
                "products": [],
                "grid": [],
                "grid_map": None,
                "grid_rows": self.grid_rows,
                "grid_cols": self.grid_cols,
                "alerts": [],
                "recommendations": [],
                "latest_sales": {},
                "frame_count": 0,
                "snapshot_count": 0,
                "fps": 0,
                "system_state": None,
            }

        state = self._shelf.get_state()
        state["ok"] = True
        state["fps"] = self.fps
        state["confidence"] = self.confidence
        state["detection_on"] = self.detection_on
        return state

    # ── System Status (NEW) ──────────────────────────────────────────
    def get_system_status(self) -> dict:
        """
        Camera health, thread state, and edge case diagnostics.
        Used by GET /api/status endpoint.
        """
        sys_state = None
        snap_info = None
        if self._shelf is not None:
            sys_state = dict(self._shelf.system_state)
            snap_info = self._shelf.tracker.get_snapshot_info()

        return {
            "ok": True,
            "running": self.is_running,
            "status": self._shelf.status if self._shelf else "idle",
            "error_msg": self._shelf.error_msg if self._shelf else "",
            "fps": self.fps,
            "confidence": self.confidence,
            "detection_on": self.detection_on,
            "grid_rows": self.grid_rows,
            "grid_cols": self.grid_cols,
            "system_state": sys_state,
            "snapshot_info": snap_info,
        }

    # ── Mode Control (NEW) ───────────────────────────────────────────
    def set_mode(self, mode: str) -> dict:
        """
        Switch between demo and production mode.
        Immediately adjusts snapshot interval on the active camera.
        """
        from camera_manager import ShelfCamera
        if mode not in ("demo", "production"):
            return {"ok": False, "message": f"Invalid mode: {mode}"}

        base_interval = ShelfCamera.MODE_INTERVALS.get(mode, 600)

        if self._shelf is not None:
            self._shelf.system_mode = mode
            self._shelf.tracker.set_mode(mode, base_interval)
            self._shelf._log(f"🔄 Mode changed to {mode} (interval={base_interval}s)")

        # Update default snap_interval for future cameras
        self.snap_interval = base_interval

        return {
            "ok": True,
            "mode": mode,
            "interval": base_interval,
            "message": f"Switched to {mode} mode",
        }

    # ── Stock (NEW) ──────────────────────────────────────────────────
    def get_stock(self) -> dict:
        """
        Current stock levels. Returns frozen stock if camera offline.
        Used by GET /api/stock endpoint.
        """
        state = self.get_state()
        return {
            "ok": True,
            "running": state.get("running", False),
            "total_stock": state.get("total_stock", 0),
            "detected_stock": state.get("detected_stock", 0),
            "total_sold": state.get("total_sold", 0),
            "products": state.get("products", []),
            "total_sales_map": state.get("total_sales_map", {}),
        }

    # ── Alerts (NEW) ─────────────────────────────────────────────────
    def get_alerts_list(self) -> dict:
        """
        Active alerts including system alerts (camera offline, etc).
        Used by GET /api/alerts endpoint.
        """
        state = self.get_state()
        return {
            "ok": True,
            "alerts": state.get("alerts", []),
            "recommendations": state.get("recommendations", []),
        }

    # ── Settings ─────────────────────────────────────────────────────
    def update_settings(self, settings: dict) -> dict:
        """Update detection / grid settings."""
        if "confidence" in settings:
            self.confidence = float(settings["confidence"])
            if self._detector:
                self._detector.set_confidence(self.confidence)

        if "detection_on" in settings:
            self.detection_on = bool(settings["detection_on"])

        if "grid_rows" in settings:
            self.grid_rows = int(settings["grid_rows"])

        if "grid_cols" in settings:
            self.grid_cols = int(settings["grid_cols"])

        if "snap_interval" in settings:
            self.snap_interval = float(settings["snap_interval"])

        if "stock_threshold" in settings:
            self.stock_threshold = int(settings["stock_threshold"])

        # Apply grid resize if camera is active
        if self._shelf and self._shelf.running:
            if "grid_rows" in settings or "grid_cols" in settings:
                self._shelf.resize_grid(
                    rows=self.grid_rows,
                    cols=self.grid_cols,
                    snap_interval=self.snap_interval,
                    buffer_size=self.buffer_size,
                    stock_threshold=self.stock_threshold,
                )

        return {
            "ok": True,
            "confidence": self.confidence,
            "detection_on": self.detection_on,
            "grid_rows": self.grid_rows,
            "grid_cols": self.grid_cols,
        }

    # ── Camera enumeration ───────────────────────────────────────────
    @staticmethod
    def enumerate_cameras(max_index: int = 5) -> List[dict]:
        """Probe camera indices 0..max_index."""
        available = []
        for i in range(max_index):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap is not None and cap.isOpened():
                available.append({"index": i, "name": f"Camera {i}"})
                cap.release()
        return available

    # ── Snapshot ──────────────────────────────────────────────────────
    def take_snapshot(self) -> dict:
        """Force a snapshot save."""
        if self._shelf is None:
            return {"ok": False, "message": "No active camera"}
        self._persist_shelf_state()
        return {"ok": True, "message": "Snapshot saved"}

    # ── History ──────────────────────────────────────────────────────
    def get_history(self) -> dict:
        """Get sales history from SQLite."""
        import json as _json
        snaps = self._db.get_snapshot_history(limit=20)
        evts = self._db.get_sales_history(limit=30)
        daily = self._db.get_daily_sales(days=30)
        today = self._db.get_sales_summary_today()
        total_all_time = self._db.get_total_sales_all_time()

        return {
            "snapshots": [
                {"time": r[0], "stock": _json.loads(r[2])} for r in snaps
            ],
            "events": [
                {"time": r[0], "item": r[1], "qty": r[2], "type": r[3]}
                for r in evts
            ],
            "daily_sales": daily,
            "today_sales": today,
            "total_all_time": total_all_time,
        }
