"""
Utility functions for the Retail Inventory Management System.
=============================================================
Drawing helpers, time formatting, smoothing, and HTML renderers
for the Streamlit grid display and heatmap.
"""

import cv2
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple


# ======================================================================
# Time helpers
# ======================================================================

def format_timestamp(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts).strftime("%H:%M:%S  %d-%b-%Y")
    except (ValueError, TypeError):
        return str(ts)


def calculate_time_to_empty(stock: int, rate: float) -> Optional[float]:
    """Hours until depleted. None if rate <= 0."""
    if rate <= 0:
        return None
    return stock / rate


def format_time_remaining(hours: Optional[float]) -> str:
    if hours is None:
        return "N/A"
    if hours < 1:
        return f"{int(hours * 60)} min"
    if hours < 24:
        return f"{hours:.1f} hrs"
    return f"{hours / 24:.1f} days"


# ======================================================================
# Drawing helpers
# ======================================================================

def get_color_for_class(class_name: str) -> Tuple[int, int, int]:
    """Consistent BGR colour for a class (hue derived from hash)."""
    hue = hash(class_name) % 180
    hsv = np.array([[[hue, 200, 230]]], dtype=np.uint8)
    bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
    return tuple(int(c) for c in bgr[0][0])


def draw_boxes(frame: np.ndarray, detections: List[dict]) -> np.ndarray:
    """Draw labelled bounding boxes with confidence scores on *frame*."""
    out = frame.copy()
    for det in detections:
        x1, y1, x2, y2 = [int(c) for c in det["bbox"]]
        cls, conf      = det["class"], det["confidence"]
        color          = get_color_for_class(cls)

        # Bounding box
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)

        # Label background + text
        label = f"{cls} {conf:.0%}"
        (tw, th), bl = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(out, (x1, y1 - th - bl - 5), (x1 + tw + 4, y1), color, -1)
        cv2.putText(
            out, label, (x1 + 2, y1 - bl - 2),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA,
        )
    return out


def resize_frame(frame: np.ndarray, max_width: int = 800) -> np.ndarray:
    h, w = frame.shape[:2]
    if w > max_width:
        s = max_width / w
        return cv2.resize(frame, (max_width, int(h * s)))
    return frame


# ======================================================================
# HTML renderers for Streamlit
# ======================================================================

# Colour palette for product labels (CSS)
_PRODUCT_COLOURS = [
    "#3b82f6",  # blue
    "#8b5cf6",  # purple
    "#f59e0b",  # amber
    "#10b981",  # emerald
    "#ef4444",  # red
    "#06b6d4",  # cyan
    "#f97316",  # orange
    "#84cc16",  # lime
    "#ec4899",  # pink
    "#14b8a6",  # teal
]


def _product_color(name: str) -> str:
    """Return a CSS hex colour for a product name."""
    return _PRODUCT_COLOURS[hash(name) % len(_PRODUCT_COLOURS)]


def render_grid_html(grid: List[List[str]]) -> str:
    """
    Render a grid map as a styled HTML table.

    Cell states
    -----------
    * Empty   → dark muted cell with ∅ icon
    * Product → coloured cell with product name + row/col label
    """
    if not grid:
        return "<p style='color:#888'>No grid data yet.</p>"

    rows = len(grid)
    cols = len(grid[0]) if grid else 0

    # Dynamic cell sizing
    cell_h = max(54, min(72, 320 // rows))
    font_s = "0.62rem" if cols > 6 else "0.70rem"

    html = (
        "<table style='"
        "border-collapse:separate;border-spacing:3px;"
        "width:100%;table-layout:fixed;'>"
    )
    for r, row in enumerate(grid):
        html += "<tr>"
        for c, cell in enumerate(row):
            coord = f"<span style='opacity:.45;font-size:0.48rem;display:block;'>R{r}·C{c}</span>"
            if cell == "empty":
                bg  = "#1a1a2e"
                border = "1px solid #2d2d4e"
                icon = "∅"
                content = f"{coord}<span style='font-size:1rem;opacity:.4;'>∅</span>"
                txt_color = "#555"
            else:
                bg  = _product_color(cell)
                border = f"2px solid {_product_color(cell)}"
                # Truncate long names
                label    = cell[:10] if len(cell) > 10 else cell
                content  = f"{coord}<b style='font-size:{font_s};'>{label}</b>"
                txt_color = "#fff"

            html += (
                f"<td style='"
                f"background:{bg};"
                f"color:{txt_color};"
                f"padding:4px 3px;"
                f"border:{border};"
                f"border-radius:6px;"
                f"text-align:center;"
                f"vertical-align:middle;"
                f"height:{cell_h}px;"
                f"font-weight:600;"
                f"transition:background .3s;"
                f"box-shadow:0 1px 4px rgba(0,0,0,.4);'>"
                f"{content}</td>"
            )
        html += "</tr>"
    html += "</table>"

    # Legend
    html += (
        "<div style='margin-top:6px;font-size:0.65rem;color:#888;display:flex;gap:12px;'>"
        "<span><span style='display:inline-block;width:10px;height:10px;"
        "background:#27ae60;border-radius:2px;margin-right:3px;'></span>Occupied</span>"
        "<span><span style='display:inline-block;width:10px;height:10px;"
        "background:#1a1a2e;border:1px solid #2d2d4e;border-radius:2px;margin-right:3px;'></span>Empty</span>"
        "</div>"
    )
    return html


def render_heatmap_html(heatmap: List[List[float]]) -> str:
    """
    Render an emptiness heatmap as an HTML table.
    0.0 = always stocked (cool blue), 1.0 = always empty (hot red).
    """
    if not heatmap:
        return "<p style='color:#888'>Not enough snapshots for a heatmap.</p>"

    rows = len(heatmap)
    cols = len(heatmap[0]) if heatmap else 0
    cell_h = max(50, min(70, 280 // rows))

    html = (
        "<table style='"
        "border-collapse:separate;border-spacing:3px;"
        "width:100%;table-layout:fixed;'>"
    )
    for r, row in enumerate(heatmap):
        html += "<tr>"
        for c, val in enumerate(row):
            # Interpolate blue (cold / stocked) → red (hot / empty)
            red   = int(val * 220)
            green = int((1 - val) * 80)
            blue  = int((1 - val) * 200)
            bg    = f"rgb({red},{green},{blue})"
            pct   = f"{val:.0%}"
            intensity = "🔥" if val >= 0.75 else ("⚠️" if val >= 0.40 else "✅")
            html += (
                f"<td style='"
                f"background:{bg};"
                f"color:#fff;"
                f"padding:4px 3px;"
                f"border-radius:6px;"
                f"text-align:center;"
                f"vertical-align:middle;"
                f"height:{cell_h}px;"
                f"font-size:0.65rem;font-weight:700;"
                f"box-shadow:0 1px 4px rgba(0,0,0,.4);'>"
                f"<span style='opacity:.5;font-size:.46rem;display:block;'>R{r}·C{c}</span>"
                f"{intensity}<br>{pct}</td>"
            )
        html += "</tr>"
    html += "</table>"

    # Gradient legend bar
    html += (
        "<div style='margin-top:8px;display:flex;align-items:center;gap:8px;"
        "font-size:0.65rem;color:#888;'>"
        "<span>Stocked</span>"
        "<div style='flex:1;height:8px;border-radius:4px;"
        "background:linear-gradient(90deg,rgb(0,80,200),rgb(220,0,40));'></div>"
        "<span>Empty</span></div>"
    )
    return html
