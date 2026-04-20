"""
AI-Powered Retail Inventory Dashboard  (Grid + Snapshot edition v2)
====================================================================
Streamlit GUI with:
  • Shelf region configuration  (sidebar)
  • Class allowlist filter      (sidebar — pick which YOLO classes matter)
  • Grid overlay on camera feed
  • Visual grid map  (per-product colours)
  • Snapshot-based sales detection (position-aware)
  • Occlusion handling (majority voting + sudden-drop guard)
  • Restocking alerts & shelf recommendations
  • Stock trend line chart (Plotly)
  • Emptiness heatmap
  • Demo / simulation mode (no camera needed)

Run:  streamlit run app.py
"""

import streamlit as st
import cv2
import json
import math
import random
import numpy as np
import pandas as pd
import time
from datetime import datetime

from detector import ProductDetector
from grid_mapper import ShelfRegion, GridMapper
from tracker import SnapshotTracker, detect_sales, detect_movement
from logic import RestockingEngine
from database import Database
from utils import (
    draw_boxes,
    format_time_remaining,
    render_grid_html,
    render_heatmap_html,
)

# ======================================================================
# Page config
# ======================================================================
st.set_page_config(
    page_title="AI Retail Inventory Dashboard",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ======================================================================
# CSS — premium dark theme with glassmorphism & micro-animations
# ======================================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* --- Metric cards --- */
[data-testid="stMetric"] {
    background: linear-gradient(135deg, #1e1e2e 0%, #2a2a3e 100%);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 14px; padding: 16px 20px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.30);
    transition: transform .2s, box-shadow .2s;
}
[data-testid="stMetric"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 32px rgba(102,126,234,0.25);
}
[data-testid="stMetricLabel"] { font-size: .82rem !important; color: #a0a0c0 !important; }
[data-testid="stMetricValue"] { font-weight: 700 !important; font-size: 1.5rem !important; }

/* --- Alert cards --- */
.alert-critical {
    background: linear-gradient(135deg,#ff416c,#ff4b2b); color:#fff;
    padding:12px 16px; border-radius:12px; margin-bottom:8px;
    font-weight:600; box-shadow:0 4px 16px rgba(255,65,108,.35);
    animation: pulse-alert 2s infinite;
}
@keyframes pulse-alert {
    0%,100% { box-shadow:0 4px 16px rgba(255,65,108,.35); }
    50%     { box-shadow:0 4px 28px rgba(255,65,108,.55); }
}
.alert-warning {
    background: linear-gradient(135deg,#f7971e,#ffd200); color:#1a1a2e;
    padding:12px 16px; border-radius:12px; margin-bottom:8px;
    font-weight:600; box-shadow:0 4px 16px rgba(247,151,30,.30);
}
.rec-card {
    background: linear-gradient(135deg,#11998e,#38ef7d); color:#1a1a2e;
    padding:12px 16px; border-radius:12px; margin-bottom:8px;
    font-weight:600; box-shadow:0 4px 16px rgba(17,153,142,.30);
}
.info-card {
    background: linear-gradient(135deg,#667eea,#764ba2); color:#fff;
    padding:12px 16px; border-radius:12px; margin-bottom:8px;
    font-weight:500; box-shadow:0 4px 16px rgba(102,126,234,.30);
}

/* --- Dashboard header --- */
.dash-header { text-align:center; padding:8px 0 18px 0; }
.dash-header h1 {
    font-size:2rem;
    background:linear-gradient(90deg,#667eea,#764ba2,#38ef7d);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent;
    font-weight:800; margin-bottom:2px;
}
.dash-header p { color:#888; font-size:.85rem; }

/* --- Sidebar --- */
[data-testid="stSidebar"] {
    background:linear-gradient(180deg,#0f0f1a 0%,#1a1a2e 100%);
}

/* --- Demo banner --- */
.demo-banner {
    background: linear-gradient(135deg,#6366f1,#8b5cf6);
    color: #fff; padding:10px 16px; border-radius:10px;
    margin-bottom:12px; font-weight:600; text-align:center;
    box-shadow:0 2px 12px rgba(99,102,241,.35);
    animation: demo-glow 3s ease-in-out infinite;
}
@keyframes demo-glow {
    0%,100% { box-shadow:0 2px 12px rgba(99,102,241,.35); }
    50%     { box-shadow:0 2px 24px rgba(139,92,246,.55); }
}

/* --- Section divider --- */
.section-divider {
    border: none; height:1px;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.08), transparent);
    margin: 12px 0;
}

/* --- Class manager pills --- */
.class-pill-wrap {
    display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px;
}

/* --- Sidebar text input tight layout --- */
[data-testid="stSidebar"] .stTextInput input {
    background:#1e1e2e !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 8px !important;
    color: #e0e0ff !important;
    font-size: .82rem !important;
}
[data-testid="stSidebar"] .stTextInput input:focus {
    border-color: #667eea !important;
    box-shadow: 0 0 0 2px rgba(102,126,234,.25) !important;
}
</style>
""", unsafe_allow_html=True)

# ======================================================================
# Header
# ======================================================================
st.markdown("""
<div class="dash-header">
    <h1>📦 AI Retail Inventory Dashboard</h1>
    <p>Grid-based shelf mapping · Snapshot sales detection · Occlusion handling</p>
</div>
""", unsafe_allow_html=True)

# ======================================================================
# Session-state defaults
# ======================================================================
_DEFAULTS = {
    "tracker": None,
    "engine": None,
    "db": Database(),
    "frame_count": 0,
    "log_lines": [],
    "last_alerts": [],
    "last_recs": [],
    "snapshot_count": 0,
    "demo_step": 0,
    # Class manager
    "active_classes": None,        # None → use detector defaults
    "custom_classes": set(),        # user-typed class names
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ======================================================================
# Sidebar — settings
# ======================================================================
with st.sidebar:
    st.markdown("## ⚙️ Detection")
    confidence = st.slider("Confidence threshold", 0.10, 1.0, 0.45, 0.05)

    st.markdown("---")
    st.markdown("## 📐 Shelf Region")
    st.caption("Set the pixel coordinates of the shelf bounding box")
    shelf_x1 = st.number_input("x_min", 0, 1920, 50,  10)
    shelf_y1 = st.number_input("y_min", 0, 1080, 30,  10)
    shelf_x2 = st.number_input("x_max", 0, 1920, 590, 10)
    shelf_y2 = st.number_input("y_max", 0, 1080, 440, 10)

    st.markdown("---")
    st.markdown("## 🔲 Grid Size")
    grid_rows = st.slider("Rows",    1, 8,  3)
    grid_cols = st.slider("Columns", 1, 10, 5)

    st.markdown("---")
    st.markdown("## ⏱️ Snapshot")
    snap_interval = st.slider(
        "Interval (seconds)", 5, 600, 30, 5,
        help="Seconds between auto-snapshots",
    )
    buffer_size = st.slider("Buffer frames (occlusion)", 3, 15, 5)

    st.markdown("---")
    st.markdown("## 🔔 Alerts")
    stock_threshold = st.slider("Low-stock threshold", 1, 20, 5)

    st.markdown("---")
    st.markdown("## 📷 Input")
    source = st.radio(
        "Source",
        ["🎥 Webcam", "🖼️ Upload image", "🧪 Demo simulation"],
        label_visibility="collapsed",
    )

    st.markdown("---")
    if st.button("🗑️ Reset all data"):
        if st.session_state.tracker:
            st.session_state.tracker.reset()
        st.session_state.frame_count  = 0
        st.session_state.log_lines    = []
        st.session_state.last_alerts  = []
        st.session_state.last_recs    = []
        st.session_state.snapshot_count = 0
        st.session_state.demo_step    = 0
        st.toast("Tracking data cleared!", icon="🗑️")

# ======================================================================
# Build objects from sidebar values
# ======================================================================
shelf       = ShelfRegion(shelf_x1, shelf_y1, shelf_x2, shelf_y2)
grid_mapper = GridMapper(shelf, grid_rows, grid_cols)

# Rebuild tracker when settings change
tracker_key = f"{snap_interval}_{buffer_size}"
if (st.session_state.tracker is None
        or getattr(st.session_state, "_tracker_key", None) != tracker_key):
    st.session_state.tracker = SnapshotTracker(
        snapshot_interval_seconds=snap_interval,
        buffer_size=buffer_size,
    )
    st.session_state._tracker_key = tracker_key

tracker: SnapshotTracker = st.session_state.tracker
engine  = RestockingEngine(stock_threshold=stock_threshold)
db: Database = st.session_state.db

# ======================================================================
# Load detector  (model cached once, confidence updated per-run)
# ======================================================================
@st.cache_resource
def load_detector():
    """Load YOLO model once.  Confidence is updated separately."""
    return ProductDetector(confidence=0.45)

try:
    detector = load_detector()
    # Apply current sidebar confidence (doesn't reload model)
    detector.set_confidence(confidence)
except Exception as exc:
    st.error(f"❌ Failed to load YOLO model: {exc}")
    st.stop()

# ======================================================================
# Class Manager (after detector loads so we know what the model supports)
# ======================================================================
with st.sidebar:
    st.markdown("---")
    st.markdown("## 🏷️ Tracked Classes")
    st.caption("Choose which product classes are tracked by the system")

    # -- Available classes from the YOLO model (base list) --
    available = detector.get_class_list()

    # -- Merge in user-added custom class names --
    all_options = sorted(set(available) | st.session_state.custom_classes)

    # -- Default selection: all_options (if no previous choice) --
    if st.session_state.active_classes is None:
        init_sel = all_options
    else:
        # Keep only classes that still exist in the combined list
        init_sel = sorted(
            st.session_state.active_classes & set(all_options)
        )

    # ---- Multiselect: pick from model + custom classes ----
    selected = st.multiselect(
        "Active classes",
        options=all_options,
        default=init_sel,
        help="Tick/untick to enable or disable a class",
        key="class_multiselect",
    )
    st.session_state.active_classes = set(selected)

    # ---- Add a brand-new custom class by name ----
    st.markdown("**➕ Add custom class**")
    col_inp, col_btn = st.columns([3, 1])
    new_cls = col_inp.text_input(
        "✉️ Class name",
        placeholder="e.g. shampoo",
        label_visibility="collapsed",
        key="new_class_input",
    ).strip().lower()
    if col_btn.button("➕ Add", use_container_width=True):
        if new_cls and new_cls not in all_options:
            st.session_state.custom_classes.add(new_cls)
            st.session_state.active_classes.add(new_cls)
            st.toast(f"✅ '{new_cls}' added to tracked classes", icon="🏷️")
            st.rerun()
        elif new_cls in all_options:
            st.warning(f"'{new_cls}' is already in the list.")
        else:
            st.warning("Please enter a class name.")

    # ---- Remove individual classes ----
    if st.session_state.active_classes:
        st.markdown("**❌ Remove a class**")
        remove_cls = st.selectbox(
            "Select to remove",
            options=sorted(st.session_state.active_classes),
            index=None,
            placeholder="Choose class…",
            label_visibility="collapsed",
            key="remove_class_select",
        )
        if st.button("🗑️ Remove", use_container_width=True):
            if remove_cls:
                st.session_state.active_classes.discard(remove_cls)
                st.session_state.custom_classes.discard(remove_cls)  # also from custom
                st.toast(f"🗑️ '{remove_cls}' removed", icon="❌")
                st.rerun()

    # ---- Active class pills display ----
    if st.session_state.active_classes:
        pill_colors = [
            "#667eea", "#764ba2", "#11998e", "#f7971e",
            "#ff416c", "#38ef7d", "#6366f1", "#f59e0b",
        ]
        pills_html = "".join(
            f"<span style='background:{pill_colors[i % len(pill_colors)]};color:#fff;"
            f"padding:3px 10px;border-radius:20px;font-size:.75rem;"
            f"font-weight:600;margin:2px;display:inline-block;'>{cls}</span>"
            for i, cls in enumerate(sorted(st.session_state.active_classes))
        )
        st.markdown(
            f"<div style='margin-top:8px;line-height:2.2;'>{pills_html}</div>",
            unsafe_allow_html=True,
        )
        st.caption(f"{len(st.session_state.active_classes)} class(es) tracked")
    else:
        st.warning("⚠️ No classes selected — nothing will be detected.")

    # ---- Apply to detector ----
    active = st.session_state.active_classes
    if active is not None and set(active) != set(available):
        detector.set_allowed_classes(set(active))
    else:
        detector.set_allowed_classes(None)   # revert to model defaults

# ======================================================================
# Process one frame  (real or synthetic)
# ======================================================================
def process_frame(frame: np.ndarray):
    """Detect → filter to shelf → map to grid → feed tracker."""
    # 1. Detect
    detections, _ = detector.detect(frame)

    # 2. Filter to shelf region only
    shelf_dets = grid_mapper.filter_shelf_detections(detections)

    # 3. Map to grid
    grid_map = grid_mapper.map_detections(shelf_dets)

    # 4. Feed tracker buffer (occlusion guard may reject)
    accepted = tracker.add_frame(grid_map)

    # 5. Auto-snapshot
    snapshot_taken = False
    if tracker.should_take_snapshot():
        snap = tracker.take_snapshot()
        if snap:
            snapshot_taken = True
            st.session_state.snapshot_count += 1
            stock = snap.item_counts
            db.save_grid_snapshot(snap.grid_map, stock)
            sales    = tracker.get_latest_sales()
            restocks = tracker.get_latest_restocks()
            if sales:
                db.log_sales(sales)
            if restocks:
                db.log_restocks(restocks)

    # 6. Draw annotated frame
    annotated = draw_boxes(frame, shelf_dets)
    annotated = grid_mapper.draw_grid_overlay(annotated, grid_map)

    # 7. Current data
    stock    = tracker.get_current_stock()
    rate     = tracker.get_sales_rate()
    grid_now = tracker.get_live_grid() or grid_map

    alerts   = engine.check_alerts(stock, rate, grid_now)
    co_grids = [s.grid_map for s in tracker.snapshot_history] if tracker.snapshot_history else []
    co_occ   = engine.analyse_co_occurrence(co_grids)
    recs     = engine.get_recommendations(stock, rate, co_occ)

    for a in alerts:
        db.log_alert(a["item"], a["severity"], a["action"])

    st.session_state.last_alerts = alerts
    st.session_state.last_recs   = recs
    st.session_state.frame_count += 1

    # Log
    ts       = datetime.now().strftime("%H:%M:%S")
    occ_tag  = "" if accepted else " [OCCLUDED—skipped]"
    snap_tag = " 📸 SNAPSHOT" if snapshot_taken else ""
    st.session_state.log_lines.append(
        f"[{ts}] Frame #{st.session_state.frame_count} — "
        f"{len(shelf_dets)} shelf objects{occ_tag}{snap_tag}"
    )
    if len(st.session_state.log_lines) > 300:
        st.session_state.log_lines = st.session_state.log_lines[-150:]

    return annotated, grid_map, stock, rate, alerts, recs


# ======================================================================
# Demo simulation  (no camera / image required)
# ======================================================================
# Product pool for demo grids
_DEMO_PRODUCTS = ["bottle", "cup", "apple", "banana", "book", "remote"]


def _random_grid(rows: int, cols: int, fill_pct: float = 0.70) -> list:
    """Generate a random shelf grid for demo mode."""
    grid = [["empty"] * cols for _ in range(rows)]
    for r in range(rows):
        for c in range(cols):
            if random.random() < fill_pct:
                grid[r][c] = random.choice(_DEMO_PRODUCTS)
    return grid


def _simulate_sales(grid: list, remove_n: int = 2) -> list:
    """Remove *remove_n* random items from the grid to simulate sales."""
    import copy
    g = copy.deepcopy(grid)
    occupied = [(r, c) for r in range(len(g)) for c in range(len(g[0])) if g[r][c] != "empty"]
    if occupied:
        for rc in random.sample(occupied, min(remove_n, len(occupied))):
            g[rc[0]][rc[1]] = "empty"
    return g


def run_demo_step():
    """Run one demo iteration — feeds a synthetic grid into the tracker."""
    step = st.session_state.demo_step

    if step == 0:
        # First step: create a well-stocked shelf
        grid = _random_grid(grid_rows, grid_cols, fill_pct=0.85)
    else:
        # Subsequent steps: remove 1-3 items to simulate sales
        prev = tracker.get_live_grid()
        if prev:
            grid = _simulate_sales(prev, remove_n=random.randint(1, 3))
        else:
            grid = _random_grid(grid_rows, grid_cols, fill_pct=0.70)

    accepted = tracker.add_frame(grid)

    # Force snapshot on every demo step for visibility
    snap = tracker.take_snapshot()
    snapshot_taken = False
    if snap:
        snapshot_taken = True
        st.session_state.snapshot_count += 1
        db.save_grid_snapshot(snap.grid_map, snap.item_counts)
        sales    = tracker.get_latest_sales()
        restocks = tracker.get_latest_restocks()
        if sales:
            db.log_sales(sales)
        if restocks:
            db.log_restocks(restocks)

    stock    = tracker.get_current_stock()
    rate     = tracker.get_sales_rate()
    grid_now = tracker.get_live_grid() or grid
    alerts   = engine.check_alerts(stock, rate, grid_now)
    recs     = engine.get_recommendations(stock, rate)

    st.session_state.last_alerts = alerts
    st.session_state.last_recs   = recs
    st.session_state.frame_count += 1
    st.session_state.demo_step   += 1

    ts       = datetime.now().strftime("%H:%M:%S")
    occ_tag  = "" if accepted else " [OCCLUDED—skipped]"
    snap_tag = " 📸 SNAPSHOT" if snapshot_taken else ""
    st.session_state.log_lines.append(
        f"[{ts}] Demo step #{st.session_state.demo_step} — "
        f"Grid {grid_rows}×{grid_cols}{occ_tag}{snap_tag}"
    )

    return grid, stock, rate, alerts, recs


# ======================================================================
# Main layout
# ======================================================================
col_vid, col_data = st.columns([3, 2], gap="large")

# ---------- LEFT: video / image / demo ----------
with col_vid:
    if source == "🎥 Webcam":
        st.markdown("### 🎥 Live Camera + Grid Overlay")
        run      = st.checkbox("▶  Start camera", value=False, key="cam_toggle")
        snap_col1, snap_col2 = st.columns(2)
        with snap_col1:
            manual_snap = st.button("📸 Manual snapshot", disabled=not run, key="snap_btn")
        frame_ph  = st.empty()
        status_ph = st.empty()

        if run:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                st.error("❌ Cannot open webcam. Check connections or use Demo mode.")
            else:
                status_ph.info("📡 Camera active — uncheck to stop")
                while run:
                    ret, frame = cap.read()
                    if not ret:
                        time.sleep(0.3)
                        continue

                    annotated, grid_map, stock, rate, alerts, recs = process_frame(frame)

                    # Manual snapshot (button is True only for the first rerun)
                    if manual_snap:
                        tracker.take_snapshot()
                        st.session_state.snapshot_count += 1

                    frame_ph.image(
                        cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB),
                        channels="RGB", use_container_width=True,
                    )
                    time.sleep(0.05)
                cap.release()
                status_ph.success("🛑 Camera stopped")
        else:
            if st.session_state.frame_count > 0:
                status_ph.info(
                    f"Paused — {st.session_state.frame_count} frames, "
                    f"{st.session_state.snapshot_count} snapshots"
                )

    elif source == "🖼️ Upload image":
        st.markdown("### 🖼️ Image Analysis")
        uploaded = st.file_uploader(
            "Upload a shelf image",
            type=["jpg", "jpeg", "png", "bmp", "webp"],
        )
        if uploaded is not None:
            raw   = np.asarray(bytearray(uploaded.read()), dtype=np.uint8)
            frame = cv2.imdecode(raw, cv2.IMREAD_COLOR)
            if frame is None:
                st.error("❌ Could not decode image.")
            else:
                annotated, grid_map, stock, rate, alerts, recs = process_frame(frame)
                # Force a snapshot on image upload
                tracker.take_snapshot()
                st.session_state.snapshot_count += 1
                stock = tracker.get_current_stock()

                st.image(
                    cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB),
                    channels="RGB", use_container_width=True,
                    caption=(
                        f"Grid: {grid_rows}×{grid_cols} | "
                        f"Shelf det: {sum(stock.values())} items"
                    ),
                )
        else:
            st.info("Upload a shelf image to begin.")

    else:  # Demo simulation
        st.markdown("### 🧪 Demo Simulation")
        st.markdown(
            "<div class='demo-banner'>🎮 Simulation mode — no camera needed</div>",
            unsafe_allow_html=True,
        )
        st.caption(
            "Each click simulates a time interval on the shelf. "
            "Items are randomly placed, then removed to mimic sales."
        )
        d1, d2 = st.columns(2)
        with d1:
            sim_btn = st.button("▶ Run 1 step", use_container_width=True, type="primary")
        with d2:
            sim5_btn = st.button("⏩ Run 5 steps", use_container_width=True)

        steps = 0
        if sim_btn:
            steps = 1
        elif sim5_btn:
            steps = 5

        if steps > 0:
            for _ in range(steps):
                grid, stock, rate, alerts, recs = run_demo_step()
            live_grid = tracker.get_live_grid()
            if live_grid:
                st.markdown("#### Current Shelf Grid")
                st.markdown(render_grid_html(live_grid), unsafe_allow_html=True)

        elif st.session_state.demo_step > 0:
            live_grid = tracker.get_live_grid()
            if live_grid:
                st.markdown("#### Current Shelf Grid")
                st.markdown(render_grid_html(live_grid), unsafe_allow_html=True)
        else:
            st.info("Click **Run 1 step** to begin the simulation.")

# ---------- RIGHT: data panels ----------
with col_data:
    stock     = tracker.get_current_stock()
    rate      = tracker.get_sales_rate()
    stats     = tracker.get_stats()
    live_grid = tracker.get_live_grid()

    # Top metrics row
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Items",     sum(stock.values()) if stock else 0)
    m2.metric("Classes",   len(stock))
    m3.metric("Snapshots", st.session_state.snapshot_count)
    m4.metric("Frames",    st.session_state.frame_count)

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

    # --- Grid map ---
    if source != "🧪 Demo simulation":
        st.markdown("### 🔲 Shelf Grid Map")
        if live_grid:
            st.markdown(render_grid_html(live_grid), unsafe_allow_html=True)
        else:
            st.caption("No grid data — start the camera or upload an image.")

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

    # --- Stock summary ---
    st.markdown("### 📦 Stock Summary")
    if stock:
        rows = [
            {"Item": k, "Count": v, "Sales/hr": f"{rate.get(k,0):.1f}"}
            for k, v in sorted(stock.items())
        ]
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("No items on shelf yet.")

    # --- Sales ---
    st.markdown("### 🔄 Sales (last snapshot)")
    sales    = tracker.get_latest_sales()
    restocks = tracker.get_latest_restocks()
    if sales:
        for item, qty in sales.items():
            st.markdown(
                f"<div class='info-card'>⬇️ <b>{item}</b> — {qty} sold</div>",
                unsafe_allow_html=True,
            )
    if restocks:
        for item, qty in restocks.items():
            st.markdown(
                f"<div class='rec-card'>⬆️ <b>{item}</b> — {qty} restocked</div>",
                unsafe_allow_html=True,
            )
    if not sales and not restocks:
        st.caption("No changes detected between snapshots yet.")

    # --- Alerts ---
    st.markdown("### 🔔 Alerts")
    alerts = st.session_state.last_alerts
    if alerts:
        for a in alerts:
            css = "alert-critical" if a["severity"] == "critical" else "alert-warning"
            tte = format_time_remaining(a.get("time_to_empty"))
            st.markdown(
                f"<div class='{css}'><b>{a['item']}</b> — stock: {a['stock']} · "
                f"rate: {a['sales_rate']:.1f}/hr · depletes: {tte}<br>"
                f"➜ {a['action']}</div>",
                unsafe_allow_html=True,
            )
    else:
        st.success("✅ All stock levels healthy")

    # --- Recommendations ---
    st.markdown("### 📋 Recommendations")
    recs = st.session_state.last_recs
    if recs:
        for r in recs:
            st.markdown(
                f"<div class='rec-card'><b>{r['item']}</b> — {r['reason']}<br>"
                f"➜ {r['suggestion']}</div>",
                unsafe_allow_html=True,
            )
    else:
        st.caption("No recommendations at this time.")

# ======================================================================
# Bottom tabs
# ======================================================================
st.markdown("---")
tab_trend, tab_heat, tab_hist, tab_log = st.tabs(
    ["📈 Stock Trends", "🌡️ Emptiness Heatmap", "🗄️ History", "📝 Log"]
)

# --- Trend chart ---
with tab_trend:
    history = tracker.get_stock_history()
    if len(history) >= 2:
        # Build dataframe: one row per snapshot, one column per item
        records = []
        for ts, counts in history:
            row = {"Time": ts.strftime("%H:%M:%S")}
            row.update(counts)
            records.append(row)
        df_trend = pd.DataFrame(records).fillna(0)
        item_cols = [c for c in df_trend.columns if c != "Time"]
        if item_cols:
            st.markdown("Stock level per item across snapshots:")
            st.line_chart(df_trend.set_index("Time")[item_cols])
        else:
            st.info("No items tracked yet.")
    else:
        st.info("Need at least 2 snapshots to show trends.")

with tab_heat:
    heatmap = tracker.compute_emptiness_heatmap()
    if heatmap:
        st.markdown("Cells that are **frequently empty** appear red.")
        st.markdown(render_heatmap_html(heatmap), unsafe_allow_html=True)
    else:
        st.info("Need at least 1 snapshot to generate a heatmap.")

with tab_hist:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Grid Snapshots")
        snap_rows = db.get_snapshot_history(limit=20)
        if snap_rows:
            df = pd.DataFrame(
                [(r[0], json.loads(r[2])) for r in snap_rows],
                columns=["Timestamp", "Stock"],
            )
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.caption("No snapshots yet.")
    with c2:
        st.markdown("#### Sales / Restock Events")
        ev_rows = db.get_sales_history(limit=30)
        if ev_rows:
            df = pd.DataFrame(ev_rows, columns=["Time", "Item", "Qty", "Type"])
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.caption("No events yet.")

with tab_log:
    if st.session_state.log_lines:
        st.code("\n".join(st.session_state.log_lines[-60:]), language="log")
    else:
        st.caption("No log entries.")

# ======================================================================
# Sales Debug panel  (collapsed by default)
# ======================================================================
with st.expander("🔍 Sales Debug — Movement vs Disappearance"):
    prev_snap = tracker.previous_snapshot
    curr_snap = tracker.current_snapshot

    if prev_snap is None or curr_snap is None:
        st.info("Need at least 2 snapshots to show a diff.")
    else:
        old_grid = prev_snap.grid_map
        new_grid = curr_snap.grid_map

        # --- Count gate summary ---
        def _count_grid(g):
            c = {}
            for row in g:
                for cell in row:
                    if cell != "empty":
                        c[cell] = c.get(cell, 0) + 1
            return c

        old_counts = _count_grid(old_grid)
        new_counts = _count_grid(new_grid)
        all_items  = sorted(set(old_counts) | set(new_counts))

        st.markdown("**Count gate** — `cap = old_count − new_count`")
        st.caption(
            "cap > 0 → sale confirmed · cap = 0 → rearrangement (no sale) "
            "· cap < 0 → restock"
        )
        cg_rows = []
        for it in all_items:
            old_n = old_counts.get(it, 0)
            new_n = new_counts.get(it, 0)
            cap   = old_n - new_n
            cg_rows.append({
                "Item":      it,
                "Prev count": old_n,
                "Curr count": new_n,
                "Cap":        cap,
                "Decision":   "✅ SALE" if cap > 0 else
                              ("🔄 REARRANGEMENT" if cap == 0 else "📦 RESTOCK"),
            })
        if cg_rows:
            st.dataframe(
                pd.DataFrame(cg_rows),
                use_container_width=True,
                hide_index=True,
            )

        # --- Per-item movement classification ---
        st.markdown("**Movement classification**")
        mv = detect_movement(old_grid, new_grid)
        if mv:
            _BADGES = {
                "SOLD":      "🔴 SOLD",
                "RESTOCKED": "🟢 RESTOCKED",
                "MOVED":     "🟡 MOVED",
                "UNCHANGED": "⚪ UNCHANGED",
            }
            for item, status in sorted(mv.items()):
                badge = _BADGES.get(status, status)
                st.markdown(
                    f"`{item}` → **{badge}**",
                    unsafe_allow_html=False,
                )
        else:
            st.caption("No items to classify.")

        # --- Confirmed sales / restocks ---
        dbg_sales, dbg_restocks = detect_sales(old_grid, new_grid)
        if dbg_sales:
            st.markdown("**Confirmed sales this diff:**")
            for item, qty in dbg_sales.items():
                st.markdown(
                    f"<div class='alert-warning'>"
                    f"⬇️ <b>{item}</b> — {qty} unit(s) confirmed sold"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        if dbg_restocks:
            st.markdown("**Confirmed restocks this diff:**")
            for item, qty in dbg_restocks.items():
                st.markdown(
                    f"<div class='rec-card'>"
                    f"⬆️ <b>{item}</b> — {qty} unit(s) restocked"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        if not dbg_sales and not dbg_restocks:
            st.success("No net sales or restocks between last two snapshots.")

# ======================================================================
# Tracking stats (collapsed)
# ======================================================================
with st.expander("📊 Tracking Stats"):
    stats = tracker.get_stats()
    sc1, sc2, sc3 = st.columns(3)
    sc1.metric("Frames processed",        stats["frames_processed"])
    sc2.metric("Frames skipped (occlusion)", stats["frames_skipped"])
    sc3.metric("Buffer fill",             f"{stats['buffer_fill']}/{buffer_size}")
    if stats["tracking_since"]:
        st.caption(f"Tracking since {stats['tracking_since'].strftime('%H:%M:%S')}")

# Footer
st.markdown(
    "<br><center style='color:#555;font-size:.7rem;'>"
    "AI Retail Dashboard v2 · Grid + Snapshot · YOLOv8 + Streamlit · Movement-Aware Sales"
    "</center>", unsafe_allow_html=True,
)
