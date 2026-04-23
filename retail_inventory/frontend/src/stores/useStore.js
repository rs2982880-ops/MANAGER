/**
 * useStore.js — Zustand global state store for ShelfAI dashboard.
 *
 * All real-time data flows through this store. The WebSocket hook
 * updates it on every frame, and components subscribe to specific
 * slices to avoid unnecessary re-renders.
 */

import { create } from 'zustand';

const useStore = create((set, get) => ({
  // ── Connection State ─────────────────────────────────────────────
  connectionStatus: 'offline',  // 'offline' | 'connecting' | 'live'
  wsConnected: false,

  // ── Camera State ─────────────────────────────────────────────────
  cameraType: 'device',         // 'device' | 'ip'
  cameraSource: 0,              // int index or URL string
  ipUrl: 'http://192.168.0.101:4747/video',
  isStreaming: false,
  cameraStatus: 'idle',         // 'idle' | 'streaming' | 'error'
  cameraError: '',

  // ── Settings ─────────────────────────────────────────────────────
  confidence: 0.45,
  detectionOn: true,
  gridRows: 3,
  gridCols: 5,

  // ── Real-time Data (from WebSocket) ──────────────────────────────
  frame: null,                  // base64 JPEG data URL
  fps: 0,
  totalStock: 0,
  detectedStock: 0,
  totalSold: 0,
  totalSalesMap: {},
  numClasses: 0,
  lowCount: 0,
  emptyCount: 0,
  products: [],
  grid: [],
  alerts: [],
  recommendations: [],
  latestSales: {},
  latestRestocks: {},
  frameCount: 0,
  snapshotCount: 0,

  // ── Snapshot / Mode State ─────────────────────────────────────────
  snapshotInfo: { mode: 'demo', base_interval: 15, current_interval: 15, time_remaining: 0 },
  snapshotFlash: false,  // true briefly when snapshot fires

  // ── Actions ──────────────────────────────────────────────────────
  setConnectionStatus: (status) => set({ connectionStatus: status }),
  setWsConnected: (connected) => set({ wsConnected: connected }),

  setCameraType: (type) => set({ cameraType: type }),
  setCameraSource: (source) => set({ cameraSource: source }),
  setIpUrl: (url) => set({ ipUrl: url }),
  setIsStreaming: (streaming) => set({ isStreaming: streaming }),
  setCameraStatus: (status) => set({ cameraStatus: status }),
  setCameraError: (error) => set({ cameraError: error }),

  setConfidence: (conf) => set({ confidence: conf }),
  setDetectionOn: (on) => set({ detectionOn: on }),
  setGridRows: (rows) => set({ gridRows: rows }),
  setGridCols: (cols) => set({ gridCols: cols }),

  // Bulk update from WebSocket message
  updateFromWS: (data) => {
    const update = {};

    if (data.frame !== undefined) update.frame = data.frame;
    if (data.fps !== undefined) update.fps = data.fps;
    if (data.status !== undefined) {
      update.cameraStatus = data.status;
      update.isStreaming = data.status === 'streaming';
    }
    if (data.running !== undefined) update.isStreaming = data.running;
    if (data.total_stock !== undefined) update.totalStock = data.total_stock;
    if (data.detected_stock !== undefined) update.detectedStock = data.detected_stock;
    if (data.total_sold !== undefined) update.totalSold = data.total_sold;
    if (data.total_sales_map !== undefined) update.totalSalesMap = data.total_sales_map;
    if (data.num_classes !== undefined) update.numClasses = data.num_classes;
    if (data.low_count !== undefined) update.lowCount = data.low_count;
    if (data.empty_count !== undefined) update.emptyCount = data.empty_count;
    if (data.products !== undefined) update.products = data.products;
    if (data.grid !== undefined) update.grid = data.grid;
    if (data.alerts !== undefined) update.alerts = data.alerts;
    if (data.recommendations !== undefined) update.recommendations = data.recommendations;
    if (data.latest_sales !== undefined) update.latestSales = data.latest_sales;
    if (data.latest_restocks !== undefined) update.latestRestocks = data.latest_restocks;
    if (data.frame_count !== undefined) update.frameCount = data.frame_count;
    if (data.snapshot_count !== undefined) update.snapshotCount = data.snapshot_count;
    if (data.grid_rows !== undefined) update.gridRows = data.grid_rows;
    if (data.grid_cols !== undefined) update.gridCols = data.grid_cols;
    if (data.confidence !== undefined) update.confidence = data.confidence;
    if (data.detection_on !== undefined) update.detectionOn = data.detection_on;
    if (data.snapshot_info !== undefined) update.snapshotInfo = data.snapshot_info;

    // Detect new snapshot (count increased) → trigger flash
    if (data.snapshot_count !== undefined) {
      const prev = get().snapshotCount;
      if (data.snapshot_count > prev) {
        update.snapshotFlash = true;
        setTimeout(() => set({ snapshotFlash: false }), 1500);
      }
    }

    // Only update connection status if we're getting data
    if (data.type === 'frame') {
      update.connectionStatus = 'live';
    } else if (data.type === 'heartbeat') {
      update.connectionStatus = 'live';
    }

    set(update);
  },

  // Reset all data
  reset: () => set({
    frame: null,
    fps: 0,
    totalStock: 0,
    detectedStock: 0,
    totalSold: 0,
    totalSalesMap: {},
    numClasses: 0,
    lowCount: 0,
    emptyCount: 0,
    products: [],
    grid: [],
    alerts: [],
    recommendations: [],
    latestSales: {},
    latestRestocks: {},
    frameCount: 0,
    snapshotCount: 0,
    snapshotInfo: { mode: 'demo', base_interval: 15, current_interval: 15, time_remaining: 0 },
    snapshotFlash: false,
  }),
}));

export default useStore;
