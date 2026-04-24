/**
 * SalesPage.jsx — Premium daily sales management page.
 *
 * Features:
 *   - KPI summary cards (today/week/month/total) with animated counters
 *   - Editable data table with inline editing, add, delete
 *   - Optimistic UI updates synced with backend
 *   - Dark glassmorphism theme
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import {
  getDailySales,
  addDailySale,
  updateDailySale,
  deleteDailySale,
} from '../services/api';

// ═══════════════════════════════════════════════════════════════════
// Animated counter hook
// ═══════════════════════════════════════════════════════════════════
function useAnimatedCount(target, duration = 600) {
  const [display, setDisplay] = useState(0);
  const raf = useRef(null);

  useEffect(() => {
    const start = display;
    const diff = target - start;
    if (diff === 0) return;
    const startTime = performance.now();

    function tick(now) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      setDisplay(Math.round(start + diff * eased));
      if (progress < 1) raf.current = requestAnimationFrame(tick);
    }
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, [target]);

  return display;
}

// ═══════════════════════════════════════════════════════════════════
// KPI Card
// ═══════════════════════════════════════════════════════════════════
function SalesKPI({ icon, label, value, accent }) {
  const animated = useAnimatedCount(value);
  return (
    <div className="kpi-card group relative overflow-hidden">
      <div
        className="absolute inset-0 opacity-[0.03] rounded-2xl"
        style={{ background: `radial-gradient(circle at 50% 0%, ${accent}, transparent 70%)` }}
      />
      <div className="text-xl mb-1.5 opacity-70">{icon}</div>
      <div className="text-3xl font-black text-gray-100 tabular-nums tracking-tight">
        {animated}
      </div>
      <div className="text-[0.6rem] text-gray-500 font-bold uppercase tracking-widest mt-1.5">
        {label}
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

  // Edit state
  const [editId, setEditId] = useState(null);
  const [editQty, setEditQty] = useState('');
  const [editNotes, setEditNotes] = useState('');

  // New row form
  const [showAdd, setShowAdd] = useState(false);
  const [newDate, setNewDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [newItem, setNewItem] = useState('');
  const [newQty, setNewQty] = useState('');
  const [newNotes, setNewNotes] = useState('');

  // Delete confirm
  const [deleteId, setDeleteId] = useState(null);

  // ── Fetch data ──
  const fetchData = useCallback(async () => {
    try {
      const data = await getDailySales(30);
      if (data.ok) {
        setRecords(data.records || []);
        setSummary(data.summary || { today: 0, week: 0, month: 0, total: 0 });
      }
    } catch (e) {
      console.error('Failed to fetch daily sales:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  // ── Add new record ──
  const handleAdd = async () => {
    if (!newItem.trim() || !newQty) return;
    const qty = parseInt(newQty, 10);
    if (isNaN(qty) || qty < 0) return;

    // Optimistic: add to UI
    const tempId = Date.now();
    const optimistic = {
      id: tempId, date: newDate, item: newItem.trim(),
      quantity: qty, notes: newNotes, created_at: '', updated_at: '',
    };
    setRecords(prev => [optimistic, ...prev]);

    const res = await addDailySale(newDate, newItem.trim(), qty, newNotes);
    if (res.ok) {
      setNewItem(''); setNewQty(''); setNewNotes(''); setShowAdd(false);
      fetchData(); // refresh to get real IDs
    }
  };

  // ── Start editing ──
  const startEdit = (rec) => {
    setEditId(rec.id);
    setEditQty(String(rec.quantity));
    setEditNotes(rec.notes || '');
  };

  // ── Save edit ──
  const saveEdit = async (id) => {
    const qty = parseInt(editQty, 10);
    if (isNaN(qty) || qty < 0) return;

    // Optimistic update
    setRecords(prev => prev.map(r =>
      r.id === id ? { ...r, quantity: qty, notes: editNotes } : r
    ));
    setEditId(null);

    await updateDailySale(id, qty, editNotes);
    fetchData();
  };

  // ── Delete ──
  const confirmDelete = async (id) => {
    setRecords(prev => prev.filter(r => r.id !== id));
    setDeleteId(null);
    await deleteDailySale(id);
    fetchData();
  };

  // ── Key handler for edit ──
  const handleEditKey = (e, id) => {
    if (e.key === 'Enter') saveEdit(id);
    if (e.key === 'Escape') setEditId(null);
  };

  const handleAddKey = (e) => {
    if (e.key === 'Enter') handleAdd();
    if (e.key === 'Escape') setShowAdd(false);
  };

  return (
    <div className="flex-1 flex flex-col p-6 gap-6 overflow-hidden animate-fade-in">
      {/* ── Header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-100 tracking-tight">Sales Log</h1>
          <p className="text-xs text-gray-600 mt-0.5">Human-verified daily sales records</p>
        </div>
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="btn-primary flex items-center gap-2 text-xs"
        >
          <span className="text-base leading-none">{showAdd ? '✕' : '＋'}</span>
          {showAdd ? 'Cancel' : 'Add Record'}
        </button>
      </div>

      {/* ── KPI Cards ── */}
      <div className="grid grid-cols-4 gap-4">
        <SalesKPI icon="📊" label="Today" value={summary.today} accent="#10b981" />
        <SalesKPI icon="📅" label="This Week" value={summary.week} accent="#06b6d4" />
        <SalesKPI icon="📆" label="This Month" value={summary.month} accent="#8b5cf6" />
        <SalesKPI icon="🏆" label="All Time" value={summary.total} accent="#f59e0b" />
      </div>

      {/* ── Add Row Form ── */}
      {showAdd && (
        <div className="glass-panel p-4 animate-slide-up">
          <div className="text-[0.65rem] font-bold text-gray-500 uppercase tracking-widest mb-3">
            New Daily Sale
          </div>
          <div className="grid grid-cols-12 gap-3">
            <div className="col-span-3">
              <label className="label-dark">Date</label>
              <input
                type="date" value={newDate}
                onChange={(e) => setNewDate(e.target.value)}
                onKeyDown={handleAddKey}
                className="input-dark"
              />
            </div>
            <div className="col-span-3">
              <label className="label-dark">Product</label>
              <input
                type="text" value={newItem} placeholder="e.g. maggi"
                onChange={(e) => setNewItem(e.target.value)}
                onKeyDown={handleAddKey}
                className="input-dark"
                autoFocus
              />
            </div>
            <div className="col-span-2">
              <label className="label-dark">Quantity</label>
              <input
                type="number" value={newQty} placeholder="0" min="0"
                onChange={(e) => setNewQty(e.target.value)}
                onKeyDown={handleAddKey}
                className="input-dark"
              />
            </div>
            <div className="col-span-3">
              <label className="label-dark">Notes</label>
              <input
                type="text" value={newNotes} placeholder="optional"
                onChange={(e) => setNewNotes(e.target.value)}
                onKeyDown={handleAddKey}
                className="input-dark"
              />
            </div>
            <div className="col-span-1 flex items-end">
              <button onClick={handleAdd} className="btn-primary w-full py-2 text-xs">
                Save
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Data Table ── */}
      <div className="flex-1 min-h-0 glass-panel overflow-hidden flex flex-col">
        {/* Table header */}
        <div className="grid grid-cols-12 gap-2 px-5 py-3 border-b border-white/[0.04]
                        text-[0.6rem] font-bold text-gray-500 uppercase tracking-widest">
          <div className="col-span-2">Date</div>
          <div className="col-span-3">Product</div>
          <div className="col-span-2">Quantity</div>
          <div className="col-span-3">Notes</div>
          <div className="col-span-2 text-right">Actions</div>
        </div>

        {/* Table body */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <div className="text-sm text-gray-600">Loading...</div>
            </div>
          ) : records.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-16 text-center">
              <div className="text-4xl opacity-15 mb-3">📋</div>
              <p className="text-sm text-gray-600">No sales records yet</p>
              <p className="text-[0.65rem] text-gray-700 mt-1">
                Click "Add Record" to create your first entry
              </p>
            </div>
          ) : (
            records.map((rec, idx) => (
              <div
                key={rec.id}
                className={`sales-table-row grid grid-cols-12 gap-2 px-5 py-3 items-center
                           border-b border-white/[0.02] transition-all duration-200
                           hover:bg-white/[0.02] group
                           ${editId === rec.id ? 'bg-accent/[0.03] border-accent/10' : ''}
                           ${idx === 0 ? '' : ''}`}
                style={{ animationDelay: `${idx * 30}ms` }}
              >
                {/* Date */}
                <div className="col-span-2 text-sm text-gray-400 font-mono">
                  {rec.date}
                </div>

                {/* Product */}
                <div className="col-span-3">
                  <span className="text-sm font-semibold text-gray-200">{rec.item}</span>
                </div>

                {/* Quantity */}
                <div className="col-span-2">
                  {editId === rec.id ? (
                    <input
                      type="number" value={editQty} min="0"
                      onChange={(e) => setEditQty(e.target.value)}
                      onKeyDown={(e) => handleEditKey(e, rec.id)}
                      className="input-dark w-20 text-center py-1"
                      autoFocus
                    />
                  ) : (
                    <span className="text-sm font-bold text-gray-100 tabular-nums">
                      {rec.quantity}
                    </span>
                  )}
                </div>

                {/* Notes */}
                <div className="col-span-3">
                  {editId === rec.id ? (
                    <input
                      type="text" value={editNotes}
                      onChange={(e) => setEditNotes(e.target.value)}
                      onKeyDown={(e) => handleEditKey(e, rec.id)}
                      className="input-dark py-1 text-xs"
                      placeholder="optional note"
                    />
                  ) : (
                    <span className="text-xs text-gray-500 italic">
                      {rec.notes || '—'}
                    </span>
                  )}
                </div>

                {/* Actions */}
                <div className="col-span-2 flex justify-end gap-1.5">
                  {editId === rec.id ? (
                    <>
                      <button
                        onClick={() => saveEdit(rec.id)}
                        className="px-2.5 py-1 rounded-lg text-[0.65rem] font-bold
                                   bg-accent/10 text-accent border border-accent/20
                                   hover:bg-accent/20 transition-all"
                      >
                        ✓ Save
                      </button>
                      <button
                        onClick={() => setEditId(null)}
                        className="px-2.5 py-1 rounded-lg text-[0.65rem] font-bold
                                   bg-white/[0.03] text-gray-500 border border-white/[0.06]
                                   hover:text-gray-300 transition-all"
                      >
                        Cancel
                      </button>
                    </>
                  ) : deleteId === rec.id ? (
                    <>
                      <button
                        onClick={() => confirmDelete(rec.id)}
                        className="px-2.5 py-1 rounded-lg text-[0.65rem] font-bold
                                   bg-red-500/10 text-red-400 border border-red-500/20
                                   hover:bg-red-500/20 transition-all"
                      >
                        Confirm
                      </button>
                      <button
                        onClick={() => setDeleteId(null)}
                        className="px-2.5 py-1 rounded-lg text-[0.65rem] font-bold
                                   bg-white/[0.03] text-gray-500 border border-white/[0.06]
                                   hover:text-gray-300 transition-all"
                      >
                        No
                      </button>
                    </>
                  ) : (
                    <>
                      <button
                        onClick={() => startEdit(rec)}
                        className="px-2 py-1 rounded-lg text-[0.65rem]
                                   text-gray-600 hover:text-accent hover:bg-accent/5
                                   opacity-0 group-hover:opacity-100 transition-all"
                        title="Edit"
                      >
                        ✏️
                      </button>
                      <button
                        onClick={() => setDeleteId(rec.id)}
                        className="px-2 py-1 rounded-lg text-[0.65rem]
                                   text-gray-600 hover:text-red-400 hover:bg-red-500/5
                                   opacity-0 group-hover:opacity-100 transition-all"
                        title="Delete"
                      >
                        🗑️
                      </button>
                    </>
                  )}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        {records.length > 0 && (
          <div className="px-5 py-2.5 border-t border-white/[0.04] flex items-center justify-between">
            <span className="text-[0.6rem] text-gray-600">
              {records.length} record{records.length !== 1 ? 's' : ''} · Last 30 days
            </span>
            <button
              onClick={fetchData}
              className="text-[0.6rem] text-gray-600 hover:text-accent transition-colors"
            >
              ↻ Refresh
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
