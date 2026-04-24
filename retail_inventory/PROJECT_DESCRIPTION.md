# AI-Powered Retail Shelf Monitoring and Inventory Management System

**Project Title:** ShelfAI — Intelligent Retail Inventory Tracking Using Computer Vision  
**Technology Stack:** Python · FastAPI · YOLOv8 · OpenCV · React · SQLite  
**Version:** 3.0 (Production-Grade Architecture)

---

## 1. Introduction

The AI-Powered Retail Shelf Monitoring and Inventory Management System (ShelfAI) is a real-time computer vision application designed to automate the process of tracking product stock levels on retail store shelves. By leveraging state-of-the-art object detection models and a purpose-built grid-based tracking engine, the system provides continuous, camera-based inventory monitoring without requiring manual stock-taking or integration with point-of-sale (POS) billing systems.

The system works by pointing a standard camera (webcam, USB, or IP camera) at a retail shelf. A YOLOv8 deep learning model identifies products in each video frame, and a custom grid-mapping algorithm translates those detections into a structured shelf representation — a rows-by-columns matrix where each cell contains either a product label or an "empty" marker. By comparing this grid over time using a multi-layer consensus pipeline, the system can infer when products have been picked up (sold), restocked, or simply rearranged, all without any barcode scanning, RFID tags, or billing system integration.

The architecture follows a modern client-server model: a FastAPI backend handles all AI processing, camera management, and data persistence, while a React-based dashboard provides real-time visualization of stock levels, sales activity, alerts, and shelf placement recommendations. Communication between the two layers uses WebSockets for low-latency frame streaming and REST APIs for configuration and historical data access.

This document provides a comprehensive technical and functional description of the system, suitable for academic project reports, technical presentations, and team onboarding.

---

## 2. Problem Statement

Traditional retail inventory management suffers from several critical inefficiencies that directly impact store profitability and customer satisfaction:

**Manual Inventory Tracking.** Most small and mid-size retail stores rely on periodic manual stock counts — employees physically walk through aisles, count products on each shelf, and record numbers on paper or spreadsheet systems. This process is time-consuming, error-prone, and typically performed only once or twice daily. Between counts, the store operates with outdated information about what is actually on its shelves.

**Lack of Real-Time Visibility.** Store managers have no way to know in real time which products are running low, which shelves are empty, or how quickly specific items are selling. By the time a manual count reveals that a popular product is out of stock, the store has already lost potential sales. Studies consistently show that out-of-stock events are one of the leading causes of lost revenue in retail, with some estimates suggesting 4–8% of total sales are lost due to stockouts.

**No Automated Stock Monitoring.** While large retail chains have invested in expensive RFID-based or weight-sensor-based smart shelf systems, these solutions are prohibitively expensive for small retailers. A single RFID reader can cost hundreds of dollars, and tagging every product adds ongoing operational overhead. There is a significant gap in the market for a low-cost, camera-based alternative that can provide similar functionality using commodity hardware.

**Inefficient Shelf Management.** Without data on which products sell fastest, which shelf positions attract the most attention, and which products are frequently co-purchased, retailers make shelf placement decisions based on intuition rather than evidence. This leads to suboptimal product arrangements that fail to maximize sales potential.

**Delayed Sales Detection.** In stores without integrated POS systems — or in scenarios where sales occur through multiple channels — there is no immediate feedback mechanism to detect that a product has been sold. The gap between a sale event and inventory awareness can be hours or even days.

ShelfAI addresses all of these problems by providing continuous, automated, camera-based shelf monitoring that detects stock changes in real time and presents actionable insights through a modern web dashboard.

---

## 3. Project Goal

The primary goal of this project is to build a complete, production-grade AI system that automates retail inventory tracking using computer vision, eliminating the need for manual stock counts, barcode scanners, RFID tags, or integration with billing systems.

### 3.1 Automating Inventory Tracking Using AI

The system replaces human stock-counting with a YOLOv8 deep learning model that continuously processes live camera feeds. Each frame is analyzed to identify and locate every product visible on the shelf. The detected products are mapped to a structured grid representation, and changes in this grid over time are interpreted as sales, restocks, or product rearrangements. This provides continuous inventory awareness with no human intervention required.

### 3.2 Using Standard Cameras Instead of Specialized Hardware

A core design principle of ShelfAI is accessibility. The system is designed to work with any standard camera — a laptop webcam, a USB webcam, or an IP camera (such as a smartphone running DroidCam). This means a small retailer can deploy the system for the cost of a single camera and a computer, rather than investing in expensive specialized sensors. The system also supports NVIDIA GPU acceleration for real-time inference on higher-resolution feeds.

### 3.3 Inferring Sales Without Billing Systems

Perhaps the most innovative aspect of the system is its ability to detect sales events purely from visual observation. By comparing successive grid snapshots and analyzing which cells transitioned from "occupied" to "empty," the system can infer that a product was picked up and presumably purchased. A multi-layer stabilization pipeline ensures that transient events — a customer's hand briefly blocking the camera, a product being temporarily moved during browsing — are not falsely counted as sales. Only sustained, confirmed changes trigger inventory updates.

### 3.4 Reducing Human Effort and Providing Actionable Insights

Beyond simple counting, the system generates automated restocking alerts when products fall below configurable thresholds, predicts time-to-depletion based on observed sales rates, and provides shelf placement recommendations based on demand patterns. These insights transform raw detection data into actionable business intelligence that helps store managers make informed decisions about restocking priorities, product placement, and promotional strategies.

---

## 4. System Overview

The ShelfAI processing pipeline transforms raw camera frames into structured inventory intelligence through five sequential stages:

```
Camera Frame → YOLO Detection → Grid Mapping → Multi-Layer Tracking → Dashboard
```

**Stage 1: Camera Capture.** A threaded camera worker continuously reads frames from the configured source (device camera or IP stream). The worker includes production-grade edge case handling: black frame detection, automatic reconnection with exponential backoff on camera disconnection, frame rate limiting to control CPU/GPU load, and state freezing to preserve the last known inventory when the camera goes offline.

**Stage 2: Object Detection.** Each captured frame is passed through a YOLOv8 large model running inference on the GPU (NVIDIA CUDA). The model identifies products in the frame, producing a list of detections each containing a class name, confidence score, and bounding box coordinates. An exclusion filter removes non-product detections (people, vehicles, animals) while a configurable allowlist controls which product classes are tracked.

**Stage 3: Grid Mapping.** The raw bounding box detections are translated into a structured rows-by-columns grid overlaying the shelf region. Each detection's center point is mapped to a specific grid cell. If multiple detections fall in the same cell, the one with the highest confidence score is retained. The output is a 2D matrix where each cell contains either a product label or "empty."

**Stage 4: Multi-Layer Tracking.** The grid is ingested into a two-stage consensus pipeline. Layer 1 (Frame Buffer) applies majority voting across the last 5 frames to produce a "stable grid" that filters out transient detection noise. Layer 2 (Decision Buffer) applies a second consensus across the last 3 stable grids to produce a "confirmed grid" that only reflects sustained changes. Sales are detected by comparing consecutive confirmed grids using displacement-aware, count-capped position differencing. Cell-level cooldowns prevent double-counting, and visibility validation rejects updates when detection coverage drops below 60%.

**Stage 5: Dashboard Visualization.** The React frontend receives real-time updates via WebSocket at approximately 20 FPS. The dashboard displays the live camera feed with grid overlay, KPI cards (net stock, total sold, alerts, empty cells), per-product stock summaries with sales rates, restocking alerts with severity classification, and AI-generated shelf placement recommendations.

---

## 5. Core Features

### 5.1 Real-Time Object Detection (YOLOv8)

The detection engine wraps Ultralytics YOLOv8 with automatic GPU acceleration. On startup, the system detects NVIDIA CUDA GPUs and moves the model to GPU memory for real-time inference. The system supports both pretrained COCO models (with a retail-specific class filter) and custom-trained models for specific product catalogs. Detection confidence thresholds are adjustable at runtime without model reload, and a hierarchical class filtering system ensures that non-product objects (people, furniture, vehicles) are never counted as inventory.

### 5.2 Grid-Based Shelf Mapping

Rather than tracking individual object identities across frames (which is computationally expensive and error-prone with identical products), the system divides the shelf into a configurable R×C grid. Each grid cell represents a physical shelf position, and the system tracks what product occupies each position. This approach naturally handles stores with many identical items (e.g., 20 bottles of the same brand) because it tracks positions, not identities.

### 5.3 Multi-Frame Stability (Two-Stage Consensus Pipeline)

Single-frame detection is inherently noisy — lighting changes, partial occlusions, and YOLO confidence fluctuations can cause a product to appear and disappear between consecutive frames. The system addresses this through a two-stage consensus pipeline:

- **Layer 1 — Frame Buffer (N=5):** Each incoming grid is added to a rolling buffer. A majority vote (threshold = ⌈N/2⌉) across all buffer frames produces a "stable grid." A cell's label must appear in at least 3 of 5 frames to be confirmed. This eliminates per-frame flicker.

- **Layer 2 — Decision Buffer (N=3):** Stable grids are pushed into a second rolling buffer. A second majority vote produces a "confirmed grid." This ensures that even coordinated noise across multiple frames (e.g., a person standing in front of the shelf for several seconds) doesn't trigger false inventory changes.

### 5.4 Change Tracking for Sales Detection

Sales are detected by comparing consecutive confirmed grids using a displacement-aware, count-capped differencing algorithm. For each product class, the system computes a "sale cap" equal to the global count decrease. If the count didn't decrease, ALL cell-level changes are classified as rearrangements (zero false sales). If the count did decrease, each cell transition is checked against adjacent cells — if the same product appeared nearby, it's classified as movement rather than a sale.

### 5.5 Count-Based Inventory Tracking

The system maintains cumulative tallies of sales and restocks per product, a rolling sales rate (units/hour) computed from the last 3 snapshots, stock history time series for trend visualization, and an emptiness heatmap showing which shelf positions are most frequently vacant.

### 5.6 Demo Mode vs. Production Mode

Two operational modes serve different use cases:

- **Demo Mode (⚡):** 10–30 second snapshot intervals for live demonstrations and testing. Provides rapid visual feedback to showcase system capabilities.
- **Production Mode (🏪):** 5–30 minute snapshot intervals for real-world deployment. Optimized for long-term stability with minimal false positives.

The snapshot interval adapts dynamically based on sales velocity — high sales activity shortens the interval for faster tracking, while low activity lengthens it to reduce unnecessary processing.

---

## 6. Sales Detection Logic

The sales detection algorithm is the most technically sophisticated component of the system. It must reliably distinguish between four distinct events that all appear similar at the pixel level:

1. **Actual Sale:** A customer picks up a product → the cell transitions from "product" to "empty" permanently.
2. **Browsing:** A customer picks up a product, examines it, and puts it back → the cell briefly shows "empty" then returns to "product."
3. **Rearrangement:** A store worker moves a product from position A to position B → one cell loses a product, another gains the same product.
4. **Occlusion:** A person or object temporarily blocks the camera's view of a product → the cell briefly shows "empty" but the product was never removed.

### How the System Handles Each Case

**Browsing** is handled by the Frame Buffer (Layer 1). The brief "empty" reading appears in only 1–2 of the 5 buffer frames. Since the majority vote requires 3/5 agreement, the momentary absence is filtered out.

**Rearrangement** is handled by the count-capped position diff. When a bottle moves from cell (0,0) to cell (0,2), the global bottle count remains unchanged. The algorithm computes `sale_cap = old_count - new_count = 0`. Since the cap is zero, the loop that scans for cell-level disappearances never executes. Zero false sales.

**Occlusion** is handled at two levels. Brief occlusions (hand blocking one cell) are filtered by majority voting. Severe occlusions (person standing in front of the camera) are caught by the occlusion guard, which discards frames where detected item count drops more than 50% below the rolling average. Additionally, the visibility validator rejects entire snapshots if the detection-to-expected ratio falls below 60%.

**Actual Sales** are confirmed only when all filters agree: the confirmed grid (Layer 2 consensus) shows a sustained cell transition, the global item count decreased, the cell is not within its cooldown period (15 seconds), and no displacement to an adjacent cell was detected.

### Additional Safety Mechanisms

- **Cell Cooldowns:** After a sale is confirmed in cell (r,c), that cell enters a 15-second cooldown. Any further "sale" detections in the same cell during this window are suppressed. This prevents a single product removal from being counted multiple times due to grid fluctuations during the transition period.

- **Minimum Change Threshold:** The system only triggers the expensive hardened comparison logic if the global stock change exceeds a configurable threshold (default: 2 items). Minor fluctuations (±1 item) due to detection noise are silently absorbed.

- **Fallback Count-Cap Logic:** If the displacement check is too aggressive (e.g., all disappearing cells have adjacent matches, but the global count genuinely decreased), the system falls back to trusting the count difference directly. This prevents under-counting in scenarios where items are simultaneously sold and rearranged.

---

## 7. System Architecture

### 7.1 Backend (Python — FastAPI + YOLOv8 + OpenCV)

The backend is a single Python process running FastAPI with Uvicorn, structured into 8 specialized modules:

| Module | Responsibility |
|--------|---------------|
| `main.py` | FastAPI application, REST endpoints, WebSocket handler |
| `camera.py` | Camera lifecycle service (start/stop/settings/persistence) |
| `camera_manager.py` | Threaded camera capture, edge case handling, ShelfCamera class |
| `detector.py` | YOLOv8 wrapper with GPU acceleration and class filtering |
| `grid_mapper.py` | Shelf region definition and R×C grid construction |
| `tracker.py` | Two-stage consensus pipeline, sales detection, cooldowns |
| `logic.py` | Restocking alerts engine and shelf recommendations |
| `storage.py` | JSON persistence with retry and in-memory fallback |
| `database.py` | SQLite persistence for sales events and snapshot history |

The backend exposes 11 REST endpoints (`/api/start-camera`, `/api/stop-camera`, `/api/state`, `/api/settings`, `/api/resize`, `/api/snapshot`, `/api/status`, `/api/stock`, `/api/alerts`, `/api/history`, `/api/set-mode`) and 1 WebSocket endpoint (`/ws/stream`) for real-time frame + state streaming at ~20 FPS.

### 7.2 Frontend (React + Zustand + TailwindCSS)

The frontend is a single-page application built with Vite + React, using Zustand for state management and TailwindCSS for styling. It consists of 9 components:

| Component | Function |
|-----------|----------|
| `Navbar` | Top bar with live status, FPS, mode indicator, countdown |
| `CameraPanel` | Camera source selection, start/stop, confidence slider |
| `SnapshotPanel` | Mode toggle (Demo/Production), countdown timer ring |
| `VideoFeed` | Live camera feed with zero-flicker `<img>` rendering |
| `GridOverlay` | SVG grid overlay on video (green=occupied, red=empty) |
| `KPICards` | Four metric cards: Net Stock, Sold, Alerts, Empty Cells |
| `StockPanel` | Per-product stock levels with status badges and sales rates |
| `AlertsPanel` | Restocking alerts with severity coloring |
| `RecommendationsPanel` | AI shelf placement recommendations |

### 7.3 Database Layer (SQLite + JSON)

Persistence uses a dual strategy:

- **SQLite (`inventory.db`):** Long-term storage with three tables — `grid_snapshots` (full grid + stock as JSON blobs), `sales_events` (individual sale/restock events with timestamps), and `alerts_log` (fired alerts). Supports daily, weekly, monthly, and yearly sales aggregation queries.

- **JSON (`stock.json` + `shelfai_state.json`):** Human-readable sidecar files for the latest snapshot state and camera configuration. These allow external scripts to read current stock without querying SQLite. The storage layer includes retry logic (3 attempts) with in-memory fallback if disk writes fail, and data validation on load to reject corrupted files.

### 7.4 Camera Input System

The system supports three camera input modes:

- **Device Camera:** Any USB webcam or built-in laptop camera, addressed by integer index (0, 1, 2).
- **IP Camera:** Network cameras or smartphone camera apps (e.g., DroidCam) addressed by URL.
- **Demo Simulation:** Synthetic grid generation for testing without a physical camera — fills 85% of cells with random products and simulates sales by removing 1–3 items per step.

The camera subsystem includes production-grade edge case handling: exponential backoff reconnection (1s→30s), black/whiteout frame detection, mass disappearance guarding, post-reconnect stabilization windows (10 frames), thread crash recovery with auto-restart (up to 5 attempts), and configurable FPS limiting.

---

## 8. Functionalities

### 8.1 Inventory Tracking

The system continuously tracks the stock level of every detected product class. Stock counts are derived from the stabilized grid (majority-voted across 5 frames), ensuring that momentary detection failures don't cause count fluctuations. Net stock is computed as current detection minus cumulative sales, providing an accurate running total. Stock history is maintained as a time series for trend visualization.

### 8.2 Sales Monitoring

Every confirmed sale event is recorded with timestamp, product name, and quantity. The system computes per-product sales rates (units/hour) from the last 3 snapshots and maintains cumulative sales tallies across the entire session. Sales data is persisted to SQLite for long-term analytics, with support for daily, weekly, monthly, and yearly aggregation queries.

### 8.3 Alerts

The restocking engine generates alerts based on three triggers:

| Trigger | Severity | Action |
|---------|----------|--------|
| Stock count ≤ 2 | Critical | "Restock immediately!" |
| Stock count < threshold (default 5) | Warning | "Restock soon" |
| Time-to-empty < 2 hours | Warning | "Restock within X time" |
| ≥ 50% of shelf cells empty | Critical | "Major restock needed!" |

System-level alerts are also generated when the camera goes offline (using frozen state) or during post-reconnect stabilization.

### 8.4 Recommendations

The system provides rule-based shelf placement recommendations:

- **High demand** (≥5 items/hr): "Place at eye level, centre shelf"
- **Low demand** (0–1 items/hr): "Reposition for visibility or bundle with popular items"
- **No movement** (0 sales, stock > 0): "Consider promotional placement or discount"
- **Co-occurrence** (items frequently seen together): "Place near [related item]"

---

## 9. Innovation and Uniqueness

### 9.1 Sales Detection Without Billing Integration

The system's ability to infer sales purely from visual observation — without any POS integration, barcode scanning, or RFID tagging — is its primary innovation. This makes it deployable in environments where traditional sales tracking infrastructure doesn't exist or is too expensive to install.

### 9.2 Multi-Layer Stabilization Logic

The two-stage consensus pipeline (Frame Buffer → Stable Grid → Decision Buffer → Confirmed Grid) with cell-level cooldowns and visibility validation represents a novel approach to handling the inherent noise in real-time object detection. This architecture eliminates the "flickering" problem that plagues simpler detection-to-inventory systems.

### 9.3 Grid-Based Tracking Instead of Object Identity

By tracking products by shelf position rather than individual object identity, the system elegantly handles the common retail scenario of multiple identical items. Traditional object tracking (SORT, DeepSORT) struggles when 15 identical bottles sit on a shelf — the system cannot maintain consistent IDs. Grid-based tracking sidesteps this entirely: it doesn't need to know *which* bottle was taken, only that cell (2,3) transitioned from "bottle" to "empty."

### 9.4 Low-Cost Deployment

The entire system runs on a single computer with a standard camera. No specialized hardware (RFID readers, weight sensors, smart shelf tags) is required. With GPU acceleration on a consumer-grade NVIDIA GPU (e.g., RTX 4050), the system achieves real-time inference at 12+ FPS.

### 9.5 Displacement-Aware Sales Detection

The count-capped, displacement-aware differencing algorithm is a unique contribution that prevents the most common source of false positives in position-based tracking systems: product rearrangement. By checking both global count changes and local adjacency before confirming a sale, the system achieves high precision even in active store environments.

---

## 10. Use Cases

### 10.1 Small Retail Stores

A corner shop or convenience store can deploy ShelfAI with a single USB camera pointed at its main product shelf. The store owner gains real-time visibility into stock levels, receives automatic alerts when products run low, and gets sales velocity data that helps with purchasing decisions — all without any manual counting or expensive POS integration.

### 10.2 Supermarkets

In a supermarket setting, multiple cameras can monitor different aisles or shelf sections. The multi-shelf architecture (ShelfCamera per section, CameraManager fleet controller) supports scaling to dozens of monitored areas. The sales analytics database provides aggregate demand data across all monitored sections.

### 10.3 Warehouses and Storage Facilities

Beyond retail, the system can monitor warehouse shelving to track parts inventory, detect when storage bins are depleted, and generate restocking alerts for supply chain operations. The grid-based approach works well for organized storage where products occupy defined positions.

### 10.4 Vending Machines and Display Cases

Any enclosed or semi-enclosed product display with a fixed camera viewpoint is an ideal deployment scenario. Vending machine operators can remotely monitor stock levels and optimize restocking routes.

---

## 11. Future Scope

### 11.1 Multi-Camera System with Centralized Dashboard

Extend the current architecture to support dozens of cameras across multiple store locations, with a centralized cloud dashboard for chain-wide inventory visibility. The existing CameraManager fleet controller provides the foundation for this scaling.

### 11.2 AI-Based Shelf Optimization

Use historical sales data and co-occurrence analysis to train a machine learning model that recommends optimal product placement. Move beyond rule-based recommendations to data-driven planogram optimization.

### 11.3 Demand Prediction and Forecasting

Apply time series forecasting (ARIMA, Prophet, or LSTM-based models) to the accumulated sales history to predict future demand by product and time period. This would enable proactive restocking before items run out.

### 11.4 Integration with Billing and ERP Systems

Add API integrations with popular POS systems and ERP platforms to cross-validate vision-based sales detection with actual transaction data, improving accuracy and enabling end-to-end inventory management.

### 11.5 Custom Product Training Pipeline

Provide an in-app workflow for store owners to train custom YOLO models on their specific product catalog. This would involve capturing training images directly from the shelf camera, labeling them with an integrated annotation tool, and fine-tuning the model without requiring ML expertise.

### 11.6 Mobile Application

Develop companion iOS/Android apps that provide push notifications for critical alerts, allow remote camera monitoring, and display KPI summaries optimized for mobile screens.

---

## 12. Conclusion

The AI-Powered Retail Shelf Monitoring and Inventory Management System represents a significant advancement in making intelligent inventory tracking accessible to businesses of all sizes. By combining state-of-the-art deep learning (YOLOv8) with a purpose-built multi-layer stabilization engine, the system achieves reliable, real-time inventory awareness using nothing more than a standard camera and a computer.

The system's ability to detect sales without billing system integration is particularly impactful for the millions of small retailers worldwide who lack sophisticated POS infrastructure. For these businesses, ShelfAI provides capabilities that were previously available only to large retail chains with significant technology budgets.

The technical architecture — featuring a two-stage consensus pipeline, displacement-aware sales detection, cell-level cooldowns, and comprehensive edge case handling — demonstrates that robust, production-grade inventory tracking can be achieved through careful algorithm design rather than expensive hardware. The system has been validated against real-world challenges including camera disconnections, partial and full occlusion, lighting variations, product rearrangements, and detection noise.

From a scalability perspective, the modular architecture (separate modules for detection, mapping, tracking, alerting, and persistence) and the multi-shelf camera management system provide a clear path to scaling from a single shelf to an entire store or chain of stores. The combination of SQLite for long-term analytics and JSON for real-time state exchange ensures both performance and data accessibility.

ShelfAI is not merely a proof of concept — it is a working, production-grade system that addresses a real market need with an innovative, low-cost approach. Its combination of technical sophistication and practical accessibility makes it a compelling solution for modern retail inventory management.

---

## Appendix: Technology Summary

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Object Detection | YOLOv8 Large (Ultralytics) | Real-time product identification |
| GPU Acceleration | NVIDIA CUDA + PyTorch | Real-time inference performance |
| Computer Vision | OpenCV | Frame capture, encoding, overlay drawing |
| Backend Framework | FastAPI + Uvicorn | REST API + WebSocket server |
| Frontend Framework | React 18 + Vite | Single-page dashboard application |
| State Management | Zustand | Lightweight React state store |
| Styling | TailwindCSS 3 | Utility-first CSS framework |
| Database | SQLite 3 | Long-term sales and snapshot persistence |
| Persistence | JSON files | Real-time state and configuration |
| Language (Backend) | Python 3.10+ | AI/ML ecosystem compatibility |
| Language (Frontend) | JavaScript (ES2022) | Modern browser compatibility |

---

*Document Version: 3.0 · Last Updated: April 2026*
