"""
AI Shelf Monitor — Premium Dashboard Edition
===============================================
A production-grade, dark-themed SaaS dashboard for real-time shelf
inventory monitoring powered by YOLOv8.

Run:
    streamlit run streamlit_app.py

Architecture:
    streamlit_app.py  → UI layer (this file)
    detector.py       → YOLO detection pipeline
    grid_mapper.py    → Shelf grid mapping system
    tracker.py        → Snapshot-based stock tracking
    camera_manager.py → Threaded camera capture
    logic.py          → Restocking alerts & recommendations
    storage.py        → JSON persistence across reloads
    database.py       → SQLite long-term storage
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import time
from datetime import datetime
from typing import Dict, Optional

import cv2
import numpy as np
import streamlit as st

from camera_manager import ShelfCamera
from detector import ProductDetector
from storage import ShelfStorage
from utils import format_time_remaining


# ═══════════════════════════════════════════════════════════════════════════
# PAGE CONFIG
# ═══════════════════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="ShelfAI — Intelligent Inventory",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══════════════════════════════════════════════════════════════════════════
# PERSISTENT STORAGE SINGLETON
# ═══════════════════════════════════════════════════════════════════════════
_storage = ShelfStorage()


# ═══════════════════════════════════════════════════════════════════════════
# PREMIUM CSS — Ultra-dark SaaS dashboard theme
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

/* ═══ Reset ═══ */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}
.stApp {
    background: #06060b !important;
}
#MainMenu, footer, header { visibility: hidden !important; }
.stDeployButton { display: none !important; }

.block-container {
    padding-top: 1rem !important;
    padding-bottom: 0 !important;
    max-width: 1500px !important;
}

/* Scrollbar */
::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #1a1a2e; border-radius: 3px; }

/* ═══ SIDEBAR ═══ */
section[data-testid="stSidebar"] {
    background: #08081090 !important;
    border-right: 1px solid rgba(16,185,129,0.06) !important;
    backdrop-filter: blur(20px);
}
section[data-testid="stSidebar"] label {
    color: #6b7280 !important;
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}
section[data-testid="stSidebar"] .stMarkdown h3 {
    color: #d1d5db !important;
    font-size: 0.85rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    margin-bottom: 0.6rem;
    margin-top: 0.2rem;
}
section[data-testid="stSidebar"] .stSelectbox > div > div,
section[data-testid="stSidebar"] .stTextInput > div > div > input,
section[data-testid="stSidebar"] .stNumberInput > div > div > input {
    background: rgba(255,255,255,0.03) !important;
    border: 1px solid rgba(255,255,255,0.06) !important;
    border-radius: 10px !important;
    color: #e5e7eb !important;
    font-size: 0.82rem !important;
}
section[data-testid="stSidebar"] .stSelectbox > div > div:hover,
section[data-testid="stSidebar"] .stTextInput > div > div > input:focus {
    border-color: rgba(16,185,129,0.35) !important;
    box-shadow: 0 0 0 2px rgba(16,185,129,0.08) !important;
}
section[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.04) !important;
    margin: 0.8rem 0 !important;
}

/* ═══ HEADER ═══ */
.dash-header {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    margin-bottom: 1rem;
    padding-bottom: 0.8rem;
    border-bottom: 1px solid rgba(255,255,255,0.04);
}
.dash-title {
    font-size: 1.8rem;
    font-weight: 900;
    color: #f9fafb;
    letter-spacing: -0.03em;
    line-height: 1;
}
.dash-title .accent { color: #10b981; }
.dash-sub {
    font-size: 0.78rem;
    color: #4b5563;
    margin-top: 4px;
    font-weight: 400;
}

/* ═══ STATUS STRIP ═══ */
.status-strip {
    display: flex;
    align-items: center;
    gap: 2rem;
    padding: 0.55rem 1.2rem;
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.04);
    border-radius: 12px;
    margin-bottom: 0.8rem;
    font-size: 0.72rem;
    color: #6b7280;
    font-weight: 500;
    letter-spacing: 0.02em;
}
.pill { display: inline-flex; align-items: center; gap: 5px; }
.dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.dot-live  { background: #10b981; box-shadow: 0 0 10px rgba(16,185,129,0.7); animation: pulse-dot 2s infinite; }
.dot-idle  { background: #374151; }
.dot-error { background: #ef4444; box-shadow: 0 0 8px rgba(239,68,68,0.5); }
@keyframes pulse-dot {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}

/* ═══ BUTTONS ═══ */
.stButton > button {
    background: rgba(255,255,255,0.03) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 10px !important;
    color: #9ca3af !important;
    font-weight: 600 !important;
    font-size: 0.78rem !important;
    padding: 0.5rem 1rem !important;
    transition: all 0.3s cubic-bezier(0.4,0,0.2,1) !important;
    letter-spacing: 0.02em;
}
.stButton > button:hover {
    border-color: rgba(16,185,129,0.4) !important;
    color: #10b981 !important;
    background: rgba(16,185,129,0.05) !important;
    box-shadow: 0 0 25px rgba(16,185,129,0.08) !important;
}
/* Green CTA button — first column */
div[data-testid="column"]:first-child .stButton > button {
    background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important;
    border: none !important;
    color: #ffffff !important;
    font-weight: 700 !important;
    box-shadow: 0 4px 20px rgba(16,185,129,0.3), inset 0 1px 0 rgba(255,255,255,0.1) !important;
}
div[data-testid="column"]:first-child .stButton > button:hover {
    box-shadow: 0 8px 35px rgba(16,185,129,0.45), inset 0 1px 0 rgba(255,255,255,0.15) !important;
    transform: translateY(-1px);
}
div[data-testid="column"]:first-child .stButton > button:disabled {
    background: rgba(255,255,255,0.04) !important;
    color: #374151 !important;
    box-shadow: none !important;
}

/* ═══ GLASS PANEL ═══ */
.glass-panel {
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.04);
    border-radius: 16px;
    padding: 1.2rem 1.4rem;
    margin-bottom: 0.6rem;
    backdrop-filter: blur(10px);
}
.glass-panel:hover {
    border-color: rgba(16,185,129,0.1);
}

/* ═══ SECTION HEADERS ═══ */
.sec-hd {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.7rem;
    font-weight: 700;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 0.8rem;
}

/* ═══ METRIC CARDS ═══ */
.kpi-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.6rem;
    margin-bottom: 0.8rem;
}
.kpi-card {
    background: rgba(255,255,255,0.02);
    border: 1px solid rgba(255,255,255,0.04);
    border-radius: 14px;
    padding: 1rem;
    text-align: center;
    transition: all 0.3s;
    position: relative;
    overflow: hidden;
}
.kpi-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, #10b981, transparent);
    opacity: 0;
    transition: opacity 0.3s;
}
.kpi-card:hover::before { opacity: 1; }
.kpi-card:hover {
    border-color: rgba(16,185,129,0.15);
    box-shadow: 0 0 30px rgba(16,185,129,0.04);
}
.kpi-val {
    font-size: 1.5rem;
    font-weight: 800;
    color: #f3f4f6;
    line-height: 1.2;
}
.kpi-val.green { color: #10b981; }
.kpi-val.amber { color: #f59e0b; }
.kpi-val.red   { color: #ef4444; }
.kpi-lbl {
    font-size: 0.62rem;
    color: #4b5563;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-top: 4px;
}

/* ═══ PRODUCT TABLE ═══ */
.ptable { width: 100%; }
.ptable .prow {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.55rem 0.9rem;
    border-radius: 10px;
    margin-bottom: 4px;
    background: rgba(255,255,255,0.015);
    border: 1px solid rgba(255,255,255,0.03);
    transition: all 0.2s;
    font-size: 0.8rem;
}
.ptable .prow:hover {
    border-color: rgba(16,185,129,0.12);
    background: rgba(16,185,129,0.03);
}
.prow .pname {
    font-weight: 600;
    color: #d1d5db;
    flex: 1;
}
.prow .pmeta {
    display: flex;
    align-items: center;
    gap: 0.8rem;
}
.prow .pcount {
    font-weight: 800;
    color: #f3f4f6;
    min-width: 28px;
    text-align: right;
    font-size: 0.85rem;
}
.prow .prate {
    font-size: 0.68rem;
    color: #4b5563;
    min-width: 50px;
    text-align: right;
}
.badge {
    font-size: 0.55rem;
    font-weight: 700;
    padding: 2px 7px;
    border-radius: 5px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.badge-ok     { background: rgba(16,185,129,0.1);  color: #34d399; }
.badge-low    { background: rgba(245,158,11,0.1);  color: #fbbf24; }
.badge-urgent { background: rgba(239,68,68,0.1);   color: #f87171; }
.badge-high   { background: rgba(99,102,241,0.1);  color: #a5b4fc; }

/* ═══ SALES ROW ═══ */
.sale-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.45rem 0.8rem;
    border-radius: 8px;
    margin-bottom: 3px;
    background: rgba(245,158,11,0.04);
    border: 1px solid rgba(245,158,11,0.08);
    font-size: 0.78rem;
    color: #fbbf24;
}
.sale-row .sale-qty {
    font-weight: 800;
    color: #f59e0b;
}

/* ═══ ALERT CARD ═══ */
.acard {
    padding: 0.7rem 0.9rem;
    border-radius: 12px;
    margin-bottom: 5px;
    font-size: 0.76rem;
    line-height: 1.5;
    display: flex;
    gap: 0.6rem;
}
.acard.crit {
    background: rgba(239,68,68,0.05);
    border: 1px solid rgba(239,68,68,0.1);
    color: #fca5a5;
}
.acard.warn {
    background: rgba(245,158,11,0.05);
    border: 1px solid rgba(245,158,11,0.1);
    color: #fde68a;
}
.acard .aicon { font-size: 0.95rem; flex-shrink: 0; margin-top: 1px; }
.acard .abody { flex: 1; }
.acard .atitle { font-weight: 700; color: #e5e7eb; }
.acard .adetail { font-size: 0.68rem; opacity: 0.65; margin-top: 2px; }
.acard .aaction {
    font-size: 0.68rem;
    font-weight: 700;
    margin-top: 3px;
    color: inherit;
}

/* ═══ RECOMMENDATION ═══ */
.rcard {
    padding: 0.55rem 0.9rem;
    border-radius: 10px;
    margin-bottom: 4px;
    background: rgba(6,182,212,0.03);
    border: 1px solid rgba(6,182,212,0.08);
    font-size: 0.75rem;
    color: #67e8f9;
    line-height: 1.5;
}
.rcard .ritem { font-weight: 700; color: #a7f3d0; }
.rcard .rsub { font-size: 0.68rem; color: #4b5563; }

/* ═══ PLACEHOLDER ═══ */
.cam-ph {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 420px;
    background: rgba(255,255,255,0.015);
    border: 1px dashed rgba(255,255,255,0.06);
    border-radius: 16px;
    color: #374151;
}
.cam-ph .ph-icon { font-size: 2.8rem; margin-bottom: 0.8rem; opacity: 0.4; }
.cam-ph .ph-title { font-size: 0.95rem; font-weight: 700; color: #4b5563; }
.cam-ph .ph-sub {
    font-size: 0.78rem; color: #374151; margin-top: 4px;
}
.cam-ph .ph-sub strong { color: #10b981; }

.data-ph {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    min-height: 300px; color: #374151; text-align: center;
}
.data-ph .dph-icon { font-size: 2.2rem; margin-bottom: 0.5rem; opacity: 0.3; }
.data-ph .dph-text { font-size: 0.82rem; color: #4b5563; line-height: 1.6; }

/* ═══ FEED IMAGE ═══ */
.stImage img { border-radius: 14px !important; }

/* ═══ SIDEBAR BRAND ═══ */
.sb-brand {
    display: flex; align-items: center; gap: 0.6rem;
    margin-bottom: 1.2rem; padding-bottom: 1rem;
    border-bottom: 1px solid rgba(255,255,255,0.04);
}
.sb-logo {
    width: 34px; height: 34px;
    background: linear-gradient(135deg, #10b981, #059669);
    border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.1rem;
    box-shadow: 0 4px 15px rgba(16,185,129,0.25);
}
.sb-name {
    font-size: 1rem; font-weight: 800; color: #f3f4f6;
    letter-spacing: -0.01em;
}
.sb-tag {
    font-size: 0.55rem; font-weight: 700; color: #10b981;
    background: rgba(16,185,129,0.1); padding: 1px 5px;
    border-radius: 4px; margin-left: 3px; letter-spacing: 0.04em;
}

/* ═══ FOOTER ═══ */
.foot-stats {
    font-size: 0.62rem; color: #1f2937; text-align: center;
    padding: 0.5rem 0; border-top: 1px solid rgba(255,255,255,0.03);
    margin-top: 0.4rem; letter-spacing: 0.02em;
}

/* ═══ RESTORED DATA BANNER ═══ */
.restore-banner {
    padding: 0.5rem 1rem;
    border-radius: 10px;
    background: rgba(16,185,129,0.06);
    border: 1px solid rgba(16,185,129,0.12);
    color: #34d399;
    font-size: 0.75rem;
    font-weight: 500;
    margin-bottom: 0.8rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

/* ═══ Streamlit overrides ═══ */
.stAlert { border-radius: 12px !important; }
.stCaption { color: #1f2937 !important; }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# SESSION STATE — initialise + restore from persistent storage
# ═══════════════════════════════════════════════════════════════════════════

def _init_session():
    """All mutable state lives here. Restored from JSON on first load."""
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
        "last_status":    "idle",
        "error_msg":      "",
        "restored":       False,
        # Persisted snapshot (survives reload)
        "saved_stock":    {},
        "saved_sales":    [],
        "saved_alerts":   [],
        "saved_grid":     None,
        "saved_frames":   0,
        "saved_snaps":    0,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # ── Restore from persistent file (once) ──
    if not st.session_state.restored:
        cam_cfg = _storage.load_camera_config()
        if cam_cfg:
            st.session_state.camera_type  = cam_cfg.get("camera_type", "Device")
            st.session_state.device_index = cam_cfg.get("device_index", 0)
            st.session_state.ip_url       = cam_cfg.get("ip_url", st.session_state.ip_url)
            st.session_state.confidence   = cam_cfg.get("confidence", 0.45)
            st.session_state.grid_rows    = cam_cfg.get("grid_rows", 3)
            st.session_state.grid_cols    = cam_cfg.get("grid_cols", 5)

        shelf_data = _storage.load_shelf_state()
        if shelf_data:
            st.session_state.saved_stock  = shelf_data.get("stock_counts", {})
            st.session_state.saved_sales  = shelf_data.get("sales_history", [])
            st.session_state.saved_alerts = shelf_data.get("alerts", [])
            st.session_state.saved_grid   = shelf_data.get("grid_state")
            st.session_state.saved_frames = shelf_data.get("frame_count", 0)
            st.session_state.saved_snaps  = shelf_data.get("snapshot_count", 0)

        st.session_state.restored = True

_init_session()


# ═══════════════════════════════════════════════════════════════════════════
# BACKEND HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def get_detector() -> ProductDetector:
    if st.session_state.detector is None:
        with st.spinner("Loading YOLOv8 model..."):
            st.session_state.detector = ProductDetector(
                confidence=st.session_state.confidence
            )
    return st.session_state.detector


def get_camera_source():
    if st.session_state.camera_type == "Device":
        return st.session_state.device_index
    return st.session_state.ip_url.strip()


def build_shelf(source) -> ShelfCamera:
    det = get_detector()
    det.set_confidence(st.session_state.confidence)
    return ShelfCamera(
        name="Main Shelf", source=source, detector=det,
        region=(50, 30, 590, 440),
        rows=st.session_state.grid_rows,
        cols=st.session_state.grid_cols,
        snap_interval=30.0, buffer_size=5, stock_threshold=5,
    )


def _persist_config():
    """Save camera settings to JSON so they survive reload."""
    _storage.save_camera_config(
        camera_type=st.session_state.camera_type,
        device_index=st.session_state.device_index,
        ip_url=st.session_state.ip_url,
        confidence=st.session_state.confidence,
        grid_rows=st.session_state.grid_rows,
        grid_cols=st.session_state.grid_cols,
    )


def _persist_shelf(state: dict):
    """Save current shelf state for reload survival."""
    sales_entries = []
    for item, qty in state.get("latest_sales", {}).items():
        sales_entries.append({
            "item": item, "qty": qty,
            "time": datetime.now().isoformat(),
        })
    _storage.save_shelf_state(
        stock_counts=dict(
            (p["name"], p["stock"]) for p in state.get("products", [])
        ),
        grid_state=None,  # Grid is large, skip for speed
        sales_history=sales_entries,
        alerts=state.get("alerts", []),
        frame_count=state.get("frame_count", 0),
        snapshot_count=state.get("snapshot_count", 0),
    )


# ═══════════════════════════════════════════════════════════════════════════
# CALLBACKS
# ═══════════════════════════════════════════════════════════════════════════

def _on_start():
    source = get_camera_source()
    shelf = build_shelf(source)
    st.session_state.shelf_camera = shelf
    _persist_config()

    ok = shelf.start_camera()
    if ok:
        st.session_state.running = True
        st.session_state.last_status = "streaming"
        st.session_state.error_msg = ""
    else:
        st.session_state.running = False
        st.session_state.last_status = "error"
        st.session_state.error_msg = shelf.error_msg or "Camera failed to open"


def _on_stop():
    shelf = st.session_state.shelf_camera
    if shelf is not None:
        # Persist final state before stopping
        try:
            _persist_shelf(shelf.get_state())
        except Exception:
            pass
        shelf.stop_camera()
    st.session_state.running = False
    st.session_state.last_status = "idle"
    st.session_state.fps = 0.0


# ═══════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("""
    <div class="sb-brand">
        <div class="sb-logo">🛒</div>
        <div><span class="sb-name">ShelfAI</span><span class="sb-tag">PRO</span></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("### 📷 Camera")

    cam_type = st.selectbox(
        "Source Type", ["Device", "IP Camera"],
        index=0 if st.session_state.camera_type == "Device" else 1,
        key="sb_cam", disabled=st.session_state.running,
    )
    st.session_state.camera_type = cam_type

    if cam_type == "Device":
        idx = st.selectbox(
            "Device Index", [0, 1, 2],
            index=st.session_state.device_index,
            key="sb_idx", disabled=st.session_state.running,
            help="0 = laptop · 1–2 = USB",
        )
        st.session_state.device_index = idx
    else:
        url = st.text_input(
            "Stream URL", st.session_state.ip_url,
            key="sb_url", disabled=st.session_state.running,
            help="e.g. http://192.168.0.101:4747/video",
        )
        st.session_state.ip_url = url

    st.markdown("---")
    st.markdown("### 🎯 Detection")

    conf = st.slider(
        "Confidence", 0.10, 0.95, st.session_state.confidence, 0.05,
        key="sb_conf", help="YOLO confidence threshold",
    )
    st.session_state.confidence = conf
    if st.session_state.detector:
        st.session_state.detector.set_confidence(conf)

    det_on = st.toggle(
        "Overlay Boxes", st.session_state.detection_on,
        key="sb_det", help="Show bounding boxes",
    )
    st.session_state.detection_on = det_on

    st.markdown("---")
    st.markdown("### 📐 Grid")

    gr = st.number_input("Rows", 1, 10, st.session_state.grid_rows, key="sb_gr", disabled=st.session_state.running)
    gc = st.number_input("Cols", 1, 10, st.session_state.grid_cols, key="sb_gc", disabled=st.session_state.running)
    st.session_state.grid_rows = gr
    st.session_state.grid_cols = gc

    st.markdown("---")
    st.caption("ShelfAI v2.0 · YOLOv8 · GPU Accelerated")


# ═══════════════════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════════════════

st.markdown("""
<div class="dash-header">
    <div>
        <div class="dash-title">Intelligent <span class="accent">Shelf Monitor</span></div>
        <div class="dash-sub">Real-time inventory and restocking intelligence powered by YOLOv8</div>
    </div>
</div>
""", unsafe_allow_html=True)

# ── Status Strip ──
status = st.session_state.last_status
dot = {"idle": "dot-idle", "streaming": "dot-live", "error": "dot-error"}.get(status, "dot-idle")
stxt = {"idle": "Idle", "streaming": "Streaming", "error": "Error"}.get(status, "Idle")
src = f"Camera {st.session_state.device_index}" if st.session_state.camera_type == "Device" else st.session_state.ip_url[:30]
fps = f"{st.session_state.fps:.1f}" if st.session_state.running else "—"

st.markdown(f"""
<div class="status-strip">
    <div class="pill"><span class="dot {dot}"></span> {stxt}</div>
    <div class="pill">📷 {src}</div>
    <div class="pill">⚡ {fps} FPS</div>
    <div class="pill">🎯 {st.session_state.confidence:.0%}</div>
    <div class="pill">📐 {st.session_state.grid_rows}×{st.session_state.grid_cols}</div>
</div>
""", unsafe_allow_html=True)

# ── Buttons ──
c1, c2, c3 = st.columns([1, 1, 5])
with c1:
    st.button("▶  Start Monitoring", on_click=_on_start,
              disabled=st.session_state.running, use_container_width=True, key="btn_go")
with c2:
    st.button("■  Stop", on_click=_on_stop,
              disabled=not st.session_state.running, use_container_width=True, key="btn_stop")

if st.session_state.error_msg:
    st.error(f"❌  {st.session_state.error_msg}")

# ── Restored data banner ──
has_saved = bool(st.session_state.saved_stock)
if has_saved and not st.session_state.running:
    st.markdown("""
    <div class="restore-banner">
        ✅ Previous session data restored — start monitoring to continue tracking.
    </div>
    """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN LAYOUT — Feed (left) + Analytics (right)
# ═══════════════════════════════════════════════════════════════════════════

col_feed, col_data = st.columns([3, 2], gap="medium")

with col_feed:
    feed_ph = st.empty()
with col_data:
    data_ph = st.empty()


# ═══════════════════════════════════════════════════════════════════════════
# ANALYTICS PANEL RENDERER
# ═══════════════════════════════════════════════════════════════════════════

def render_analytics(container, state: dict):
    """Render the full analytics panel from a state dict."""
    with container.container():
        total    = state.get("total_stock", 0)
        classes  = state.get("num_classes", 0)
        snaps    = state.get("snapshot_count", 0)
        low      = state.get("low_count", 0)
        products = state.get("products", [])
        sales    = state.get("latest_sales", {})
        alerts   = state.get("alerts", [])
        recs     = state.get("recommendations", [])
        frames   = state.get("frame_count", 0)
        buf      = state.get("buffer_fill", 0)
        rows     = state.get("rows", 3)
        cols     = state.get("cols", 5)

        # ── KPI Cards ──
        low_cls = "amber" if low > 0 else ""
        st.markdown(f"""
        <div class="kpi-row">
            <div class="kpi-card">
                <div class="kpi-val green">{total}</div>
                <div class="kpi-lbl">Total Items</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-val">{classes}</div>
                <div class="kpi-lbl">Products</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-val {low_cls}">{low}</div>
                <div class="kpi-lbl">Low Stock</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-val">{snaps}</div>
                <div class="kpi-lbl">Snapshots</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── Stock Table ──
        if products:
            st.markdown('<div class="sec-hd">📦 Current Stock</div>', unsafe_allow_html=True)
            rows_html = ""
            for p in products:
                bcls = {"ok":"badge-ok","low":"badge-low","urgent":"badge-urgent","high":"badge-high"}.get(p["status"],"badge-ok")
                rate = f"{p['rate']}/hr" if p["rate"] > 0 else "—"
                rows_html += f"""<div class="prow">
                    <span class="pname">{p['name']}</span>
                    <div class="pmeta">
                        <span class="prate">{rate}</span>
                        <span class="pcount">{p['stock']}</span>
                        <span class="badge {bcls}">{p['status']}</span>
                    </div>
                </div>"""
            st.markdown(f'<div class="ptable">{rows_html}</div>', unsafe_allow_html=True)

        # ── Sales ──
        if sales:
            st.markdown('<div class="sec-hd" style="margin-top:0.8rem">🔄 Sales Detected</div>', unsafe_allow_html=True)
            sh = ""
            for item, qty in sales.items():
                sh += f'<div class="sale-row"><span>🛒 {item}</span><span class="sale-qty">−{qty}</span></div>'
            st.markdown(sh, unsafe_allow_html=True)

        # ── Alerts ──
        if alerts:
            st.markdown('<div class="sec-hd" style="margin-top:0.8rem">🔔 Alerts</div>', unsafe_allow_html=True)
            ah = ""
            for a in alerts:
                cls = "crit" if a.get("severity") == "critical" else "warn"
                ico = "🚨" if cls == "crit" else "⚠️"
                ah += f"""<div class="acard {cls}">
                    <span class="aicon">{ico}</span>
                    <div class="abody">
                        <div class="atitle">{a['item']}</div>
                        <div class="adetail">Stock: {a['stock']} · Rate: {a.get('rate',0)}/hr · Depletes: {a.get('time_to_empty','N/A')}</div>
                        <div class="aaction">→ {a['action']}</div>
                    </div>
                </div>"""
            st.markdown(ah, unsafe_allow_html=True)

        # ── Recommendations ──
        if recs:
            st.markdown('<div class="sec-hd" style="margin-top:0.8rem">💡 Recommendations</div>', unsafe_allow_html=True)
            rh = ""
            for r in recs:
                rh += f"""<div class="rcard">
                    <span class="ritem">{r['item']}</span> — {r['reason']}
                    <br><span class="rsub">{r['suggestion']}</span>
                </div>"""
            st.markdown(rh, unsafe_allow_html=True)

        # ── Footer ──
        st.markdown(f"""
        <div class="foot-stats">
            Frames: {frames} · Snapshots: {snaps} · Buffer: {buf} · Grid: {rows}×{cols}
        </div>
        """, unsafe_allow_html=True)


def render_saved_analytics(container):
    """Show analytics from the last saved session (before monitoring starts)."""
    stock = st.session_state.saved_stock
    sales = st.session_state.saved_sales
    alerts = st.session_state.saved_alerts

    if not stock:
        return  # Nothing saved

    # Build a mock state dict from saved data
    products = []
    for name, count in stock.items():
        s = "urgent" if count <= 2 else ("low" if count <= 5 else "ok")
        products.append({"name": name, "stock": count, "rate": 0, "status": s})

    latest_sales = {}
    for entry in sales[-10:]:
        item = entry.get("item", "")
        qty = entry.get("qty", 0)
        if item:
            latest_sales[item] = latest_sales.get(item, 0) + qty

    state = {
        "total_stock": sum(stock.values()),
        "num_classes": len(stock),
        "low_count": sum(1 for v in stock.values() if 0 < v <= 5),
        "snapshot_count": st.session_state.saved_snaps,
        "frame_count": st.session_state.saved_frames,
        "buffer_fill": 0,
        "rows": st.session_state.grid_rows,
        "cols": st.session_state.grid_cols,
        "products": products,
        "latest_sales": latest_sales,
        "alerts": alerts,
        "recommendations": [],
    }
    render_analytics(container, state)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN LOOP
# ═══════════════════════════════════════════════════════════════════════════

if st.session_state.running and st.session_state.shelf_camera is not None:
    shelf = st.session_state.shelf_camera

    if not shelf.running:
        feed_ph.info("📡 Connecting to camera...")
        time.sleep(1)
        if not shelf.running:
            st.session_state.running = False
            st.session_state.last_status = "error"
            st.session_state.error_msg = shelf.error_msg or "Camera connection lost"
            st.rerun()

    fps_win = []
    tick = 0
    persist_tick = 0

    while st.session_state.running and shelf.running:
        t0 = time.time()

        with shelf.lock:
            jpg = shelf.latest_jpg

        if jpg is not None:
            arr = np.frombuffer(jpg, np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is not None:
                feed_ph.image(
                    cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
                    caption="Live Shelf Feed",
                    use_container_width=True,
                )
        else:
            feed_ph.markdown("""
            <div class="cam-ph" style="min-height:300px">
                <div class="ph-icon">📡</div>
                <div class="ph-title">Waiting for frames...</div>
            </div>
            """, unsafe_allow_html=True)

        # Update analytics every ~0.5s
        tick += 1
        if tick % 10 == 0:
            state = shelf.get_state()
            render_analytics(data_ph, state)

            # Persist to JSON every ~5s
            persist_tick += 1
            if persist_tick % 10 == 0:
                try:
                    _persist_shelf(state)
                except Exception:
                    pass

        # FPS
        dt = time.time() - t0
        fps_win.append(dt)
        if len(fps_win) > 20:
            fps_win.pop(0)
        st.session_state.fps = 1.0 / max(sum(fps_win)/len(fps_win), 0.001)

        time.sleep(max(0.02, 0.05 - dt))

    if st.session_state.running and not shelf.running:
        st.session_state.running = False
        st.session_state.last_status = "error"
        st.session_state.error_msg = shelf.error_msg or "Camera disconnected"
        st.rerun()

else:
    # ── Idle placeholders ──
    with col_feed:
        feed_ph.markdown("""
        <div class="cam-ph">
            <div class="ph-icon">📷</div>
            <div class="ph-title">No Camera Active</div>
            <div class="ph-sub">Select a source and click <strong>Start Monitoring</strong></div>
        </div>
        """, unsafe_allow_html=True)

    with col_data:
        if has_saved:
            render_saved_analytics(data_ph)
        else:
            data_ph.markdown("""
            <div class="data-ph">
                <div class="dph-icon">📊</div>
                <div class="dph-text">Inventory insights will appear here<br>once monitoring begins.</div>
            </div>
            """, unsafe_allow_html=True)
