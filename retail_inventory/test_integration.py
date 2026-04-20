# -*- coding: utf-8 -*-
"""
Integration tests for the grid-based inventory system.
======================================================
Tests cover:
  1. Basic snapshot flow  (5 items â†’ 2 items, real YOLO-mapped grids)
  2. Alerts engine
  3. Heatmap + HTML renders
  4. Occlusion guard  (sudden empty frame is rejected)
  5. REARRANGEMENT   â†’ ZERO sales  (items move, count unchanged)
  6. DISAPPEARANCE   â†’ confirmed sales  (items globally gone)
  7. Mixed scenario  (sold + moved + unchanged items simultaneously)
"""
import sys
import io
# Ensure UTF-8 output on Windows terminals
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


import time
from grid_mapper import ShelfRegion, GridMapper
from tracker import SnapshotTracker, detect_sales, detect_movement
from logic import RestockingEngine
from database import Database
from utils import render_grid_html, render_heatmap_html


# ======================================================================
# Shared fixtures
# ======================================================================
shelf   = ShelfRegion(50, 30, 590, 440)
mapper  = GridMapper(shelf, rows=3, cols=5)
# occlusion_drop_threshold=0.0 disables the occlusion guard so Test 1
# can freely transition from a full shelf to a sparse one without the
# guard rejecting the low-occupancy frames.
tracker = SnapshotTracker(snapshot_interval_seconds=0.1, buffer_size=3,
                          occlusion_drop_threshold=0.0)
engine  = RestockingEngine(stock_threshold=3)


# ======================================================================
# TEST 1 â€” Basic snapshot flow  (5 items â†’ 2 items, YOLO-mapped grids)
# ======================================================================
print("=" * 60)
print("TEST 1: Basic snapshot flow")
print("=" * 60)

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

dets2 = [
    {"class": "bottle", "confidence": 0.9, "bbox": [100, 100, 150, 200]},
    {"class": "cup",    "confidence": 0.8, "bbox": [300, 100, 350, 200]},
]
grid2 = mapper.map_detections(dets2)
print(f"\nGrid 2 (2 items):")
for r, row in enumerate(grid2):
    print(f"  R{r}: {row}")

# Feed buffer_size+1 frames so grid2 fully overwrites the buffer
# (buffer_size = 3, so 4 frames ensures majority is all grid2)
for _ in range(4):
    tracker.add_frame(grid2)
    time.sleep(0.04)
time.sleep(0.15)
snap2 = tracker.take_snapshot()
print(f"\nSnapshot 2 stock: {snap2.item_counts}")

sales    = tracker.get_latest_sales()
restocks = tracker.get_latest_restocks()
print(f"\nPOSITION-BASED SALES:    {sales}")
print(f"POSITION-BASED RESTOCKS: {restocks}")
assert "bottle" in sales and sales["bottle"] >= 1, \
    f"Expected bottle sale, got {sales}"
assert "cup" in sales and sales["cup"] >= 1, \
    f"Expected cup sale, got {sales}"
print("âœ“ PASS")


# ======================================================================
# TEST 2 â€” Alerts engine
# ======================================================================
print("\n" + "=" * 60)
print("TEST 2: Alerts engine")
print("=" * 60)
alerts = engine.check_alerts(snap2.item_counts, tracker.get_sales_rate(), grid2)
print(f"Alerts ({len(alerts)}):")
for a in alerts:
    print(f"  [{a['severity'].upper()}] {a['item']} â€” {a['action']}")
print("âœ“ PASS")


# ======================================================================
# TEST 3 â€” Heatmap + HTML renders
# ======================================================================
print("\n" + "=" * 60)
print("TEST 3: Heatmap + HTML renders")
print("=" * 60)
hm     = tracker.compute_emptiness_heatmap()
html_g = render_grid_html(grid2)
html_h = render_heatmap_html(hm)
print(f"Heatmap: {len(hm)} rows Ã— {len(hm[0]) if hm else 0} cols")
print(f"Grid HTML:    {len(html_g)} chars")
print(f"Heatmap HTML: {len(html_h)} chars")
assert len(html_g) > 0, "Grid HTML is empty"
assert len(html_h) > 0, "Heatmap HTML is empty"
print("âœ“ PASS")


# ======================================================================
# TEST 4 â€” Occlusion guard  (sudden empty frame is rejected)
# ======================================================================
print("\n" + "=" * 60)
print("TEST 4: Occlusion guard")
print("=" * 60)
tracker2 = SnapshotTracker(
    snapshot_interval_seconds=0.1,
    buffer_size=5,
    occlusion_drop_threshold=0.5,
)
for _ in range(5):
    tracker2.add_frame(grid1)
    time.sleep(0.02)

empty_grid = [["empty"] * 5 for _ in range(3)]
accepted   = tracker2.add_frame(empty_grid)
print(f"Empty frame accepted? {accepted}  (expected: False)")
assert not accepted, "Sudden drop should be flagged as occlusion"

stats = tracker2.get_stats()
print(f"Frames skipped: {stats['frames_skipped']}  (expected: 1)")
assert stats["frames_skipped"] == 1, \
    f"Expected 1 skipped frame, got {stats['frames_skipped']}"
print("âœ“ PASS")


# ======================================================================
# TEST 5 â€” REARRANGEMENT â†’ ZERO sales  â† THE KEY NEW TEST
# ======================================================================
print("\n" + "=" * 60)
print("TEST 5: REARRANGEMENT â€” must produce ZERO sales")
print("=" * 60)
#
#  3 bottles exist in BOTH snapshots â€” just in DIFFERENT cells.
#
#  old row 0: [ bottle | bottle | bottle | empty  | empty  ]
#  new row 0: [ empty  | bottle | bottle | bottle | empty  ]
#                â†‘ disappeared                 â†‘ appeared
#
#  Naive cell-diff â†’ fires 1 fake "bottle sold" + 1 fake "bottle restock"
#  Count-capped    â†’ cap = 3 âˆ’ 3 = 0 â†’ NO sales, NO restocks
#
old_rearrange = [
    ["bottle", "bottle", "bottle", "empty",  "empty"],
    ["empty",  "empty",  "empty",  "empty",  "empty"],
    ["empty",  "empty",  "empty",  "empty",  "empty"],
]
new_rearrange = [
    ["empty",  "bottle", "bottle", "bottle", "empty"],
    ["empty",  "empty",  "empty",  "empty",  "empty"],
    ["empty",  "empty",  "empty",  "empty",  "empty"],
]

sales_r, restocks_r = detect_sales(old_rearrange, new_rearrange)
movement_r          = detect_movement(old_rearrange, new_rearrange)

print(f"  old row 0: {old_rearrange[0]}")
print(f"  new row 0: {new_rearrange[0]}")
print(f"  detect_sales()    â†’ sales={sales_r}, restocks={restocks_r}")
print(f"  detect_movement() â†’ {movement_r}")

assert sales_r.get("bottle", 0) == 0, \
    f"REARRANGEMENT fired a FALSE SALE! sales={sales_r}"
assert restocks_r.get("bottle", 0) == 0, \
    f"REARRANGEMENT fired a FALSE RESTOCK! restocks={restocks_r}"
assert movement_r.get("bottle") == "MOVED", \
    f"Expected MOVED, got {movement_r.get('bottle')}"
print("âœ“ PASS: Rearrangement â†’ 0 sales (classified MOVED)")


# ======================================================================
# TEST 6 â€” TRUE DISAPPEARANCE â†’ confirmed sales
# ======================================================================
print("\n" + "=" * 60)
print("TEST 6: DISAPPEARANCE â€” must produce confirmed sales")
print("=" * 60)
#
#  3 bottles before â†’ 1 bottle after.
#  Bottles at cells (0,1) and (0,2) vanish completely.
#  Expected: sales["bottle"] = 2
#
old_vanish = [
    ["bottle", "bottle", "bottle", "empty", "empty"],
    ["empty",  "empty",  "empty",  "empty", "empty"],
    ["empty",  "empty",  "empty",  "empty", "empty"],
]
new_vanish = [
    ["bottle", "empty",  "empty",  "empty", "empty"],
    ["empty",  "empty",  "empty",  "empty", "empty"],
    ["empty",  "empty",  "empty",  "empty", "empty"],
]

sales_v, restocks_v = detect_sales(old_vanish, new_vanish)
movement_v          = detect_movement(old_vanish, new_vanish)

print(f"  old row 0: {old_vanish[0]}")
print(f"  new row 0: {new_vanish[0]}")
print(f"  detect_sales()    â†’ sales={sales_v}, restocks={restocks_v}")
print(f"  detect_movement() â†’ {movement_v}")

assert sales_v.get("bottle", 0) == 2, \
    f"Expected 2 bottle sales, got {sales_v.get('bottle', 0)}"
assert movement_v.get("bottle") == "SOLD", \
    f"Expected SOLD, got {movement_v.get('bottle')}"
print("âœ“ PASS: Disappearance â†’ 2 confirmed sales (classified SOLD)")


# ======================================================================
# TEST 7 â€” Mixed scenario: sold + moved + unchanged simultaneously
# ======================================================================
print("\n" + "=" * 60)
print("TEST 7: Mixed scenario (sold + moved + unchanged)")
print("=" * 60)
#
#  cup:    2 â†’ 1    â†’ 1 SOLD
#  bottle: 2 â†’ 2    â†’ MOVED  (different cells)
#  apple:  1 â†’ 1    â†’ UNCHANGED  (same cell)
#
#            (0,0)    (0,1)    (0,2)    (0,3)     (0,4)
old_mixed = [
    ["cup",    "cup",    "bottle", "apple",  "empty"],
    ["bottle", "empty",  "empty",  "empty",  "empty"],
    ["empty",  "empty",  "empty",  "empty",  "empty"],
]
new_mixed = [
    ["cup",    "empty",  "empty",  "apple",  "bottle"],
    ["empty",  "empty",  "bottle", "empty",  "empty"],
    ["empty",  "empty",  "empty",  "empty",  "empty"],
]

sales_m, restocks_m = detect_sales(old_mixed, new_mixed)
movement_m          = detect_movement(old_mixed, new_mixed)

print(f"  detect_sales()    â†’ {sales_m}")
print(f"  detect_movement() â†’ {movement_m}")

assert sales_m.get("cup",    0) == 1, \
    f"Expected 1 cup sold,       got {sales_m}"
assert sales_m.get("bottle", 0) == 0, \
    f"Expected 0 bottle sales,   got {sales_m}"
assert sales_m.get("apple",  0) == 0, \
    f"Expected 0 apple sales,    got {sales_m}"
assert movement_m.get("cup")    == "SOLD",      \
    f"cup should be SOLD,        got {movement_m}"
assert movement_m.get("bottle") == "MOVED",     \
    f"bottle should be MOVED,    got {movement_m}"
assert movement_m.get("apple")  == "UNCHANGED", \
    f"apple should be UNCHANGED, got {movement_m}"
print("âœ“ PASS: Mixed â†’ cup SOLD / bottle MOVED / apple UNCHANGED")


# ======================================================================
print("\n" + "=" * 60)
print("=== ALL 7 TESTS PASSED ===")
print("=" * 60)

