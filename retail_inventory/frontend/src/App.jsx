/**
 * App.jsx — Main application layout.
 *
 * 3-panel layout:
 *   LEFT:   Camera controls + settings
 *   CENTER: Live video feed + KPI cards
 *   RIGHT:  Stock, Alerts, Recommendations
 */

import Navbar from './components/Navbar';
import CameraPanel from './components/CameraPanel';
import SnapshotPanel from './components/SnapshotPanel';
import VideoFeed from './components/VideoFeed';
import KPICards from './components/KPICards';
import StockPanel from './components/StockPanel';
import AlertsPanel from './components/AlertsPanel';
import RecommendationsPanel from './components/RecommendationsPanel';
import useWebSocket from './hooks/useWebSocket';

export default function App() {
  // Initialize WebSocket connection
  useWebSocket();

  return (
    <div className="h-screen flex flex-col bg-dark-900 overflow-hidden">
      {/* Top Navbar */}
      <Navbar />

      {/* Main 3-Panel Layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* LEFT PANEL — Camera Controls */}
        <aside className="w-64 flex-shrink-0 border-r border-white/[0.04] bg-dark-800/50 backdrop-blur-sm overflow-y-auto">
          <CameraPanel />
          <div className="px-3 pb-3">
            <SnapshotPanel />
          </div>
        </aside>

        {/* CENTER — Video Feed + KPIs */}
        <main className="flex-1 flex flex-col p-4 gap-4 overflow-hidden">
          {/* KPI Cards Row */}
          <KPICards />

          {/* Video Feed */}
          <div className="flex-1 min-h-0">
            <VideoFeed />
          </div>
        </main>

        {/* RIGHT PANEL — Stock, Alerts, Recommendations */}
        <aside className="w-80 flex-shrink-0 border-l border-white/[0.04] bg-dark-800/30 backdrop-blur-sm overflow-y-auto p-4 space-y-4">
          <StockPanel />
          <AlertsPanel />
          <RecommendationsPanel />
        </aside>
      </div>
    </div>
  );
}
