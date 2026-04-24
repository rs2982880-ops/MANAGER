/**
 * SalesPage.jsx — Premium daily sales management with audit tracking.
 *
 * Features: KPI cards, edit modal with reason/preview, audit history,
 * toast notifications, bulk edit, lock/unlock days, undo.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import {
  getDailySales, addDailySale, updateDailySale, deleteDailySale,
  getAuditLog, undoSaleChange, lockDay, unlockDay, bulkUpdateSales,
} from '../services/api';

// ═══════════════════════════════════════════════════════════════════
// Hooks & Helpers
// ═══════════════════════════════════════════════════════════════════
function useAnimatedCount(target, duration = 600) {
  const [display, setDisplay] = useState(0);
  const raf = useRef(null);
  useEffect(() => {
    const start = display;
    const diff = target - start;
    if (diff === 0) return;
    const t0 = performance.now();
    function tick(now) {
      const p = Math.min((now - t0) / duration, 1);
      setDisplay(Math.round(start + diff * (1 - Math.pow(1 - p, 3))));
      if (p < 1) raf.current = requestAnimationFrame(tick);
    }
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [target]);
  return display;
}

// ═══════════════════════════════════════════════════════════════════
// Toast System
// ═══════════════════════════════════════════════════════════════════
function ToastContainer({ toasts, onDismiss }) {
  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`flex items-center gap-3 px-4 py-3 rounded-xl border backdrop-blur-xl
                      shadow-2xl animate-slide-up text-xs font-semibold max-w-xs
                      ${t.type === 'success'
                        ? 'bg-emerald-500/15 border-emerald-500/25 text-emerald-300'
                        : 'bg-red-500/15 border-red-500/25 text-red-300'}`}
          onClick={() => onDismiss(t.id)}
        >
          <span className="text-base">{t.type === 'success' ? '✅' : '❌'}</span>
          <span>{t.message}</span>
        </div>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// KPI Card
// ═══════════════════════════════════════════════════════════════════
function SalesKPI({ icon, label, value, accent }) {
  const animated = useAnimatedCount(value);
  return (
    <div className="kpi-card group relative overflow-hidden">
      <div className="absolute inset-0 opacity-[0.03] rounded-2xl"
        style={{ background: `radial-gradient(circle at 50% 0%, ${accent}, transparent 70%)` }} />
      <div className="text-xl mb-1.5 opacity-70">{icon}</div>
      <div className="text-3xl font-black text-gray-100 tabular-nums tracking-tight">{animated}</div>
      <div className="text-[0.6rem] text-gray-500 font-bold uppercase tracking-widest mt-1.5">{label}</div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Edit Modal
// ═══════════════════════════════════════════════════════════════════
const REASONS = ['Manual count', 'AI correction', 'Return/refund', 'Damaged goods', 'Stock take', 'Other'];

function EditModal({ record, onSave, onCancel }) {
  const [qty, setQty] = useState(String(record.quantity));
  const [notes, setNotes] = useState(record.notes || '');
  const [reason, setReason] = useState('');
  const diff = parseInt(qty, 10) - record.quantity;
  const isValid = !isNaN(parseInt(qty, 10)) && parseInt(qty, 10) >= 0 && reason;

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center" onClick={onCancel}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div className="relative glass-panel p-6 w-full max-w-md animate-fade-in" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-base font-bold text-gray-100 mb-1">Update Sale Record</h3>
        <p className="text-[0.65rem] text-gray-500 mb-5">{record.item} · {record.date}</p>

        {/* Current vs New preview */}
        <div className="flex items-center justify-center gap-4 mb-5 py-3 rounded-xl bg-white/[0.02] border border-white/[0.04]">
          <div className="text-center">
            <div className="text-[0.6rem] text-gray-600 uppercase tracking-wider mb-1">Current</div>
            <div className="text-2xl font-black text-gray-400 tabular-nums">{record.quantity}</div>
          </div>
          <div className="text-xl text-gray-600">→</div>
          <div className="text-center">
            <div className="text-[0.6rem] text-gray-600 uppercase tracking-wider mb-1">New</div>
            <div className="text-2xl font-black text-gray-100 tabular-nums">{qty || '—'}</div>
          </div>
          {diff !== 0 && !isNaN(diff) && (
            <div className={`px-2.5 py-1 rounded-lg text-xs font-bold ${diff > 0 ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>
              {diff > 0 ? '+' : ''}{diff}
            </div>
          )}
        </div>

        {/* Quantity input */}
        <label className="label-dark">New Quantity</label>
        <input type="number" value={qty} min="0" onChange={(e) => setQty(e.target.value)}
          className="input-dark mb-3" autoFocus />

        {/* Reason selector */}
        <label className="label-dark">Reason for change *</label>
        <div className="flex flex-wrap gap-1.5 mb-3">
          {REASONS.map((r) => (
            <button key={r} onClick={() => setReason(r)}
              className={`px-2.5 py-1 rounded-lg text-[0.6rem] font-semibold border transition-all
                ${reason === r
                  ? 'bg-accent/15 border-accent/30 text-accent'
                  : 'bg-white/[0.02] border-white/[0.06] text-gray-500 hover:text-gray-300'}`}>
              {r}
            </button>
          ))}
        </div>

        {/* Notes */}
        <label className="label-dark">Notes</label>
        <input type="text" value={notes} placeholder="optional details"
          onChange={(e) => setNotes(e.target.value)} className="input-dark mb-5" />

        {/* Actions */}
        <div className="flex gap-2">
          <button onClick={onCancel}
            className="flex-1 py-2.5 rounded-xl text-xs font-bold bg-white/[0.03] text-gray-500 border border-white/[0.06] hover:text-gray-300 transition-all">
            Cancel
          </button>
          <button onClick={() => isValid && onSave(parseInt(qty, 10), notes, reason)}
            disabled={!isValid}
            className={`flex-1 py-2.5 rounded-xl text-xs font-bold transition-all
              ${isValid
                ? 'bg-accent/15 text-accent border border-accent/30 hover:bg-accent/25'
                : 'bg-white/[0.02] text-gray-700 border border-white/[0.04] cursor-not-allowed'}`}>
            Save Changes
          </button>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Audit History Panel
// ═══════════════════════════════════════════════════════════════════
function AuditPanel({ onClose }) {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getAuditLog(30).then((d) => { setLogs(d.logs || []); setLoading(false); });
  }, []);

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
      <div className="relative glass-panel p-6 w-full max-w-2xl max-h-[80vh] flex flex-col animate-fade-in"
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-bold text-gray-100">Change History</h3>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 text-lg">✕</button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="text-center py-8 text-sm text-gray-600">Loading...</div>
          ) : logs.length === 0 ? (
            <div className="text-center py-8 text-sm text-gray-600">No changes recorded yet</div>
          ) : (
            <div className="space-y-1.5">
              {logs.map((l) => (
                <div key={l.id} className="flex items-center gap-3 px-4 py-2.5 rounded-xl bg-white/[0.02] border border-white/[0.03] text-xs">
                  <div className="w-20 text-gray-500 font-mono shrink-0">{l.date}</div>
                  <div className="font-semibold text-gray-300 w-24 shrink-0">{l.item}</div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-red-400 tabular-nums">{l.old_value}</span>
                    <span className="text-gray-600">→</span>
                    <span className="text-emerald-400 tabular-nums">{l.new_value}</span>
                  </div>
                  <div className="flex-1 text-gray-600 italic truncate">{l.reason || '—'}</div>
                  <div className="text-[0.55rem] text-gray-700 shrink-0">{l.timestamp?.slice(11, 19)}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Main Sales Page
// ═══════════════════════════════════════════════════════════════════
export default function SalesPage() {
  const [records, setRecords] = useState([]);
  const [summary, setSummary] = useState({ today: 0, week: 0, month: 0, total: 0 });
  const [loading, setLoading] = useState(true);
  const [toasts, setToasts] = useState([]);

  // Modal state
  const [editRecord, setEditRecord] = useState(null);
  const [showAudit, setShowAudit] = useState(false);

  // Bulk select
  const [selected, setSelected] = useState(new Set());
  const [bulkQty, setBulkQty] = useState('');

  // New row form
  const [showAdd, setShowAdd] = useState(false);
  const [newDate, setNewDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [newItem, setNewItem] = useState('');
  const [newQty, setNewQty] = useState('');
  const [newNotes, setNewNotes] = useState('');

  // Delete confirm
  const [deleteId, setDeleteId] = useState(null);

  // ── Toast helpers ──
  const toast = (message, type = 'success') => {
    const id = Date.now();
    setToasts((p) => [...p, { id, message, type }]);
    setTimeout(() => setToasts((p) => p.filter((t) => t.id !== id)), 3500);
  };
  const dismissToast = (id) => setToasts((p) => p.filter((t) => t.id !== id));

  // ── Fetch ──
  const fetchData = useCallback(async () => {
    try {
      const data = await getDailySales(30);
      if (data.ok) {
        setRecords(data.records || []);
        setSummary(data.summary || { today: 0, week: 0, month: 0, total: 0 });
      }
    } catch (e) { console.error('Fetch failed:', e); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { fetchData(); }, [fetchData]);

  // ── Add ──
  const handleAdd = async () => {
    if (!newItem.trim() || !newQty) return;
    const qty = parseInt(newQty, 10);
    if (isNaN(qty) || qty < 0) return;
    const res = await addDailySale(newDate, newItem.trim(), qty, newNotes);
    if (res.ok) {
      setNewItem(''); setNewQty(''); setNewNotes(''); setShowAdd(false);
      toast(`Added ${newItem.trim()} × ${qty}`);
      fetchData();
    } else { toast(res.message || 'Failed to add', 'error'); }
  };

  // ── Edit (modal save) ──
  const handleSaveEdit = async (qty, notes, reason) => {
    const rec = editRecord;
    setEditRecord(null);
    const res = await updateDailySale(rec.id, qty, notes, reason);
    if (res.ok) {
      toast(`${rec.item}: ${res.old_value} → ${res.new_value}`);
      fetchData();
    } else { toast(res.message || 'Update failed', 'error'); }
  };

  // ── Delete ──
  const confirmDelete = async (id) => {
    setDeleteId(null);
    const res = await deleteDailySale(id);
    if (res.ok) { toast('Record deleted'); fetchData(); }
    else { toast(res.message || 'Delete failed', 'error'); }
  };

  // ── Undo ──
  const handleUndo = async (id) => {
    const res = await undoSaleChange(id);
    if (res.ok) { toast(`Reverted to ${res.reverted_to}`); fetchData(); }
    else { toast(res.message || 'Undo failed', 'error'); }
  };

  // ── Lock/Unlock ──
  const toggleLock = async (date, isLocked) => {
    const res = isLocked ? await unlockDay(date) : await lockDay(date);
    if (res.ok) { toast(res.message); fetchData(); }
    else { toast(res.message || 'Failed', 'error'); }
  };

  // ── Bulk update ──
  const handleBulkUpdate = async () => {
    const qty = parseInt(bulkQty, 10);
    if (isNaN(qty) || qty < 0 || selected.size === 0) return;
    const updates = [...selected].map((id) => ({ id, quantity: qty }));
    const res = await bulkUpdateSales(updates, 'Bulk update');
    if (res.ok) {
      toast(`Updated ${res.success} records`);
      setSelected(new Set()); setBulkQty('');
      fetchData();
    }
  };

  const toggleSelect = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  // Group records by date for lock buttons
  const dates = [...new Set(records.map((r) => r.date))];

  return (
    <div className="flex-1 flex flex-col p-6 gap-6 overflow-hidden animate-fade-in">
      {/* Toasts */}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />

      {/* Edit Modal */}
      {editRecord && <EditModal record={editRecord} onSave={handleSaveEdit} onCancel={() => setEditRecord(null)} />}

      {/* Audit Panel */}
      {showAudit && <AuditPanel onClose={() => setShowAudit(false)} />}

      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-100 tracking-tight">Sales Log</h1>
          <p className="text-xs text-gray-600 mt-0.5">Human-verified daily sales records</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowAudit(true)}
            className="px-3 py-2 rounded-xl text-[0.65rem] font-bold bg-white/[0.03] text-gray-500 border border-white/[0.06] hover:text-gray-300 transition-all">
            📜 History
          </button>
          <button onClick={() => setShowAdd(!showAdd)} className="btn-primary flex items-center gap-2 text-xs">
            <span className="text-base leading-none">{showAdd ? '✕' : '＋'}</span>
            {showAdd ? 'Cancel' : 'Add Record'}
          </button>
        </div>
      </div>

      {/* ── KPI Cards ── */}
      <div className="grid grid-cols-4 gap-4">
        <SalesKPI icon="📊" label="Today" value={summary.today} accent="#10b981" />
        <SalesKPI icon="📅" label="This Week" value={summary.week} accent="#06b6d4" />
        <SalesKPI icon="📆" label="This Month" value={summary.month} accent="#8b5cf6" />
        <SalesKPI icon="🏆" label="All Time" value={summary.total} accent="#f59e0b" />
      </div>

      {/* ── Bulk Actions Bar ── */}
      {selected.size > 0 && (
        <div className="glass-panel px-4 py-3 flex items-center gap-3 animate-slide-up">
          <span className="text-xs font-bold text-accent">{selected.size} selected</span>
          <input type="number" value={bulkQty} min="0" placeholder="Set qty"
            onChange={(e) => setBulkQty(e.target.value)}
            className="input-dark w-24 py-1 text-center text-xs" />
          <button onClick={handleBulkUpdate}
            className="px-3 py-1.5 rounded-lg text-[0.65rem] font-bold bg-accent/10 text-accent border border-accent/20 hover:bg-accent/20 transition-all">
            Apply to All
          </button>
          <button onClick={() => setSelected(new Set())}
            className="px-3 py-1.5 rounded-lg text-[0.65rem] font-bold bg-white/[0.03] text-gray-500 border border-white/[0.06] hover:text-gray-300 transition-all">
            Clear
          </button>
        </div>
      )}

      {/* ── Add Row Form ── */}
      {showAdd && (
        <div className="glass-panel p-4 animate-slide-up">
          <div className="text-[0.65rem] font-bold text-gray-500 uppercase tracking-widest mb-3">New Daily Sale</div>
          <div className="grid grid-cols-12 gap-3">
            <div className="col-span-3">
              <label className="label-dark">Date</label>
              <input type="date" value={newDate} onChange={(e) => setNewDate(e.target.value)} className="input-dark" />
            </div>
            <div className="col-span-3">
              <label className="label-dark">Product</label>
              <input type="text" value={newItem} placeholder="e.g. maggi" onChange={(e) => setNewItem(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAdd()} className="input-dark" autoFocus />
            </div>
            <div className="col-span-2">
              <label className="label-dark">Quantity</label>
              <input type="number" value={newQty} placeholder="0" min="0" onChange={(e) => setNewQty(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAdd()} className="input-dark" />
            </div>
            <div className="col-span-3">
              <label className="label-dark">Notes</label>
              <input type="text" value={newNotes} placeholder="optional" onChange={(e) => setNewNotes(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAdd()} className="input-dark" />
            </div>
            <div className="col-span-1 flex items-end">
              <button onClick={handleAdd} className="btn-primary w-full py-2 text-xs">Save</button>
            </div>
          </div>
        </div>
      )}

      {/* ── Lock Day Controls ── */}
      {dates.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {dates.map((d) => {
            const isLocked = records.find((r) => r.date === d)?.locked;
            return (
              <button key={d} onClick={() => toggleLock(d, isLocked)}
                className={`px-2.5 py-1 rounded-lg text-[0.6rem] font-bold border transition-all
                  ${isLocked
                    ? 'bg-amber-500/10 border-amber-500/20 text-amber-400'
                    : 'bg-white/[0.02] border-white/[0.05] text-gray-600 hover:text-gray-400'}`}>
                {isLocked ? '🔒' : '🔓'} {d}
              </button>
            );
          })}
        </div>
      )}

      {/* ── Data Table ── */}
      <div className="flex-1 min-h-0 glass-panel overflow-hidden flex flex-col">
        <div className="grid grid-cols-12 gap-2 px-5 py-3 border-b border-white/[0.04]
                        text-[0.6rem] font-bold text-gray-500 uppercase tracking-widest">
          <div className="col-span-1">☐</div>
          <div className="col-span-2">Date</div>
          <div className="col-span-2">Product</div>
          <div className="col-span-2">Quantity</div>
          <div className="col-span-3">Notes</div>
          <div className="col-span-2 text-right">Actions</div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="text-sm text-gray-600">Loading...</div>
            </div>
          ) : records.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="text-4xl opacity-15 mb-3">📋</div>
              <p className="text-sm text-gray-600">No sales records yet</p>
            </div>
          ) : (
            records.map((rec, idx) => (
              <div key={rec.id}
                className={`sales-table-row grid grid-cols-12 gap-2 px-5 py-3 items-center
                  border-b border-white/[0.02] transition-all duration-200 hover:bg-white/[0.02] group
                  ${selected.has(rec.id) ? 'bg-accent/[0.04] border-accent/10' : ''}
                  ${rec.locked ? 'opacity-60' : ''}`}
                style={{ animationDelay: `${idx * 20}ms` }}>

                {/* Checkbox */}
                <div className="col-span-1">
                  <input type="checkbox" checked={selected.has(rec.id)}
                    onChange={() => toggleSelect(rec.id)}
                    className="w-3.5 h-3.5 rounded accent-emerald-500 cursor-pointer" />
                </div>

                {/* Date */}
                <div className="col-span-2 text-sm text-gray-400 font-mono flex items-center gap-1.5">
                  {rec.locked && <span className="text-[0.55rem]">🔒</span>}
                  {rec.date}
                </div>

                {/* Product */}
                <div className="col-span-2">
                  <span className="text-sm font-semibold text-gray-200">{rec.item}</span>
                </div>

                {/* Quantity */}
                <div className="col-span-2">
                  <span className="text-sm font-bold text-gray-100 tabular-nums">{rec.quantity}</span>
                </div>

                {/* Notes */}
                <div className="col-span-3">
                  <span className="text-xs text-gray-500 italic">{rec.notes || '—'}</span>
                </div>

                {/* Actions */}
                <div className="col-span-2 flex justify-end gap-1">
                  {deleteId === rec.id ? (
                    <>
                      <button onClick={() => confirmDelete(rec.id)}
                        className="px-2 py-1 rounded-lg text-[0.6rem] font-bold bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-all">
                        Confirm
                      </button>
                      <button onClick={() => setDeleteId(null)}
                        className="px-2 py-1 rounded-lg text-[0.6rem] font-bold bg-white/[0.03] text-gray-500 border border-white/[0.06] hover:text-gray-300 transition-all">
                        No
                      </button>
                    </>
                  ) : (
                    <>
                      <button onClick={() => !rec.locked && setEditRecord(rec)} disabled={rec.locked}
                        className="px-1.5 py-1 rounded-lg text-[0.6rem] text-gray-600 hover:text-accent hover:bg-accent/5
                          opacity-0 group-hover:opacity-100 transition-all disabled:opacity-30" title="Edit">
                        ✏️
                      </button>
                      <button onClick={() => handleUndo(rec.id)}
                        className="px-1.5 py-1 rounded-lg text-[0.6rem] text-gray-600 hover:text-cyan-400 hover:bg-cyan-500/5
                          opacity-0 group-hover:opacity-100 transition-all" title="Undo last change">
                        ↩️
                      </button>
                      <button onClick={() => !rec.locked && setDeleteId(rec.id)} disabled={rec.locked}
                        className="px-1.5 py-1 rounded-lg text-[0.6rem] text-gray-600 hover:text-red-400 hover:bg-red-500/5
                          opacity-0 group-hover:opacity-100 transition-all disabled:opacity-30" title="Delete">
                        🗑️
                      </button>
                    </>
                  )}
                </div>
              </div>
            ))
          )}
        </div>

        {records.length > 0 && (
          <div className="px-5 py-2.5 border-t border-white/[0.04] flex items-center justify-between">
            <span className="text-[0.6rem] text-gray-600">
              {records.length} record{records.length !== 1 ? 's' : ''} · Last 30 days
            </span>
            <button onClick={fetchData} className="text-[0.6rem] text-gray-600 hover:text-accent transition-colors">
              ↻ Refresh
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
