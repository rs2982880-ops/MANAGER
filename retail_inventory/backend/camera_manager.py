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
# EDGE CASE CONSTANTS (production tuning)
# ══════════════════════════════════════════════════════════════════════════
_MAX_RECONNECT_DELAY   = 30.0    # Max seconds between reconnect attempts
_INITIAL_RECONNECT_DELAY = 1.0   # Starting backoff delay
_STABILIZATION_FRAMES  = 10      # Frames to wait after reconnect before comparing
_MASS_DISAPPEAR_RATIO  = 0.30    # If detections drop below 30% of previous → skip
_BLACK_FRAME_LOW       = 15      # Mean brightness below this = black frame
_BLACK_FRAME_HIGH      = 250     # Mean brightness above this = whiteout frame
_MAX_THREAD_RESTARTS   = 5       # Max auto-restart attempts for crashed thread
_THREAD_RESTART_DELAY  = 2.0     # Seconds to wait before restarting thread
_DEFAULT_TARGET_FPS    = 12      # Target processing FPS to limit CPU/GPU load
_MAX_READ_FAILURES     = 30      # Consecutive read failures before reconnect attempt


# ══════════════════════════════════════════════════════════════════════════
# ShelfCamera — ONE shelf, ONE camera source, ONE pipeline
# ══════════════════════════════════════════════════════════════════════════

class ShelfCamera:
    """
    Encapsulates everything for a single shelf:
      - Camera capture thread (real or absent)
      - Demo simulation
      - Per-shelf YOLO detection + grid mapping + stock tracking
      - Full edge case handling for production reliability
      - Adaptive snapshot intervals with demo/production modes
    """

    # ── Mode configuration ──
    MODE_INTERVALS = {
        "demo":       15,    # 15 seconds base interval
        "production": 600,   # 10 minutes base interval
    }

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
        target_fps: int = _DEFAULT_TARGET_FPS,
    ):
        self.name             = name
        self.source           = source
        self.enabled          = True
        self.status           = "idle"   # idle | demo | streaming | error | reconnecting
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
        self.target_fps       = target_fps

        # ── System mode (demo / production) — must be set before _rebuild_backends ──
        self.system_mode = "demo"

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

        # ── EDGE CASE: System state for camera health tracking ──
        # Tracks camera connectivity, stabilization, and failure counters
        # so the API can report accurate system health and frozen state.
        self.system_state = {
            "camera_active": False,       # True when camera is reading frames
            "stabilizing": False,         # True during post-reconnect stabilization
            "frames_since_reconnect": 0,  # Counter for stabilization window
            "consecutive_read_failures": 0,
            "thread_restarts": 0,         # How many times thread auto-restarted
            "last_error": "",
            "last_detection_count": 0,    # For mass disappearance detection
            "frozen_grid": None,          # Grid preserved when camera goes offline
            "frozen_stock": None,         # Stock preserved when camera goes offline
            "frames_skipped_black": 0,    # Black/empty frames rejected
            "frames_skipped_mass_disappear": 0,  # Mass disappearance frames rejected
        }

    # ── Backend factory ────────────────────────────────────────────────
    def _rebuild_backends(self):
        shelf_reg       = ShelfRegion(*self.region)
        self.gmapper    = GridMapper(shelf_reg, self.rows, self.cols)
        self.tracker    = SnapshotTracker(self.snap_interval, self.buffer_size, system_mode=self.system_mode)
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
        """Refresh alerts, recommendations, and adapt snapshot interval."""
        stock = self.tracker.get_current_stock()
        rate  = self.tracker.get_sales_rate()
        gnow  = self.tracker.get_stable_grid() or []
        self.last_alerts = self.engine.check_alerts(stock, rate, gnow)
        self.last_recs   = self.engine.get_recommendations(stock, rate)
        # Adapt snapshot interval based on current sales activity
        self.tracker.adapt_interval(rate)

    # ══ EDGE CASE HELPERS ═══════════════════════════════════════════

    @staticmethod
    def _is_black_frame(frame) -> bool:
        """
        EDGE CASE #10: Detect black/empty or whiteout frames.
        Camera glitches can produce all-black or all-white frames
        that would cause all items to "disappear" — triggering false sales.
        We reject these frames entirely.
        """
        import numpy as np
        if frame is None or frame.size == 0:
            return True
        mean_brightness = np.mean(frame)
        return mean_brightness < _BLACK_FRAME_LOW or mean_brightness > _BLACK_FRAME_HIGH

    def _is_mass_disappearance(self, current_count: int) -> bool:
        """
        EDGE CASE #3: Sudden mass disappearance guard.
        If current detection count drops below 30% of the previous frame's
        count, something is blocking the camera (person, hand, etc).
        We skip this frame entirely — do NOT update snapshots or grid.
        """
        prev = self.system_state["last_detection_count"]
        if prev <= 0:
            return False  # No baseline yet
        return current_count < prev * _MASS_DISAPPEAR_RATIO

    def _freeze_state(self):
        """
        EDGE CASE #1: Preserve grid + stock when camera goes offline.
        Prevents the system from showing empty shelves during camera
        downtime. The frozen state is returned by get_state() until
        the camera reconnects and stabilizes.
        """
        live_grid = self.tracker.get_live_grid()
        stock = self.tracker.get_current_stock()
        if live_grid:
            self.system_state["frozen_grid"] = live_grid
        if stock:
            self.system_state["frozen_stock"] = stock
        self._log("❄️ State frozen — camera offline, grid/stock preserved")

    def _attempt_reconnect(self, cap) -> "cv2.VideoCapture | None":
        """
        EDGE CASE #2: Camera reconnect with exponential backoff.
        After camera disconnects, we try to reopen it with increasing
        delays (1s → 2s → 4s → ... → max 30s) to avoid hammering
        a dead device. On success, we reset the baseline snapshot
        and enter a stabilization window.
        """
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass

        delay = _INITIAL_RECONNECT_DELAY
        self.status = "reconnecting"
        self._log(f"🔄 Attempting camera reconnect (source={self.source})...")

        while self.running:
            time.sleep(delay)
            if not self.running:
                return None

            candidates = [self.source] if isinstance(self.source, str) else [self.source, 0, 1, 2]
            for s in candidates:
                new_cap = cv2.VideoCapture(s)
                if new_cap.isOpened():
                    # EDGE CASE #2: Reset baseline — do NOT compare with old snapshot
                    self.tracker.reset()
                    self.system_state["stabilizing"] = True
                    self.system_state["frames_since_reconnect"] = 0
                    self.system_state["consecutive_read_failures"] = 0
                    self.system_state["camera_active"] = True
                    self.status = "streaming"
                    self._log(f"✅ Camera reconnected (source={s}), entering stabilization...")
                    return new_cap
                new_cap.release()

            # Exponential backoff
            delay = min(delay * 2, _MAX_RECONNECT_DELAY)
            self._log(f"⏳ Reconnect failed, retrying in {delay:.0f}s...")

        return None

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
        self.system_state["thread_restarts"] = 0
        # EDGE CASE #11: Launch via _safe_cam_worker which wraps with crash recovery
        t = threading.Thread(target=self._safe_cam_worker, daemon=True)
        t.start()
        self.thread = t

        # Wait up to 1.5 s for first frame or failure
        for _ in range(15):
            time.sleep(0.1)
            if self.latest_jpg is not None or not self.running:
                break

        return self.running

    def stop_camera(self):
        """Signal the capture thread to stop and clear camera state."""
        self.running     = False
        self.latest_jpg  = None
        self.mode        = "demo"
        self.status      = "idle"
        self.system_state["camera_active"] = False
        self._log(f"[{self.name}] Camera stopped")

    def _safe_cam_worker(self):
        """
        EDGE CASE #11: Thread crash recovery wrapper.
        Wraps _cam_worker in try/except to catch any unhandled exceptions.
        Auto-restarts the worker up to _MAX_THREAD_RESTARTS times.
        If all retries are exhausted, the system stops gracefully.
        """
        while self.running and self.system_state["thread_restarts"] < _MAX_THREAD_RESTARTS:
            try:
                self._cam_worker()
                # Normal exit (self.running set to False)
                break
            except Exception as e:
                self.system_state["thread_restarts"] += 1
                self.system_state["last_error"] = str(e)
                self.status = "error"
                self.error_msg = f"Thread crash #{self.system_state['thread_restarts']}: {e}"
                self._log(f"💥 Camera thread crashed: {e}")
                self._log(f"🔁 Auto-restart {self.system_state['thread_restarts']}/{_MAX_THREAD_RESTARTS}...")
                if self.running:
                    time.sleep(_THREAD_RESTART_DELAY)

        if self.system_state["thread_restarts"] >= _MAX_THREAD_RESTARTS:
            self._log(f"❌ Max thread restarts ({_MAX_THREAD_RESTARTS}) reached. Stopping.")
            self.running = False
            self.status = "error"
            self.error_msg = "Camera thread exhausted all restart attempts"

    def _cam_worker(self):
        """
        Camera capture + detection loop (runs in its own thread).

        Handles edge cases:
          #1  Camera disconnect → freeze state, attempt reconnect
          #2  Camera reconnect → reset baseline, stabilize
          #3  Mass disappearance → skip frame
          #10 Black/empty frame → skip frame
          #12 FPS limiting → configurable target_fps
        """
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
            self.system_state["camera_active"] = False
            self._log(f"❌ Cannot open camera source '{source}'")
            return

        self.status    = "streaming"
        self.error_msg = ""
        self.system_state["camera_active"] = True
        self.system_state["consecutive_read_failures"] = 0
        self._log(f"✅ Camera opened: {source}")

        # ── Auto-adapt shelf region to actual frame dimensions ──
        region_adapted = False
        # EDGE CASE #12: FPS limiting — compute target frame interval
        frame_interval = 1.0 / max(self.target_fps, 1)

        while self.running:
            loop_start = time.time()

            ret, frame = cap.read()

            # ── EDGE CASE #1: Camera disconnected / frame read failure ──
            if not ret or frame is None:
                self.system_state["consecutive_read_failures"] += 1
                self.system_state["camera_active"] = False

                if self.system_state["consecutive_read_failures"] >= _MAX_READ_FAILURES:
                    # Too many failures — freeze state and try reconnect
                    self._freeze_state()
                    self._log(f"📵 Camera disconnected after {_MAX_READ_FAILURES} read failures")
                    cap = self._attempt_reconnect(cap)
                    if cap is None:
                        break  # self.running was set to False
                    region_adapted = False  # Re-adapt region on new connection
                    continue

                time.sleep(0.1)
                continue

            # Reset failure counter on successful read
            self.system_state["consecutive_read_failures"] = 0
            self.system_state["camera_active"] = True

            # ── EDGE CASE #10: Black/empty frame detection ──
            if self._is_black_frame(frame):
                self.system_state["frames_skipped_black"] += 1
                self._log(f"⬛ Black/empty frame detected — skipping (total: {self.system_state['frames_skipped_black']})")
                time.sleep(0.1)
                continue

            # On first successful frame, adapt the shelf region to camera resolution
            if not region_adapted:
                fh, fw = frame.shape[:2]
                margin = 10
                new_region = (margin, margin, fw - margin, fh - margin)
                if new_region != self.region:
                    self.region = new_region
                    self.gmapper.update_shelf(ShelfRegion(*new_region))
                    self._log(
                        f"📐 Region auto-adapted to camera resolution "
                        f"{fw}×{fh} → region ({margin},{margin},{fw-margin},{fh-margin})"
                    )
                region_adapted = True

            # ── Run YOLO detection ──
            detections, _ = self._detector.detect(frame)
            shelf_dets    = self.gmapper.filter_shelf_detections(detections)
            current_det_count = len(shelf_dets)

            # ── EDGE CASE #3: Sudden mass disappearance guard ──
            if self._is_mass_disappearance(current_det_count):
                self.system_state["frames_skipped_mass_disappear"] += 1
                self._log(
                    f"👤 Mass disappearance detected ({current_det_count} vs "
                    f"{self.system_state['last_detection_count']} previous) — frame skipped"
                )
                # Still encode frame for display but do NOT update tracking
                annotated = draw_boxes(frame, shelf_dets)
                annotated = self.gmapper.draw_grid_overlay(annotated, None)
                _, jpg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])
                with self.lock:
                    self.latest_jpg = jpg.tobytes()
                elapsed = time.time() - loop_start
                if elapsed < frame_interval:
                    time.sleep(frame_interval - elapsed)
                continue

            # Update detection count baseline for mass disappearance check
            self.system_state["last_detection_count"] = current_det_count



            # ── EDGE CASE #2: Stabilization after reconnect ──
            # During stabilization, we accept frames into the buffer
            # but do NOT compare snapshots (no sales detection).
            if self.system_state["stabilizing"]:
                self.system_state["frames_since_reconnect"] += 1
                if self.system_state["frames_since_reconnect"] >= _STABILIZATION_FRAMES:
                    self.system_state["stabilizing"] = False
                    self.system_state["frozen_grid"] = None
                    self.system_state["frozen_stock"] = None
                    self._log(f"✅ Stabilization complete after {_STABILIZATION_FRAMES} frames")

            # ── Core pipeline: grid mapping → continuous tracking ──
            grid_map      = self.gmapper.map_detections(shelf_dets)
            accepted      = self.tracker.add_frame(grid_map)

            # Sync snapshot count from tracker (for WS dedup)
            self.snapshot_count = self.tracker.snapshot_count

            self._refresh_insights()
            self.frame_count += 1

            # ── Encode annotated frame for WebSocket streaming ──
            annotated = draw_boxes(frame, shelf_dets)
            # Use stable grid (consensus) for the visual overlay
            display_grid = self.tracker.get_stable_grid()
            annotated = self.gmapper.draw_grid_overlay(annotated, display_grid)
            _, jpg = cv2.imencode(
                ".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 75]
            )
            with self.lock:
                self.latest_jpg = jpg.tobytes()

            ts      = datetime.now().strftime("%H:%M:%S")
            occ_tag = "" if accepted else " [OCCLUDED]"
            stab_tag = " [STABILIZING]" if self.system_state["stabilizing"] else ""
            self._log(
                f"[{ts}] Frame #{self.frame_count} — "
                f"{current_det_count} objects{occ_tag}{stab_tag}"
            )

            # ── EDGE CASE #12: FPS limiting ──
            elapsed = time.time() - loop_start
            if elapsed < frame_interval:
                time.sleep(frame_interval - elapsed)

        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass
        self.system_state["camera_active"] = False
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
        live_grid = self.tracker.get_stable_grid()
        history   = self.tracker.get_stock_history()
        thr       = self.stock_threshold

        # ── EDGE CASE #1: Use frozen state when camera is offline ──
        # If camera disconnected, return the last known grid/stock
        # so the dashboard doesn't show empty shelves during downtime.
        if not self.system_state["camera_active"] and self.running:
            if self.system_state["frozen_grid"] and not live_grid:
                live_grid = self.system_state["frozen_grid"]
            if self.system_state["frozen_stock"] and not stock:
                stock = self.system_state["frozen_stock"]

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

        # ── EDGE CASE #1: Add system alert when camera is offline ──
        if self.running and not self.system_state["camera_active"]:
            alerts_out.append(dict(
                item="CAMERA", severity="critical",
                stock=0, rate=0,
                action="Camera offline — using frozen state",
                time_to_empty="N/A",
            ))

        if self.system_state["stabilizing"]:
            alerts_out.append(dict(
                item="CAMERA", severity="warning",
                stock=0, rate=0,
                action=f"Stabilizing after reconnect ({self.system_state['frames_since_reconnect']}/{_STABILIZATION_FRAMES})",
                time_to_empty="N/A",
            ))

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

        # Cumulative sales/restocks
        total_sales = dict(self.tracker.get_total_sales() or {})
        total_restocks_map = dict(self.tracker.get_total_restocks() or {})
        total_sold = sum(total_sales.values())

        # Net stock = current detected minus cumulative sales
        current_detected = sum(stock.values())
        net_stock = max(0, current_detected - total_sold)

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
            total_stock=net_stock,
            detected_stock=current_detected,
            total_sold=total_sold,
            total_sales_map=total_sales,
            num_classes=len(stock),
            low_count=low_count,
            empty_count=empty_count,
            grid_rows=self.rows,
            grid_cols=self.cols,
            products=products,
            grid=grid_out,
            grid_map=live_grid,
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
            # ── Edge case diagnostics ──
            system_state=dict(self.system_state),
            # ── Snapshot timing (countdown, mode, interval) ──
            snapshot_info=self.tracker.get_snapshot_info(),
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
