"""
Grid-based shelf mapping module.
=================================
Divides a user-defined shelf region into an R×C grid and maps
YOLO detections to individual cells.  Cells without a detection
are labelled "empty" — this is the foundation for position-based
sales detection.
"""

import cv2
import numpy as np
from typing import Dict, List, Optional, Tuple


# ======================================================================
# Shelf region
# ======================================================================

class ShelfRegion:
    """Bounding box of the shelf area inside the camera frame."""

    def __init__(self, x_min: int, y_min: int, x_max: int, y_max: int):
        self.x_min = max(0, x_min)
        self.y_min = max(0, y_min)
        self.x_max = max(self.x_min + 1, x_max)
        self.y_max = max(self.y_min + 1, y_max)

    @property
    def width(self) -> int:
        return self.x_max - self.x_min

    @property
    def height(self) -> int:
        return self.y_max - self.y_min

    def contains(self, x: float, y: float) -> bool:
        """True if *(x, y)* is within the shelf rectangle."""
        return self.x_min <= x <= self.x_max and self.y_min <= y <= self.y_max

    def as_tuple(self) -> Tuple[int, int, int, int]:
        return (self.x_min, self.y_min, self.x_max, self.y_max)


# ======================================================================
# Grid mapper
# ======================================================================

class GridMapper:
    """
    Maps product detections onto an R×C grid overlaying the shelf.

    Workflow
    --------
    1.  Receive a list of detections (each with bbox + class).
    2.  Filter to only those whose **centre** falls inside the shelf.
    3.  For each surviving detection compute the grid cell via:
            col = int((cx - shelf.x_min) / cell_width)
            row = int((cy - shelf.y_min) / cell_height)
    4.  If a cell has several detections, keep the one with highest
        confidence.
    5.  Return a 2-D list  ``grid[row][col]`` — class label or ``"empty"``.
    """

    def __init__(self, shelf: ShelfRegion, rows: int = 3, cols: int = 5):
        self.shelf = shelf
        self.rows = rows
        self.cols = cols
        self._recalc()

    def _recalc(self):
        """Recompute cell dimensions (call after changing shelf/grid)."""
        self.cell_width = self.shelf.width / max(self.cols, 1)
        self.cell_height = self.shelf.height / max(self.rows, 1)

    def update_shelf(self, shelf: ShelfRegion):
        self.shelf = shelf
        self._recalc()

    def update_grid_size(self, rows: int, cols: int):
        self.rows = rows
        self.cols = cols
        self._recalc()

    # ------------------------------------------------------------------
    # Core mapping (legacy — returns string grid)
    # ------------------------------------------------------------------
    def map_detections(self, detections: List[dict]) -> List[List[str]]:
        """
        Map *detections* to grid cells. Returns string grid for backward compat.
        """
        counted = self.map_detections_counted(detections)
        return [
            [cell[0] for cell in row]
            for row in counted
        ]

    # ------------------------------------------------------------------
    # Count-aware mapping (NEW — returns (label, count) per cell)
    # ------------------------------------------------------------------
    def map_detections_counted(
        self, detections: List[dict]
    ) -> List[List[Tuple[str, int]]]:
        """
        Map detections to grid cells, counting ALL detections per cell.

        Returns 2-D list of (label, count) tuples.
        - ("empty", 0) for cells with no detections
        - ("book", 3) for cells with 3 book detections
        If a cell has mixed labels, the most frequent label wins.
        """
        grid: List[List[Tuple[str, int]]] = [
            [("empty", 0)] * self.cols for _ in range(self.rows)
        ]
        # Accumulate ALL detections per cell
        candidates: List[List[List[dict]]] = [
            [[] for _ in range(self.cols)] for _ in range(self.rows)
        ]

        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2

            if not self.shelf.contains(cx, cy):
                continue

            col = int((cx - self.shelf.x_min) / self.cell_width)
            row = int((cy - self.shelf.y_min) / self.cell_height)
            col = max(0, min(col, self.cols - 1))
            row = max(0, min(row, self.rows - 1))

            candidates[row][col].append(det)

        for r in range(self.rows):
            for c in range(self.cols):
                dets = candidates[r][c]
                if not dets:
                    continue
                # Group by label, pick most frequent
                from collections import Counter
                label_counts = Counter(d["class"] for d in dets)
                best_label = label_counts.most_common(1)[0][0]
                count = label_counts[best_label]
                grid[r][c] = (best_label, count)

        return grid

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def filter_shelf_detections(self, detections: List[dict]) -> List[dict]:
        """Keep only detections whose centre falls within the shelf."""
        out = []
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            if self.shelf.contains(cx, cy):
                out.append(det)
        return out

    def count_items(self, grid: List[List[str]]) -> Dict[str, int]:
        """Count items per class in a string grid map."""
        counts: Dict[str, int] = {}
        for row in grid:
            for cell in row:
                if cell != "empty":
                    counts[cell] = counts.get(cell, 0) + 1
        return counts

    def count_empty(self, grid: List[List[str]]) -> int:
        return sum(1 for row in grid for c in row if c == "empty")

    def count_occupied(self, grid: List[List[str]]) -> int:
        return sum(1 for row in grid for c in row if c != "empty")

    # ------------------------------------------------------------------
    # Drawing (handles both string and counted grids)
    # ------------------------------------------------------------------
    def draw_grid_overlay(
        self,
        frame: np.ndarray,
        grid: Optional[List] = None,
    ) -> np.ndarray:
        """
        Draw the shelf region + grid lines + cell status on *frame*.
        Accepts both string grids and counted grids.
        """
        overlay = frame.copy()
        s = self.shelf

        cv2.rectangle(overlay, (s.x_min, s.y_min), (s.x_max, s.y_max),
                       (255, 255, 0), 2)

        for i in range(1, self.rows):
            y = s.y_min + int(i * self.cell_height)
            cv2.line(overlay, (s.x_min, y), (s.x_max, y), (180, 180, 180), 1)
        for j in range(1, self.cols):
            x = s.x_min + int(j * self.cell_width)
            cv2.line(overlay, (x, s.y_min), (x, s.y_max), (180, 180, 180), 1)

        if grid:
            for r in range(min(self.rows, len(grid))):
                for c in range(min(self.cols, len(grid[0]))):
                    x1 = s.x_min + int(c * self.cell_width)
                    y1_c = s.y_min + int(r * self.cell_height)
                    x2 = s.x_min + int((c + 1) * self.cell_width)
                    y2_c = s.y_min + int((r + 1) * self.cell_height)

                    fh, fw = frame.shape[:2]
                    x1, x2 = max(0, x1), min(fw, x2)
                    y1_c, y2_c = max(0, y1_c), min(fh, y2_c)
                    if x2 <= x1 or y2_c <= y1_c:
                        continue

                    # Handle both string grid and counted grid
                    cell = grid[r][c]
                    if isinstance(cell, tuple):
                        lbl, cnt = cell
                    else:
                        lbl, cnt = cell, (1 if cell != "empty" else 0)

                    sub = overlay[y1_c:y2_c, x1:x2]
                    if lbl == "empty":
                        tint = np.full_like(sub, (0, 0, 180))
                        cv2.addWeighted(sub, 0.75, tint, 0.25, 0, sub)
                    else:
                        tint = np.full_like(sub, (0, 160, 0))
                        cv2.addWeighted(sub, 0.75, tint, 0.25, 0, sub)
                        display = f"{lbl[:8]}x{cnt}" if cnt > 1 else lbl[:10]
                        cv2.putText(overlay, display, (x1 + 2, y1_c + 14),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.35,
                                    (255, 255, 255), 1, cv2.LINE_AA)

        cv2.putText(overlay, "SHELF", (s.x_min + 4, s.y_min - 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1, cv2.LINE_AA)
        return overlay
