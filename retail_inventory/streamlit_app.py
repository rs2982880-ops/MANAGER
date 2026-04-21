"""
AI Shelf Monitor — Streamlit Edition
======================================
A clean, stable, single-shelf monitoring interface.

Run:
    streamlit run streamlit_app.py

Features:
    • Camera selection (device index or IP/DroidCam URL)
    • Start / Stop monitoring controls
    • Live camera feed with YOLO detection overlay
    • Real-time inventory panel (stock, sales, alerts, recommendations)
    • Confidence threshold slider
    • Detection on/off toggle
    • FPS & status indicator
    • No auto-scrolling — all state managed via st.session_state
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"  # Fix OpenMP DLL conflict on Windows

import time
from datetime import datetime

import cv2
import numpy as np
import streamlit as st

# ── Backend imports (reused as-is) ─────────────────────────────────────────
from camera_manager import ShelfCamera
from detector import ProductDetector
from grid_mapper import GridMapper, ShelfRegion
from tracker import SnapshotTracker
from logic import RestockingEngine
from utils import draw_boxes, format_time_remaining


# ═══════════════════════════════════════════════════════════════════════════
# PAGE CONFIG — must be the first Streamlit call
# ═══════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="AI Shelf Monitor",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ═══════════════════════════════════════════════════════════════════════════
# CUSTOM CSS — professional dark theme, no auto-scroll
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
    /* ── Suppress Streamlit default top padding ───────────────── */
    .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 1rem !important;
    }

    /* ── Title styling ────────────────────────────────────────── */
    .main-title {
        font-size: 2rem;
        font-weight: 800;
        background: linear-gradient(135deg, #6366f1, #06b6d4);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 0.95rem;
        color: #94a3b8;
        margin-bottom: 1.2rem;
    }

    /* ── Status bar ───────────────────────────────────────────── */
    .status-bar {
        display: flex;
        gap: 1.5rem;
        align-items: center;
        padding: 0.6rem 1rem;
        background: rgba(30, 30, 50, 0.6);
        border: 1px solid rgba(99, 102, 241, 0.3);
        border-radius: 10px;
        margin-bottom: 1rem;
        font-size: 0.85rem;
    }
    .status-dot {
        width: 10px; height: 10px;
        border-radius: 50%;
        display: inline-block;
        margin-right: 6px;
    }
    .status-dot.live    { background: #22c55e; box-shadow: 0 0 6px #22c55e; }
    .status-dot.idle    { background: #64748b; }
    .status-dot.error   { background: #ef4444; box-shadow: 0 0 6px #ef4444; }

    /* ── Metric cards ─────────────────────────────────────────── */
    .metric-card {
        background: rgba(30, 30, 50, 0.7);
        border: 1px solid rgba(99, 102, 241, 0.2);
        border-radius: 12px;
        padding: 1rem 1.2rem;
        text-align: center;
    }
    .metric-card .value {
        font-size: 1.8rem;
        font-weight: 800;
        color: #e2e8f0;
    }
    .metric-card .label {
        font-size: 0.78rem;
        color: #94a3b8;
        margin-top: 0.3rem;
    }

    /* ── Alert cards ──────────────────────────────────────────── */
    .alert-card {
        padding: 0.8rem 1rem;
        border-radius: 10px;
        margin-bottom: 0.5rem;
        font-size: 0.85rem;
    }
    .alert-card.critical {
        background: rgba(239, 68, 68, 0.15);
        border-left: 4px solid #ef4444;
        color: #fca5a5;
    }
    .alert-card.warning {
        background: rgba(245, 158, 11, 0.15);
        border-left: 4px solid #f59e0b;
        color: #fcd34d;
    }

    /* ── Section headers ─────────────────────────────────────── */
    .section-header {
        font-size: 1.1rem;
        font-weight: 700;
        color: #c4b5fd;
        margin: 1.2rem 0 0.6rem 0;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    /* ── Recommendation chip ─────────────────────────────────── */
    .rec-chip {
        background: rgba(6, 182, 212, 0.12);
        border: 1px solid rgba(6, 182, 212, 0.3);
        border-radius: 8px;
        padding: 0.6rem 1rem;
        margin-bottom: 0.4rem;
        font-size: 0.82rem;
        color: #67e8f9;
    }

    /* ── Sidebar styling ─────────────────────────────────────── */
    section[data-testid="stSidebar"] {
        background: rgba(15, 15, 30, 0.95);
    }
    section[data-testid="stSidebar"] .stMarkdown h3 {
        color: #a78bfa;
    }

    /* ── Hide Streamlit menu & footer ─────────────────────────  */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# SESSION STATE INITIALISATION
# ═══════════════════════════════════════════════════════════════════════════
# Using session_state for ALL mutable state prevents auto-scrolling
# and ensures the UI stays stable across Streamlit reruns.

def _init_session_state():
    """Initialise all session_state keys exactly once."""
    defaults = {
        "running":        False,     # Is monitoring active?
        "camera_type":    "Device",  # "Device" or "IP Camera"
        "device_index":   0,         # Camera index (0, 1, 2)
        "ip_url":         "http://192.168.0.101:4747/video",
        "confidence":     0.45,      # YOLO confidence threshold
        "detection_on":   True,      # Toggle detection overlay
        "grid_rows":      3,
        "grid_cols":      5,
        "detector":       None,      # ProductDetector singleton
        "shelf_camera":   None,      # ShelfCamera instance
        "fps":            0.0,       # Current FPS
        "frame_count":    0,
        "last_status":    "idle",    # idle | streaming | error
        "error_msg":      "",
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

_init_session_state()


# ═══════════════════════════════════════════════════════════════════════════
# BACKEND HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def get_detector() -> ProductDetector:
    """Return the singleton ProductDetector (loaded once, cached in session_state)."""
    if st.session_state.detector is None:
        with st.spinner("🔄 Loading YOLO model (first time may take a moment)..."):
            st.session_state.detector = ProductDetector(
                confidence=st.session_state.confidence
            )
    return st.session_state.detector


def get_camera_source():
    """
    Return the camera source based on user selection.
    - Device: integer index (0, 1, 2)
    - IP Camera: URL string
    """
    if st.session_state.camera_type == "Device":
        return st.session_state.device_index
    else:
        return st.session_state.ip_url.strip()


def build_shelf_camera(source) -> ShelfCamera:
    """Create a fresh ShelfCamera instance with current settings."""
    detector = get_detector()
    detector.set_confidence(st.session_state.confidence)

    shelf = ShelfCamera(
        name="Main Shelf",
        source=source,
        detector=detector,
        region=(50, 30, 590, 440),
        rows=st.session_state.grid_rows,
        cols=st.session_state.grid_cols,
        snap_interval=30.0,
        buffer_size=5,
        stock_threshold=5,
    )
    return shelf


# ═══════════════════════════════════════════════════════════════════════════
# START / STOP CALLBACKS
# ═══════════════════════════════════════════════════════════════════════════

def _on_start():
    """Called when the Start Monitoring button is pressed."""
    source = get_camera_source()

    # Build or reuse shelf camera
    shelf = build_shelf_camera(source)
    st.session_state.shelf_camera = shelf

    ok = shelf.start_camera()
    if ok:
        st.session_state.running = True
        st.session_state.last_status = "streaming"
        st.session_state.error_msg = ""
    else:
        st.session_state.running = False
        st.session_state.last_status = "error"
        st.session_state.error_msg = shelf.error_msg or "Failed to open camera"


def _on_stop():
    """Called when the Stop Monitoring button is pressed."""
    shelf = st.session_state.shelf_camera
    if shelf is not None:
        shelf.stop_camera()
    st.session_state.running = False
    st.session_state.last_status = "idle"
    st.session_state.fps = 0.0


# ═══════════════════════════════════════════════════════════════════════════
# SIDEBAR — Camera Selection & Settings
# ═══════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("### 🎛️ Camera Settings")
    st.markdown("---")

    # Camera type selector
    cam_type = st.selectbox(
        "Camera Type",
        options=["Device", "IP Camera"],
        index=0 if st.session_state.camera_type == "Device" else 1,
        key="sidebar_cam_type",
        disabled=st.session_state.running,
    )
    st.session_state.camera_type = cam_type

    # Conditional input based on camera type
    if cam_type == "Device":
        dev_idx = st.selectbox(
            "Camera Index",
            options=[0, 1, 2],
            index=st.session_state.device_index,
            key="sidebar_dev_idx",
            help="0 = Laptop camera, 1-2 = USB cameras",
            disabled=st.session_state.running,
        )
        st.session_state.device_index = dev_idx
    else:
        ip_url = st.text_input(
            "Camera URL",
            value=st.session_state.ip_url,
            key="sidebar_ip_url",
            help="e.g. http://192.168.0.101:4747/video",
            disabled=st.session_state.running,
        )
        st.session_state.ip_url = ip_url

    st.markdown("---")
    st.markdown("### ⚙️ Detection Settings")

    # Confidence threshold slider
    conf = st.slider(
        "Confidence Threshold",
        min_value=0.1,
        max_value=0.95,
        value=st.session_state.confidence,
        step=0.05,
        key="sidebar_confidence",
        help="Minimum detection confidence",
    )
    st.session_state.confidence = conf
    # Update detector confidence in real-time if it exists
    if st.session_state.detector is not None:
        st.session_state.detector.set_confidence(conf)

    # Detection toggle
    det_on = st.toggle(
        "Detection Overlay",
        value=st.session_state.detection_on,
        key="sidebar_det_toggle",
        help="Show/hide bounding boxes on the feed",
    )
    st.session_state.detection_on = det_on

    st.markdown("---")
    st.markdown("### 📐 Grid Settings")

    grid_r = st.number_input(
        "Grid Rows", min_value=1, max_value=10,
        value=st.session_state.grid_rows,
        key="sidebar_grid_rows",
        disabled=st.session_state.running,
    )
    grid_c = st.number_input(
        "Grid Columns", min_value=1, max_value=10,
        value=st.session_state.grid_cols,
        key="sidebar_grid_cols",
        disabled=st.session_state.running,
    )
    st.session_state.grid_rows = grid_r
    st.session_state.grid_cols = grid_c


# ═══════════════════════════════════════════════════════════════════════════
# MAIN AREA — Title + Status + Controls + Feed + Inventory
# ═══════════════════════════════════════════════════════════════════════════

# ── Title ─────────────────────────────────────────────────────────────────
st.markdown('<div class="main-title">🔍 AI Shelf Monitor</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">Real-time inventory tracking powered by YOLOv8</div>',
    unsafe_allow_html=True,
)

# ── Status Bar ────────────────────────────────────────────────────────────
status = st.session_state.last_status
dot_class = {"idle": "idle", "streaming": "live", "error": "error"}.get(status, "idle")
status_label = {"idle": "Idle", "streaming": "🟢 Live", "error": "❌ Error"}.get(status, "Idle")

source_label = (
    f"Camera {st.session_state.device_index}"
    if st.session_state.camera_type == "Device"
    else st.session_state.ip_url
)
fps_label = f"{st.session_state.fps:.1f} FPS" if st.session_state.running else "—"

st.markdown(f"""
<div class="status-bar">
    <span><span class="status-dot {dot_class}"></span> {status_label}</span>
    <span>📷 {source_label}</span>
    <span>⚡ {fps_label}</span>
    <span>🎯 Conf: {st.session_state.confidence:.0%}</span>
</div>
""", unsafe_allow_html=True)

# ── Start / Stop Buttons ─────────────────────────────────────────────────
col_start, col_stop, col_spacer = st.columns([1, 1, 4])

with col_start:
    st.button(
        "▶️ Start Monitoring",
        on_click=_on_start,
        disabled=st.session_state.running,
        use_container_width=True,
        key="btn_start",
    )

with col_stop:
    st.button(
        "⏹️ Stop Monitoring",
        on_click=_on_stop,
        disabled=not st.session_state.running,
        use_container_width=True,
        key="btn_stop",
    )

# ── Error display ────────────────────────────────────────────────────────
if st.session_state.error_msg:
    st.error(f"❌ {st.session_state.error_msg}")

# ── Live Feed + Inventory Panel ──────────────────────────────────────────
# Two columns: left = camera feed, right = inventory data
col_feed, col_data = st.columns([3, 2], gap="medium")

# Placeholders for in-place updates (prevents DOM growth / scrolling)
with col_feed:
    feed_placeholder = st.empty()

with col_data:
    data_placeholder = st.empty()


# ═══════════════════════════════════════════════════════════════════════════
# INVENTORY PANEL RENDERER
# ═══════════════════════════════════════════════════════════════════════════

def render_inventory_panel(container, shelf: ShelfCamera):
    """
    Render the inventory insights panel inside a Streamlit container.
    Uses shelf.get_state() for all data to avoid thread-safety issues.
    """
    state = shelf.get_state()

    with container.container():
        # ── Summary Metrics ──────────────────────────────────────
        st.markdown('<div class="section-header">📊 Dashboard</div>', unsafe_allow_html=True)

        m1, m2, m3 = st.columns(3)
        with m1:
            st.markdown(f"""
            <div class="metric-card">
                <div class="value">{state['total_stock']}</div>
                <div class="label">Total Items</div>
            </div>
            """, unsafe_allow_html=True)
        with m2:
            st.markdown(f"""
            <div class="metric-card">
                <div class="value">{state['num_classes']}</div>
                <div class="label">Product Types</div>
            </div>
            """, unsafe_allow_html=True)
        with m3:
            st.markdown(f"""
            <div class="metric-card">
                <div class="value">{state['snapshot_count']}</div>
                <div class="label">Snapshots</div>
            </div>
            """, unsafe_allow_html=True)

        # ── Current Stock ────────────────────────────────────────
        st.markdown('<div class="section-header">📦 Current Stock</div>', unsafe_allow_html=True)

        products = state.get("products", [])
        if products:
            for p in products:
                status_icon = {
                    "ok": "🟢", "low": "🟡", "urgent": "🔴", "high": "🔥"
                }.get(p["status"], "⚪")
                rate_str = f" · {p['rate']}/hr" if p["rate"] > 0 else ""
                st.markdown(
                    f"&nbsp;&nbsp;{status_icon} **{p['name']}** — "
                    f"`{p['stock']}` units{rate_str}",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No items detected yet. Start monitoring to see stock data.")

        # ── Recent Sales ─────────────────────────────────────────
        sales = state.get("latest_sales", {})
        if sales:
            st.markdown('<div class="section-header">🔄 Recent Sales</div>', unsafe_allow_html=True)
            for item, qty in sales.items():
                st.markdown(f"&nbsp;&nbsp;🛒 **{item}** — {qty} sold")

        # ── Alerts ───────────────────────────────────────────────
        alerts = state.get("alerts", [])
        if alerts:
            st.markdown('<div class="section-header">🔔 Alerts</div>', unsafe_allow_html=True)
            for a in alerts:
                sev = a.get("severity", "warning")
                css_class = "critical" if sev == "critical" else "warning"
                icon = "🚨" if sev == "critical" else "⚠️"
                st.markdown(f"""
                <div class="alert-card {css_class}">
                    {icon} <strong>{a['item']}</strong> — Stock: {a['stock']}
                    &nbsp;|&nbsp; Rate: {a['rate']}/hr
                    &nbsp;|&nbsp; Depletes: {a.get('time_to_empty', 'N/A')}
                    <br><em>{a['action']}</em>
                </div>
                """, unsafe_allow_html=True)

        # ── Recommendations ──────────────────────────────────────
        recs = state.get("recommendations", [])
        if recs:
            st.markdown('<div class="section-header">📋 Recommendations</div>', unsafe_allow_html=True)
            for r in recs:
                st.markdown(f"""
                <div class="rec-chip">
                    💡 <strong>{r['item']}</strong> — {r['reason']}
                    <br>{r['suggestion']}
                </div>
                """, unsafe_allow_html=True)

        # ── Frame Stats ──────────────────────────────────────────
        st.markdown("---")
        st.caption(
            f"Frames: {state['frame_count']} · "
            f"Snapshots: {state['snapshot_count']} · "
            f"Buffer: {state.get('buffer_fill', 0)} · "
            f"Grid: {state['rows']}×{state['cols']}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# MAIN MONITORING LOOP
# ═══════════════════════════════════════════════════════════════════════════
# This runs ONLY when st.session_state.running is True.
# The loop reads JPEG frames from the ShelfCamera's capture thread
# (which runs in a background thread) and displays them in-place
# using st.empty() — this prevents DOM growth and auto-scrolling.

if st.session_state.running and st.session_state.shelf_camera is not None:
    shelf = st.session_state.shelf_camera

    # Show initial "connecting" message
    if not shelf.running:
        feed_placeholder.info("📡 Connecting to camera...")
        time.sleep(1)
        if not shelf.running:
            st.session_state.running = False
            st.session_state.last_status = "error"
            st.session_state.error_msg = shelf.error_msg or "Camera connection lost"
            st.rerun()

    # FPS tracking
    fps_window = []
    refresh_counter = 0

    # Main frame loop — updates placeholders in-place
    while st.session_state.running and shelf.running:
        t0 = time.time()

        # Read the latest JPEG from the camera thread
        with shelf.lock:
            jpg_bytes = shelf.latest_jpg

        if jpg_bytes is not None:
            # Decode JPEG → numpy → RGB for Streamlit
            arr = np.frombuffer(jpg_bytes, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)

            if frame is not None:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                feed_placeholder.image(
                    frame_rgb,
                    caption="Live Shelf Feed",
                    use_container_width=True,
                )
        else:
            feed_placeholder.info("⏳ Waiting for camera frames...")

        # Update inventory panel every 10 frames (~0.5s) to reduce flicker
        refresh_counter += 1
        if refresh_counter % 10 == 0:
            render_inventory_panel(data_placeholder, shelf)

        # FPS calculation
        elapsed = time.time() - t0
        fps_window.append(elapsed)
        if len(fps_window) > 20:
            fps_window.pop(0)
        avg = sum(fps_window) / len(fps_window) if fps_window else 1
        st.session_state.fps = 1.0 / max(avg, 0.001)

        # Sleep to maintain smooth ~20 FPS display rate
        sleep_time = max(0.02, 0.05 - elapsed)
        time.sleep(sleep_time)

    # Camera stopped externally (e.g., disconnected)
    if st.session_state.running and not shelf.running:
        st.session_state.running = False
        st.session_state.last_status = "error"
        st.session_state.error_msg = shelf.error_msg or "Camera disconnected"
        st.rerun()

else:
    # ── Idle state — show placeholder ────────────────────────────────
    with col_feed:
        feed_placeholder.markdown("""
        <div style="
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 400px;
            background: rgba(20, 20, 40, 0.5);
            border: 2px dashed rgba(99, 102, 241, 0.3);
            border-radius: 16px;
            color: #64748b;
        ">
            <div style="font-size: 3rem; margin-bottom: 0.8rem;">📷</div>
            <div style="font-size: 1.1rem; font-weight: 600;">No Camera Active</div>
            <div style="font-size: 0.85rem; margin-top: 0.3rem;">
                Select a camera source and click <strong>Start Monitoring</strong>
            </div>
        </div>
        """, unsafe_allow_html=True)

    with col_data:
        data_placeholder.markdown("""
        <div style="
            padding: 2rem;
            text-align: center;
            color: #64748b;
        ">
            <div style="font-size: 2rem; margin-bottom: 0.5rem;">📊</div>
            <div style="font-size: 0.95rem;">
                Inventory data will appear here<br>once monitoring starts.
            </div>
        </div>
        """, unsafe_allow_html=True)
