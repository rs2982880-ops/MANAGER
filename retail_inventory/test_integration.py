"""Quick integration test for the grid-based inventory system."""
import time
from grid_mapper import ShelfRegion, GridMapper
from tracker import SnapshotTracker
from logic import RestockingEngine
from database import Database
from utils import render_grid_html, render_heatmap_html

shelf = ShelfRegion(50, 30, 590, 440)
mapper = GridMapper(shelf, rows=3, cols=5)
tracker = SnapshotTracker(snapshot_interval_seconds=0.1, buffer_size=3)
engine = RestockingEngine(stock_threshold=3)

# --- Snapshot 1: 5 items on shelf ---
dets1 = [
    {"class": "bottle", "confidence": 0.9,  "bbox": [100, 100, 150, 200]},
    {"class": "bottle", "confidence": 0.85, "bbox": [200, 100, 250, 200]},
    {"class": "cup",    "confidence": 0.8,  "bbox": [300, 100, 350, 200]},
    {"class": "bottle", "confidence": 0.7,  "bbox": [100, 250, 150, 350]},
    {"class": "cup",    "confidence": 0.75, "bbox": [400, 250, 450, 350]},
]
grid1 = mapper.map_detections(dets1)
print("Grid 1 (5 items):")
for r, row in enumerate(grid1):
    print(f"  R{r}: {row}")

for _ in range(3):
    tracker.add_frame(grid1)
    time.sleep(0.04)
time.sleep(0.15)
snap1 = tracker.take_snapshot()
print(f"\nSnapshot 1 stock: {snap1.item_counts}")
print(f"Occupied: {snap1.total_occupied()}, Empty: {snap1.total_empty()}")

# --- Snapshot 2: 3 items removed (sales) ---
dets2 = [
    {"class": "bottle", "confidence": 0.9, "bbox": [100, 100, 150, 200]},
    {"class": "cup",    "confidence": 0.8, "bbox": [300, 100, 350, 200]},
]
grid2 = mapper.map_detections(dets2)
print(f"\nGrid 2 (2 items):")
for r, row in enumerate(grid2):
    print(f"  R{r}: {row}")

for _ in range(3):
    tracker.add_frame(grid2)
    time.sleep(0.04)
time.sleep(0.15)
snap2 = tracker.take_snapshot()
print(f"\nSnapshot 2 stock: {snap2.item_counts}")

# --- Position-based sales ---
sales = tracker.get_latest_sales()
restocks = tracker.get_latest_restocks()
print(f"\nPOSITION-BASED SALES:    {sales}")
print(f"POSITION-BASED RESTOCKS: {restocks}")
assert "bottle" in sales and sales["bottle"] >= 1, "Should detect bottle sales"
assert "cup" in sales and sales["cup"] >= 1, "Should detect cup sales"

# --- Alerts ---
alerts = engine.check_alerts(snap2.item_counts, tracker.get_sales_rate(), grid2)
print(f"\nAlerts ({len(alerts)}):")
for a in alerts:
    print(f"  [{a['severity'].upper()}] {a['item']} — {a['action']}")

# --- Heatmap ---
hm = tracker.compute_emptiness_heatmap()
print(f"\nHeatmap: {len(hm)} rows x {len(hm[0]) if hm else 0} cols")

# --- HTML renders ---
html_g = render_grid_html(grid2)
html_h = render_heatmap_html(hm)
print(f"Grid HTML: {len(html_g)} chars")
print(f"Heatmap HTML: {len(html_h)} chars")

# --- Occlusion test ---
print("\n--- Occlusion test ---")
tracker2 = SnapshotTracker(snapshot_interval_seconds=0.1, buffer_size=5,
                            occlusion_drop_threshold=0.5)
# Fill with normal grid (5 items)
for _ in range(5):
    tracker2.add_frame(grid1)
    time.sleep(0.02)

# Sudden drop to 0 (person blocking camera)
empty_grid = [["empty"] * 5 for _ in range(3)]
accepted = tracker2.add_frame(empty_grid)
print(f"Empty frame accepted? {accepted}  (should be False = blocked)")
assert not accepted, "Sudden drop should be flagged as occlusion"

stats = tracker2.get_stats()
print(f"Frames skipped: {stats['frames_skipped']} (should be 1)")

print("\n=== ALL TESTS PASSED ===")
