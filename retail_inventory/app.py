"""
AI-Powered Retail Inventory Dashboard  (Grid + Snapshot edition)
=================================================================
Streamlit GUI with:
  • Shelf region configuration
  • Grid overlay on camera feed
  • Visual grid map
  • Snapshot-based sales detection (position-aware)
  • Occlusion handling (majority voting + sudden-drop guard)
  • Restocking alerts & shelf recommendations
  • Emptiness heatmap

Run:  streamlit run app.py
"""

import streamlit as st
import cv2
import json
import numpy as np
import pandas as pd
import time
from datetime import datetime

from detector import ProductDetector
from grid_mapper import ShelfRegion, GridMapper
from tracker import SnapshotTracker
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
# CSS — dark premium theme
# ======================================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

[data-testid="stMetric"] {
    background: linear-gradient(135deg, #1e1e2e 0%, #2a2a3e 100%);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px; padding: 14px 18px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.25);
}
[data-testid="stMetricLabel"] { font-size: .82rem !important; color: #a0a0c0 !important; }
[data-testid="stMetricValue"] { font-weight: 700 !important; font-size: 1.5rem !important; }

.alert-critical {
    background: linear-gradient(135deg,#ff416c,#ff4b2b); color:#fff;
    padding:12px 16px; border-radius:10px; margin-bottom:8px;
    font-weight:600; box-shadow:0 2px 12px rgba(255,65,108,.35);
}
.alert-warning {
    background: linear-gradient(135deg,#f7971e,#ffd200); color:#1a1a2e;
    padding:12px 16px; border-radius:10px; margin-bottom:8px;
    font-weight:600; box-shadow:0 2px 12px rgba(247,151,30,.30);
}
.rec-card {
    background: linear-gradient(135deg,#11998e,#38ef7d); color:#1a1a2e;
    padding:12px 16px; border-radius:10px; margin-bottom:8px;
    font-weight:600; box-shadow:0 2px 12px rgba(17,153,142,.30);
}
.info-card {
    background: linear-gradient(135deg,#667eea,#764ba2); color:#fff;
    padding:12px 16px; border-radius:10px; margin-bottom:8px;
    font-weight:500; box-shadow:0 2px 12px rgba(102,126,234,.30);
}
.dash-header { text-align:center; padding:8px 0 18px 0; }
.dash-header h1 {
    font-size:1.9rem;
    background:linear-gradient(90deg,#667eea,#764ba2,#38ef7d);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent;
    font-weight:800; margin-bottom:2px;
}
.dash-header p { color:#888; font-size:.85rem; }
[data-testid="stSidebar"] { background:linear-gradient(180deg,#0f0f1a 0%,#1a1a2e 100%); }
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
    "tracker": None,       # will init after sidebar
    "engine": None,
    "db": Database(),
    "frame_count": 0,
    "log_lines": [],
    "last_alerts": [],
    "last_recs": [],
    "snapshot_count": 0,
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
    shelf_x1 = st.number_input("x_min", 0, 1920, 50, 10)
    shelf_y1 = st.number_input("y_min", 0, 1080, 30, 10)
    shelf_x2 = st.number_input("x_max", 0, 1920, 590, 10)
    shelf_y2 = st.number_input("y_max", 0, 1080, 440, 10)

    st.markdown("---")
    st.markdown("## 🔲 Grid Size")
    grid_rows = st.slider("Rows", 1, 8, 3)
    grid_cols = st.slider("Columns", 1, 10, 5)

    st.markdown("---")
    st.markdown("## ⏱️ Snapshot")
    snap_interval = st.slider("Interval (seconds)", 5, 600, 30, 5,
                               help="Seconds between auto-snapshots")
    buffer_size = st.slider("Buffer frames (occlusion)", 3, 15, 5)

    st.markdown("---")
    st.markdown("## 🔔 Alerts")
    stock_threshold = st.slider("Low-stock threshold", 1, 20, 5)

    st.markdown("---")
    st.markdown("## 📷 Input")
    source = st.radio("Source", ["🎥 Webcam", "🖼️ Upload image"],
                       label_visibility="collapsed")

    st.markdown("---")
    if st.button("🗑️ Reset all data"):
        if st.session_state.tracker:
            st.session_state.tracker.reset()
        st.session_state.frame_count = 0
        st.session_state.log_lines = []
        st.session_state.last_alerts = []
        st.session_state.last_recs = []
        st.session_state.snapshot_count = 0
        st.toast("Tracking data cleared!", icon="🗑️")

# ======================================================================
# Build objects from sidebar values
# ======================================================================
shelf = ShelfRegion(shelf_x1, shelf_y1, shelf_x2, shelf_y2)
grid_mapper = GridMapper(shelf, grid_rows, grid_cols)

# Rebuild tracker when settings change (keyed on interval + buffer)
tracker_key = f"{snap_interval}_{buffer_size}"
if (st.session_state.tracker is None
        or getattr(st.session_state, "_tracker_key", None) != tracker_key):
    st.session_state.tracker = SnapshotTracker(
        snapshot_interval_seconds=snap_interval,
        buffer_size=buffer_size,
    )
    st.session_state._tracker_key = tracker_key

tracker: SnapshotTracker = st.session_state.tracker

engine = RestockingEngine(stock_threshold=stock_threshold)
db: Database = st.session_state.db

# ======================================================================
# Load detector (cached)
# ======================================================================
@st.cache_resource
def load_detector(conf: float):
    return ProductDetector(confidence=conf)

try:
    detector = load_detector(confidence)
except Exception as exc:
    st.error(f"❌ Failed to load YOLO model: {exc}")
    st.stop()

# ======================================================================
# Process one frame
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
            sales = tracker.get_latest_sales()
            restocks = tracker.get_latest_restocks()
            if sales:
                db.log_sales(sales)
            if restocks:
                db.log_restocks(restocks)

    # 6. Draw annotated frame
    annotated = draw_boxes(frame, shelf_dets)
    annotated = grid_mapper.draw_grid_overlay(annotated, grid_map)

    # 7. Current data
    stock = tracker.get_current_stock()
    rate = tracker.get_sales_rate()
    grid_now = tracker.get_live_grid() or grid_map

    alerts = engine.check_alerts(stock, rate, grid_now)
    co_grids = [s.grid_map for s in tracker.snapshot_history] if tracker.snapshot_history else []
    co_occ = engine.analyse_co_occurrence(co_grids)
    recs = engine.get_recommendations(stock, rate, co_occ)

    for a in alerts:
        db.log_alert(a["item"], a["severity"], a["action"])

    st.session_state.last_alerts = alerts
    st.session_state.last_recs = recs
    st.session_state.frame_count += 1

    # Log
    ts = datetime.now().strftime("%H:%M:%S")
    occ_tag = "" if accepted else " [OCCLUDED—skipped]"
    snap_tag = " 📸 SNAPSHOT" if snapshot_taken else ""
    st.session_state.log_lines.append(
        f"[{ts}] Frame #{st.session_state.frame_count} — "
        f"{len(shelf_dets)} shelf objects{occ_tag}{snap_tag}"
    )
    if len(st.session_state.log_lines) > 300:
        st.session_state.log_lines = st.session_state.log_lines[-150:]

    return annotated, grid_map, stock, rate, alerts, recs

# ======================================================================
# Main layout
# ======================================================================
col_vid, col_data = st.columns([3, 2], gap="large")

# ---------- LEFT: video / image ----------
with col_vid:
    if source == "🎥 Webcam":
        st.markdown("### 🎥 Live Camera + Grid Overlay")
        run = st.checkbox("▶  Start camera", value=False, key="cam_toggle")
        snap_btn = st.button("📸 Manual snapshot", disabled=not run)
        frame_ph = st.empty()
        status_ph = st.empty()

        if run:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                st.error("❌ Cannot open webcam.")
            else:
                status_ph.info("📡 Camera active — uncheck to stop")
                while run:
                    ret, frame = cap.read()
                    if not ret:
                        time.sleep(0.3)
                        continue

                    annotated, grid_map, stock, rate, alerts, recs = process_frame(frame)

                    # Manual snapshot
                    if snap_btn:
                        tracker.take_snapshot()
                        st.session_state.snapshot_count += 1
                        snap_btn = False

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

    else:  # Upload image
        st.markdown("### 🖼️ Image Analysis")
        uploaded = st.file_uploader(
            "Upload a shelf image", type=["jpg", "jpeg", "png", "bmp", "webp"],
        )
        if uploaded is not None:
            raw = np.asarray(bytearray(uploaded.read()), dtype=np.uint8)
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
                    caption=f"Grid: {grid_rows}×{grid_cols} | "
                            f"Shelf det: {sum(stock.values())} items",
                )
        else:
            st.info("Upload a shelf image to begin.")

# ---------- RIGHT: data panels ----------
with col_data:
    stock = tracker.get_current_stock()
    rate = tracker.get_sales_rate()
    stats = tracker.get_stats()
    live_grid = tracker.get_live_grid()

    # Top metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Items", sum(stock.values()) if stock else 0)
    m2.metric("Classes", len(stock))
    m3.metric("Snapshots", st.session_state.snapshot_count)
    m4.metric("Frames", st.session_state.frame_count)

    st.markdown("---")

    # --- Grid map ---
    st.markdown("### 🔲 Shelf Grid Map")
    if live_grid:
        st.markdown(render_grid_html(live_grid), unsafe_allow_html=True)
    else:
        st.caption("No grid data — start the camera or upload an image.")

    st.markdown("---")

    # --- Stock summary ---
    st.markdown("### 📦 Stock Summary")
    if stock:
        rows = [{"Item": k, "Count": v, "Sales/hr": f"{rate.get(k,0):.1f}"}
                for k, v in sorted(stock.items())]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.caption("No items on shelf yet.")

    # --- Sales ---
    st.markdown("### 🔄 Sales (last snapshot)")
    sales = tracker.get_latest_sales()
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
tab_heat, tab_hist, tab_log = st.tabs(
    ["🌡️ Emptiness Heatmap", "🗄️ History", "📝 Log"]
)

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
# Tracking stats (collapsed)
# ======================================================================
with st.expander("📊 Tracking Stats"):
    stats = tracker.get_stats()
    sc1, sc2, sc3 = st.columns(3)
    sc1.metric("Frames processed", stats["frames_processed"])
    sc2.metric("Frames skipped (occlusion)", stats["frames_skipped"])
    sc3.metric("Buffer fill", f"{stats['buffer_fill']}/{buffer_size}")
    if stats["tracking_since"]:
        st.caption(f"Tracking since {stats['tracking_since'].strftime('%H:%M:%S')}")

# Footer
st.markdown(
    "<br><center style='color:#555;font-size:.7rem;'>"
    "AI Retail Dashboard · Grid + Snapshot · YOLOv8 + Streamlit"
    "</center>", unsafe_allow_html=True,
)
