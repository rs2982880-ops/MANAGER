# 🛒 ShelfAI — AI-Powered Retail Inventory Monitor

> Real-time shelf monitoring using computer vision. Detects products, tracks sales, and provides actionable inventory insights — all from a single camera.

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![React](https://img.shields.io/badge/React-18+-61dafb?logo=react)
![YOLO](https://img.shields.io/badge/YOLOv8-Ultralytics-purple)
![License](https://img.shields.io/badge/License-MIT-green)

---

## 🎯 What It Does

Point a camera at a retail shelf → ShelfAI automatically:

- **Detects** every product using YOLOv8 object detection
- **Maps** products to a configurable grid (rows × columns)
- **Tracks** inventory changes using consensus-based algorithms
- **Detects sales** when items disappear from the grid
- **Logs everything** to SQLite with full audit trail
- **Streams live** to a premium dark-themed dashboard

---

## 🏗️ Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────────────┐
│   Camera     │────▶│  FastAPI      │────▶│  React Dashboard │
│  (USB/IP)    │     │  Backend      │     │  (Vite + Zustand)│
└─────────────┘     │              │     └──────────────────┘
                    │  YOLO v8     │            ▲
                    │  Grid Mapper │            │ WebSocket
                    │  Tracker     │────────────┘
                    │  SQLite DB   │
                    └──────────────┘
```

### Backend Modules

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app — REST + WebSocket endpoints |
| `camera.py` | Camera lifecycle service (start/stop/state) |
| `camera_manager.py` | Threaded camera capture with edge-case handling |
| `detector.py` | YOLOv8 detection pipeline with class filtering |
| `grid_mapper.py` | Maps detections to R×C shelf grid cells |
| `tracker.py` | Consensus-based inventory tracking engine |
| `logic.py` | Restocking alerts & recommendation engine |
| `database.py` | SQLite persistence — sales events, daily sales, audit log |
| `storage.py` | JSON persistence for config & state |
| `utils.py` | Drawing utilities for bounding boxes |

### Frontend Components

| File | Purpose |
|------|---------|
| `App.jsx` | Tab navigation (Dashboard / Sales Log) |
| `VideoFeed.jsx` | Live camera feed with grid overlay |
| `GridOverlay.jsx` | SVG grid visualization on video |
| `Sidebar.jsx` | Product list, alerts, recommendations |
| `ControlPanel.jsx` | Camera controls, settings, mode switch |
| `SalesPage.jsx` | Editable daily sales log with audit tracking |
| `Navbar.jsx` | Top navigation bar |

---

## 🧠 How Sales Detection Works

### The Pipeline

```
Camera Frame → YOLO Detection → Grid Mapping → Buffer → Consensus → Compare → Sale
```

### Step-by-Step

1. **YOLO Detection** — YOLOv8 scans each frame, identifies products (bottle, cup, banana, etc.)
2. **Class Filtering** — Excludes non-shelf items (person, laptop, phone, furniture)
3. **Grid Mapping** — Each detection's center point maps to a grid cell (row, col)
4. **Frame Buffer (N=7)** — Raw grids accumulate in a rolling buffer
5. **Majority Voting** — For each cell, the label appearing in ≥4/7 frames wins (eliminates YOLO flicker)
6. **Snapshot Comparison** — Confirmed grid compared with previous snapshot
7. **Sale Confirmation** — If item count decreased AND item wasn't displaced to a neighbor cell → **confirmed sale**
8. **DB Persistence** — Sale logged to `sales_events` table in real-time

### Edge Cases Handled

| Edge Case | Protection |
|-----------|-----------|
| YOLO misses item for 1-2 frames | Buffer majority voting (4/7 threshold) |
| Customer moves item to adjacent cell | Displacement check (radius=1) |
| Hand/person blocks camera briefly | Mass disappearance guard (30% threshold) |
| Camera disconnects | Black frame detection + state freeze |
| Same sale counted twice | Per-cell cooldown (5 seconds) |
| Count exceeds actual decrease | Count-cap rule |
| Camera reconnects | 10-frame stabilization window |

---

## 📊 Features

### Real-Time Dashboard
- **Live video** with annotated bounding boxes and grid overlay
- **Product cards** with stock levels, sales rates, and status indicators
- **KPI metrics** — total stock, items sold, classes detected
- **Alerts** — low stock warnings, restocking recommendations
- **FPS counter** and frame diagnostics

### Sales Log (Human-Verified Layer)
- **Editable table** of daily sales records
- **Edit modal** with change preview (old → new), reason selector, notes
- **Audit trail** — every change logged with timestamp and reason
- **🔒 Lock days** — finalize a day to prevent accidental edits
- **↩️ Undo** — revert any record to its previous value
- **Bulk edit** — select multiple rows, update all at once
- **Toast notifications** — success/error feedback on every action
- **KPI cards** — today, week, month, all-time sales summaries

### Camera Management
- **USB cameras** — auto-detected device cameras (index 0, 1, 2...)
- **IP cameras** — DroidCam, RTSP streams, HTTP URLs
- **Settings** — confidence threshold, grid size, snapshot interval
- **Demo/Production modes** — different snapshot timing for testing vs. live

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+** with pip
- **Node.js 18+** with npm
- A webcam or IP camera (DroidCam app works great)

### One-Click Launch

**Windows:**
```bash
double-click start.bat
```

**Mac/Linux:**
```bash
chmod +x start.sh
./start.sh
```

This installs all dependencies and starts both backend + frontend.

### Manual Setup

```bash
# 1. Install Python dependencies
cd retail_inventory/backend
pip install -r requirements.txt

# 2. Install frontend dependencies
cd ../frontend
npm install

# 3. Start backend (Terminal 1)
cd ../backend
uvicorn main:app --host 0.0.0.0 --port 8000

# 4. Start frontend (Terminal 2)
cd ../frontend
npm run dev
```

Then open **http://localhost:5173** in your browser.

---

## 🔌 API Endpoints

### Camera
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/start-camera` | Start camera (device index or IP URL) |
| POST | `/api/stop-camera` | Stop camera |
| GET | `/api/state` | Full shelf state |
| GET | `/api/cameras/available` | List available cameras |

### Settings
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/settings` | Current settings |
| POST | `/api/settings` | Update settings |
| POST | `/api/resize` | Change grid dimensions |
| POST | `/api/set-mode` | Switch demo/production mode |

### Sales Log
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/sales/daily` | Fetch daily sales + summary |
| POST | `/api/sales/daily` | Add/upsert daily sale |
| PUT | `/api/sales/daily/:id` | Update with audit logging |
| DELETE | `/api/sales/daily/:id` | Delete (respects day lock) |
| POST | `/api/sales/daily/:id/undo` | Revert last change |
| POST | `/api/sales/daily/bulk` | Bulk update records |

### Audit & Lock
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/sales/audit` | Change history log |
| POST | `/api/sales/lock/:date` | Lock a day |
| DELETE | `/api/sales/lock/:date` | Unlock a day |
| GET | `/api/sales/locks` | List locked dates |

### WebSocket
| Endpoint | Description |
|----------|-------------|
| `ws://localhost:8000/ws/stream` | Real-time frame + state streaming |

---

## 📁 Project Structure

```
retail_inventory/
├── backend/
│   ├── main.py              # FastAPI app
│   ├── camera.py            # Camera service
│   ├── camera_manager.py    # Threaded capture
│   ├── detector.py          # YOLOv8 pipeline
│   ├── grid_mapper.py       # Grid mapping
│   ├── tracker.py           # Inventory tracker
│   ├── logic.py             # Alerts engine
│   ├── database.py          # SQLite DB
│   ├── storage.py           # JSON persistence
│   ├── utils.py             # Drawing utils
│   ├── requirements.txt     # Python deps
│   └── inventory.db         # SQLite database
├── frontend/
│   ├── src/
│   │   ├── components/      # React components
│   │   ├── stores/           # Zustand state
│   │   ├── services/         # API client
│   │   └── index.css         # Global styles
│   ├── package.json
│   └── vite.config.js
├── start.bat                 # Windows launcher
├── start.sh                  # Mac/Linux launcher
└── README.md                 # This file
```

---

## 🗄️ Database Schema

```sql
-- AI-detected sales events (raw, noisy)
sales_events (id, timestamp, item_name, quantity, event_type)

-- Human-verified daily sales (authoritative)
daily_sales (id, date, item_name, quantity, notes, created_at, updated_at)

-- Change tracking for every edit
sales_audit_log (id, sale_id, date, item_name, old_value, new_value, reason, notes, timestamp)

-- Finalized days that cannot be edited
locked_days (date, locked_at)
```

---

## 🛡️ Two-Layer Data Design

```
┌──────────────────────────┐
│  AI Sales Events         │  ← Raw, automatic, may contain noise
│  (sales_events table)    │
└──────────┬───────────────┘
           │ Suggested
           ▼
┌──────────────────────────┐
│  Daily Sales Log         │  ← Human-verified, editable, authoritative
│  (daily_sales table)     │
│  + Audit trail           │
│  + Lock days             │
└──────────────────────────┘
```

> **Rule:** AI events are never overwritten by manual edits. The daily sales log is a separate, verified layer.

---

## ⚙️ Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| Confidence | 0.55 | YOLO detection threshold |
| Grid | 3×5 | Shelf grid dimensions |
| Buffer | 7 frames | Consensus voting window |
| Cooldown | 5 seconds | Sale deduplication window |
| Snapshot interval | 30s (demo) | Time between comparisons |

---

## 📜 License

MIT License — free for personal and commercial use.
