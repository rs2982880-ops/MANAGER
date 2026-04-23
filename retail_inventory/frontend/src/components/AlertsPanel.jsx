/**
 * AlertsPanel.jsx — Restocking alerts with severity coloring.
 */

import useStore from '../stores/useStore';

export default function AlertsPanel() {
  const alerts = useStore((s) => s.alerts);

  return (
    <div className="glass-panel p-4">
      <div className="section-header">
        <span>🔔</span>
        <span>Alerts</span>
        {alerts.length > 0 && (
          <span className="ml-auto badge badge-urgent">{alerts.length}</span>
        )}
      </div>

      {alerts.length === 0 ? (
        <div className="flex flex-col items-center py-6 text-center">
          <div className="text-2xl opacity-20 mb-2">✅</div>
          <p className="text-[0.75rem] text-gray-600">All clear — no alerts</p>
        </div>
      ) : (
        <div className="space-y-2 max-h-60 overflow-y-auto">
          {alerts.map((alert, idx) => {
            const isCritical = alert.severity === 'critical';
            return (
              <div
                key={`${alert.item}-${idx}`}
                className={`flex gap-3 p-3 rounded-xl text-[0.75rem] leading-relaxed animate-fade-in ${
                  isCritical
                    ? 'bg-red-500/[0.05] border border-red-500/10 text-red-200'
                    : 'bg-amber-500/[0.05] border border-amber-500/10 text-amber-200'
                }`}
              >
                {/* Icon */}
                <div className="text-base flex-shrink-0 mt-0.5">
                  {isCritical ? '🚨' : '⚠️'}
                </div>

                {/* Body */}
                <div className="flex-1 min-w-0">
                  <div className="font-bold text-gray-200">{alert.item}</div>
                  <div className="text-[0.65rem] opacity-60 mt-0.5">
                    Stock: {alert.stock} · Rate: {alert.rate}/hr
                    {alert.time_to_empty && alert.time_to_empty !== 'N/A'
                      ? ` · Depletes in ${alert.time_to_empty}`
                      : ''}
                  </div>
                  <div className={`text-[0.65rem] font-bold mt-1 ${isCritical ? 'text-red-400' : 'text-amber-400'}`}>
                    → {alert.action}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
