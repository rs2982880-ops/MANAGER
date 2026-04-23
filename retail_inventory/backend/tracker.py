"""
tracker.py — Count-Aware Two-Level Stabilized Tracking Engine
===============================================================
Architecture (two-level pipeline):
  Frame → Frame Buffer (5) → Stable Grid (L1 vote)
    → Decision Buffer (3) → Confirmed Grid (L2 vote)
      → Compare with Stored State → Cooldown + Visibility
        → Sales Update

Cell format: (label, count) tuple
  ("book", 3) = 3 books detected in this cell
  ("empty", 0) = nothing in this cell

Sales are count-based:
  old=("book",3), new=("book",1) → 2 books sold
"""

import copy
import math
import time
from collections import Counter, defaultdict
from datetime import datetime
from statistics import median
from typing import Dict, List, Optional, Tuple

# Type alias for counted grid cell
Cell = Tuple[str, int]      # (label, count)
CountedGrid = List[List[Cell]]

# ======================================================================
# Constants
# ======================================================================
_DECISION_BUFFER_SIZE = 3
_COOLDOWN_DEMO        = 15.0
_COOLDOWN_PRODUCTION  = 60.0
_VISIBILITY_THRESHOLD = 0.60
_MIN_STOCK_CHANGE     = 2

# ======================================================================
# Snapshot
# ======================================================================

class Snapshot:
    """Point-in-time capture with per-cell counts."""

    def __init__(self, grid: CountedGrid, timestamp: datetime = None):
        self.grid_map  = copy.deepcopy(grid)
        self.timestamp = timestamp or datetime.now()
        self.item_counts = self._count()

    def _count(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for row in self.grid_map:
            for label, cnt in row:
                if label != "empty" and cnt > 0:
                    counts[label] = counts.get(label, 0) + cnt
        return counts

    def total_occupied(self) -> int:
        return sum(self.item_counts.values())

    def total_cells(self) -> int:
        return len(self.grid_map) * (len(self.grid_map[0]) if self.grid_map else 0)

    def total_empty(self) -> int:
        return self.total_cells() - self.total_occupied()


# ======================================================================
# Helper: convert between string and counted grids
# ======================================================================

def _string_to_counted(grid: List[List[str]]) -> CountedGrid:
    """Convert legacy string grid to counted grid."""
    return [
        [(cell, 1) if cell != "empty" else ("empty", 0) for cell in row]
        for row in grid
    ]

def _counted_to_string(grid: CountedGrid) -> List[List[str]]:
    """Convert counted grid back to string grid for backward compat."""
    return [[label for label, _ in row] for row in grid]

def _count_grid_items(grid: CountedGrid) -> Dict[str, int]:
    """Sum up all items across a counted grid."""
    counts: Dict[str, int] = {}
    for row in grid:
        for label, cnt in row:
            if label != "empty" and cnt > 0:
                counts[label] = counts.get(label, 0) + cnt
    return counts

def _total_items(grid: CountedGrid) -> int:
    return sum(cnt for row in grid for _, cnt in row)

def _get_adjacent(r: int, c: int, rows: int, cols: int) -> List[Tuple[int, int]]:
    neighbors = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols:
                neighbors.append((nr, nc))
    return neighbors


# ======================================================================
# Tracker
# ======================================================================

class SnapshotTracker:
    """
    Count-aware, two-level stabilized tracker.

    Level 1: frame_buffer (5 counted grids) → stable grid via majority vote
    Level 2: decision_buffer (3 stable grids) → confirmed grid via consensus
    Sales compare confirmed grids using per-cell counts.
    """

    HIGH_SALES_THRESHOLD = 5.0
    LOW_SALES_THRESHOLD  = 1.0
    STOCK_CHANGE_TRIGGER = 3
    MODE_BOUNDS = {
        "demo":       {"min": 10, "max": 30},
        "production": {"min": 300, "max": 1800},
    }

    def __init__(
        self,
        snapshot_interval_seconds: float = 600.0,
        buffer_size: int = 5,
        occlusion_drop_threshold: float = 0.50,
        system_mode: str = "demo",
    ):
        self.base_interval     = snapshot_interval_seconds
        self.snapshot_interval  = snapshot_interval_seconds
        self.buffer_size        = buffer_size
        self.occlusion_drop_threshold = occlusion_drop_threshold
        self.system_mode        = system_mode
        self.majority_threshold = math.ceil(buffer_size / 2)

        # Level 1: frame buffer (counted grids)
        self.frame_buffer: List[CountedGrid] = []

        # Level 2: decision buffer (stable grids)
        self.decision_buffer: List[CountedGrid] = []
        self.decision_buffer_size = _DECISION_BUFFER_SIZE
        self.decision_threshold   = math.ceil(_DECISION_BUFFER_SIZE / 2)

        # Per-cell cooldown: {(r,c): timestamp}
        self._cell_cooldown: Dict[Tuple[int, int], float] = {}

        # Snapshot chain
        self.previous_snapshot: Optional[Snapshot] = None
        self.current_snapshot:  Optional[Snapshot] = None
        self.snapshot_history:  List[Snapshot]      = []

        # Sales tracking
        self.latest_sales:    Dict[str, int] = {}
        self.latest_restocks: Dict[str, int] = {}
        self.total_sales:     Dict[str, int] = defaultdict(int)
        self.total_restocks:  Dict[str, int] = defaultdict(int)

        # Timing
        self.last_snapshot_time: Optional[datetime] = None
        self.tracking_start:     Optional[datetime] = None

        # Stats
        self.frames_processed:         int = 0
        self.frames_skipped_occlusion: int = 0

        # Stock history for charts
        self.stock_history: List[Tuple[datetime, Dict[str, int]]] = []
        self._prev_stock_total: int = 0

    # ==================================================================
    # Mode + adaptive interval
    # ==================================================================
    def set_mode(self, mode: str, base_interval: float):
        self.system_mode = mode
        self.base_interval = base_interval
        self.snapshot_interval = base_interval
        self.last_snapshot_time = datetime.now()

    def adapt_interval(self, sales_rate: Dict[str, float]):
        total_rate = sum(sales_rate.values()) if sales_rate else 0
        bounds = self.MODE_BOUNDS.get(self.system_mode, self.MODE_BOUNDS["production"])
        if total_rate > self.HIGH_SALES_THRESHOLD:
            new = self.base_interval * 0.5
        elif total_rate < self.LOW_SALES_THRESHOLD:
            new = self.base_interval * 1.5
        else:
            new = self.base_interval
        self.snapshot_interval = max(bounds["min"], min(bounds["max"], new))

    def get_time_remaining(self) -> float:
        if self.last_snapshot_time is None:
            return 0.0
        elapsed = (datetime.now() - self.last_snapshot_time).total_seconds()
        return max(0.0, self.snapshot_interval - elapsed)

    def get_snapshot_info(self) -> dict:
        return {
            "mode": self.system_mode,
            "base_interval": self.base_interval,
            "current_interval": round(self.snapshot_interval, 1),
            "time_remaining": round(self.get_time_remaining(), 1),
        }

    # ==================================================================
    # Frame ingestion (accepts both formats)
    # ==================================================================
    def add_frame(self, grid_map) -> bool:
        """
        Ingest one frame. Accepts:
          - CountedGrid: List[List[Tuple[str,int]]]
          - Legacy string grid: List[List[str]]
        """
        self.frames_processed += 1
        if self.tracking_start is None:
            self.tracking_start = datetime.now()

        # Auto-convert string grid to counted
        if grid_map and grid_map[0] and isinstance(grid_map[0][0], str):
            counted = _string_to_counted(grid_map)
        else:
            counted = grid_map

        if self._is_likely_occluded(counted):
            self.frames_skipped_occlusion += 1
            return False

        self.frame_buffer.append(copy.deepcopy(counted))
        if len(self.frame_buffer) > self.buffer_size:
            self.frame_buffer.pop(0)
        return True

    # ==================================================================
    # Snapshot lifecycle
    # ==================================================================
    def should_take_snapshot(self) -> bool:
        min_frames = min(3, self.buffer_size)
        if len(self.frame_buffer) < min_frames:
            return False
        if self.last_snapshot_time is None:
            return True
        elapsed = (datetime.now() - self.last_snapshot_time).total_seconds()
        if elapsed >= self.snapshot_interval:
            return True
        if self.frame_buffer and self.current_snapshot:
            current_total = _total_items(self.frame_buffer[-1])
            if abs(current_total - self._prev_stock_total) > self.STOCK_CHANGE_TRIGGER:
                return True
        return False

    def take_snapshot(self) -> Optional[Snapshot]:
        """
        Two-level pipeline:
          1. Frame buffer → stable grid (L1 majority + median count)
          2. Decision buffer → confirmed grid (L2 consensus)
          3. Visibility validation
          4. Count-based sales detection with cooldown
        """
        if not self.frame_buffer:
            return None

        # Level 1: build stable grid
        stable = self._build_stable_grid()

        # Level 2: push to decision buffer and build confirmed
        self.decision_buffer.append(copy.deepcopy(stable))
        if len(self.decision_buffer) > self.decision_buffer_size:
            self.decision_buffer.pop(0)
        confirmed = self._build_confirmed_grid()

        # Visibility check
        if not self._validate_visibility(confirmed):
            return self.current_snapshot

        # Create snapshot from confirmed grid
        self.previous_snapshot = self.current_snapshot
        self.current_snapshot  = Snapshot(confirmed)
        self.last_snapshot_time = datetime.now()
        self._prev_stock_total = self.current_snapshot.total_occupied()

        self.snapshot_history.append(self.current_snapshot)
        if len(self.snapshot_history) > 100:
            self.snapshot_history = self.snapshot_history[-50:]

        # Count-based sales detection
        if self.previous_snapshot is not None:
            self._compare_snapshots()

        # Stock history
        self.stock_history.append(
            (self.current_snapshot.timestamp, self.current_snapshot.item_counts.copy())
        )
        if len(self.stock_history) > 200:
            self.stock_history = self.stock_history[-100:]

        return self.current_snapshot

    # ==================================================================
    # Level 1: Stable grid (majority vote on label + median count)
    # ==================================================================
    def _build_stable_grid(self) -> CountedGrid:
        """
        For each cell across the frame buffer:
          1. Vote on label: most frequent label wins if ≥ threshold
          2. Compute count: median of counts where label matches
        """
        if not self.frame_buffer:
            return []
        rows = len(self.frame_buffer[0])
        cols = len(self.frame_buffer[0][0]) if rows else 0
        stable: CountedGrid = [[("empty", 0)] * cols for _ in range(rows)]
        threshold = self.majority_threshold

        for r in range(rows):
            for c in range(cols):
                labels = [buf[r][c][0] for buf in self.frame_buffer]
                counts_for_cell = [buf[r][c][1] for buf in self.frame_buffer]

                # Step 1: majority vote on label
                label_counter = Counter(labels)
                best_label, best_count = label_counter.most_common(1)[0]

                if best_count < threshold:
                    stable[r][c] = ("empty", 0)
                    continue

                if best_label == "empty":
                    stable[r][c] = ("empty", 0)
                    continue

                # Step 2: median count from frames where this label appeared
                matching_counts = [
                    counts_for_cell[i]
                    for i in range(len(labels))
                    if labels[i] == best_label and counts_for_cell[i] > 0
                ]
                final_count = int(median(matching_counts)) if matching_counts else 1
                stable[r][c] = (best_label, max(1, final_count))

        return stable

    # ==================================================================
    # Level 2: Confirmed grid (second consensus)
    # ==================================================================
    def _build_confirmed_grid(self) -> CountedGrid:
        """
        Second majority vote across decision buffer.
        A change must persist across ≥ ceil(D/2) stable grids.
        Count is the median across matching entries.
        """
        if not self.decision_buffer:
            return []
        if len(self.decision_buffer) < self.decision_threshold:
            return copy.deepcopy(self.decision_buffer[-1])

        rows = len(self.decision_buffer[0])
        cols = len(self.decision_buffer[0][0]) if rows else 0
        confirmed: CountedGrid = [[("empty", 0)] * cols for _ in range(rows)]
        threshold = self.decision_threshold

        for r in range(rows):
            for c in range(cols):
                labels = [buf[r][c][0] for buf in self.decision_buffer]
                counts = [buf[r][c][1] for buf in self.decision_buffer]

                label_counter = Counter(labels)
                best_label, best_count = label_counter.most_common(1)[0]

                if best_count < threshold or best_label == "empty":
                    confirmed[r][c] = ("empty", 0)
                    continue

                matching = [counts[i] for i in range(len(labels))
                           if labels[i] == best_label and counts[i] > 0]
                final_count = int(median(matching)) if matching else 1
                confirmed[r][c] = (best_label, max(1, final_count))

        return confirmed

    # ==================================================================
    # Occlusion detection
    # ==================================================================
    def _is_likely_occluded(self, grid: CountedGrid) -> bool:
        if len(self.frame_buffer) < 3:
            return False
        current_occ = _total_items(grid)
        lookback = self.frame_buffer[-3:]
        avg_occ = sum(_total_items(b) for b in lookback) / len(lookback)
        if avg_occ == 0:
            return False
        return (current_occ / avg_occ) < self.occlusion_drop_threshold

    # ==================================================================
    # Visibility validation
    # ==================================================================
    def _validate_visibility(self, grid: CountedGrid) -> bool:
        if not self.current_snapshot:
            return True
        expected = self.current_snapshot.total_occupied()
        if expected == 0:
            return True
        current = _total_items(grid)
        return (current / expected) >= _VISIBILITY_THRESHOLD

    # ==================================================================
    # Cooldown
    # ==================================================================
    def _get_cooldown(self) -> float:
        return _COOLDOWN_DEMO if self.system_mode == "demo" else _COOLDOWN_PRODUCTION

    def _is_on_cooldown(self, r: int, c: int) -> bool:
        key = (r, c)
        if key not in self._cell_cooldown:
            return False
        if time.time() - self._cell_cooldown[key] >= self._get_cooldown():
            del self._cell_cooldown[key]
            return False
        return True

    def _set_cooldown(self, r: int, c: int):
        self._cell_cooldown[(r, c)] = time.time()

    # ==================================================================
    # Count-based sales detection (core algorithm)
    # ==================================================================
    def _compare_snapshots(self):
        """
        Count-based, displacement-aware, cooldown-filtered sales detection.

        For each cell:
          old = ("book", 3), new = ("book", 1) → 2 sold
          old = ("book", 3), new = ("empty", 0) → 3 sold (if passes filters)
          old = ("empty", 0), new = ("book", 2) → 2 restocked

        Filters: count-cap gate, displacement check, cooldown, min threshold.
        """
        old_grid = self.previous_snapshot.grid_map
        new_grid = self.current_snapshot.grid_map

        rows = min(len(old_grid), len(new_grid))
        cols = min(
            len(old_grid[0]) if old_grid else 0,
            len(new_grid[0]) if new_grid else 0,
        )
        if rows == 0 or cols == 0:
            return

        old_counts = _count_grid_items(old_grid)
        new_counts = _count_grid_items(new_grid)

        # Minimum change threshold
        old_total = sum(old_counts.values())
        new_total = sum(new_counts.values())
        if abs(old_total - new_total) < _MIN_STOCK_CHANGE:
            self.latest_sales = {}
            self.latest_restocks = {}
            return

        all_items = set(old_counts) | set(new_counts)
        sales: Dict[str, int] = {}
        restocks: Dict[str, int] = {}

        for item in all_items:
            old_n = old_counts.get(item, 0)
            new_n = new_counts.get(item, 0)

            # ── Sales: global count decreased ──
            sale_cap = old_n - new_n
            if sale_cap > 0:
                confirmed = 0
                for r in range(rows):
                    if confirmed >= sale_cap:
                        break
                    for c in range(cols):
                        if confirmed >= sale_cap:
                            break
                        old_label, old_cnt = old_grid[r][c]
                        new_label, new_cnt = new_grid[r][c]

                        if old_label != item:
                            continue

                        # Case 1: item completely gone from cell
                        if new_label != item:
                            if self._is_on_cooldown(r, c):
                                continue
                            # Displacement: check adjacent cells
                            adj = _get_adjacent(r, c, rows, cols)
                            if any(new_grid[nr][nc][0] == item for nr, nc in adj):
                                continue  # Moved, not sold
                            confirmed += old_cnt
                            self._set_cooldown(r, c)

                        # Case 2: count decreased in same cell
                        elif new_cnt < old_cnt:
                            if self._is_on_cooldown(r, c):
                                continue
                            confirmed += (old_cnt - new_cnt)
                            self._set_cooldown(r, c)

                # Cap to actual global decrease
                if confirmed > 0:
                    sales[item] = min(confirmed, sale_cap)
                elif sale_cap > 0:
                    # Fallback if displacement filtered everything
                    sales[item] = sale_cap

            # ── Restocks: global count increased ──
            restock_cap = new_n - old_n
            if restock_cap > 0:
                confirmed = 0
                for r in range(rows):
                    if confirmed >= restock_cap:
                        break
                    for c in range(cols):
                        if confirmed >= restock_cap:
                            break
                        old_label, old_cnt = old_grid[r][c]
                        new_label, new_cnt = new_grid[r][c]

                        if new_label != item:
                            continue
                        if old_label != item:
                            confirmed += new_cnt
                        elif new_cnt > old_cnt:
                            confirmed += (new_cnt - old_cnt)

                if confirmed > 0:
                    restocks[item] = min(confirmed, restock_cap)

        self.latest_sales = sales
        self.latest_restocks = restocks
        for item, qty in sales.items():
            self.total_sales[item] += qty
        for item, qty in restocks.items():
            self.total_restocks[item] += qty

    # ==================================================================
    # Sales rate
    # ==================================================================
    def get_sales_rate(self) -> Dict[str, float]:
        if len(self.snapshot_history) < 2:
            return {}
        recent = self.snapshot_history[-3:]
        span = (recent[-1].timestamp - recent[0].timestamp).total_seconds()
        hrs = max(span / 3600, 0.001)
        sales: Dict[str, int] = defaultdict(int)
        for i in range(1, len(recent)):
            s, _ = detect_sales(recent[i-1].grid_map, recent[i].grid_map)
            for item, qty in s.items():
                sales[item] += qty
        return {item: cnt / hrs for item, cnt in sales.items()}

    # ==================================================================
    # Heatmap
    # ==================================================================
    def compute_emptiness_heatmap(self) -> List[List[float]]:
        if not self.snapshot_history:
            return []
        rows = len(self.snapshot_history[0].grid_map)
        cols = len(self.snapshot_history[0].grid_map[0]) if rows else 0
        empty_acc = [[0] * cols for _ in range(rows)]
        for snap in self.snapshot_history:
            for r in range(min(rows, len(snap.grid_map))):
                for c in range(min(cols, len(snap.grid_map[0]))):
                    if snap.grid_map[r][c][0] == "empty":
                        empty_acc[r][c] += 1
        total = len(self.snapshot_history)
        return [[empty_acc[r][c] / total for c in range(cols)] for r in range(rows)]

    # ==================================================================
    # Public getters (return string grids for backward compat)
    # ==================================================================
    def get_stock_history(self) -> List[Tuple[datetime, Dict[str, int]]]:
        return list(self.stock_history)

    def get_current_stock(self) -> Dict[str, int]:
        if self.current_snapshot:
            return self.current_snapshot.item_counts.copy()
        return {}

    def get_current_grid(self) -> Optional[List[List[str]]]:
        """Return string grid for backward compat (UI/storage)."""
        if self.current_snapshot:
            return _counted_to_string(self.current_snapshot.grid_map)
        return None

    def get_live_grid(self) -> Optional[List[List[str]]]:
        """Most recent buffer frame as string grid."""
        if self.frame_buffer:
            return _counted_to_string(self.frame_buffer[-1])
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
            "decision_fill":    len(self.decision_buffer),
            "tracking_since":   self.tracking_start,
        }

    def reset(self):
        self.frame_buffer.clear()
        self.decision_buffer.clear()
        self._cell_cooldown.clear()
        self.previous_snapshot  = None
        self.current_snapshot   = None
        self.snapshot_history.clear()
        self.latest_sales.clear()
        self.latest_restocks.clear()
        self.total_sales.clear()
        self.total_restocks.clear()
        self.last_snapshot_time = None
        self.tracking_start    = None
        self.frames_processed  = 0
        self.frames_skipped_occlusion = 0
        self.stock_history.clear()
        self._prev_stock_total = 0


# ======================================================================
# Standalone functions (for unit tests / sales rate)
# ======================================================================

def detect_sales(
    old_grid: CountedGrid,
    new_grid: CountedGrid,
) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Count-based, displacement-aware sales detection (standalone)."""
    if not old_grid or not new_grid:
        return {}, {}
    rows = min(len(old_grid), len(new_grid))
    cols = min(len(old_grid[0]) if old_grid else 0, len(new_grid[0]) if new_grid else 0)
    if rows == 0 or cols == 0:
        return {}, {}

    old_counts = _count_grid_items(old_grid)
    new_counts = _count_grid_items(new_grid)
    all_items = set(old_counts) | set(new_counts)
    sales: Dict[str, int] = {}
    restocks: Dict[str, int] = {}

    for item in all_items:
        old_n = old_counts.get(item, 0)
        new_n = new_counts.get(item, 0)
        if old_n > new_n:
            sales[item] = old_n - new_n
        elif new_n > old_n:
            restocks[item] = new_n - old_n

    return sales, restocks


def detect_movement(old_grid: CountedGrid, new_grid: CountedGrid) -> Dict[str, str]:
    """Classify per-item changes as SOLD, RESTOCKED, MOVED, or UNCHANGED."""
    if not old_grid or not new_grid:
        return {}
    old_counts = _count_grid_items(old_grid)
    new_counts = _count_grid_items(new_grid)
    all_items = set(old_counts) | set(new_counts)
    result: Dict[str, str] = {}
    for item in all_items:
        old_n = old_counts.get(item, 0)
        new_n = new_counts.get(item, 0)
        if new_n < old_n:
            result[item] = "SOLD"
        elif new_n > old_n:
            result[item] = "RESTOCKED"
        else:
            # Check if positions changed
            old_pos = {(r, c) for r, row in enumerate(old_grid) for c, (l, _) in enumerate(row) if l == item}
            new_pos = {(r, c) for r, row in enumerate(new_grid) for c, (l, _) in enumerate(row) if l == item}
            result[item] = "MOVED" if old_pos != new_pos else "UNCHANGED"
    return result
