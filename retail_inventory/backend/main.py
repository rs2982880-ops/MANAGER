"""
ShelfAI — FastAPI Backend
===========================
Production-grade REST + WebSocket backend for the AI Shelf Monitor.

Replaces the old Streamlit/Flask architecture with:
  - REST endpoints for camera control, settings, history
  - WebSocket endpoint for real-time frame + state streaming
  - Full persistence via JSON + SQLite (existing modules)

Run:
    cd backend
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Architecture:
    main.py           → This file (FastAPI app)
    camera.py         → Camera lifecycle service
    detector.py       → YOLO detection pipeline
    grid_mapper.py    → Shelf grid mapping
    tracker.py        → Snapshot-based stock tracking
    camera_manager.py → Threaded camera capture
    logic.py          → Restocking alerts & recommendations
    storage.py        → JSON persistence
    database.py       → SQLite long-term storage
"""

import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import asyncio
import json
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path

from camera import CameraService


# ═══════════════════════════════════════════════════════════════════════════
# LIFESPAN — Initialize camera service on startup
# ═══════════════════════════════════════════════════════════════════════════

camera_service: Optional[CameraService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global camera_service
    print("\n" + "=" * 55)
    print("  [+]  ShelfAI FastAPI Backend Starting...")
    print("=" * 55)
    camera_service = CameraService()
    # Pre-load the YOLO model so first request is fast
    camera_service.get_detector()
    print("  [OK]  Backend ready -> http://localhost:8000")
    print("  [WS]  WebSocket     -> ws://localhost:8000/ws/stream")
    print("=" * 55 + "\n")
    yield
    # Shutdown
    if camera_service and camera_service.is_running:
        camera_service.stop()
    print("\n  [-]  ShelfAI Backend stopped.\n")


# ═══════════════════════════════════════════════════════════════════════════
# APP SETUP
# ═══════════════════════════════════════════════════════════════════════════

app = FastAPI(
    title="ShelfAI — AI Shelf Monitor",
    version="3.0.0",
    description="Real-time AI inventory monitoring backend",
    lifespan=lifespan,
)

# CORS — Allow all origins for ngrok / deployment access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════════════════
# REQUEST MODELS
# ═══════════════════════════════════════════════════════════════════════════

class CameraStartRequest(BaseModel):
    source: str | int = 0


class CameraStopRequest(BaseModel):
    pass


class SettingsUpdate(BaseModel):
    confidence: Optional[float] = None
    detection_on: Optional[bool] = None
    grid_rows: Optional[int] = None
    grid_cols: Optional[int] = None
    snap_interval: Optional[float] = None
    stock_threshold: Optional[int] = None


class GridResize(BaseModel):
    rows: int
    cols: int
    shelf_x1: Optional[int] = None
    shelf_y1: Optional[int] = None
    shelf_x2: Optional[int] = None
    shelf_y2: Optional[int] = None


class ModeRequest(BaseModel):
    mode: str  # "demo" or "production"


class DailySaleCreate(BaseModel):
    date: str
    item: str
    quantity: int
    notes: str = ""


class DailySaleUpdate(BaseModel):
    quantity: int
    notes: str = ""
    reason: str = ""


class BulkUpdateItem(BaseModel):
    id: int
    quantity: int
    notes: str = ""


class BulkUpdateRequest(BaseModel):
    updates: list[BulkUpdateItem]
    reason: str = "Bulk update"


# ═══════════════════════════════════════════════════════════════════════════
# REST API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/info")
async def api_info():
    return {"name": "ShelfAI", "version": "3.0.0", "status": "running"}


@app.get("/")
async def root():
    """Serve frontend if built, otherwise return API info."""
    _dist = Path(__file__).resolve().parent.parent / "frontend" / "dist" / "index.html"
    if _dist.is_file():
        return FileResponse(str(_dist))
    return {"name": "ShelfAI", "version": "3.0.0", "status": "running"}


# ── Camera Control ────────────────────────────────────────────────────────

@app.post("/api/start-camera")
async def start_camera(req: CameraStartRequest):
    """Start camera with device index (int) or IP URL (string)."""
    source = req.source
    # Try to parse as int if it's a string digit
    if isinstance(source, str):
        try:
            source = int(source)
        except ValueError:
            pass  # Keep as URL string
    result = camera_service.start(source)
    return JSONResponse(content=result)


@app.post("/api/stop-camera")
async def stop_camera():
    """Stop the active camera."""
    result = camera_service.stop()
    return JSONResponse(content=result)


@app.get("/api/cameras/available")
async def available_cameras():
    """Enumerate available device cameras."""
    cameras = camera_service.enumerate_cameras()
    return {"ok": True, "cameras": cameras}


# ── Mode Control ──────────────────────────────────────────────────────

@app.post("/api/set-mode")
async def set_mode(req: ModeRequest):
    """Switch between demo and production mode."""
    result = camera_service.set_mode(req.mode)
    return JSONResponse(content=result)


# ── State ─────────────────────────────────────────────────────────────────

@app.get("/api/state")
async def get_state():
    """Get full shelf state (stock, alerts, grid, etc.)."""
    state = camera_service.get_state()
    return JSONResponse(content=state)


# ── Settings ──────────────────────────────────────────────────────────────

@app.get("/api/settings")
async def get_settings():
    """Get current settings."""
    return {
        "confidence": camera_service.confidence,
        "detection_on": camera_service.detection_on,
        "grid_rows": camera_service.grid_rows,
        "grid_cols": camera_service.grid_cols,
        "snap_interval": camera_service.snap_interval,
        "buffer_size": camera_service.buffer_size,
        "stock_threshold": camera_service.stock_threshold,
    }


@app.post("/api/settings")
async def update_settings(settings: SettingsUpdate):
    """Update detection / grid settings."""
    update_dict = settings.model_dump(exclude_none=True)
    result = camera_service.update_settings(update_dict)
    return JSONResponse(content=result)


# ── Grid Resize ───────────────────────────────────────────────────────────

@app.post("/api/resize")
async def resize_grid(req: GridResize):
    """Change grid dimensions on the fly."""
    result = camera_service.update_settings({
        "grid_rows": req.rows,
        "grid_cols": req.cols,
    })
    return JSONResponse(content=result)


# ── Snapshot ──────────────────────────────────────────────────────────────

@app.post("/api/snapshot")
async def take_snapshot():
    """Force a snapshot save."""
    result = camera_service.take_snapshot()
    return JSONResponse(content=result)


# ── Status / Stock / Alerts (NEW) ─────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    """Camera health, thread state, and edge case diagnostics."""
    result = camera_service.get_system_status()
    return JSONResponse(content=result)


@app.get("/api/stock")
async def get_stock():
    """Current stock levels (or frozen stock if camera offline)."""
    result = camera_service.get_stock()
    return JSONResponse(content=result)


@app.get("/api/alerts")
async def get_alerts():
    """Active alerts including system alerts (camera offline, etc)."""
    result = camera_service.get_alerts_list()
    return JSONResponse(content=result)


# ── History ───────────────────────────────────────────────────────────────

@app.get("/api/history")
async def get_history():
    """Get sales history from SQLite."""
    history = camera_service.get_history()
    return JSONResponse(content=history)


# ═══════════════════════════════════════════════════════════════════════════
# DAILY SALES LOG — Human-corrected, editable sales layer
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/sales/daily")
async def get_daily_sales(days: int = 30):
    """Fetch editable daily sales log + summary KPIs."""
    from database import Database
    db = Database()
    return JSONResponse(content={
        "ok": True,
        "records": db.get_daily_sales_log(days),
        "summary": db.get_daily_sales_summary(),
    })


@app.post("/api/sales/daily")
async def create_daily_sale(sale: DailySaleCreate):
    """Insert or update a daily sale record (upsert on date+item)."""
    if not sale.item.strip():
        return JSONResponse(content={"ok": False, "message": "Item name required"}, status_code=400)
    if sale.quantity < 0:
        return JSONResponse(content={"ok": False, "message": "Quantity must be >= 0"}, status_code=400)
    from database import Database
    db = Database()
    row_id = db.upsert_daily_sale(sale.date, sale.item.strip(), sale.quantity, sale.notes)
    return JSONResponse(content={"ok": True, "id": row_id, "message": "Saved"})


@app.put("/api/sales/daily/{sale_id}")
async def update_daily_sale(sale_id: int, sale: DailySaleUpdate):
    """Update a daily sale record with audit logging."""
    if sale.quantity < 0:
        return JSONResponse(content={"ok": False, "message": "Quantity must be >= 0"}, status_code=400)
    from database import Database
    db = Database()
    result = db.update_daily_sale(sale_id, sale.quantity, sale.notes, sale.reason)
    if not result.get("ok"):
        code = 423 if "locked" in result.get("message", "").lower() else 400
        return JSONResponse(content=result, status_code=code)
    return JSONResponse(content=result)


@app.delete("/api/sales/daily/{sale_id}")
async def delete_daily_sale(sale_id: int):
    """Delete a daily sale record (respects day lock)."""
    from database import Database
    db = Database()
    ok = db.delete_daily_sale(sale_id)
    if not ok:
        return JSONResponse(content={"ok": False, "message": "Record not found or day is locked"}, status_code=400)
    return JSONResponse(content={"ok": True, "message": "Deleted"})


@app.get("/api/sales/audit")
async def get_audit_log(days: int = 30, item: str = None):
    """Fetch change history for all or a specific item."""
    from database import Database
    db = Database()
    logs = db.get_audit_log(days, item)
    return JSONResponse(content={"ok": True, "logs": logs})


@app.post("/api/sales/daily/{sale_id}/undo")
async def undo_sale_change(sale_id: int):
    """Revert the most recent change to a daily sale record."""
    from database import Database
    db = Database()
    result = db.undo_last_change(sale_id)
    if not result.get("ok"):
        return JSONResponse(content=result, status_code=400)
    return JSONResponse(content=result)


@app.post("/api/sales/lock/{date}")
async def lock_day(date: str):
    """Lock a day to prevent further edits."""
    from database import Database
    db = Database()
    ok = db.lock_day(date)
    return JSONResponse(content={"ok": ok, "message": f"Day {date} locked" if ok else "Failed"})


@app.delete("/api/sales/lock/{date}")
async def unlock_day(date: str):
    """Unlock a day to allow edits."""
    from database import Database
    db = Database()
    ok = db.unlock_day(date)
    return JSONResponse(content={"ok": ok, "message": f"Day {date} unlocked" if ok else "Not found"})


@app.get("/api/sales/locks")
async def get_locked_days():
    """Get all locked dates."""
    from database import Database
    db = Database()
    dates = db.get_locked_days()
    return JSONResponse(content={"ok": True, "dates": dates})


@app.post("/api/sales/daily/bulk")
async def bulk_update_sales(req: BulkUpdateRequest):
    """Bulk update multiple daily sale records."""
    from database import Database
    db = Database()
    result = db.bulk_update_daily_sales(
        [{"id": u.id, "quantity": u.quantity, "notes": u.notes} for u in req.updates],
        req.reason,
    )
    return JSONResponse(content=result)


# ═══════════════════════════════════════════════════════════════════════════
# WEBSOCKET — Real-time frame + state streaming
# ═══════════════════════════════════════════════════════════════════════════

@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    """
    Real-time streaming endpoint.

    Sends JSON messages containing:
      - frame: base64-encoded JPEG of the annotated camera feed
      - All state data (stock, alerts, grid, etc.)

    Receives JSON commands from the client:
      - {"action": "start", "source": 0}
      - {"action": "stop"}
      - {"action": "settings", ...}
    """
    await websocket.accept()
    print("[ws] Client connected")
    _last_logged_snapshot = 0  # Track snapshot count to avoid duplicate DB writes

    try:
        while True:
            # ── Check for incoming commands (non-blocking) ──
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(), timeout=0.02
                )
                try:
                    cmd = json.loads(data)
                    await _handle_ws_command(cmd)
                except json.JSONDecodeError:
                    pass
            except asyncio.TimeoutError:
                pass

            # ── Send frame + state ──
            if camera_service.is_running:
                camera_service.update_fps()
                frame_b64 = camera_service.get_latest_frame_base64()
                state = camera_service.get_state()

                payload = {
                    "type": "frame",
                    "frame": f"data:image/jpeg;base64,{frame_b64}" if frame_b64 else None,
                    "fps": camera_service.fps,
                    "status": state.get("status", "idle"),
                    "running": state.get("running", False),
                    "total_stock": state.get("total_stock", 0),
                    "detected_stock": state.get("detected_stock", 0),
                    "total_sold": state.get("total_sold", 0),
                    "total_sales_map": state.get("total_sales_map", {}),
                    "num_classes": state.get("num_classes", 0),
                    "low_count": state.get("low_count", 0),
                    "empty_count": state.get("empty_count", 0),
                    "products": state.get("products", []),
                    "grid": state.get("grid", []),
                    "grid_rows": state.get("grid_rows", 3),
                    "grid_cols": state.get("grid_cols", 5),
                    "alerts": state.get("alerts", []),
                    "recommendations": state.get("recommendations", []),
                    "latest_sales": state.get("latest_sales", {}),
                    "latest_restocks": state.get("latest_restocks", {}),
                    "frame_count": state.get("frame_count", 0),
                    "snapshot_count": state.get("snapshot_count", 0),
                    "confidence": camera_service.confidence,
                    "detection_on": camera_service.detection_on,
                    "system_state": state.get("system_state"),
                    "snapshot_info": state.get("snapshot_info"),
                }

                # ── Real-time sales persistence to SQLite ──
                latest_sales = state.get("latest_sales", {})
                snap_count = state.get("snapshot_count", 0)
                if latest_sales and snap_count > _last_logged_snapshot:
                    _last_logged_snapshot = snap_count
                    try:
                        camera_service._db.log_sales(latest_sales)
                        print(f"[ws] Logged sales to DB: {latest_sales}")
                    except Exception as e:
                        print(f"[ws] DB log_sales error: {e}")

                await websocket.send_text(json.dumps(payload))
            else:
                # Send idle heartbeat
                state = camera_service.get_state()
                heartbeat = {
                    "type": "heartbeat",
                    "status": state.get("status", "idle"),
                    "running": False,
                    "fps": 0,
                    "total_stock": state.get("total_stock", 0),
                    "detected_stock": state.get("detected_stock", 0),
                    "total_sold": state.get("total_sold", 0),
                    "total_sales_map": state.get("total_sales_map", {}),
                    "products": state.get("products", []),
                    "grid": state.get("grid", []),
                    "grid_rows": state.get("grid_rows", 3),
                    "grid_cols": state.get("grid_cols", 5),
                    "alerts": state.get("alerts", []),
                    "recommendations": state.get("recommendations", []),
                    "frame_count": state.get("frame_count", 0),
                    "snapshot_count": state.get("snapshot_count", 0),
                    "confidence": camera_service.confidence,
                    "detection_on": camera_service.detection_on,
                    "system_state": state.get("system_state"),
                    "snapshot_info": state.get("snapshot_info"),
                }
                await websocket.send_text(json.dumps(heartbeat))

            # Target ~20 FPS for WS updates
            await asyncio.sleep(0.05)

    except WebSocketDisconnect:
        print("[ws] Client disconnected")
    except Exception as e:
        print(f"[ws] Error: {e}")


async def _handle_ws_command(cmd: dict):
    """Handle commands received over WebSocket."""
    action = cmd.get("action")

    if action == "start":
        source = cmd.get("source", 0)
        if isinstance(source, str):
            try:
                source = int(source)
            except ValueError:
                pass
        camera_service.start(source)

    elif action == "stop":
        camera_service.stop()

    elif action == "settings":
        settings = {k: v for k, v in cmd.items() if k != "action"}
        camera_service.update_settings(settings)

    elif action == "snapshot":
        camera_service.take_snapshot()


# ═══════════════════════════════════════════════════════════════════════════
# STATIC FILES — Serve React frontend build
# ═══════════════════════════════════════════════════════════════════════════

_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.is_dir():
    # Serve static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="assets")

    # Catch-all: serve index.html for SPA routing
    @app.get("/{path:path}")
    async def serve_spa(path: str):
        # Try to serve the exact file first
        file = _FRONTEND_DIST / path
        if file.is_file():
            return FileResponse(str(file))
        # Fallback to index.html for client-side routing
        return FileResponse(str(_FRONTEND_DIST / "index.html"))


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
