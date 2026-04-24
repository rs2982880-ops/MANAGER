/**
 * Navbar.jsx — Top navigation bar with live status + tab navigation.
 */

import useStore from '../stores/useStore';

export default function Navbar({ activeTab = 'dashboard', onTabChange }) {
  const connectionStatus = useStore((s) => s.connectionStatus);
  const isStreaming = useStore((s) => s.isStreaming);
  const fps = useStore((s) => s.fps);
  const confidence = useStore((s) => s.confidence);
  const gridRows = useStore((s) => s.gridRows);
  const gridCols = useStore((s) => s.gridCols);
  const frameCount = useStore((s) => s.frameCount);
  const snapshotInfo = useStore((s) => s.snapshotInfo);
  const snapshotFlash = useStore((s) => s.snapshotFlash);

  const mode = snapshotInfo?.mode || 'demo';
  const timeRemaining = Math.round(snapshotInfo?.time_remaining || 0);

  const statusDot = isStreaming ? 'dot-live' : connectionStatus === 'live' ? 'dot-idle' : 'dot-error';
  const statusText = isStreaming ? 'Live' : connectionStatus === 'live' ? 'Idle' : 'Offline';

  const tabs = [
    { id: 'dashboard', label: 'Dashboard', icon: '📊' },
    { id: 'sales',     label: 'Sales Log', icon: '📋' },
  ];

  return (
    <nav className="flex items-center justify-between px-6 py-2.5 border-b border-white/[0.04] bg-dark-800/80 backdrop-blur-lg">
      {/* Left: Brand + Tabs */}
      <div className="flex items-center gap-6">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl flex items-center justify-center text-lg"
               style={{
                 background: 'linear-gradient(135deg, #10b981, #059669)',
                 boxShadow: '0 4px 15px rgba(16, 185, 129, 0.25)'
               }}>
            🛒
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-base font-extrabold text-gray-100 tracking-tight">
                ShelfAI
              </span>
              <span className="text-[0.55rem] font-bold text-accent bg-accent/10 px-1.5 py-0.5 rounded tracking-wider">
                PRO
              </span>
            </div>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-1 bg-white/[0.02] border border-white/[0.04] rounded-xl p-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => onTabChange?.(tab.id)}
              className={`nav-tab flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-semibold
                         transition-all duration-200 ${
                activeTab === tab.id
                  ? 'bg-accent/10 text-accent border border-accent/20 shadow-sm shadow-accent/5'
                  : 'text-gray-500 hover:text-gray-300 hover:bg-white/[0.03] border border-transparent'
              }`}
            >
              <span className="text-sm">{tab.icon}</span>
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Right: Status Strip */}
      <div className="flex items-center gap-5 px-4 py-2 bg-white/[0.02] border border-white/[0.04] rounded-xl text-[0.7rem] text-gray-500 font-medium">
        <div className="flex items-center gap-2">
          <div className={statusDot}></div>
          <span>{statusText}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span>⚡</span>
          <span>{isStreaming ? `${fps} FPS` : '—'}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span>🎯</span>
          <span>{Math.round(confidence * 100)}%</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span>📐</span>
          <span>{gridRows}×{gridCols}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span>🎬</span>
          <span>{frameCount.toLocaleString()}</span>
        </div>
        <div className={`flex items-center gap-1.5 px-2 py-0.5 rounded-md transition-all duration-300 ${
          mode === 'demo'
            ? 'bg-amber-500/10 text-amber-400'
            : 'bg-blue-500/10 text-blue-400'
        }`}>
          <span>{mode === 'demo' ? '⚡' : '🏪'}</span>
          <span className="capitalize">{mode}</span>
        </div>
        {isStreaming && (
          <div className={`flex items-center gap-1.5 transition-all duration-300 ${
            snapshotFlash ? 'text-accent' : ''
          }`}>
            <span>📸</span>
            <span>{timeRemaining > 0 ? `${timeRemaining}s` : 'Now'}</span>
          </div>
        )}
      </div>
    </nav>
  );
}
