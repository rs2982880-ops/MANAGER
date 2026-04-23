/**
 * api.js — REST API client for the ShelfAI FastAPI backend.
 * 
 * All endpoints use fetch() (no external dependencies).
 * Base URL defaults to localhost:8000 (FastAPI dev server).
 */

const API_BASE = 'http://localhost:8000';

/**
 * POST /api/start-camera
 * @param {number|string} source - Device index (0,1,2) or IP camera URL
 */
export async function startCamera(source) {
  const res = await fetch(`${API_BASE}/api/start-camera`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source }),
  });
  return res.json();
}

/**
 * POST /api/stop-camera
 */
export async function stopCamera() {
  const res = await fetch(`${API_BASE}/api/stop-camera`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  });
  return res.json();
}

/**
 * GET /api/state — Full shelf state
 */
export async function getState() {
  const res = await fetch(`${API_BASE}/api/state`);
  return res.json();
}

/**
 * GET /api/cameras/available — Enumerate device cameras
 */
export async function getAvailableCameras() {
  const res = await fetch(`${API_BASE}/api/cameras/available`);
  return res.json();
}

/**
 * GET /api/settings
 */
export async function getSettings() {
  const res = await fetch(`${API_BASE}/api/settings`);
  return res.json();
}

/**
 * POST /api/settings — Update detection/grid settings
 */
export async function updateSettings(settings) {
  const res = await fetch(`${API_BASE}/api/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  return res.json();
}

/**
 * POST /api/resize — Change grid dimensions
 */
export async function resizeGrid(rows, cols) {
  const res = await fetch(`${API_BASE}/api/resize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ rows, cols }),
  });
  return res.json();
}

/**
 * POST /api/snapshot — Force a snapshot save
 */
export async function takeSnapshot() {
  const res = await fetch(`${API_BASE}/api/snapshot`, {
    method: 'POST',
  });
  return res.json();
}

/**
 * GET /api/history — Sales history from SQLite
 */
export async function getHistory() {
  const res = await fetch(`${API_BASE}/api/history`);
  return res.json();
}

/**
 * POST /api/set-mode — Switch between demo and production mode
 * @param {string} mode - "demo" or "production"
 */
export async function setMode(mode) {
  const res = await fetch(`${API_BASE}/api/set-mode`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode }),
  });
  return res.json();
}

/**
 * WebSocket URL for real-time streaming
 */
export const WS_URL = 'ws://localhost:8000/ws/stream';
