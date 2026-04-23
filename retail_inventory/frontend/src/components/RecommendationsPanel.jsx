/**
 * RecommendationsPanel.jsx — AI-generated shelf placement recommendations.
 */

import useStore from '../stores/useStore';

const PRIORITY_COLORS = {
  high: 'text-accent-light',
  medium: 'text-cyan-300',
  low: 'text-gray-400',
};

const PRIORITY_ICONS = {
  high: '🔥',
  medium: '💡',
  low: '📋',
};

export default function RecommendationsPanel() {
  const recommendations = useStore((s) => s.recommendations);

  return (
    <div className="glass-panel p-4">
      <div className="section-header">
        <span>📋</span>
        <span>Recommendations</span>
      </div>

      {recommendations.length === 0 ? (
        <div className="flex flex-col items-center py-6 text-center">
          <div className="text-2xl opacity-20 mb-2">💡</div>
          <p className="text-[0.75rem] text-gray-600">No recommendations yet</p>
          <p className="text-[0.6rem] text-gray-700 mt-1">
            Insights appear after tracking sales patterns
          </p>
        </div>
      ) : (
        <div className="space-y-2 max-h-48 overflow-y-auto">
          {recommendations.map((rec, idx) => (
            <div
              key={`${rec.item}-${idx}`}
              className="p-2.5 rounded-xl bg-cyan-500/[0.03] border border-cyan-500/[0.08]
                         text-[0.73rem] text-cyan-100 leading-relaxed animate-fade-in"
            >
              <div className="flex items-start gap-2">
                <span className="text-sm flex-shrink-0">
                  {PRIORITY_ICONS[rec.priority] || '📋'}
                </span>
                <div className="flex-1 min-w-0">
                  <span className={`font-bold ${PRIORITY_COLORS[rec.priority] || 'text-cyan-300'}`}>
                    {rec.item}
                  </span>
                  <span className="text-gray-400"> — {rec.reason}</span>
                  <div className="text-[0.65rem] text-gray-500 mt-1">
                    → {rec.suggestion}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
