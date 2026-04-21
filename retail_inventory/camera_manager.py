"""
camera_manager.py
=================
Multi-shelf, multi-camera management for ShelfAI.

Each ShelfCamera:
  - Owns a GridMapper, SnapshotTracker, RestockingEngine
  - Runs its own capture/detection thread (real camera or demo)
  - Exposes start_camera() / stop_camera() / run_demo_step() / resize_grid()

CameraManager:
  - Fleet controller — shared YOLO detector, dict of ShelfCamera instances
  - get_global_state() aggregates totals across all shelves
"""

import copy
import random
import threading
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import cv2

from grid_mapper import GridMapper, ShelfRegion
from logic import RestockingEngine
from tracker import SnapshotTracker
from utils import draw_boxes, format_time_remaining

# ── Demo product pool ──────────────────────────────────────────────────────
_DEMO_PRODS = ["bottle", "cup", "apple", "banana", "book", "remote"]


# ══════════════════════════════════════════════════════════════════════════
# ShelfCamera — ONE shelf, ONE camera source, ONE pipeline
# ══════════════════════════════════════════════════════════════════════════

class ShelfCamera:
    """
    Encapsulates everything for a single shelf:
      - Camera capture thread (real or absent)
      - Demo simulation
      - Per-shelf YOLO detection + grid mapping + stock tracking
    """

    def __init__(
        self,
        name: str,
        source,                          # int index or URL string
        detector,                        # shared ProductDetector
        region: Tuple = (50, 30, 590, 440),
        rows: int = 3,
        cols: int = 5,
        snap_interval: float = 30.0,
        buffer_size: int = 5,
        stock_threshold: int = 5,
    ):
        self.name             = name
        self.source           = source
        self.enabled          = True
        self.status           = "idle"   # idle | demo | streaming | error
        self.error_msg        = ""
        self.mode             = "demo"   # demo | camera

        # Shared YOLO detector (not owned)
        self._detector = detector

        # Grid / tracking config
        self.rows             = rows
        self.cols             = cols
        self.region           = tuple(region)
        self.snap_interval    = snap_interval
        self.buffer_size      = buffer_size
        self.stock_threshold  = stock_threshold

        # Per-shelf backends
        self._rebuild_backends()

        # Runtime counters
        self.frame_count      = 0
        self.snapshot_count   = 0
        self.demo_step        = 0
        self.log_lines: List[str] = []
        self.last_alerts: List    = []
        self.last_recs: List      = []

        # Camera
        self.latest_jpg: Optional[bytes] = None
        self.lock     = threading.Lock()
        self.running  = False
        self.thread: Optional[threading.Thread] = None

    # ── Backend factory ────────────────────────────────────────────────
    def _rebuild_backends(self):
        shelf_reg       = ShelfRegion(*self.region)
        self.gmapper    = GridMapper(shelf_reg, self.rows, self.cols)
        self.tracker    = SnapshotTracker(self.snap_interval, self.buffer_size)
        self.engine     = RestockingEngine(self.stock_threshold)

    # ── Logging ───────────────────────────────────────────────────────
    def _log(self, msg: str):
        self.log_lines.append(msg)
        if len(self.log_lines) > 200:
            self.log_lines = self.log_lines[-100:]

    # ══ DEMO SIMULATION ══════════════════════════════════════════════

    def _mk_grid(self, fill: float = 0.85) -> List[List[str]]:
        g = [["empty"] * self.cols for _ in range(self.rows)]
        for r in range(self.rows):
            for c in range(self.cols):
                if random.random() < fill:
                    g[r][c] = random.choice(_DEMO_PRODS)
        return g

    def _sell(self, grid: List[List[str]], n: int = 2) -> List[List[str]]:
        g = copy.deepcopy(grid)
        occ = [(r, c) for r in range(len(g))
               for c in range(len(g[0])) if g[r][c] != "empty"]
        for rc in random.sample(occ, min(n, len(occ))):
            g[rc[0]][rc[1]] = "empty"
        return g

    def run_demo_step(self):
        """Simulate one shelf activity step — no camera required."""
        if self.demo_step == 0:
            grid = self._mk_grid(fill=0.85)
        else:
            prev = self.tracker.get_live_grid()
            grid = (
                self._sell(prev, random.randint(1, 3)) if prev
                else self._mk_grid(fill=0.7)
            )

        accepted = self.tracker.add_frame(grid)
        snap     = self.tracker.take_snapshot()
        if snap:
            self.snapshot_count += 1

        self._refresh_insights()
        self.frame_count += 1
        self.demo_step   += 1
        self.status       = "demo"

        ts      = datetime.now().strftime("%H:%M:%S")
        occ_tag = "" if accepted else " [OCCLUDED]"
        self._log(f"[{ts}] Demo #{self.demo_step} — Grid {self.rows}×{self.cols}{occ_tag} 📸")

    def _refresh_insights(self):
        stock = self.tracker.get_current_stock()
        rate  = self.tracker.get_sales_rate()
        gnow  = self.tracker.get_live_grid() or []
        self.last_alerts = self.engine.check_alerts(stock, rate, gnow)
        self.last_recs   = self.engine.get_recommendations(stock, rate)

    # ══ LIVE CAMERA ══════════════════════════════════════════════════

    def start_camera(self) -> bool:
        """
        Open the camera source and start the capture thread.
        Returns True if the camera confirmed open within 1.5 s.
        """
        if self.running:
            return True
        self.running = True
        self.mode    = "camera"
        t = threading.Thread(target=self._cam_worker, daemon=True)
        t.start()
        self.thread = t

        # Wait up to 1.5 s for first frame or failure
        for _ in range(15):
            time.sleep(0.1)
            if self.latest_jpg is not None or not self.running:
                break

        return self.running

    def stop_camera(self):
        """Signal the capture thread to stop."""
        self.running     = False
        self.latest_jpg  = None
        self.mode        = "demo"
        self.status      = "idle"
        self._log(f"[{self.name}] Camera stopped")

    def _cam_worker(self):
        """Camera capture + detection loop (runs in its own thread)."""
        source = self.source

        # Try the configured source; for integer sources also try neighbours
        cap = None
        candidates = [source] if isinstance(source, str) else [source, 0, 1, 2]
        for s in candidates:
            _cap = cv2.VideoCapture(s)
            if _cap.isOpened():
                cap = _cap
                break
            _cap.release()

        if cap is None or not cap.isOpened():
            self.running   = False
            self.status    = "error"
            self.error_msg = f"Cannot open source '{source}'"
            self._log(f"❌ Cannot open camera source '{source}'")
            return

        self.status    = "streaming"
        self.error_msg = ""
        self._log(f"✅ Camera opened: {source}")

        while self.running:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.1)
                continue

            detections, _ = self._detector.detect(frame)
            shelf_dets    = self.gmapper.filter_shelf_detections(detections)
            grid_map      = self.gmapper.map_detections(shelf_dets)
            accepted      = self.tracker.add_frame(grid_map)

            if self.tracker.should_take_snapshot():
                snap = self.tracker.take_snapshot()
                if snap:
                    self.snapshot_count += 1

            self._refresh_insights()
            self.frame_count += 1

            annotated = draw_boxes(frame, shelf_dets)
            annotated = self.gmapper.draw_grid_overlay(annotated, grid_map)
            _, jpg = cv2.imencode(
                ".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 75]
            )
            with self.lock:
                self.latest_jpg = jpg.tobytes()

            ts      = datetime.now().strftime("%H:%M:%S")
            occ_tag = "" if accepted else " [OCCLUDED]"
            self._log(
                f"[{ts}] Frame #{self.frame_count} — "
                f"{len(shelf_dets)} objects{occ_tag}"
            )
            time.sleep(0.05)

        cap.release()
        self._log(f"📷 Camera released for {self.name}")

    # ══ GRID RESIZE (Extend Shelf) ════════════════════════════════════

    def resize_grid(
        self,
        rows: int,
        cols: int,
        region: Optional[Tuple] = None,
        snap_interval: Optional[float] = None,
        buffer_size: Optional[int] = None,
        stock_threshold: Optional[int] = None,
    ):
        """
        Change the grid dimensions / region on-the-fly.
        Stops the camera if running, rebuilds backends, restarts.
        """
        was_running = self.running
        if was_running:
            self.stop_camera()
            time.sleep(0.6)

        self.rows = rows
        self.cols = cols
        if region:
            self.region = tuple(region)
        if snap_interval is not None:
            self.snap_interval = snap_interval
        if buffer_size is not None:
            self.buffer_size = buffer_size
        if stock_threshold is not None:
            self.stock_threshold = stock_threshold

        self._rebuild_backends()
        self.demo_step = 0
        self._log(f"Grid resized to {rows}×{cols}")

        if was_running:
            self.start_camera()

    # ══ RESET ═════════════════════════════════════════════════════════

    def reset(self):
        self.tracker.reset()
        self.frame_count    = 0
        self.snapshot_count = 0
        self.demo_step      = 0
        self.log_lines.clear()
        self.last_alerts.clear()
        self.last_recs.clear()
        if not self.running:
            self.status = "idle"

    # ══ STATE EXPORT ══════════════════════════════════════════════════

    def get_state(self) -> dict:
        stock     = self.tracker.get_current_stock()
        rate      = self.tracker.get_sales_rate()
        live_grid = self.tracker.get_live_grid()
        history   = self.tracker.get_stock_history()
        thr       = self.stock_threshold

        # Products list
        products = []
        for nm, cnt in stock.items():
            r  = rate.get(nm, 0)
            st = ("urgent" if cnt == 0 else
                  "low"    if cnt <= thr else
                  "high"   if r > 6     else "ok")
            products.append(dict(
                name=nm, stock=cnt,
                max=max(cnt * 2, thr * 4, 10),
                rate=round(r, 1), status=st,
            ))

        # Grid cells
        grid_out = []
        if live_grid:
            for ri, row in enumerate(live_grid):
                for ci, cell in enumerate(row):
                    state = ("empty" if cell == "empty" else
                             "low"   if stock.get(cell, 0) <= thr else "filled")
                    grid_out.append(
                        dict(row=ri, col=ci, product=cell, state=state)
                    )

        # History sparkline
        hist_labels = [ts.strftime("%H:%M") for ts, _ in history[-20:]]
        hist_vals   = [sum(c.values())       for _,  c in history[-20:]]

        # Alerts
        alerts_out = []
        for a in self.last_alerts:
            tte = format_time_remaining(a.get("time_to_empty"))
            alerts_out.append(dict(
                item=a["item"], severity=a["severity"],
                stock=a["stock"],
                rate=round(a.get("sales_rate", 0), 1),
                action=a["action"], time_to_empty=tte,
            ))

        recs_out = [
            dict(item=r["item"], reason=r["reason"], suggestion=r["suggestion"])
            for r in self.last_recs
        ]

        empty_count = sum(1 for c in grid_out if c["state"] == "empty")
        low_count   = sum(1 for v in stock.values() if 0 < v <= thr)
        stats       = self.tracker.get_stats()

        return dict(
            name=self.name,
            source=str(self.source),
            status=self.status,
            enabled=self.enabled,
            running=self.running,
            mode=self.mode,
            error_msg=self.error_msg,
            rows=self.rows,
            cols=self.cols,
            region=list(self.region),
            frame_count=self.frame_count,
            snapshot_count=self.snapshot_count,
            demo_step=self.demo_step,
            total_stock=sum(stock.values()),
            num_classes=len(stock),
            low_count=low_count,
            empty_count=empty_count,
            grid_rows=self.rows,
            grid_cols=self.cols,
            products=products,
            grid=grid_out,
            alerts=alerts_out,
            recommendations=recs_out,
            latest_sales=dict(self.tracker.get_latest_sales() or {}),
            latest_restocks=dict(self.tracker.get_latest_restocks() or {}),
            hist_labels=hist_labels,
            hist_vals=hist_vals,
            log=self.log_lines[-25:],
            buffer_fill=stats["buffer_fill"],
            snap_interval=self.snap_interval,
            buffer_size=self.buffer_size,
            stock_threshold=self.stock_threshold,
        )


# ══════════════════════════════════════════════════════════════════════════
# CameraManager — fleet controller
# ══════════════════════════════════════════════════════════════════════════

class CameraManager:
    """
    Manages the full fleet of ShelfCamera instances.
    Shares a single ProductDetector across all shelves.
    """

    def __init__(self, detector):
        self._detector = detector
        self.shelves: Dict[str, ShelfCamera] = {}
        self._lock   = threading.Lock()

    # ── CRUD ──────────────────────────────────────────────────────────

    def add(
        self,
        name: str,
        source=None,
        region=None,
        rows: int = 3,
        cols: int = 5,
        snap_interval: float = 30.0,
        buffer_size: int = 5,
        stock_threshold: int = 5,
    ) -> "ShelfCamera":
        if region is None:
            region = (50, 30, 590, 440)
        if source is None:
            source = len(self.shelves)  # default to next device index
        shelf = ShelfCamera(
            name=name, source=source, detector=self._detector,
            region=region, rows=rows, cols=cols,
            snap_interval=snap_interval, buffer_size=buffer_size,
            stock_threshold=stock_threshold,
        )
        with self._lock:
            self.shelves[name] = shelf
        return shelf

    def remove(self, name: str) -> bool:
        shelf = self.shelves.get(name)
        if shelf is None:
            return False
        shelf.stop_camera()
        time.sleep(0.3)
        with self._lock:
            del self.shelves[name]
        return True

    def get(self, name: str) -> Optional["ShelfCamera"]:
        return self.shelves.get(name)

    def names(self) -> List[str]:
        return list(self.shelves.keys())

    # ── Bulk ops ─────────────────────────────────────────────────────

    def reset_all(self):
        for shelf in self.shelves.values():
            shelf.reset()

    def stop_all(self):
        for shelf in self.shelves.values():
            shelf.stop_camera()

    # ── Global state ──────────────────────────────────────────────────

    def get_global_state(self) -> dict:
        """Aggregated totals + per-shelf summary rows."""
        summaries   = []
        total_stock = 0
        total_low   = 0
        total_empty = 0
        all_alerts  = []
        active_cams = 0

        for shelf in self.shelves.values():
            s = shelf.get_state()
            total_stock += s["total_stock"]
            total_low   += s["low_count"]
            total_empty += s["empty_count"]
            for a in s["alerts"]:
                ac = dict(a)
                ac["shelf"] = shelf.name
                all_alerts.append(ac)
            if shelf.running:
                active_cams += 1

            summaries.append(dict(
                name=shelf.name,
                source=str(shelf.source),
                status=shelf.status,
                mode=shelf.mode,
                enabled=shelf.enabled,
                running=shelf.running,
                error_msg=shelf.error_msg,
                rows=shelf.rows,
                cols=shelf.cols,
                total_stock=s["total_stock"],
                num_classes=s["num_classes"],
                low_count=s["low_count"],
                empty_count=s["empty_count"],
                alert_count=len(s["alerts"]),
                frame_count=shelf.frame_count,
                snapshot_count=shelf.snapshot_count,
                demo_step=shelf.demo_step,
                snap_interval=shelf.snap_interval,
                buffer_size=shelf.buffer_size,
                stock_threshold=shelf.stock_threshold,
                region=list(shelf.region),
            ))

        return dict(
            ok=True,
            total_stock=total_stock,
            total_low=total_low,
            total_empty=total_empty,
            total_shelves=len(self.shelves),
            active_cameras=active_cams,
            total_alert_count=len(all_alerts),
            all_alerts=all_alerts,
            shelves=summaries,
        )
