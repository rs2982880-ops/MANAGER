# 🧠 How It Works — AI Retail Inventory System

A complete technical explanation of every module, algorithm, and design decision in the system.

---

## 🏗️ System Architecture at a Glance

```
Camera / Image / Demo
        │
        ▼
 ┌─────────────┐
 │  detector.py │   ← YOLOv8 runs inference; returns bounding boxes + class names
 └──────┬──────┘
        │  detections: [{class, confidence, bbox}, ...]
        ▼
 ┌─────────────────┐
 │ grid_mapper.py  │   ← Filters to shelf region; maps each detection to an R×C cell
 └──────┬──────────┘
        │  grid_map: List[List[str]]  e.g. [["bottle","empty","cup"],[...],...]
        ▼
 ┌─────────────┐
 │  tracker.py  │   ← Rolling buffer → majority vote → snapshot diff → sales/restocks
 └──────┬──────┘
        │  stock counts, sales rate, alerts input
        ▼
 ┌──────────┐    ┌─────────────┐
 │ logic.py │    │ database.py │   ← Alerts engine & shelf recommendations
 └──────┬───┘    └──────┬──────┘   ← SQLite + stock.json persistence
        │               │
        └───────┬────────┘
                ▼
          ┌──────────┐
          │  app.py   │   ← Streamlit dashboard assembles everything
          └──────────┘
                │
          utils.py      ← Drawing, HTML renderers, time helpers
```

---

## 📦 Module Deep-Dives

---

### 1. `detector.py` — YOLOv8 Product Detection

**Purpose:** Wrap Ultralytics YOLOv8 and expose a clean `detect(frame)` interface.

#### Model Loading (priority order)
1. If `best.pt` exists (custom-trained model) → load it. Every class passes through.
2. Otherwise → download/load `yolov8l.pt` (pretrained COCO, 80 classes). Only shelf-relevant classes pass through via `RETAIL_CLASSES`.

#### Class Filtering Logic
The `_is_allowed(class_name)` method applies rules in this priority order:

| Priority | Rule | Result |
|---|---|---|
| 1 | Class is in `EXCLUDED_CLASSES` (persons, animals, vehicles) | Always **drop** |
| 2 | User set a custom allowlist via sidebar | Keep only if **in allowlist** |
| 3 | Custom model, no allowlist | Keep **everything** non-excluded |
| 4 | Pretrained COCO, no allowlist | Keep only **RETAIL_CLASSES** |

This means: a person walking past the camera is **never** counted as stock.

#### `detect(frame)` Output
Each detection is a dict:
```python
{
  "class":      "bottle",
  "confidence": 0.82,
  "bbox":       [x1, y1, x2, y2]  # pixel coordinates
}
```

#### Runtime Configuration (no model reload)
- `set_confidence(value)` — changes the detection threshold immediately.
- `set_allowed_classes(set)` — changes the filter at runtime; called every sidebar update.
- `get_class_list()` — used to populate the sidebar multiselect.

---

### 2. `grid_mapper.py` — Shelf Region & Grid Mapping

**Purpose:** Translate raw bounding boxes into a structured R×C shelf grid.

#### `ShelfRegion`
A simple bounding box defined by `(x_min, y_min, x_max, y_max)` in pixel space.  
`contains(cx, cy)` returns `True` if a detection centre falls inside the shelf area.

This is a **manual filter** — the user sets the shelf coordinates in the sidebar to exclude anything outside the shelf (floor objects, price tags, etc.).

#### `GridMapper`

The shelf is divided into a uniform **R × C grid**:
```
cell_width  = shelf_width  / cols
cell_height = shelf_height / rows
```

**Mapping a detection to a cell:**
```python
col = int((cx - shelf.x_min) / cell_width)
row = int((cy - shelf.y_min) / cell_height)
```

If multiple detections map to the same cell, the one with the **highest confidence** wins.

**Output:** A 2-D Python list `grid[row][col]` where each value is either a class name string (e.g. `"bottle"`) or `"empty"`.

#### Grid Overlay on Camera Frame
`draw_grid_overlay()` draws directly on the OpenCV frame:
- **Cyan border** around the entire shelf region.
- **Grey lines** separating grid cells.
- **Green tint** on occupied cells (with product label).
- **Red tint** on empty cells.

---

### 3. `tracker.py` — Snapshot Tracker, Occlusion Guard, Sales Detection

This is the most complex and important module. It solves three hard problems:

#### Problem 1: False Sales from Occlusion
If a person walks in front of the camera and temporarily blocks products, a naive count-difference system would think items were sold.

**Solution: Rolling Frame Buffer + Majority Voting**

Every incoming grid is added to a **rolling buffer** of the last N frames (default N=5).

When a snapshot is taken, instead of using the latest single frame, the tracker does a **majority vote** across all N buffer frames:

```
Cell (0,0) across 5 frames: ["bottle","bottle","empty","bottle","bottle"]
Majority vote result:  "bottle"   ← single empty frame is overridden
```

This means a brief occlusion (person's hand, shopping cart) does not register as a sale.

#### Problem 2: Sudden Total Occlusion (Camera Blocked)
If someone stands directly in front of the camera, the entire grid becomes empty.

**Solution: Occlusion Drop Guard**

Before adding a frame to the buffer, the system checks:
```
occupied_cells_this_frame / rolling_average_occupied < 50%
```
If this is true → the frame is **discarded** and a log entry is written: `[OCCLUDED—skipped]`.

This catches catastrophic occlusion where majority voting alone would not be enough.

#### Problem 3: False Sales from Rearrangement
If a stock worker moves a bottle from shelf position (0,0) to (0,2), a naive position-diff system would count one sale (bottle disappeared from (0,0)) and one restock (bottle appeared at (0,2)).

**Solution: Count-Capped Movement-Aware Diff (`detect_sales()`)**

For each item class, the algorithm computes:
```
sale_cap = old_count(item) - new_count(item)
```

- If `sale_cap ≤ 0` → the item's global count did **not decrease**. Any cell transitions from `item → empty` are **rearrangements**, not sales. Skip.
- If `sale_cap > 0` → the item count actually decreased. Scan cells where `old[r][c] == item` and `new[r][c] == "empty"` and confirm up to `sale_cap` sales.

**In the rearrangement example:**
- old_count(bottle) = 3, new_count(bottle) = 3 → cap = 0 → **no sale recorded**. ✅

#### Snapshot Lifecycle
```
add_frame(grid)       → add to buffer (with occlusion check)
should_take_snapshot() → True if interval elapsed AND buffer has ≥ 3 frames
take_snapshot()        → majority_vote() → Snapshot object → compare_snapshots()
```

#### Sales Rate Calculation
```python
span_hours = (latest_snapshot.time - 2nd_oldest_snapshot.time) / 3600
rate[item] = total_sales[item] / span_hours
```
Uses the same `detect_sales()` logic so rearrangements are excluded here too.

#### Emptiness Heatmap
For each grid cell, the fraction of all snapshots where it was `"empty"`.  
`0.0` = always stocked (blue), `1.0` = always empty (red).

---

### 4. `logic.py` — Restocking Engine & Recommendations

**Purpose:** Turn raw stock numbers into actionable alerts and shelf advice.

#### `check_alerts(stock, sales_rate, grid)` → List of alert dicts

Three alert triggers:

| Trigger | Severity | Action |
|---|---|---|
| `item_count ≤ 2` | critical | "Restock immediately!" |
| `item_count < threshold` (default 5) | warning | "Restock soon" |
| `time_to_empty < 2 hours` | warning | "Restock within X hrs" |
| `≥ 50% of shelf cells are empty` | critical (SHELF) | "Major restock needed!" |

Critical alerts sort above warnings.  
`time_to_empty = stock / rate` (in hours).

#### `get_recommendations(stock, sales_rate, co_occurrence)` → List of rec dicts

Rule-based suggestions:

| Rule | Recommendation |
|---|---|
| `rate ≥ 5 items/hr` | "Place at eye level, centre shelf" |
| `0 < rate ≤ 1 item/hr` | "Reposition for visibility or bundle with popular items" |
| `rate == 0 AND stock > 0` | "Consider promotional placement or discount" |
| Frequently co-occurs with another item | "Place near [item]" |

#### `analyse_co_occurrence(snapshot_grids)`
Scans all past snapshot grids. If two items appear together in ≥ 50% of snapshots where either appears, they are flagged as co-occurring. Used to suggest placing related products next to each other.

---

### 5. `database.py` — SQLite + JSON Persistence

**Purpose:** Store all tracking history so data survives page refreshes.

#### SQLite Tables (in `inventory.db`)

```sql
grid_snapshots (id, timestamp, grid_json, stock_json)
sales_events   (id, timestamp, item_name, quantity, event_type)
alerts_log     (id, timestamp, item_name, alert_type, message)
```

- `grid_snapshots` — every snapshot's full grid and stock counts as JSON blobs.
- `sales_events` — individual sale or restock events (`event_type` = "sale" or "restock").
- `alerts_log` — every alert that was fired.

#### JSON Sidecar (`stock.json`)
A human-readable snapshot of the latest state:
```json
{
  "timestamp": "2026-04-20T23:50:58",
  "stock": {"bottle": 3, "cup": 1},
  "grid": [["bottle","empty","cup"],["empty","empty","empty"]]
}
```
This lets other tools (scripts, dashboards) read current stock without querying SQLite.

---

### 6. `utils.py` — Drawing Helpers & HTML Renderers

**Purpose:** Shared helpers used by multiple modules.

#### Drawing
- `get_color_for_class(name)` — generates a consistent BGR colour per class name using its hash, so "bottle" is always the same colour.
- `draw_boxes(frame, detections)` — draws coloured bounding boxes with class + confidence % label on each detection.
- `resize_frame(frame, max_width)` — downscales frames wider than a maximum (performance guard).

#### Time Helpers
- `calculate_time_to_empty(stock, rate)` → hours until depleted.
- `format_time_remaining(hours)` → "45 min", "2.3 hrs", "1.5 days".

#### HTML Renderers (for Streamlit `st.markdown(..., unsafe_allow_html=True)`)
- `render_grid_html(grid)` — converts the 2-D grid into a styled HTML table with:
  - Dark cells + ∅ for empty slots.
  - Coloured cells + product name for occupied slots.
  - Row/Col coordinate labels in each cell.
- `render_heatmap_html(heatmap)` — converts the float emptiness matrix into an HTML table with blue→red gradient colouring.

---

### 7. `app.py` — Streamlit Dashboard

**Purpose:** The user-facing interface. Wires all modules together and handles all UI state through the Streamlit session.

#### Session State
Streamlit re-runs the entire script on every user interaction. To keep objects alive between reruns, they are stored in `st.session_state`:
- `tracker` — the `SnapshotTracker` instance (rebuilt only when snapshot interval or buffer size changes).
- `db` — the `Database` instance (persistent across entire session).
- `frame_count`, `snapshot_count` — counters.
- `log_lines` — last 300 log entries (trimmed to 150 when exceeded).
- `active_classes`, `custom_classes` — class manager state.

#### Model Caching
```python
@st.cache_resource
def load_detector():
    return ProductDetector(confidence=0.45)
```
`@st.cache_resource` ensures the YOLO model is loaded **once** for the entire Streamlit process, not on every rerun. Confidence is updated separately via `detector.set_confidence()`.

#### `process_frame(frame)` — The Main Pipeline

```
frame (BGR numpy array)
  │
  ├─ detector.detect(frame)     → detections list
  ├─ grid_mapper.filter_shelf_detections()  → shelf-only detections
  ├─ grid_mapper.map_detections()           → grid_map 2-D list
  ├─ tracker.add_frame(grid_map)            → accepted? (occlusion guard)
  ├─ tracker.should_take_snapshot()         → auto-snapshot logic
  │   └─ tracker.take_snapshot()            → stable grid, sales diff
  │       └─ db.save_grid_snapshot()        → persist to SQLite + JSON
  ├─ draw_boxes(frame, shelf_dets)          → annotated frame
  ├─ grid_mapper.draw_grid_overlay()        → grid lines on frame
  ├─ engine.check_alerts()                  → alerts list
  └─ engine.get_recommendations()           → recs list
```

Returns: `(annotated_frame, grid_map, stock, rate, alerts, recs)`

#### Input Modes

**Webcam mode:**  
A `while run:` loop continuously reads frames from `cv2.VideoCapture(0)` and calls `process_frame()`. Streamlit's `st.empty()` placeholder is updated each iteration. Loop exits when the user unchecks the toggle.

**Upload image mode:**  
Image decoded from bytes using `cv2.imdecode()`. `process_frame()` is called once. A snapshot is forced immediately.

**Demo simulation mode:**  
`run_demo_step()` generates synthetic grids using a list of demo product names. Step 0 fills 85% of cells. Each subsequent step removes 1-3 random items to simulate sales. A snapshot is forced on every step so the dashboard updates visibly.

---

## 🔄 Data Flow Summary

```
[Camera / Image / Demo Grid]
         │
         ▼
   YOLOv8 Detection
         │
         ▼
   Shelf Region Filter  ← user-defined pixel bbox
         │
         ▼
   Grid Mapping (R × C)
         │
         ▼
   Occlusion Guard      ← rejects frames where occupancy drops >50%
         │
         ▼
   Rolling Frame Buffer (last N frames)
         │
         ▼
   Majority Vote        ← one "stable" grid per snapshot period
         │
         ▼
   Count-Capped Diff    ← detects sales/restocks, ignores rearrangements
         │
         ▼
   Alerts Engine        ← fires on low stock, high emptiness, fast depletion
         │
         ▼
   Recommendations      ← shelf placement suggestions (rule-based)
         │
         ▼
   SQLite + JSON        ← history, trends, heatmap
         │
         ▼
   Streamlit Dashboard  ← live display, charts, alerts, logs
```

---

## 🗂️ File Reference

| File | Role |
|---|---|
| `app.py` | Main Streamlit dashboard — UI & pipeline orchestration |
| `detector.py` | YOLOv8 wrapper — model load, inference, class filtering |
| `grid_mapper.py` | Shelf region definition & R×C grid construction |
| `tracker.py` | Rolling buffer, majority vote, occlusion guard, sales diff |
| `logic.py` | Alert rules, shelf recommendations, co-occurrence analysis |
| `database.py` | SQLite persistence layer for snapshots, sales, alerts |
| `utils.py` | Drawing helpers, time formatters, HTML grid/heatmap renderers |
| `main.py` | Standalone CLI alternative (runs without Streamlit) |
| `test_integration.py` | Integration tests for tracker and grid mapper logic |
| `requirements.txt` | Python dependency list |
| `stock.json` | Latest snapshot state (JSON sidecar, auto-updated) |
| `inventory.db` | SQLite database (auto-created on first run) |
| `yolov8n.pt` / `yolov8l.pt` | YOLO model weights (auto-downloaded if missing) |

---

## 💡 Key Design Decisions

### Why snapshots instead of per-frame diffs?
Per-frame diffs are noisy — objects flicker in and out of detection. Snapshots taken every N seconds give a stable, reliable view of what's actually on the shelf.

### Why majority voting?
A single frame can have a product temporarily blocked. By voting across 5 frames, one bad frame can't flip a "bottle" cell to "empty". This gives the system resilience to real-world occlusion without any complex tracking.

### Why count-capped diff for sales?
Movement is the #1 cause of false sales in position-aware systems. By checking whether the global item count actually decreased before looking at cell transitions, the system is immune to stock rearrangements — a very common retail activity.

### Why SQLite + JSON?
SQLite gives queryable history for the dashboard's History tab. The JSON sidecar gives a zero-dependency human-readable snapshot that external scripts or APIs can consume without connecting to SQLite.

### Why `@st.cache_resource` for the detector?
Loading a YOLO model takes ~2 seconds. Streamlit re-runs the script on every button click. Without caching, the model reloads constantly. `cache_resource` pins it to the Streamlit server process for the entire session.
