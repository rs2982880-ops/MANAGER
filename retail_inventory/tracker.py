"""
Snapshot-based stock tracking module.
======================================
Replaces simple count-difference tracking with a **position-aware**
system built on grid snapshots.

Key concepts
------------
* **Rolling frame buffer** — last N grid observations are kept.
* **Majority voting** — a stable grid is produced by voting across
  the buffer; a cell is only "empty" if the *majority* of recent
  frames agree.  This eliminates false sales from momentary occlusion.
* **Occlusion guard** — if occupied-cell count drops by > 50 %
  compared to the running average the frame is discarded (someone is
  blocking the camera).
* **Position-based diff** — sales and restocks are detected by
  comparing cell-by-cell: ``old[r][c]="product" → new[r][c]="empty"``
  counts as one sale.
* **Stock history** — each snapshot's item counts are kept for
  real-time trend charts in the Streamlit dashboard.
"""

import copy
from collections import Counter, defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple


# ======================================================================
# Snapshot data object
# ======================================================================

class Snapshot:
    """One point-in-time capture of the shelf grid."""

    def __init__(self, grid_map: List[List[str]], timestamp: datetime = None):
        self.grid_map  = copy.deepcopy(grid_map)
        self.timestamp = timestamp or datetime.now()
        self.item_counts = self._count()

    def _count(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for row in self.grid_map:
            for cell in row:
                if cell != "empty":
                    counts[cell] = counts.get(cell, 0) + 1
        return counts

    def total_occupied(self) -> int:
        return sum(self.item_counts.values())

    def total_cells(self) -> int:
        return len(self.grid_map) * (len(self.grid_map[0]) if self.grid_map else 0)

    def total_empty(self) -> int:
        return self.total_cells() - self.total_occupied()


# ======================================================================
# Snapshot tracker
# ======================================================================

class SnapshotTracker:
    """
    Periodic-snapshot tracker with occlusion handling.

    Usage
    -----
    1.  Each frame → ``add_frame(grid_map)``
    2.  Periodically check ``should_take_snapshot()``
    3.  When ready → ``take_snapshot()`` to lock in a stable grid
        and compare with the previous snapshot.
    """

    def __init__(
        self,
        snapshot_interval_seconds: float = 600.0,
        buffer_size: int = 5,
        occlusion_drop_threshold: float = 0.50,
    ):
        """
        Args:
            snapshot_interval_seconds: seconds between auto-snapshots.
            buffer_size:               rolling-buffer depth for majority voting.
                                       Larger = more resistance to occlusion.
            occlusion_drop_threshold:  if occupied-cell ratio vs. rolling average
                                       drops below this, the frame is discarded.
        """
        self.snapshot_interval       = snapshot_interval_seconds
        self.buffer_size             = buffer_size
        self.occlusion_drop_threshold = occlusion_drop_threshold

        # Rolling buffer of recent grid observations
        # Each entry is a complete grid: List[List[str]]
        self.frame_buffer: List[List[List[str]]] = []

        # Snapshot chain
        self.previous_snapshot: Optional[Snapshot] = None
        self.current_snapshot:  Optional[Snapshot] = None
        self.snapshot_history:  List[Snapshot]     = []

        # Per-interval sales / restocks (reset each snapshot)
        self.latest_sales:    Dict[str, int] = {}
        self.latest_restocks: Dict[str, int] = {}

        # Cumulative tallies
        self.total_sales:    Dict[str, int] = defaultdict(int)
        self.total_restocks: Dict[str, int] = defaultdict(int)

        # Timing
        self.last_snapshot_time: Optional[datetime] = None
        self.tracking_start:     Optional[datetime] = None

        # Stats counters
        self.frames_processed:          int = 0
        self.frames_skipped_occlusion:  int = 0

        # --- Stock history for trend charts ---
        # Each entry: (datetime, {item: count})
        self.stock_history: List[Tuple[datetime, Dict[str, int]]] = []

    # ------------------------------------------------------------------
    # Frame ingestion
    # ------------------------------------------------------------------
    def add_frame(self, grid_map: List[List[str]]) -> bool:
        """
        Ingest one frame's grid into the rolling buffer.

        Occlusion guard: if the number of occupied cells drops
        sharply (> 50 % by default) vs. the rolling average,
        the frame is flagged as occluded and rejected.

        Returns True if accepted, False if flagged as occluded.
        """
        self.frames_processed += 1
        if self.tracking_start is None:
            self.tracking_start = datetime.now()

        # --- Occlusion guard ---
        if self._is_likely_occluded(grid_map):
            self.frames_skipped_occlusion += 1
            return False

        self.frame_buffer.append(copy.deepcopy(grid_map))
        if len(self.frame_buffer) > self.buffer_size:
            self.frame_buffer.pop(0)
        return True

    # ------------------------------------------------------------------
    # Snapshot lifecycle
    # ------------------------------------------------------------------
    def should_take_snapshot(self) -> bool:
        """True when enough frames have buffered AND the interval has elapsed."""
        # Need at least min(3, buffer_size) accepted frames before first snapshot
        min_frames = min(3, self.buffer_size)
        if len(self.frame_buffer) < min_frames:
            return False
        if self.last_snapshot_time is None:
            return True
        elapsed = (datetime.now() - self.last_snapshot_time).total_seconds()
        return elapsed >= self.snapshot_interval

    def take_snapshot(self) -> Optional[Snapshot]:
        """
        Build a **stable** grid via majority voting, wrap it in a
        ``Snapshot``, compare to the previous one, and persist the counts
        to the stock history.

        Majority voting ensures that a cell is only "empty" if the
        majority of recent buffer frames agree — preventing momentary
        occlusion from triggering false sales.
        """
        if not self.frame_buffer:
            return None

        # --- Majority-vote across buffer to get stable grid ---
        stable_grid = self._majority_vote_grid()

        self.previous_snapshot = self.current_snapshot
        self.current_snapshot  = Snapshot(stable_grid)
        self.last_snapshot_time = datetime.now()

        self.snapshot_history.append(self.current_snapshot)
        if len(self.snapshot_history) > 100:
            self.snapshot_history = self.snapshot_history[-50:]

        # --- Position-based diff vs. previous snapshot ---
        if self.previous_snapshot is not None:
            self._compare_snapshots()

        # --- Record to stock history for trend charts ---
        self.stock_history.append(
            (self.current_snapshot.timestamp, self.current_snapshot.item_counts.copy())
        )
        if len(self.stock_history) > 200:
            self.stock_history = self.stock_history[-100:]

        return self.current_snapshot

    # ------------------------------------------------------------------
    # Occlusion detection
    # ------------------------------------------------------------------
    def _is_likely_occluded(self, grid: List[List[str]]) -> bool:
        """
        Flag a frame as occluded if the number of occupied cells
        drops sharply compared to the recent rolling average.

        We look at the last 3 buffer frames to compute the average
        occupancy.  If the new frame's occupancy is below
        ``occlusion_drop_threshold × average``, it is rejected.

        This catches the scenario where a person walks in front of
        the camera and temporarily blocks all products.
        """
        # Need at least 3 frames in buffer to establish a baseline
        if len(self.frame_buffer) < 3:
            return False

        current_occ = sum(1 for row in grid for c in row if c != "empty")

        # Average occupancy over the last 3 frames
        lookback  = self.frame_buffer[-3:]
        avg_occ   = sum(
            sum(1 for row in buf for c in row if c != "empty")
            for buf in lookback
        ) / len(lookback)

        if avg_occ == 0:
            return False

        # If current occupancy is less than threshold × average → occluded
        return (current_occ / avg_occ) < self.occlusion_drop_threshold

    # ------------------------------------------------------------------
    # Majority voting  (core occlusion resilience)
    # ------------------------------------------------------------------
    def _majority_vote_grid(self) -> List[List[str]]:
        """
        For each cell, choose the label that appears most often
        across the buffer frames.

        Example: if a cell shows ["bottle","bottle","empty","bottle","bottle"]
        across 5 frames, the voted result is "bottle" — the single
        "empty" frame (e.g. someone's hand briefly covering the product)
        is overridden by the majority.
        """
        if not self.frame_buffer:
            return []

        rows = len(self.frame_buffer[0])
        cols = len(self.frame_buffer[0][0]) if rows else 0
        stable: List[List[str]] = [["empty"] * cols for _ in range(rows)]

        for r in range(rows):
            for c in range(cols):
                labels = [buf[r][c] for buf in self.frame_buffer]
                stable[r][c] = Counter(labels).most_common(1)[0][0]

        return stable

    # ------------------------------------------------------------------
    # Position-based snapshot comparison
    # ------------------------------------------------------------------
    def _compare_snapshots(self):
        """
        Cell-by-cell diff between previous and current snapshot.

        Sales detection rule:
            old[r][c] = "product"  AND  new[r][c] = "empty"
            → 1 sale of that product

        Restock detection rule:
            old[r][c] = "empty"    AND  new[r][c] = "product"
            → 1 restock of that product

        This is the core of position-based tracking — it does NOT
        rely on total counts, so it's immune to temporary count
        fluctuations caused by occlusion.
        """
        old = self.previous_snapshot.grid_map
        new = self.current_snapshot.grid_map

        self.latest_sales    = {}
        self.latest_restocks = {}

        rows = min(len(old), len(new))
        cols = min(
            len(old[0]) if old else 0,
            len(new[0]) if new else 0,
        )

        for r in range(rows):
            for c in range(cols):
                o, n = old[r][c], new[r][c]
                if o != "empty" and n == "empty":
                    # Product disappeared → sale
                    self.latest_sales[o] = self.latest_sales.get(o, 0) + 1
                    self.total_sales[o] += 1
                elif o == "empty" and n != "empty":
                    # Cell filled → restock
                    self.latest_restocks[n] = self.latest_restocks.get(n, 0) + 1
                    self.total_restocks[n] += 1

    # ------------------------------------------------------------------
    # Sales rate  (items / hour from last 2-3 snapshots)
    # ------------------------------------------------------------------
    def get_sales_rate(self) -> Dict[str, float]:
        """
        Compute per-item sales rate (units / hour) using the last 3
        snapshots.  Using multiple intervals smooths out noise.
        """
        if len(self.snapshot_history) < 2:
            return {}

        recent    = self.snapshot_history[-3:]
        span_secs = (recent[-1].timestamp - recent[0].timestamp).total_seconds()
        span_hrs  = max(span_secs / 3600, 0.001)

        sales: Dict[str, int] = defaultdict(int)
        for i in range(1, len(recent)):
            o = recent[i - 1].grid_map
            n = recent[i].grid_map
            for r in range(min(len(o), len(n))):
                for c in range(min(
                    len(o[0]) if o else 0,
                    len(n[0]) if n else 0,
                )):
                    if o[r][c] != "empty" and n[r][c] == "empty":
                        sales[o[r][c]] += 1

        return {item: cnt / span_hrs for item, cnt in sales.items()}

    # ------------------------------------------------------------------
    # Heatmap  (fraction of snapshots each cell was empty)
    # ------------------------------------------------------------------
    def compute_emptiness_heatmap(self) -> List[List[float]]:
        """
        Return a 2-D array where each value is the fraction of
        snapshots in which that cell was empty.
        0.0 = always stocked, 1.0 = always empty.
        """
        if not self.snapshot_history:
            return []
        rows = len(self.snapshot_history[0].grid_map)
        cols = len(self.snapshot_history[0].grid_map[0]) if rows else 0
        empty_acc = [[0] * cols for _ in range(rows)]

        for snap in self.snapshot_history:
            for r in range(min(rows, len(snap.grid_map))):
                for c in range(min(cols, len(snap.grid_map[0]))):
                    if snap.grid_map[r][c] == "empty":
                        empty_acc[r][c] += 1

        total = len(self.snapshot_history)
        return [[empty_acc[r][c] / total for c in range(cols)] for r in range(rows)]

    # ------------------------------------------------------------------
    # Stock history for trend charts
    # ------------------------------------------------------------------
    def get_stock_history(self) -> List[Tuple[datetime, Dict[str, int]]]:
        """
        Returns a list of (timestamp, {item: count}) tuples from past
        snapshots — used by the dashboard to render trend line charts.
        """
        return list(self.stock_history)

    # ------------------------------------------------------------------
    # Public getters
    # ------------------------------------------------------------------
    def get_current_stock(self) -> Dict[str, int]:
        if self.current_snapshot:
            return self.current_snapshot.item_counts.copy()
        return {}

    def get_current_grid(self) -> Optional[List[List[str]]]:
        if self.current_snapshot:
            return copy.deepcopy(self.current_snapshot.grid_map)
        return None

    def get_live_grid(self) -> Optional[List[List[str]]]:
        """Most recent accepted buffer frame (not yet voted on)."""
        if self.frame_buffer:
            return copy.deepcopy(self.frame_buffer[-1])
        return None

    def get_latest_sales(self) -> Dict[str, int]:
        return self.latest_sales.copy()

    def get_latest_restocks(self) -> Dict[str, int]:
        return self.latest_restocks.copy()

    def get_total_sales(self) -> Dict[str, int]:
        return dict(self.total_sales)

    def get_total_restocks(self) -> Dict[str, int]:
        return dict(self.total_restocks)

    def get_stats(self) -> dict:
        return {
            "frames_processed": self.frames_processed,
            "frames_skipped":   self.frames_skipped_occlusion,
            "snapshots_taken":  len(self.snapshot_history),
            "buffer_fill":      len(self.frame_buffer),
            "tracking_since":   self.tracking_start,
        }

    def reset(self):
        self.frame_buffer.clear()
        self.previous_snapshot   = None
        self.current_snapshot    = None
        self.snapshot_history.clear()
        self.latest_sales.clear()
        self.latest_restocks.clear()
        self.total_sales.clear()
        self.total_restocks.clear()
        self.last_snapshot_time  = None
        self.tracking_start      = None
        self.frames_processed    = 0
        self.frames_skipped_occlusion = 0
        self.stock_history.clear()
