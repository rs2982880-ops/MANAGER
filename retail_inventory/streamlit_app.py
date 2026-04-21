"""
AI Shelf Monitor — Streamlit Premium Edition
==============================================
A clean, stable, single-shelf monitoring interface with a premium
dark-mode UI inspired by modern fintech dashboards.

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
    page_title="ShelfAI — Intelligent Inventory",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ═══════════════════════════════════════════════════════════════════════════
# PREMIUM CSS — Cryptix-inspired ultra-dark theme
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
    /* ═══ Google Font Import ═══ */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

    /* ═══ Global Overrides ═══ */
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }
    .stApp {
        background: #08080d !important;
    }

    /* ═══ Hide Streamlit chrome ═══ */
    #MainMenu, footer, header {visibility: hidden !important;}
    .stDeployButton {display: none !important;}

    /* ═══ Top padding reduction ═══ */
    .block-container {
        padding-top: 1.2rem !important;
        padding-bottom: 0.5rem !important;
        max-width: 1400px !important;
    }

    /* ═══ Scrollbar ═══ */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: #08080d; }
    ::-webkit-scrollbar-thumb { background: #1a1a2e; border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: #10b981; }

    /* ═══ SIDEBAR — deep dark, borderless ═══ */
    section[data-testid="stSidebar"] {
        background: #0a0a12 !important;
        border-right: 1px solid rgba(16, 185, 129, 0.08) !important;
    }
    section[data-testid="stSidebar"] > div {
        padding-top: 1.5rem;
    }

    /* Sidebar labels */
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] .stMarkdown p {
        color: #8892a4 !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        letter-spacing: 0.02em;
    }
    section[data-testid="stSidebar"] .stMarkdown h3 {
        color: #e2e8f0 !important;
        font-size: 0.95rem !important;
        font-weight: 700 !important;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        margin-bottom: 0.8rem;
    }

    /* Sidebar selectbox / inputs — dark glass */
    section[data-testid="stSidebar"] .stSelectbox > div > div,
    section[data-testid="stSidebar"] .stTextInput > div > div > input,
    section[data-testid="stSidebar"] .stNumberInput > div > div > input {
        background: #0f0f1a !important;
        border: 1px solid rgba(255,255,255,0.06) !important;
        border-radius: 10px !important;
        color: #e2e8f0 !important;
        font-size: 0.85rem !important;
    }
    section[data-testid="stSidebar"] .stSelectbox > div > div:hover,
    section[data-testid="stSidebar"] .stTextInput > div > div > input:focus {
        border-color: rgba(16, 185, 129, 0.4) !important;
        box-shadow: 0 0 0 1px rgba(16, 185, 129, 0.15) !important;
    }

    /* Sidebar slider */
    section[data-testid="stSidebar"] .stSlider > div > div > div > div {
        background: #10b981 !important;
    }

    /* Sidebar toggle */
    section[data-testid="stSidebar"] .stCheckbox label span {
        color: #8892a4 !important;
    }

    /* Sidebar divider */
    section[data-testid="stSidebar"] hr {
        border-color: rgba(255,255,255,0.04) !important;
        margin: 1rem 0 !important;
    }

    /* ═══ MAIN CONTENT ═══ */

    /* ── Hero Title ── */
    .hero-title {
        font-size: 2.2rem;
        font-weight: 900;
        color: #ffffff;
        letter-spacing: -0.03em;
        line-height: 1.1;
        margin-bottom: 0.15rem;
    }
    .hero-title span.accent {
        background: linear-gradient(135deg, #10b981, #06d6a0, #34d399);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .hero-sub {
        font-size: 0.88rem;
        color: #5a6478;
        font-weight: 400;
        margin-bottom: 1.4rem;
        letter-spacing: 0.01em;
    }

    /* ── Status Pill Bar ── */
    .status-strip {
        display: flex;
        align-items: center;
        gap: 1.8rem;
        padding: 0.65rem 1.2rem;
        background: #0c0c14;
        border: 1px solid rgba(255,255,255,0.04);
        border-radius: 14px;
        margin-bottom: 1rem;
        font-size: 0.8rem;
        color: #5a6478;
        font-weight: 500;
    }
    .status-strip .pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }
    .status-strip .dot {
        width: 8px; height: 8px;
        border-radius: 50%;
        display: inline-block;
    }
    .dot-live   { background: #10b981; box-shadow: 0 0 8px rgba(16,185,129,0.6); }
    .dot-idle   { background: #2d3348; }
    .dot-error  { background: #ef4444; box-shadow: 0 0 8px rgba(239,68,68,0.5); }

    /* ── Buttons ── */
    .stButton > button {
        background: transparent !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
        border-radius: 10px !important;
        color: #8892a4 !important;
        font-weight: 600 !important;
        font-size: 0.82rem !important;
        padding: 0.55rem 1.2rem !important;
        transition: all 0.25s ease !important;
        letter-spacing: 0.02em;
    }
    .stButton > button:hover {
        border-color: rgba(16, 185, 129, 0.5) !important;
        color: #10b981 !important;
        background: rgba(16, 185, 129, 0.06) !important;
        box-shadow: 0 0 20px rgba(16, 185, 129, 0.08) !important;
    }
    /* Start button special — green filled */
    div[data-testid="column"]:first-child .stButton > button {
        background: linear-gradient(135deg, #10b981, #059669) !important;
        border: none !important;
        color: #ffffff !important;
        box-shadow: 0 4px 15px rgba(16, 185, 129, 0.25) !important;
    }
    div[data-testid="column"]:first-child .stButton > button:hover {
        box-shadow: 0 6px 25px rgba(16, 185, 129, 0.4) !important;
        transform: translateY(-1px);
    }
    div[data-testid="column"]:first-child .stButton > button:disabled {
        background: #1a1a2e !important;
        color: #3d4559 !important;
        box-shadow: none !important;
    }

    /* ── Glass Card ── */
    .glass-card {
        background: #0c0c14;
        border: 1px solid rgba(255,255,255,0.04);
        border-radius: 16px;
        padding: 1.4rem;
        margin-bottom: 0.8rem;
    }
    .glass-card:hover {
        border-color: rgba(16,185,129,0.12);
    }

    /* ── Section Headers ── */
    .sec-head {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-size: 0.78rem;
        font-weight: 700;
        color: #5a6478;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 0.9rem;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid rgba(255,255,255,0.03);
    }
    .sec-head .sec-icon {
        font-size: 0.9rem;
    }

    /* ── Metric Cards ── */
    .metric-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 0.7rem;
        margin-bottom: 1rem;
    }
    .metric-box {
        background: #0f0f1a;
        border: 1px solid rgba(255,255,255,0.04);
        border-radius: 14px;
        padding: 1rem 1rem;
        text-align: center;
        transition: border-color 0.3s, box-shadow 0.3s;
    }
    .metric-box:hover {
        border-color: rgba(16,185,129,0.2);
        box-shadow: 0 0 20px rgba(16,185,129,0.05);
    }
    .metric-box .m-val {
        font-size: 1.7rem;
        font-weight: 800;
        color: #e2e8f0;
        line-height: 1.2;
    }
    .metric-box .m-lbl {
        font-size: 0.68rem;
        color: #4a5568;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin-top: 0.3rem;
    }
    .metric-box.accent .m-val {
        color: #10b981;
    }

    /* ── Product Row ── */
    .prod-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0.6rem 0.8rem;
        border-radius: 10px;
        margin-bottom: 0.35rem;
        background: #0f0f1a;
        border: 1px solid rgba(255,255,255,0.03);
        transition: all 0.2s;
    }
    .prod-row:hover {
        border-color: rgba(16,185,129,0.15);
        background: #101020;
    }
    .prod-row .prod-name {
        font-size: 0.82rem;
        font-weight: 600;
        color: #c9d1d9;
    }
    .prod-row .prod-meta {
        display: flex;
        align-items: center;
        gap: 1rem;
    }
    .prod-row .prod-count {
        font-size: 0.85rem;
        font-weight: 700;
        color: #e2e8f0;
        min-width: 30px;
        text-align: right;
    }
    .prod-row .prod-rate {
        font-size: 0.7rem;
        color: #4a5568;
        font-weight: 500;
    }
    .prod-row .prod-badge {
        font-size: 0.6rem;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 6px;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    .badge-ok       { background: rgba(16,185,129,0.12); color: #10b981; }
    .badge-low      { background: rgba(245,158,11,0.12); color: #f59e0b; }
    .badge-urgent   { background: rgba(239,68,68,0.12);  color: #ef4444; }
    .badge-high     { background: rgba(99,102,241,0.12); color: #818cf8; }

    /* ── Alert Cards ── */
    .alert-row {
        display: flex;
        align-items: flex-start;
        gap: 0.7rem;
        padding: 0.75rem 1rem;
        border-radius: 12px;
        margin-bottom: 0.4rem;
        font-size: 0.8rem;
        line-height: 1.5;
    }
    .alert-row.crit {
        background: rgba(239,68,68,0.06);
        border: 1px solid rgba(239,68,68,0.12);
        color: #fca5a5;
    }
    .alert-row.warn {
        background: rgba(245,158,11,0.06);
        border: 1px solid rgba(245,158,11,0.12);
        color: #fcd34d;
    }
    .alert-row .alert-icon { font-size: 1rem; flex-shrink: 0; }
    .alert-row .alert-body { flex: 1; }
    .alert-row .alert-title {
        font-weight: 700;
        color: #e2e8f0;
        font-size: 0.82rem;
    }
    .alert-row .alert-detail {
        font-size: 0.72rem;
        opacity: 0.7;
        margin-top: 2px;
    }
    .alert-row .alert-action {
        font-size: 0.72rem;
        font-weight: 600;
        margin-top: 4px;
        color: inherit;
    }

    /* ── Recommendation Chips ── */
    .rec-row {
        padding: 0.65rem 1rem;
        border-radius: 10px;
        margin-bottom: 0.35rem;
        background: rgba(6,182,212,0.04);
        border: 1px solid rgba(6,182,212,0.08);
        font-size: 0.78rem;
        color: #67e8f9;
        line-height: 1.5;
    }
    .rec-row .rec-item {
        font-weight: 700;
        color: #a7f3d0;
    }
    .rec-row .rec-detail {
        color: #4a5568;
        font-size: 0.72rem;
    }

    /* ── Camera Placeholder ── */
    .cam-placeholder {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        height: 450px;
        background: #0c0c14;
        border: 1px dashed rgba(255,255,255,0.06);
        border-radius: 16px;
        color: #2d3348;
    }
    .cam-placeholder .cam-icon {
        font-size: 3rem;
        margin-bottom: 1rem;
        opacity: 0.5;
    }
    .cam-placeholder .cam-title {
        font-size: 1rem;
        font-weight: 700;
        color: #3d4559;
        margin-bottom: 0.3rem;
    }
    .cam-placeholder .cam-sub {
        font-size: 0.8rem;
        color: #2d3348;
    }
    .cam-placeholder .cam-sub strong {
        color: #10b981;
    }

    /* ── Data placeholder ── */
    .data-placeholder {
        padding: 3rem 2rem;
        text-align: center;
        color: #2d3348;
    }
    .data-placeholder .dp-icon { font-size: 2.5rem; margin-bottom: 0.6rem; opacity: 0.4; }
    .data-placeholder .dp-text { font-size: 0.85rem; color: #3d4559; line-height: 1.6; }

    /* ── Footer stats ── */
    .footer-stats {
        font-size: 0.68rem;
        color: #2d3348;
        text-align: center;
        padding: 0.6rem 0;
        border-top: 1px solid rgba(255,255,255,0.03);
        margin-top: 0.5rem;
        letter-spacing: 0.02em;
    }

    /* ── Feed image rounding ── */
    .stImage img {
        border-radius: 14px !important;
    }

    /* ── Sidebar brand ── */
    .sidebar-brand {
        display: flex;
        align-items: center;
        gap: 0.6rem;
        margin-bottom: 1.5rem;
        padding-bottom: 1rem;
        border-bottom: 1px solid rgba(255,255,255,0.04);
    }
    .sidebar-brand .sb-logo {
        width: 32px; height: 32px;
        background: linear-gradient(135deg, #10b981, #059669);
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1rem;
    }
    .sidebar-brand .sb-name {
        font-size: 1.05rem;
        font-weight: 800;
        color: #e2e8f0;
        letter-spacing: -0.02em;
    }
    .sidebar-brand .sb-tag {
        font-size: 0.6rem;
        color: #10b981;
        font-weight: 600;
        background: rgba(16,185,129,0.1);
        padding: 1px 6px;
        border-radius: 4px;
        margin-left: 4px;
    }

    /* ═══ Streamlit element overrides ═══ */
    .stAlert { border-radius: 12px !important; }
    div[data-testid="stMetricValue"] { color: #e2e8f0 !important; }
    .stCaption { color: #2d3348 !important; }

    /* Toggle styling */
    .st-emotion-cache-1p2iens { /* toggle track */
        background-color: #1a1a2e !important;
    }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# SESSION STATE INITIALISATION
# ═══════════════════════════════════════════════════════════════════════════

def _init_session_state():
    """Initialise all session_state keys exactly once."""
    defaults = {
        "running":        False,
        "camera_type":    "Device",
        "device_index":   0,
        "ip_url":         "http://192.168.0.101:4747/video",
        "confidence":     0.45,
        "detection_on":   True,
        "grid_rows":      3,
        "grid_cols":      5,
        "detector":       None,
        "shelf_camera":   None,
        "fps":            0.0,
        "frame_count":    0,
        "last_status":    "idle",
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
        with st.spinner("Loading YOLOv8 model..."):
            st.session_state.detector = ProductDetector(
                confidence=st.session_state.confidence
            )
    return st.session_state.detector


def get_camera_source():
    """Return the camera source based on user selection."""
    if st.session_state.camera_type == "Device":
        return st.session_state.device_index
    else:
        return st.session_state.ip_url.strip()


def build_shelf_camera(source) -> ShelfCamera:
    """Create a fresh ShelfCamera instance with current settings."""
    detector = get_detector()
    detector.set_confidence(st.session_state.confidence)
    return ShelfCamera(
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


# ═══════════════════════════════════════════════════════════════════════════
# START / STOP CALLBACKS
# ═══════════════════════════════════════════════════════════════════════════

def _on_start():
    """Called when Start Monitoring is pressed."""
    source = get_camera_source()
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
    """Called when Stop Monitoring is pressed."""
    shelf = st.session_state.shelf_camera
    if shelf is not None:
        shelf.stop_camera()
    st.session_state.running = False
    st.session_state.last_status = "idle"
    st.session_state.fps = 0.0


# ═══════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════

with st.sidebar:
    # Brand
    st.markdown("""
    <div class="sidebar-brand">
        <div class="sb-logo">🛒</div>
        <div>
            <span class="sb-name">ShelfAI</span>
            <span class="sb-tag">PRO</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 📷 Camera")

    cam_type = st.selectbox(
        "Camera Type",
        options=["Device", "IP Camera"],
        index=0 if st.session_state.camera_type == "Device" else 1,
        key="sidebar_cam_type",
        disabled=st.session_state.running,
    )
    st.session_state.camera_type = cam_type

    if cam_type == "Device":
        dev_idx = st.selectbox(
            "Device Index",
            options=[0, 1, 2],
            index=st.session_state.device_index,
            key="sidebar_dev_idx",
            help="0 = Laptop webcam · 1-2 = USB cameras",
            disabled=st.session_state.running,
        )
        st.session_state.device_index = dev_idx
    else:
        ip_url = st.text_input(
            "Stream URL",
            value=st.session_state.ip_url,
            key="sidebar_ip_url",
            help="e.g. http://192.168.0.101:4747/video",
            disabled=st.session_state.running,
        )
        st.session_state.ip_url = ip_url

    st.markdown("---")
    st.markdown("### 🎯 Detection")

    conf = st.slider(
        "Confidence",
        min_value=0.10,
        max_value=0.95,
        value=st.session_state.confidence,
        step=0.05,
        key="sidebar_confidence",
        help="Minimum detection confidence threshold",
    )
    st.session_state.confidence = conf
    if st.session_state.detector is not None:
        st.session_state.detector.set_confidence(conf)

    det_on = st.toggle(
        "Bounding Boxes",
        value=st.session_state.detection_on,
        key="sidebar_det_toggle",
        help="Show / hide detection overlay on feed",
    )
    st.session_state.detection_on = det_on

    st.markdown("---")
    st.markdown("### 📐 Grid")

    grid_r = st.number_input(
        "Rows", min_value=1, max_value=10,
        value=st.session_state.grid_rows,
        key="sidebar_grid_rows",
        disabled=st.session_state.running,
    )
    grid_c = st.number_input(
        "Columns", min_value=1, max_value=10,
        value=st.session_state.grid_cols,
        key="sidebar_grid_cols",
        disabled=st.session_state.running,
    )
    st.session_state.grid_rows = grid_r
    st.session_state.grid_cols = grid_c

    # Sidebar footer
    st.markdown("---")
    st.markdown(
        "<p style='text-align:center;font-size:0.65rem;color:#2d3348;'>"
        "ShelfAI v2.0 · YOLOv8 · GPU Accelerated</p>",
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════════════════════
# MAIN CONTENT — Hero + Status + Controls + Feed + Inventory
# ═══════════════════════════════════════════════════════════════════════════

# ── Hero Title ────────────────────────────────────────────────────────────
st.markdown(
    '<div class="hero-title">Intelligent <span class="accent">Shelf Monitor</span></div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="hero-sub">Real-time inventory tracking powered by YOLOv8 · '
    'Instant detection, optimized insights, and premium analytics.</div>',
    unsafe_allow_html=True,
)

# ── Status Strip ──────────────────────────────────────────────────────────
status = st.session_state.last_status
dot_cls = {"idle": "dot-idle", "streaming": "dot-live", "error": "dot-error"}.get(status, "dot-idle")
status_txt = {"idle": "Idle", "streaming": "Streaming", "error": "Error"}.get(status, "Idle")

src_label = (
    f"Camera {st.session_state.device_index}"
    if st.session_state.camera_type == "Device"
    else st.session_state.ip_url[:35]
)
fps_txt = f"{st.session_state.fps:.1f}" if st.session_state.running else "—"

st.markdown(f"""
<div class="status-strip">
    <div class="pill"><span class="dot {dot_cls}"></span> {status_txt}</div>
    <div class="pill">📷 {src_label}</div>
    <div class="pill">⚡ {fps_txt} FPS</div>
    <div class="pill">🎯 {st.session_state.confidence:.0%}</div>
    <div class="pill">📐 {st.session_state.grid_rows}×{st.session_state.grid_cols}</div>
</div>
""", unsafe_allow_html=True)

# ── Start / Stop Buttons ─────────────────────────────────────────────────
col_s, col_x, col_sp = st.columns([1, 1, 5])
with col_s:
    st.button(
        "▶  Start Monitoring",
        on_click=_on_start,
        disabled=st.session_state.running,
        use_container_width=True,
        key="btn_start",
    )
with col_x:
    st.button(
        "■  Stop",
        on_click=_on_stop,
        disabled=not st.session_state.running,
        use_container_width=True,
        key="btn_stop",
    )

# ── Error Banner ─────────────────────────────────────────────────────────
if st.session_state.error_msg:
    st.error(f"❌  {st.session_state.error_msg}")

# ── Two-Column Layout: Feed | Data ──────────────────────────────────────
col_feed, col_data = st.columns([3, 2], gap="medium")

with col_feed:
    feed_placeholder = st.empty()
with col_data:
    data_placeholder = st.empty()


# ═══════════════════════════════════════════════════════════════════════════
# INVENTORY PANEL RENDERER
# ═══════════════════════════════════════════════════════════════════════════

def render_inventory_panel(container, shelf: ShelfCamera):
    """Render the premium inventory panel inside a container."""
    state = shelf.get_state()

    with container.container():
        # ── Metrics Grid ─────────────────────────────────────────
        st.markdown("""
        <div class="sec-head">
            <span class="sec-icon">📊</span> Dashboard Overview
        </div>
        """, unsafe_allow_html=True)

        total = state["total_stock"]
        classes = state["num_classes"]
        snaps = state["snapshot_count"]
        low = state.get("low_count", 0)

        st.markdown(f"""
        <div class="metric-grid">
            <div class="metric-box accent">
                <div class="m-val">{total}</div>
                <div class="m-lbl">Total Items</div>
            </div>
            <div class="metric-box">
                <div class="m-val">{classes}</div>
                <div class="m-lbl">Product Types</div>
            </div>
            <div class="metric-box">
                <div class="m-val">{snaps}</div>
                <div class="m-lbl">Snapshots</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── Current Stock ────────────────────────────────────────
        products = state.get("products", [])
        if products:
            st.markdown("""
            <div class="sec-head">
                <span class="sec-icon">📦</span> Current Stock
            </div>
            """, unsafe_allow_html=True)

            html_rows = ""
            for p in products:
                badge_cls = {
                    "ok": "badge-ok", "low": "badge-low",
                    "urgent": "badge-urgent", "high": "badge-high",
                }.get(p["status"], "badge-ok")
                badge_txt = p["status"].upper()
                rate_str = f"{p['rate']}/hr" if p["rate"] > 0 else "—"

                html_rows += f"""
                <div class="prod-row">
                    <span class="prod-name">{p['name']}</span>
                    <div class="prod-meta">
                        <span class="prod-rate">{rate_str}</span>
                        <span class="prod-count">{p['stock']}</span>
                        <span class="prod-badge {badge_cls}">{badge_txt}</span>
                    </div>
                </div>
                """
            st.markdown(html_rows, unsafe_allow_html=True)

        # ── Recent Sales ─────────────────────────────────────────
        sales = state.get("latest_sales", {})
        if sales:
            st.markdown("""
            <div class="sec-head" style="margin-top:1rem;">
                <span class="sec-icon">🔄</span> Recent Sales
            </div>
            """, unsafe_allow_html=True)

            sales_html = ""
            for item, qty in sales.items():
                sales_html += f"""
                <div class="prod-row">
                    <span class="prod-name">🛒 {item}</span>
                    <span class="prod-count" style="color:#f59e0b;">-{qty}</span>
                </div>
                """
            st.markdown(sales_html, unsafe_allow_html=True)

        # ── Alerts ───────────────────────────────────────────────
        alerts = state.get("alerts", [])
        if alerts:
            st.markdown("""
            <div class="sec-head" style="margin-top:1rem;">
                <span class="sec-icon">🔔</span> Alerts
            </div>
            """, unsafe_allow_html=True)

            alerts_html = ""
            for a in alerts:
                sev = a.get("severity", "warning")
                cls = "crit" if sev == "critical" else "warn"
                icon = "🚨" if sev == "critical" else "⚠️"
                alerts_html += f"""
                <div class="alert-row {cls}">
                    <span class="alert-icon">{icon}</span>
                    <div class="alert-body">
                        <div class="alert-title">{a['item']}</div>
                        <div class="alert-detail">
                            Stock: {a['stock']} · Rate: {a['rate']}/hr · Depletes: {a.get('time_to_empty', 'N/A')}
                        </div>
                        <div class="alert-action">→ {a['action']}</div>
                    </div>
                </div>
                """
            st.markdown(alerts_html, unsafe_allow_html=True)

        # ── Recommendations ──────────────────────────────────────
        recs = state.get("recommendations", [])
        if recs:
            st.markdown("""
            <div class="sec-head" style="margin-top:1rem;">
                <span class="sec-icon">💡</span> Recommendations
            </div>
            """, unsafe_allow_html=True)

            recs_html = ""
            for r in recs:
                recs_html += f"""
                <div class="rec-row">
                    <span class="rec-item">{r['item']}</span> — {r['reason']}
                    <br><span class="rec-detail">{r['suggestion']}</span>
                </div>
                """
            st.markdown(recs_html, unsafe_allow_html=True)

        # ── Footer Stats ─────────────────────────────────────────
        st.markdown(f"""
        <div class="footer-stats">
            Frames: {state['frame_count']} · Snapshots: {state['snapshot_count']}
            · Buffer: {state.get('buffer_fill', 0)} · Grid: {state['rows']}×{state['cols']}
        </div>
        """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN MONITORING LOOP
# ═══════════════════════════════════════════════════════════════════════════

if st.session_state.running and st.session_state.shelf_camera is not None:
    shelf = st.session_state.shelf_camera

    # Handle connection loss
    if not shelf.running:
        feed_placeholder.info("📡 Connecting to camera...")
        time.sleep(1)
        if not shelf.running:
            st.session_state.running = False
            st.session_state.last_status = "error"
            st.session_state.error_msg = shelf.error_msg or "Camera connection lost"
            st.rerun()

    fps_window = []
    refresh_counter = 0

    while st.session_state.running and shelf.running:
        t0 = time.time()

        with shelf.lock:
            jpg_bytes = shelf.latest_jpg

        if jpg_bytes is not None:
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
            feed_placeholder.markdown("""
            <div class="cam-placeholder" style="height:300px;">
                <div class="cam-icon">📡</div>
                <div class="cam-title">Waiting for frames...</div>
            </div>
            """, unsafe_allow_html=True)

        # Update data panel every ~0.5s
        refresh_counter += 1
        if refresh_counter % 10 == 0:
            render_inventory_panel(data_placeholder, shelf)

        # FPS
        elapsed = time.time() - t0
        fps_window.append(elapsed)
        if len(fps_window) > 20:
            fps_window.pop(0)
        avg = sum(fps_window) / len(fps_window) if fps_window else 1
        st.session_state.fps = 1.0 / max(avg, 0.001)

        sleep_time = max(0.02, 0.05 - elapsed)
        time.sleep(sleep_time)

    # External camera stop
    if st.session_state.running and not shelf.running:
        st.session_state.running = False
        st.session_state.last_status = "error"
        st.session_state.error_msg = shelf.error_msg or "Camera disconnected"
        st.rerun()

else:
    # ── Idle state placeholders ──────────────────────────────────────
    with col_feed:
        feed_placeholder.markdown("""
        <div class="cam-placeholder">
            <div class="cam-icon">📷</div>
            <div class="cam-title">No Camera Active</div>
            <div class="cam-sub">Select a source and click <strong>Start Monitoring</strong></div>
        </div>
        """, unsafe_allow_html=True)

    with col_data:
        data_placeholder.markdown("""
        <div class="data-placeholder">
            <div class="dp-icon">📊</div>
            <div class="dp-text">
                Inventory insights will appear here<br>once monitoring begins.
            </div>
        </div>
        """, unsafe_allow_html=True)
