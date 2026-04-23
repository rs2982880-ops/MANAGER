/**
 * SnapshotPanel.jsx — Mode toggle + countdown timer + snapshot flash.
 *
 * Displays:
 *   - Demo ⚡ / Production 🏪 toggle
 *   - Live countdown timer to next snapshot
 *   - Current adaptive interval display
 *   - Snapshot flash indicator
 */

import { useState, useEffect, useRef } from 'react';
import useStore from '../stores/useStore';
import { setMode } from '../services/api';

export default function SnapshotPanel() {
  const snapshotInfo = useStore((s) => s.snapshotInfo);
  const snapshotFlash = useStore((s) => s.snapshotFlash);
  const snapshotCount = useStore((s) => s.snapshotCount);
  const isStreaming = useStore((s) => s.isStreaming);

  const [localCountdown, setLocalCountdown] = useState(0);
  const [switching, setSwitching] = useState(false);
  const lastUpdateRef = useRef(Date.now());

  const mode = snapshotInfo?.mode || 'demo';
  const interval = snapshotInfo?.current_interval || 15;

  // Sync countdown from backend + tick locally
  useEffect(() => {
    const serverRemaining = snapshotInfo?.time_remaining ?? 0;
    setLocalCountdown(serverRemaining);
    lastUpdateRef.current = Date.now();
  }, [snapshotInfo?.time_remaining]);

  // Local tick — decrement countdown every second between WS updates
  useEffect(() => {
    const timer = setInterval(() => {
      setLocalCountdown((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const handleModeSwitch = async (newMode) => {
    if (newMode === mode || switching) return;
    setSwitching(true);
    try {
      await setMode(newMode);
    } catch (e) {
      console.error('Mode switch failed:', e);
    }
    setSwitching(false);
  };

  // Format countdown
  const formatTime = (seconds) => {
    const s = Math.round(seconds);
    if (s >= 60) {
      const m = Math.floor(s / 60);
      const sec = s % 60;
      return `${m}m ${sec}s`;
    }
    return `${s}s`;
  };

  // Progress ring percentage
  const progress = interval > 0 ? ((interval - localCountdown) / interval) * 100 : 0;

  return (
    <div className={`relative rounded-2xl border transition-all duration-500 ${
      snapshotFlash
        ? 'border-accent/60 bg-accent/10 shadow-[0_0_20px_rgba(16,185,129,0.2)]'
        : 'border-white/[0.04] bg-white/[0.02]'
    }`}>

      {/* Snapshot flash overlay */}
      {snapshotFlash && (
        <div className="absolute inset-0 rounded-2xl bg-accent/5 animate-pulse pointer-events-none" />
      )}

      <div className="p-4 space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm">📸</span>
            <span className="text-xs font-bold text-gray-300 uppercase tracking-wider">
              Snapshot System
            </span>
          </div>
          {/* Mode badge */}
          <span className={`text-[0.6rem] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full ${
            mode === 'demo'
              ? 'bg-amber-500/15 text-amber-400 border border-amber-500/20'
              : 'bg-blue-500/15 text-blue-400 border border-blue-500/20'
          }`}>
            {mode === 'demo' ? '⚡ Demo' : '🏪 Production'}
          </span>
        </div>

        {/* Mode Toggle */}
        <div className="flex gap-1.5 p-1 bg-dark-900/50 rounded-xl">
          <button
            onClick={() => handleModeSwitch('demo')}
            disabled={switching}
            className={`flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg text-xs font-bold transition-all duration-300 ${
              mode === 'demo'
                ? 'bg-gradient-to-r from-amber-500/20 to-orange-500/20 text-amber-300 shadow-lg shadow-amber-500/10 border border-amber-500/20'
                : 'text-gray-600 hover:text-gray-400 hover:bg-white/[0.03]'
            }`}
          >
            <span>⚡</span>
            <span>Demo</span>
          </button>
          <button
            onClick={() => handleModeSwitch('production')}
            disabled={switching}
            className={`flex-1 flex items-center justify-center gap-1.5 py-2 px-3 rounded-lg text-xs font-bold transition-all duration-300 ${
              mode === 'production'
                ? 'bg-gradient-to-r from-blue-500/20 to-indigo-500/20 text-blue-300 shadow-lg shadow-blue-500/10 border border-blue-500/20'
                : 'text-gray-600 hover:text-gray-400 hover:bg-white/[0.03]'
            }`}
          >
            <span>🏪</span>
            <span>Production</span>
          </button>
        </div>

        {/* Countdown Timer */}
        <div className="flex items-center gap-4">
          {/* Circular progress ring */}
          <div className="relative w-14 h-14 flex-shrink-0">
            <svg className="w-14 h-14 -rotate-90" viewBox="0 0 56 56">
              {/* Background ring */}
              <circle cx="28" cy="28" r="24" fill="none"
                stroke="rgba(255,255,255,0.04)" strokeWidth="3" />
              {/* Progress ring */}
              <circle cx="28" cy="28" r="24" fill="none"
                stroke={mode === 'demo' ? '#f59e0b' : '#3b82f6'}
                strokeWidth="3"
                strokeLinecap="round"
                strokeDasharray={`${2 * Math.PI * 24}`}
                strokeDashoffset={`${2 * Math.PI * 24 * (1 - progress / 100)}`}
                className="transition-all duration-1000 ease-linear"
              />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center">
              <span className={`text-sm font-extrabold ${
                localCountdown <= 3 && isStreaming ? 'text-red-400 animate-pulse' : 'text-gray-200'
              }`}>
                {formatTime(localCountdown)}
              </span>
            </div>
          </div>

          {/* Countdown details */}
          <div className="flex-1 space-y-1.5">
            <div className="text-[0.65rem] text-gray-500 font-semibold uppercase tracking-wider">
              Next Snapshot In
            </div>
            <div className="text-lg font-extrabold text-gray-100">
              {isStreaming ? formatTime(localCountdown) : '—'}
            </div>
            <div className="text-[0.6rem] text-gray-600">
              Interval: {formatTime(interval)} • {snapshotCount} taken
            </div>
          </div>
        </div>

        {/* Snapshot flash banner */}
        {snapshotFlash && (
          <div className="flex items-center gap-2 py-2 px-3 bg-accent/10 border border-accent/20 rounded-lg animate-pulse">
            <span className="text-accent text-sm">📸</span>
            <span className="text-accent text-xs font-bold">Snapshot taken — Sales updated</span>
          </div>
        )}
      </div>
    </div>
  );
}
