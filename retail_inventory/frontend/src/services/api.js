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

// ═══════════════════════════════════════════════════════════════════════
// Daily Sales Log — Human-corrected, editable sales layer
// ═══════════════════════════════════════════════════════════════════════

/** GET /api/sales/daily — Fetch daily sales log + summary */
export async function getDailySales(days = 30) {
  const res = await fetch(`${API_BASE}/api/sales/daily?days=${days}`);
  return res.json();
}

/** POST /api/sales/daily — Add or update a daily sale record */
export async function addDailySale(date, item, quantity, notes = '') {
  const res = await fetch(`${API_BASE}/api/sales/daily`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ date, item, quantity, notes }),
  });
  return res.json();
}

/** PUT /api/sales/daily/:id — Update with audit logging */
export async function updateDailySale(id, quantity, notes = '', reason = '') {
  const res = await fetch(`${API_BASE}/api/sales/daily/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ quantity, notes, reason }),
  });
  return res.json();
}

/** DELETE /api/sales/daily/:id — Delete a record */
export async function deleteDailySale(id) {
  const res = await fetch(`${API_BASE}/api/sales/daily/${id}`, {
    method: 'DELETE',
  });
  return res.json();
}

/** GET /api/sales/audit — Fetch change history */
export async function getAuditLog(days = 30, item = null) {
  const params = new URLSearchParams({ days });
  if (item) params.set('item', item);
  const res = await fetch(`${API_BASE}/api/sales/audit?${params}`);
  return res.json();
}

/** POST /api/sales/daily/:id/undo — Revert last change */
export async function undoSaleChange(id) {
  const res = await fetch(`${API_BASE}/api/sales/daily/${id}/undo`, {
    method: 'POST',
  });
  return res.json();
}

/** POST /api/sales/lock/:date — Lock a day */
export async function lockDay(date) {
  const res = await fetch(`${API_BASE}/api/sales/lock/${date}`, {
    method: 'POST',
  });
  return res.json();
}

/** DELETE /api/sales/lock/:date — Unlock a day */
export async function unlockDay(date) {
  const res = await fetch(`${API_BASE}/api/sales/lock/${date}`, {
    method: 'DELETE',
  });
  return res.json();
}

/** GET /api/sales/locks — Get locked dates */
export async function getLockedDays() {
  const res = await fetch(`${API_BASE}/api/sales/locks`);
  return res.json();
}

/** POST /api/sales/daily/bulk — Bulk update records */
export async function bulkUpdateSales(updates, reason = 'Bulk update') {
  const res = await fetch(`${API_BASE}/api/sales/daily/bulk`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ updates, reason }),
  });
  return res.json();
}

/**
 * WebSocket URL for real-time streaming
 */
export const WS_URL = 'ws://localhost:8000/ws/stream';

