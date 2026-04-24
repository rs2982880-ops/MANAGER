/**
 * App.jsx — Main application layout with tab navigation.
 *
 * Two views:
 *   DASHBOARD:  Live video feed + KPI cards + stock/alerts
 *   SALES LOG:  Editable daily sales management
 */

import { useState } from 'react';
import Navbar from './components/Navbar';
import CameraPanel from './components/CameraPanel';
import SnapshotPanel from './components/SnapshotPanel';
import VideoFeed from './components/VideoFeed';
import KPICards from './components/KPICards';
import StockPanel from './components/StockPanel';
import AlertsPanel from './components/AlertsPanel';
import RecommendationsPanel from './components/RecommendationsPanel';
import SalesPage from './components/SalesPage';
import useWebSocket from './hooks/useWebSocket';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');

  // Initialize WebSocket connection
  useWebSocket();

  return (
    <div className="h-screen flex flex-col bg-dark-900 overflow-hidden">
      {/* Top Navbar with tab navigation */}
      <Navbar activeTab={activeTab} onTabChange={setActiveTab} />

      {activeTab === 'dashboard' ? (
        /* ═══ DASHBOARD VIEW ═══ */
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
      ) : (
        /* ═══ SALES LOG VIEW ═══ */
        <SalesPage />
      )}
    </div>
  );
}
