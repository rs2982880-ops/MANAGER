"""
ShelfAI Web Server — Single-Shelf Edition
==========================================
Flask backend serving dashboard.html with a single shelf and camera selector.

Run:
    python server.py
Open:
    http://localhost:5050
"""

import json
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, Response, jsonify, make_response, request, send_from_directory

from camera_manager import ShelfCamera
from database import Database
from detector import ProductDetector
from utils import format_time_remaining

# ── Flask ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
app = Flask(__name__, static_folder=str(BASE_DIR))
app.config["JSON_SORT_KEYS"] = False

# ── Global defaults ───────────────────────────────────────────────────────
DEFAULTS = dict(
    confidence=0.45,
    shelf_x1=50, shelf_y1=30, shelf_x2=590, shelf_y2=440,
    grid_rows=3, grid_cols=5,
    snap_interval=30, buffer_size=5,
    stock_threshold=5,
)

# ── Singletons ─────────────────────────────────────────────────────────────
_db:       Database        = Database()
_detector: ProductDetector = None
_shelf:    ShelfCamera     = None


def init_backend():
    """Initialise YOLO detector and the single shelf."""
    global _detector, _shelf

    if _detector is None:
        _detector = ProductDetector(confidence=DEFAULTS["confidence"])

    if _shelf is None:
        default_region = (
            DEFAULTS["shelf_x1"], DEFAULTS["shelf_y1"],
            DEFAULTS["shelf_x2"], DEFAULTS["shelf_y2"],
        )
        _shelf = ShelfCamera(
            name="Shelf",
            source=0,
            detector=_detector,
            region=default_region,
            rows=DEFAULTS["grid_rows"],
            cols=DEFAULTS["grid_cols"],
            snap_interval=DEFAULTS["snap_interval"],
            buffer_size=DEFAULTS["buffer_size"],
            stock_threshold=DEFAULTS["stock_threshold"],
        )

    _detector.set_confidence(DEFAULTS["confidence"])


init_backend()


# ── Camera enumeration ─────────────────────────────────────────────────────
def enumerate_cameras(max_index: int = 5):
    """Probe camera indices 0..max_index and return list of available ones."""
    available = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap is not None and cap.isOpened():
            available.append({"index": i, "name": f"Camera {i}"})
            cap.release()
    return available


# ── MJPEG generator ────────────────────────────────────────────────────────
def _gen_mjpeg():
    while _shelf.running:
        with _shelf.lock:
            jpg = _shelf.latest_jpg
        if jpg:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: " + str(len(jpg)).encode() + b"\r\n\r\n" +
                jpg + b"\r\n"
            )
        time.sleep(0.04)


# ════════════════════════════════════════════════════════════════════════════
# ROUTES
# ════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    resp = send_from_directory(str(BASE_DIR), "dashboard.html")
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


# ── /api/state — full shelf state ─────────────────────────────────────────
@app.route("/api/state")
def api_state():
    s = _shelf.get_state()
    # Add alert shelf labels for compatibility
    alerts_out = []
    for a in s.get("alerts", []):
        ac = dict(a)
        ac["shelf"] = _shelf.name
        alerts_out.append(ac)
    s["all_alerts"] = alerts_out
    s["ok"] = True
    return jsonify(s)


# ── /api/feed — MJPEG stream ──────────────────────────────────────────────
@app.route("/api/feed")
def api_feed():
    if not _shelf.running:
        return ("", 404)
    resp = Response(
        _gen_mjpeg(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )
    resp.headers["Cache-Control"]     = "no-cache, no-store"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp


# ── /api/cameras/available — enumerate device cameras ─────────────────────
@app.route("/api/cameras/available")
def api_cameras_available():
    cams = enumerate_cameras()
    return jsonify(ok=True, cameras=cams)


# ── /api/camera/start ─────────────────────────────────────────────────────
@app.route("/api/camera/start", methods=["POST"])
def api_camera_start():
    body = request.get_json(force=True, silent=True) or {}
    if "source" in body:
        raw = body["source"]
        try:
            _shelf.source = int(raw)
        except (TypeError, ValueError):
            _shelf.source = str(raw).strip()

    ok = _shelf.start_camera()
    return jsonify(
        ok=ok,
        camera_active=ok,
        message="Streaming" if ok else (_shelf.error_msg or "Camera failed"),
    )


# ── /api/camera/stop ──────────────────────────────────────────────────────
@app.route("/api/camera/stop", methods=["POST"])
def api_camera_stop():
    _shelf.stop_camera()
    return jsonify(ok=True, camera_active=False)


# ── /api/resize — change grid dimensions ─────────────────────────────────
@app.route("/api/resize", methods=["POST"])
def api_resize():
    body = request.get_json(force=True, silent=True) or {}
    rows = int(body.get("rows", _shelf.rows))
    cols = int(body.get("cols", _shelf.cols))

    region = None
    if "shelf_x1" in body:
        region = (
            int(body["shelf_x1"]), int(body.get("shelf_y1", _shelf.region[1])),
            int(body.get("shelf_x2", _shelf.region[2])), int(body.get("shelf_y2", _shelf.region[3])),
        )

    _shelf.resize_grid(
        rows=rows, cols=cols, region=region,
        snap_interval=float(body.get("snap_interval", _shelf.snap_interval)),
        buffer_size=int(body.get("buffer_size", _shelf.buffer_size)),
        stock_threshold=int(body.get("stock_threshold", _shelf.stock_threshold)),
    )
    return jsonify(ok=True, rows=_shelf.rows, cols=_shelf.cols)


# ── /api/demo-step — run demo simulation ─────────────────────────────────
@app.route("/api/demo-step", methods=["POST"])
def api_demo_step():
    body = request.get_json(force=True, silent=True) or {}
    n    = int(body.get("steps", 1))

    if not _shelf.running:
        for _ in range(n):
            _shelf.run_demo_step()

    return jsonify(
        ok=True,
        demo_step=_shelf.demo_step,
        total_stock=_shelf.tracker.get_current_stock(),
    )


# ── /api/reset ────────────────────────────────────────────────────────────
@app.route("/api/reset", methods=["POST"])
def api_reset():
    _shelf.reset()
    return jsonify(ok=True)


# ── /api/settings — global defaults ──────────────────────────────────────
@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "GET":
        return jsonify(DEFAULTS)
    body = request.get_json(force=True, silent=True) or {}
    for k, v in body.items():
        if k in DEFAULTS:
            DEFAULTS[k] = type(DEFAULTS[k])(v)
    _detector.set_confidence(DEFAULTS["confidence"])
    return jsonify(ok=True, settings=DEFAULTS)


# ── /api/upload — analyse a shelf photo ──────────────────────────────────
@app.route("/api/upload", methods=["POST"])
def api_upload():
    import base64
    if "file" not in request.files:
        return jsonify(ok=False, error="No file"), 400

    raw   = np.frombuffer(request.files["file"].read(), np.uint8)
    frame = cv2.imdecode(raw, cv2.IMREAD_COLOR)
    if frame is None:
        return jsonify(ok=False, error="Cannot decode image"), 400

    detections, _ = _detector.detect(frame)
    shelf_dets    = _shelf.gmapper.filter_shelf_detections(detections)
    grid_map      = _shelf.gmapper.map_detections(shelf_dets)
    _shelf.tracker.add_frame(grid_map)
    snap = _shelf.tracker.take_snapshot()
    if snap:
        _shelf.snapshot_count += 1
    _shelf.frame_count += 1
    _shelf._refresh_insights()

    import cv2 as _cv2
    annotated = _shelf.gmapper.draw_grid_overlay(frame, grid_map)
    _, buf  = _cv2.imencode(".jpg", annotated, [_cv2.IMWRITE_JPEG_QUALITY, 85])
    img_b64 = base64.b64encode(buf).decode()

    ts = datetime.now().strftime("%H:%M:%S")
    _shelf._log(f"[{ts}] Upload — {len(shelf_dets)} shelf objects 📸")

    return jsonify(
        ok=True,
        image=f"data:image/jpeg;base64,{img_b64}",
        items_detected=len(shelf_dets),
    )


# ── /api/export ───────────────────────────────────────────────────────────
@app.route("/api/export")
def api_export():
    state = _shelf.get_state()
    payload = dict(
        exported_at=datetime.now().isoformat(),
        shelf=state,
        settings=DEFAULTS,
    )
    resp = make_response(json.dumps(payload, indent=2))
    resp.headers["Content-Type"]        = "application/json"
    resp.headers["Content-Disposition"] = (
        f'attachment; filename="shelfai_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json"'
    )
    return resp


# ── /api/history ─────────────────────────────────────────────────────────
@app.route("/api/history")
def api_history():
    snaps = _db.get_snapshot_history(limit=20)
    evts  = _db.get_sales_history(limit=30)
    return jsonify(
        snapshots=[dict(time=r[0], stock=json.loads(r[2])) for r in snaps],
        events   =[dict(time=r[0], item=r[1], qty=r[2], type=r[3]) for r in evts],
    )


# ─────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("  🟢  ShelfAI → http://localhost:5050")
    print("=" * 55 + "\n")
    app.run(host="0.0.0.0", port=5050, debug=False, threaded=True)
