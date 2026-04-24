"""
tracker.py — Core Inventory Tracking Engine
=============================================
Position-aware, buffer-based inventory tracking using grid snapshots,
majority voting, and displacement-aware sales detection.

Architecture:  Frame → Buffer → Consensus Grid → Compare → Sales/Restocks

Key Design Principles:
  - Track by POSITION (grid cells), NOT by object identity
  - Multiple identical items handled naturally via cell positions
  - Frame buffer (N=5) + majority voting eliminates flicker/noise
  - Displacement check prevents false sales from rearrangements
  - Count-cap ensures sales never exceed actual count decrease
"""

import copy
import math
from collections import Counter, defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple


# ======================================================================
# Constants
# ======================================================================
CONFIDENCE_THRESHOLD = 0.5
DEFAULT_BUFFER_SIZE = 7
DISPLACEMENT_RADIUS = 1


# ======================================================================
# Snapshot data object
# ======================================================================

class Snapshot:
    """One point-in-time capture of the shelf grid."""

    def __init__(self, grid_map: List[List[str]], timestamp: datetime = None):
        self.grid_map = copy.deepcopy(grid_map)
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
# Core standalone functions
# ======================================================================

def _get_adjacent_cells(
    r: int, c: int, rows: int, cols: int, radius: int = 1
) -> List[Tuple[int, int]]:
    """Return all valid cell coordinates within radius of (r, c)."""
    neighbors = []
    for dr in range(-radius, radius + 1):
        for dc in range(-radius, radius + 1):
            if dr == 0 and dc == 0:
                continue
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols:
                neighbors.append((nr, nc))
    return neighbors


def _is_true_displacement(
    old_map: List[List[str]], new_map: List[List[str]],
    r: int, c: int, item: str,
    rows: int, cols: int, radius: int = 1,
) -> bool:
    """
    Check if item at (r,c) was displaced rather than sold.
    True displacement = item appeared in an adjacent cell that was
    previously empty (item moved there, not pre-existing).
    """
    for nr, nc in _get_adjacent_cells(r, c, rows, cols, radius):
        if new_map[nr][nc] == item and old_map[nr][nc] != item:
            return True
    return False


def build_consensus(buffer: List[List[List[str]]]) -> List[List[str]]:
    """
    Build stable grid from buffer using majority voting.

    For each cell, collect labels across all buffer frames.
    The most common label wins if it appears >= ceil(N/2) times.
    If no label reaches majority, fall back to most-common non-empty
    label if it appears >= ceil(N/3) times (mild stickiness).
    Otherwise the cell is "empty".
    """
    if not buffer:
        return []

    rows = len(buffer[0])
    cols = len(buffer[0][0]) if rows else 0
    grid: List[List[str]] = [["empty"] * cols for _ in range(rows)]
    majority = math.ceil(len(buffer) / 2)
    sticky_min = math.ceil(len(buffer) / 3)  # mild stickiness threshold

    for r in range(rows):
        for c in range(cols):
            labels = [b[r][c] for b in buffer]
            counts = Counter(labels)
            most_common, count = counts.most_common(1)[0]

            if count >= majority:
                # Clear majority — use it (even if "empty")
                grid[r][c] = most_common
            else:
                # No majority — prefer non-empty if it has decent support
                non_empty = {k: v for k, v in counts.items() if k != "empty"}
                if non_empty:
                    best_item, best_count = max(non_empty.items(), key=lambda x: x[1])
                    if best_count >= sticky_min:
                        grid[r][c] = best_item
                # else stays "empty"

    return grid


def count_stock(grid: List[List[str]]) -> Dict[str, int]:
    """Count every non-empty cell label in a grid."""
    counts: Dict[str, int] = {}
    for row in grid:
        for cell in row:
            if cell != "empty":
                counts[cell] = counts.get(cell, 0) + 1
    return counts


def detect_sales_detailed(
    old_map: List[List[str]], new_map: List[List[str]],
    displacement_radius: int = DISPLACEMENT_RADIUS,
) -> Tuple[Dict[str, int], Dict[str, List[Tuple[int, int]]], Dict[str, int]]:
    """
    Displacement-aware, count-capped diff between two grid snapshots.

    Returns (sales, sale_cells, restocks):
      sales      : {item: qty_sold}
      sale_cells : {item: [(r,c), ...]}
      restocks   : {item: qty_added}

    Algorithm per item X:
      sale_cap = old_count(X) - new_count(X)
      If cap <= 0: all changes are rearrangements, skip.
      If cap > 0: scan cells old=X, new=empty:
        - If displaced to adjacent cell → skip (movement)
        - Otherwise → confirmed sale (up to cap)
    """
    if not old_map or not new_map:
        return {}, {}, {}

    rows = min(len(old_map), len(new_map))
    cols = min(
        len(old_map[0]) if old_map else 0,
        len(new_map[0]) if new_map else 0,
    )
    if rows == 0 or cols == 0:
        return {}, {}, {}

    old_counts = count_stock(old_map)
    new_counts = count_stock(new_map)
    all_items = set(old_counts) | set(new_counts)

    sales: Dict[str, int] = {}
    sale_cells: Dict[str, List[Tuple[int, int]]] = {}
    restocks: Dict[str, int] = {}

    for item in all_items:
        old_n = old_counts.get(item, 0)
        new_n = new_counts.get(item, 0)

        # Sales: item count decreased
        sale_cap = old_n - new_n
        if sale_cap > 0:
            confirmed = 0
            cells: List[Tuple[int, int]] = []
            for r in range(rows):
                if confirmed >= sale_cap:
                    break
                for c in range(cols):
                    if confirmed >= sale_cap:
                        break
                    if old_map[r][c] == item and new_map[r][c] == "empty":
                        if not _is_true_displacement(
                            old_map, new_map, r, c, item,
                            rows, cols, displacement_radius,
                        ):
                            confirmed += 1
                            cells.append((r, c))
            if confirmed > 0:
                sales[item] = min(confirmed, sale_cap)
                sale_cells[item] = cells[:sale_cap]

        # Restocks: item count increased
        restock_cap = new_n - old_n
        if restock_cap > 0:
            confirmed = 0
            for r in range(rows):
                if confirmed >= restock_cap:
                    break
                for c in range(cols):
                    if confirmed >= restock_cap:
                        break
                    if old_map[r][c] == "empty" and new_map[r][c] == item:
                        confirmed += 1
            if confirmed > 0:
                restocks[item] = confirmed

    return sales, sale_cells, restocks


def detect_sales(
    old_map: List[List[str]], new_map: List[List[str]],
    displacement_radius: int = DISPLACEMENT_RADIUS,
) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Wrapper returning only (sales, restocks) counts."""
    sales, _, restocks = detect_sales_detailed(old_map, new_map, displacement_radius)
    return sales, restocks


def detect_movement(
    old_map: List[List[str]], new_map: List[List[str]],
) -> Dict[str, str]:
    """Classify per-item changes as MOVED, SOLD, RESTOCKED, or UNCHANGED."""
    if not old_map or not new_map:
        return {}

    old_counts = count_stock(old_map)
    new_counts = count_stock(new_map)
    all_items = set(old_counts) | set(new_counts)

    def _positions(grid, item):
        return {(r, c) for r, row in enumerate(grid) for c, cell in enumerate(row) if cell == item}

    result: Dict[str, str] = {}
    for item in all_items:
        old_n = old_counts.get(item, 0)
        new_n = new_counts.get(item, 0)
        if new_n < old_n:
            result[item] = "SOLD"
        elif new_n > old_n:
            result[item] = "RESTOCKED"
        else:
            result[item] = "MOVED" if _positions(old_map, item) != _positions(new_map, item) else "UNCHANGED"
    return result


# ======================================================================
# SnapshotTracker — Main tracking engine
# ======================================================================

class SnapshotTracker:
    """
    Two-layer consensus tracker with displacement-aware sales detection.

    Layer 1: Frame buffer (N=5) → majority voting → stable grid
    Layer 2: Decision buffer (N=3) → majority voting → confirmed grid

    Post-processing: cooldowns, visibility checks, change thresholds.
    """

    HIGH_SALES_THRESHOLD = 5.0
    LOW_SALES_THRESHOLD = 1.0
    STOCK_CHANGE_TRIGGER = 3

    MODE_BOUNDS = {
        "demo": {"min": 10, "max": 30},
        "production": {"min": 300, "max": 1800},
    }

    def __init__(
        self,
        snapshot_interval_seconds: float = 600.0,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
        occlusion_drop_threshold: float = 0.50,
        system_mode: str = "demo",
        decision_buffer_size: int = 5,
        cooldown_period: float = 15.0,
        visibility_threshold: float = 0.60,
        min_change_threshold: int = 1,
    ):
        self.base_interval = snapshot_interval_seconds
        self.snapshot_interval = snapshot_interval_seconds
        self.buffer_size = buffer_size
        self.occlusion_drop_threshold = occlusion_drop_threshold
        self.system_mode = system_mode

        # Stability layers
        self.decision_buffer_size = decision_buffer_size
        self.frame_buffer: List[List[List[str]]] = []
        self.decision_buffer: List[List[List[str]]] = []

        # Cached consensus grids
        self._cached_stable_grid: Optional[List[List[str]]] = None
        self._cached_confirmed_grid: Optional[List[List[str]]] = None

        # Post-processing filters
        self.cooldown_period = cooldown_period
        self.visibility_threshold = visibility_threshold
        self.min_change_threshold = min_change_threshold
        self.cell_cooldowns: Dict[Tuple[int, int], float] = {}

        # Snapshot chain
        self.previous_snapshot: Optional[Snapshot] = None
        self.current_snapshot: Optional[Snapshot] = None
        self.snapshot_history: List[Snapshot] = []

        # Per-interval sales/restocks
        self.latest_sales: Dict[str, int] = {}
        self.latest_restocks: Dict[str, int] = {}

        # Cumulative tallies
        self.total_sales: Dict[str, int] = defaultdict(int)
        self.total_restocks: Dict[str, int] = defaultdict(int)

        # Timing
        self.last_snapshot_time: Optional[datetime] = None
        self.tracking_start: Optional[datetime] = None

        # Stats
        self.frames_processed: int = 0
        self.frames_skipped_occlusion: int = 0

        # Stock history for trend charts
        self.stock_history: List[Tuple[datetime, Dict[str, int]]] = []
        self._prev_stock_total: int = 0

    # ==================================================================
    # Layer 1: Frame Buffer
    # ==================================================================

    def update_frame_buffer(self, grid: List[List[str]]) -> bool:
        """Add raw grid to frame buffer. Returns False if occluded."""
        self.frames_processed += 1
        if self.tracking_start is None:
            self.tracking_start = datetime.now()

        if self._is_likely_occluded(grid):
            self.frames_skipped_occlusion += 1
            return False

        self.frame_buffer.append(copy.deepcopy(grid))
        if len(self.frame_buffer) > self.buffer_size:
            self.frame_buffer.pop(0)
        return True

    def build_stable_grid(self) -> List[List[str]]:
        """Layer 1: Majority voting across frame buffer."""
        return build_consensus(self.frame_buffer)

    # ==================================================================
    # Layer 2: Decision Buffer
    # ==================================================================

    def update_decision_buffer(self, stable_grid: List[List[str]]):
        """Add stable grid to decision buffer."""
        self.decision_buffer.append(copy.deepcopy(stable_grid))
        if len(self.decision_buffer) > self.decision_buffer_size:
            self.decision_buffer.pop(0)

    def build_confirmed_grid(self) -> List[List[str]]:
        """Layer 2: Consensus across decision buffer."""
        return build_consensus(self.decision_buffer)

    # ==================================================================
    # Pipeline Ingestion
    # ==================================================================

    def add_frame(self, grid_map: List[List[str]]) -> bool:
        """Ingest frame, build stable grid, update decision buffer."""
        accepted = self.update_frame_buffer(grid_map)
        if accepted:
            stable = self.build_stable_grid()
            self._cached_stable_grid = copy.deepcopy(stable)
            self.update_decision_buffer(stable)
            self._cached_confirmed_grid = copy.deepcopy(self.build_confirmed_grid())
        return accepted

    # ==================================================================
    # Snapshot lifecycle
    # ==================================================================

    def should_take_snapshot(self) -> bool:
        """True when buffers are full AND interval has elapsed."""
        if len(self.frame_buffer) < self.buffer_size:
            return False
        if len(self.decision_buffer) < self.decision_buffer_size:
            return False
        if self.last_snapshot_time is None:
            return True

        elapsed = (datetime.now() - self.last_snapshot_time).total_seconds()
        if elapsed >= self.snapshot_interval:
            return True

        # Stock-change trigger
        if self.decision_buffer:
            current_total = sum(1 for row in self.decision_buffer[-1] for c in row if c != "empty")
            if abs(current_total - self._prev_stock_total) > self.STOCK_CHANGE_TRIGGER:
                return True
        return False

    def take_snapshot(self) -> Optional[Snapshot]:
        """Build confirmed grid, detect sales, persist."""
        if not self.decision_buffer:
            return None

        confirmed_grid = self.build_confirmed_grid()
        if not confirmed_grid:
            return None

        new_counts = count_stock(confirmed_grid)
        new_total = sum(new_counts.values())

        self.previous_snapshot = self.current_snapshot
        self.current_snapshot = Snapshot(confirmed_grid)
        self.last_snapshot_time = datetime.now()

        # Compare with previous snapshot if one exists
        if self.previous_snapshot is not None:
            old_total = self.previous_snapshot.total_occupied()
            if abs(new_total - old_total) >= self.min_change_threshold:
                self._compare_snapshots()
            else:
                self.latest_sales = {}
                self.latest_restocks = {}
        else:
            self.latest_sales = {}
            self.latest_restocks = {}

        self._prev_stock_total = self.current_snapshot.total_occupied()
        self.snapshot_history.append(self.current_snapshot)
        if len(self.snapshot_history) > 100:
            self.snapshot_history = self.snapshot_history[-50:]

        self.stock_history.append(
            (self.current_snapshot.timestamp, self.current_snapshot.item_counts.copy())
        )
        return self.current_snapshot

    def _compare_snapshots(self):
        """Displacement-filtered + cooldown-filtered comparison."""
        old = self.previous_snapshot.grid_map
        new = self.current_snapshot.grid_map

        sales_raw, sale_cells, restocks_raw = detect_sales_detailed(old, new)

        # Filter via cooldowns
        sales_filtered: Dict[str, int] = {}
        for item, cells in sale_cells.items():
            confirmed = sum(1 for r, c in cells if not self._is_on_cooldown(r, c))
            if confirmed > 0:
                sales_filtered[item] = min(confirmed, sales_raw.get(item, confirmed))

        # Set cooldowns for confirmed sale cells
        for item, cells in sale_cells.items():
            if item in sales_filtered:
                for r, c in cells:
                    if not self._is_on_cooldown(r, c):
                        self._set_cooldown(r, c)

        self.latest_sales = sales_filtered
        self.latest_restocks = restocks_raw

        for item, qty in sales_filtered.items():
            self.total_sales[item] += qty
        for item, qty in restocks_raw.items():
            self.total_restocks[item] += qty

    # ==================================================================
    # Post-processing helpers
    # ==================================================================

    def _validate_visibility(self, grid: List[List[str]]) -> bool:
        if not grid:
            return False
        detected = sum(count_stock(grid).values())
        expected = self._prev_stock_total or 1
        return (detected / expected) >= self.visibility_threshold

    def _is_on_cooldown(self, r: int, c: int) -> bool:
        now = datetime.now().timestamp()
        return (now - self.cell_cooldowns.get((r, c), 0)) < self.cooldown_period

    def _set_cooldown(self, r: int, c: int):
        self.cell_cooldowns[(r, c)] = datetime.now().timestamp()

    def _is_likely_occluded(self, grid: List[List[str]]) -> bool:
        if len(self.frame_buffer) < 3:
            return False
        current_occ = sum(1 for row in grid for c in row if c != "empty")
        lookback = self.frame_buffer[-3:]
        avg_occ = sum(sum(1 for row in b for c in row if c != "empty") for b in lookback) / len(lookback)
        if avg_occ == 0:
            return False
        return (current_occ / avg_occ) < self.occlusion_drop_threshold

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
            new_interval = self.base_interval * 0.5
        elif total_rate < self.LOW_SALES_THRESHOLD:
            new_interval = self.base_interval * 1.5
        else:
            new_interval = self.base_interval
        self.snapshot_interval = max(bounds["min"], min(bounds["max"], new_interval))

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
    # Sales rate
    # ==================================================================

    def get_sales_rate(self) -> Dict[str, float]:
        if len(self.snapshot_history) < 2:
            return {}
        recent = self.snapshot_history[-3:]
        span_secs = (recent[-1].timestamp - recent[0].timestamp).total_seconds()
        span_hrs = max(span_secs / 3600, 0.001)
        sales: Dict[str, int] = defaultdict(int)
        for i in range(1, len(recent)):
            s, _ = detect_sales(recent[i - 1].grid_map, recent[i].grid_map)
            for item, qty in s.items():
                sales[item] += qty
        return {item: cnt / span_hrs for item, cnt in sales.items()}

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
                    if snap.grid_map[r][c] == "empty":
                        empty_acc[r][c] += 1
        total = len(self.snapshot_history)
        return [[empty_acc[r][c] / total for c in range(cols)] for r in range(rows)]

    # ==================================================================
    # Public getters (API contract with camera_manager.py)
    # ==================================================================

    def get_current_stock(self) -> Dict[str, int]:
        return self.current_snapshot.item_counts.copy() if self.current_snapshot else {}

    def get_current_grid(self) -> Optional[List[List[str]]]:
        return copy.deepcopy(self.current_snapshot.grid_map) if self.current_snapshot else None

    def get_live_grid(self) -> Optional[List[List[str]]]:
        return copy.deepcopy(self.frame_buffer[-1]) if self.frame_buffer else None

    def get_stable_grid(self) -> Optional[List[List[str]]]:
        if self._cached_stable_grid is not None:
            return copy.deepcopy(self._cached_stable_grid)
        if len(self.frame_buffer) < 2:
            return self.get_live_grid()
        return self.build_stable_grid()

    def get_confirmed_grid(self) -> Optional[List[List[str]]]:
        if self._cached_confirmed_grid is not None:
            return copy.deepcopy(self._cached_confirmed_grid)
        if not self.decision_buffer:
            return self.get_stable_grid()
        return self.build_confirmed_grid()

    def get_latest_sales(self) -> Dict[str, int]:
        return self.latest_sales.copy()

    def get_latest_restocks(self) -> Dict[str, int]:
        return self.latest_restocks.copy()

    def get_total_sales(self) -> Dict[str, int]:
        return dict(self.total_sales)

    def get_total_restocks(self) -> Dict[str, int]:
        return dict(self.total_restocks)

    def get_stock_history(self) -> List[Tuple[datetime, Dict[str, int]]]:
        return list(self.stock_history)

    def get_stats(self) -> dict:
        return {
            "frames_processed": self.frames_processed,
            "frames_skipped": self.frames_skipped_occlusion,
            "snapshots_taken": len(self.snapshot_history),
            "buffer_fill": len(self.frame_buffer),
            "tracking_since": self.tracking_start,
        }

    def reset(self):
        self.frame_buffer.clear()
        self.decision_buffer.clear()
        self._cached_stable_grid = None
        self._cached_confirmed_grid = None
        self.cell_cooldowns.clear()
        self.previous_snapshot = None
        self.current_snapshot = None
        self.snapshot_history.clear()
        self.latest_sales.clear()
        self.latest_restocks.clear()
        self.total_sales.clear()
        self.total_restocks.clear()
        self.last_snapshot_time = None
        self.tracking_start = None
        self.frames_processed = 0
        self.frames_skipped_occlusion = 0
        self.stock_history.clear()
        self._prev_stock_total = 0
