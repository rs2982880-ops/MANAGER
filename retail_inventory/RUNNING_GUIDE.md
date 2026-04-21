# 🚀 Running Guide — AI Retail Inventory System

A step-by-step guide to get the system up and running on your machine.

---

## 📋 Prerequisites

| Requirement | Minimum Version | Notes |
|---|---|---|
| Python | 3.9+ | 3.10 or 3.11 recommended |
| pip | latest | comes with Python |
| Webcam (optional) | any | only needed for live mode |
| GPU (optional) | CUDA-capable | speeds up detection, not required |

---

## 1️⃣  Clone / Open the Project

The project folder is:
```
c:\Users\lonew\OneDrive\Documents\.vscode\retail_inventory\
```

Open a terminal (PowerShell or Command Prompt) and navigate to it:
```powershell
cd "c:\Users\lonew\OneDrive\Documents\.vscode\retail_inventory"
```

---

## 2️⃣  Create a Virtual Environment (Recommended)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

> If PowerShell blocks script execution, run:
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

---

## 3️⃣  Install Dependencies

```powershell
pip install -r requirements.txt
```

This installs:
- `ultralytics` — YOLOv8 model framework
- `opencv-python` — camera capture & image processing
- `streamlit` — the interactive web dashboard
- `numpy` — numerical arrays
- `Pillow` — image decode helpers
- `pandas` — data tables in the dashboard

> **First-time note:** On first run, `ultralytics` will automatically download
> `yolov8l.pt` (~87 MB) if `best.pt` is not present. This only happens once.

---

## 4️⃣  Launch the Dashboard

```powershell
streamlit run app.py
```

Streamlit will print a URL like:
```
  Local URL: http://localhost:8501
  Network URL: http://192.168.x.x:8501
```

Open the **Local URL** in your browser. The dashboard will load immediately.

---

## 5️⃣  Choose an Input Mode

In the **sidebar → 📷 Input**, pick one of three modes:

### 🧪 Demo Simulation (No Camera Needed — Start Here)
- No webcam or images required.
- Click **▶ Run 1 step** or **⏩ Run 5 steps** to simulate shelf activity.
- Items are randomly placed and removed to mimic real sales.
- Best for exploring all dashboard features quickly.

### 🖼️ Upload Image
- Click **Browse files** and upload any shelf photo (JPG, PNG, BMP, WebP).
- The system runs YOLO detection on it immediately.
- A snapshot is taken automatically after upload.

### 🎥 Webcam
- Point your webcam at a shelf (or any surface with objects).
- Check **▶ Start camera** to begin live detection.
- Use **📸 Manual snapshot** to force an immediate snapshot.
- Uncheck the box to stop the camera.

---

## 6️⃣  Configure the Sidebar Settings

| Setting | What It Does | Default |
|---|---|---|
| Confidence threshold | Min YOLO detection certainty | 0.45 |
| x_min / y_min / x_max / y_max | Pixel coords of the shelf region | 50, 30, 590, 440 |
| Grid Rows / Columns | How many rows & columns to divide the shelf into | 3 × 5 |
| Snapshot interval | Seconds between automatic snapshots | 30 s |
| Buffer frames | Frames kept for majority-vote occlusion guard | 5 |
| Low-stock threshold | Alert when item count drops below this | 5 |

### 🏷️ Tracked Classes
- The multiselect shows every product class the YOLO model knows about.
- Un-tick any class you don't want tracked (e.g. "book").
- Use **➕ Add custom class** to invent a new label (useful with custom models).
- Use **❌ Remove a class** to drop a class entirely from tracking.

---

## 7️⃣  Reading the Dashboard

### Top Metrics (right panel)
| Card | Meaning |
|---|---|
| **Items** | Total items currently detected on the shelf |
| **Classes** | Number of distinct product types detected |
| **Snapshots** | How many snapshots have been taken this session |
| **Frames** | Total frames processed |

### Shelf Grid Map
- Visual R×C grid of the shelf.
- **Coloured cells** = occupied (product name shown).
- **Dark cells with ∅** = empty slots.

### Stock Summary Table
- Item name, current count, and sales rate per hour.

### Sales (last snapshot)
- Blue cards = items that were sold since the last snapshot.
- Green cards = items that were restocked.

### Alerts 🔔
- **Red (critical)** — stock ≤ 2 or shelf ≥ 50 % empty. Pulsing animation.
- **Orange (warning)** — stock below threshold or depletion < 2 hrs away.
- **Green ✅** — everything is healthy.

### Recommendations 📋
- High-demand items → suggested to move to eye level / centre.
- Low-demand items → reposition or bundle.
- Co-occurring items → suggested to place near each other.

### Bottom Tabs
| Tab | Content |
|---|---|
| 📈 Stock Trends | Line chart of stock level per item across snapshots |
| 🌡️ Emptiness Heatmap | Grid showing which shelf positions are frequently empty (red = always empty) |
| 🗄️ History | SQLite-backed tables of past snapshots and sales/restock events |
| 📝 Log | Real-time frame-by-frame log with timestamps |

### Sales Debug Panel (expandable)
- Expander at the bottom: **🔍 Sales Debug — Movement vs Disappearance**.
- Shows a per-item classification: SOLD / RESTOCKED / MOVED / UNCHANGED.

---

## 8️⃣  Reset Data

Click **🗑️ Reset all data** in the sidebar to clear all tracking state and start fresh.

---

## 9️⃣  Run the Integration Tests (Optional)

```powershell
python -m pytest test_integration.py -v
```

Tests verify the tracker, sales detection, and grid mapper logic work correctly.

---

## 🗂️ Files Produced at Runtime

| File | Description |
|---|---|
| `inventory.db` | SQLite database — snapshots, sales events, alerts |
| `stock.json` | Latest snapshot as JSON (human-readable sidecar) |

---

## ⚠️ Common Issues

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: ultralytics` | Run `pip install -r requirements.txt` |
| Camera won't open | Try a different camera index or use Demo / Upload mode |
| Model download hangs | Check internet connection; `yolov8l.pt` is ~87 MB |
| Streamlit port busy | Kill the old process or run `streamlit run app.py --server.port 8502` |
| Nothing detected | Lower the **Confidence threshold** slider or check the tracked classes list |
| False sales on rearrangement | Increase **Buffer frames** slider (higher = more occlusion resistance) |

---

## 🔄 Stopping the App

Press `Ctrl + C` in the terminal to stop the Streamlit server.
