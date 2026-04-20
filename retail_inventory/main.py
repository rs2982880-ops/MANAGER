"""
CLI entry-point — Grid + Snapshot edition.
==========================================
Supports:
  • image  — process a single shelf image, show grid map
  • webcam — live camera with grid overlay and auto-snapshots

Usage:
    python main.py --mode image --image_path shelf.jpg
    python main.py --mode webcam
"""

import argparse
import os
import sys
import time

import cv2

from detector import ProductDetector
from grid_mapper import ShelfRegion, GridMapper
from tracker import SnapshotTracker
from logic import RestockingEngine
from database import Database
from utils import draw_boxes, format_time_remaining


def print_grid(grid):
    """Pretty-print the shelf grid to the console."""
    if not grid:
        print("  (no grid data)")
        return
    col_w = 12
    header = "     " + "".join(f"{'C'+str(c):^{col_w}}" for c in range(len(grid[0])))
    print(header)
    print("     " + "-" * (col_w * len(grid[0])))
    for r, row in enumerate(grid):
        cells = "".join(f"{cell[:col_w-1]:^{col_w}}" for cell in row)
        print(f"  R{r} |{cells}")
    print()


def process_and_print(frame, detector, grid_mapper, tracker, engine, db):
    """Full pipeline: detect → grid → track → alert → print."""
    # 1. Detect + filter to shelf
    detections, _ = detector.detect(frame)
    shelf_dets = grid_mapper.filter_shelf_detections(detections)

    # 2. Map to grid
    grid_map = grid_mapper.map_detections(shelf_dets)

    # 3. Feed tracker
    accepted = tracker.add_frame(grid_map)

    # 4. Auto-snapshot
    snapshot_taken = False
    if tracker.should_take_snapshot():
        snap = tracker.take_snapshot()
        if snap:
            snapshot_taken = True
            db.save_grid_snapshot(snap.grid_map, snap.item_counts)
            sales = tracker.get_latest_sales()
            restocks = tracker.get_latest_restocks()
            if sales:
                db.log_sales(sales)
            if restocks:
                db.log_restocks(restocks)

    # 5. Draw
    annotated = draw_boxes(frame, shelf_dets)
    annotated = grid_mapper.draw_grid_overlay(annotated, grid_map)

    # 6. Gather data
    stock = tracker.get_current_stock()
    rate = tracker.get_sales_rate()
    alerts = engine.check_alerts(stock, rate, grid_map)
    recs = engine.get_recommendations(stock, rate)

    # 7. Print
    occ_tag = " [OCCLUDED]" if not accepted else ""
    snap_tag = " 📸 SNAPSHOT TAKEN" if snapshot_taken else ""
    print(f"\n{'='*55}")
    print(f"  Frame — {len(shelf_dets)} shelf objects{occ_tag}{snap_tag}")
    print(f"{'='*55}")

    print("\n🔲 GRID MAP:")
    print_grid(grid_map)

    print("📦 STOCK:")
    if stock:
        for item, cnt in sorted(stock.items()):
            r = rate.get(item, 0.0)
            print(f"   {item:20s}  count={cnt:3d}   rate={r:.1f}/hr")
    else:
        print("   (no items)")

    sales = tracker.get_latest_sales()
    if sales:
        print("\n🔄 SALES (last snapshot):")
        for item, qty in sales.items():
            print(f"   {item:20s}  {qty} sold")

    restocks = tracker.get_latest_restocks()
    if restocks:
        print("\n⬆️ RESTOCKED:")
        for item, qty in restocks.items():
            print(f"   {item:20s}  {qty} restocked")

    if alerts:
        print("\n🔔 ALERTS:")
        for a in alerts:
            tte = format_time_remaining(a.get("time_to_empty"))
            print(f"   [{a['severity'].upper():8s}] {a['item']} — "
                  f"stock={a['stock']}, rate={a['sales_rate']:.1f}/hr, "
                  f"depletes={tte}  →  {a['action']}")

    if recs:
        print("\n📋 RECOMMENDATIONS:")
        for r in recs:
            print(f"   {r['item']:20s}  {r['reason']}  →  {r['suggestion']}")

    stats = tracker.get_stats()
    print(f"\n📊 Frames: {stats['frames_processed']}  "
          f"Skipped: {stats['frames_skipped']}  "
          f"Snapshots: {stats['snapshots_taken']}  "
          f"Buffer: {stats['buffer_fill']}")
    print(f"{'='*55}")

    return annotated


# ----------------------------------------------------------------------
# Image mode
# ----------------------------------------------------------------------
def run_image(image_path, confidence, shelf_coords, rows, cols):
    if not os.path.exists(image_path):
        print(f"[ERROR] Image not found: {image_path}")
        sys.exit(1)

    frame = cv2.imread(image_path)
    if frame is None:
        print(f"[ERROR] Could not decode: {image_path}")
        sys.exit(1)

    detector = ProductDetector(confidence=confidence)
    shelf = ShelfRegion(*shelf_coords)
    mapper = GridMapper(shelf, rows, cols)
    tracker = SnapshotTracker(snapshot_interval_seconds=1, buffer_size=1)
    engine = RestockingEngine()
    db = Database()

    annotated = process_and_print(frame, detector, mapper, tracker, engine, db)

    out = f"annotated_{os.path.basename(image_path)}"
    cv2.imwrite(out, annotated)
    print(f"\n✅ Saved → {out}")

    try:
        cv2.imshow("Grid Detection", annotated)
        print("Press any key to close…")
        cv2.waitKey(0)
    except cv2.error:
        pass
    finally:
        try:
            cv2.destroyAllWindows()
        except cv2.error:
            pass


# ----------------------------------------------------------------------
# Webcam mode
# ----------------------------------------------------------------------
def run_webcam(confidence, shelf_coords, rows, cols, snap_interval):
    detector = ProductDetector(confidence=confidence)
    shelf = ShelfRegion(*shelf_coords)
    mapper = GridMapper(shelf, rows, cols)
    tracker = SnapshotTracker(
        snapshot_interval_seconds=snap_interval, buffer_size=5,
    )
    engine = RestockingEngine()
    db = Database()

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Cannot open webcam.")
        sys.exit(1)

    print("[INFO] Press 'q' to quit.\n")
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.3)
                continue

            annotated = process_and_print(
                frame, detector, mapper, tracker, engine, db,
            )

            try:
                cv2.imshow("Retail Inventory — press q", annotated)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
            except cv2.error:
                print("[ERROR] No GUI. Use:  streamlit run app.py")
                break
    finally:
        cap.release()
        try:
            cv2.destroyAllWindows()
        except cv2.error:
            pass


# ----------------------------------------------------------------------
# Entry
# ----------------------------------------------------------------------
if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Retail Inventory (CLI)")
    p.add_argument("--mode", choices=["image", "webcam"], default="image")
    p.add_argument("--image_path", default="shelf.jpg")
    p.add_argument("--confidence", type=float, default=0.45)
    p.add_argument("--shelf", type=int, nargs=4, default=[50, 30, 590, 440],
                   metavar=("X_MIN", "Y_MIN", "X_MAX", "Y_MAX"),
                   help="Shelf bounding box in pixels")
    p.add_argument("--rows", type=int, default=3, help="Grid rows")
    p.add_argument("--cols", type=int, default=5, help="Grid columns")
    p.add_argument("--snap_interval", type=int, default=30,
                   help="Seconds between snapshots (webcam only)")
    args = p.parse_args()

    if args.mode == "image":
        run_image(args.image_path, args.confidence, args.shelf,
                  args.rows, args.cols)
    else:
        run_webcam(args.confidence, args.shelf, args.rows, args.cols,
                   args.snap_interval)
