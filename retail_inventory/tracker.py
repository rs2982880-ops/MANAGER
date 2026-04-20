"""
Snapshot-based stock tracking module.
======================================
Replaces simple count-difference tracking with a **position-aware,
movement-aware** system built on grid snapshots.

Key concepts
------------
* **Rolling frame buffer** — last N grid observations are kept.

* **Majority voting** — a stable grid is produced by voting across
  the buffer; a cell is only "empty" if the *majority* of recent
  frames agree.  This eliminates false sales from momentary occlusion.

* **Occlusion guard** — if occupied-cell count drops by > 50 %
  compared to the running average the frame is discarded (someone is
  blocking the camera).

* **Count-capped position diff** — the critical upgrade over a naive
  cell-by-cell diff.  Sales for each item are capped at:

      cap = old_count(item) – new_count(item)

  If cap ≤ 0 the item count has not decreased, so any ``product →
  empty`` cell transitions are treated as *movements*, not sales.
  If cap > 0, exactly ``cap`` disappeared cells are counted as
  confirmed sales.  This makes the system immune to rearrangements:
  a bottle that moves from (0,0) → (0,2) causes NO sale because the
  global bottle count stays the same.

* **Standalone helpers** — ``detect_sales()`` and
  ``detect_movement()`` are module-level functions usable outside the
  tracker class for unit testing or custom pipelines.

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
    # Grid item counter (helper used by comparison logic)
    # ------------------------------------------------------------------
    @staticmethod
    def _count_items_in_grid(grid: List[List[str]]) -> Dict[str, int]:
        """
        Count every non-empty cell label in *grid*.

        Returns a dict mapping class → count, e.g. {"bottle": 3, "cup": 1}.
        Used by the movement-aware comparison to establish per-item caps.
        """
        counts: Dict[str, int] = {}
        for row in grid:
            for cell in row:
                if cell != "empty":
                    counts[cell] = counts.get(cell, 0) + 1
        return counts

    # ------------------------------------------------------------------
    # Position-based snapshot comparison  (movement-aware)
    # ------------------------------------------------------------------
    def _compare_snapshots(self):
        """
        Count-capped, movement-aware diff between previous and current
        snapshot grids.

        Algorithm
        ---------
        For each item class:

        1. **Count gate** — compute cap = old_count – new_count.
           * cap ≤ 0  → the item did not decrease globally.  Any
             ``product → empty`` cell transitions are rearrangements,
             not sales.  Skip sales detection for this item.
           * cap > 0  → the item count decreased; up to *cap* cells
             are considered confirmed sales.

        2. **Cell scan (sales)** — iterate over cells where
           ``old[r][c] == item`` and ``new[r][c] == "empty"``.
           Count each as a sale until the cap is reached.

        3. **Restock scan** — cells where ``old[r][c] == "empty"``
           and ``new[r][c] == item``, capped at new_count – old_count
           (symmetric logic).

        Why this works for rearrangements
        -----------------------------------
        If a bottle moves from (0,0) to (0,2) the global bottle count
        stays the same, so cap = 0 and the loop body is never entered.
        No false sale is generated even though (0,0) changed from
        "bottle" → "empty".
        """
        old = self.previous_snapshot.grid_map
        new = self.current_snapshot.grid_map

        # Delegate to the standalone function so logic lives in one place
        sales, restocks = detect_sales(old, new)

        self.latest_sales    = sales
        self.latest_restocks = restocks

        for item, qty in sales.items():
            self.total_sales[item] += qty
        for item, qty in restocks.items():
            self.total_restocks[item] += qty

    # ------------------------------------------------------------------
    # Sales rate  (items / hour from last 2-3 snapshots)
    # ------------------------------------------------------------------
    def get_sales_rate(self) -> Dict[str, float]:
        """
        Compute per-item sales rate (units / hour) using the last 3
        snapshots.  Uses the same movement-aware detect_sales() logic
        as snapshot comparison so rearrangements are excluded here too.
        """
        if len(self.snapshot_history) < 2:
            return {}

        recent    = self.snapshot_history[-3:]
        span_secs = (recent[-1].timestamp - recent[0].timestamp).total_seconds()
        span_hrs  = max(span_secs / 3600, 0.001)

        # Accumulate movement-aware sales across the recent window
        sales: Dict[str, int] = defaultdict(int)
        for i in range(1, len(recent)):
            interval_sales, _ = detect_sales(
                recent[i - 1].grid_map,
                recent[i].grid_map,
            )
            for item, qty in interval_sales.items():
                sales[item] += qty

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


# ======================================================================
# Module-level standalone functions (importable for unit tests / pipelines)
# ======================================================================

def detect_sales(
    old_map: List[List[str]],
    new_map: List[List[str]],
) -> Tuple[Dict[str, int], Dict[str, int]]:
    """
    Count-capped, movement-aware diff between two grid snapshots.

    Parameters
    ----------
    old_map : 2-D list of labels from the **previous** snapshot.
    new_map : 2-D list of labels from the **current** snapshot.

    Returns
    -------
    sales    : {item: qty_sold}    — confirmed disappearances only.
    restocks : {item: qty_added}   — confirmed new arrivals only.

    Algorithm
    ---------
    For each item class *X*:

    **Sales** (item count decreased):
        cap = old_count(X) - new_count(X)
        If cap <= 0  → no net reduction; any cell changes are
                        rearrangements → skip.
        If cap > 0   → scan cells where old[r][c]=="X" and
                        new[r][c]=="empty"; count as sale until
                        *cap* is reached.

    **Restocks** (item count increased):
        cap = new_count(X) - old_count(X)
        Scan cells where old[r][c]=="empty" and new[r][c]=="X";
        count up to *cap*.

    Why this is movement-proof
    --------------------------
    If a bottle moves from (0,0) to (0,2) the global count stays at 3.
    cap = 3 - 3 = 0, so the inner loop never executes and no false
    sale is recorded.
    """
    if not old_map or not new_map:
        return {}, {}

    rows = min(len(old_map), len(new_map))
    cols = min(
        len(old_map[0]) if old_map else 0,
        len(new_map[0]) if new_map else 0,
    )
    if rows == 0 or cols == 0:
        return {}, {}

    # --- Step 1: per-item global counts ---
    def _count(grid: List[List[str]]) -> Dict[str, int]:
        c: Dict[str, int] = {}
        for row in grid:
            for cell in row:
                if cell != "empty":
                    c[cell] = c.get(cell, 0) + 1
        return c

    old_counts = _count(old_map)
    new_counts = _count(new_map)

    # Gather all item classes seen in either snapshot
    all_items = set(old_counts) | set(new_counts)

    sales:    Dict[str, int] = {}
    restocks: Dict[str, int] = {}

    for item in all_items:
        old_n = old_counts.get(item, 0)
        new_n = new_counts.get(item, 0)

        # ---- Sales: item count decreased ----
        sale_cap = old_n - new_n
        if sale_cap > 0:
            confirmed = 0
            for r in range(rows):
                for c in range(cols):
                    if confirmed >= sale_cap:
                        break
                    # Cell had the item before AND is now empty
                    if old_map[r][c] == item and new_map[r][c] == "empty":
                        confirmed += 1
                if confirmed >= sale_cap:
                    break
            if confirmed > 0:
                sales[item] = confirmed

        # ---- Restocks: item count increased ----
        restock_cap = new_n - old_n
        if restock_cap > 0:
            confirmed = 0
            for r in range(rows):
                for c in range(cols):
                    if confirmed >= restock_cap:
                        break
                    # Cell was empty before AND now has the item
                    if old_map[r][c] == "empty" and new_map[r][c] == item:
                        confirmed += 1
                if confirmed >= restock_cap:
                    break
            if confirmed > 0:
                restocks[item] = confirmed

    return sales, restocks


def detect_movement(
    old_map: List[List[str]],
    new_map: List[List[str]],
) -> Dict[str, str]:
    """
    Classify per-item changes between two snapshots as MOVED, SOLD,
    RESTOCKED, or UNCHANGED.

    Returns
    -------
    A dict mapping item name to one of:
        "SOLD"       — net count decreased (confirmed disappearance)
        "RESTOCKED"  — net count increased
        "MOVED"      — cell positions changed but global count unchanged
        "UNCHANGED"  — no change in count or positions

    Useful for the dashboard debug panel and human-readable logging.
    """
    if not old_map or not new_map:
        return {}

    def _count(grid: List[List[str]]) -> Dict[str, int]:
        c: Dict[str, int] = {}
        for row in grid:
            for cell in row:
                if cell != "empty":
                    c[cell] = c.get(cell, 0) + 1
        return c

    def _positions(grid: List[List[str]], item: str) -> set:
        return {
            (r, c)
            for r, row in enumerate(grid)
            for c, cell in enumerate(row)
            if cell == item
        }

    old_counts = _count(old_map)
    new_counts = _count(new_map)
    all_items  = set(old_counts) | set(new_counts)

    result: Dict[str, str] = {}
    for item in all_items:
        old_n = old_counts.get(item, 0)
        new_n = new_counts.get(item, 0)

        if new_n < old_n:
            result[item] = "SOLD"
        elif new_n > old_n:
            result[item] = "RESTOCKED"
        else:
            # Same count — check if positions changed (movement)
            old_pos = _positions(old_map, item)
            new_pos = _positions(new_map, item)
            result[item] = "MOVED" if old_pos != new_pos else "UNCHANGED"

    return result
