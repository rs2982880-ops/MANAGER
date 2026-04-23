/**
 * KPICards.jsx — Key performance indicator metric cards.
 *
 * 4 glassmorphism cards: Total Stock, Total Sold, Active Alerts, Snapshots
 */

import useStore from '../stores/useStore';

export default function KPICards() {
  const totalStock = useStore((s) => s.totalStock);
  const totalSold = useStore((s) => s.totalSold);
  const alerts = useStore((s) => s.alerts);
  const snapshotCount = useStore((s) => s.snapshotCount);
  const numClasses = useStore((s) => s.numClasses);
  const emptyCount = useStore((s) => s.emptyCount);

  const criticalAlerts = alerts.filter((a) => a.severity === 'critical').length;

  const cards = [
    {
      label: 'Net Stock',
      value: totalStock,
      icon: '📦',
      color: totalStock > 0 ? 'text-gray-100' : 'text-red-400',
      sub: `${numClasses} product types`,
    },
    {
      label: 'Total Sold',
      value: totalSold,
      icon: '🔄',
      color: totalSold > 0 ? 'text-amber-400' : 'text-gray-100',
      sub: 'cumulative sales',
    },
    {
      label: 'Alerts',
      value: alerts.length,
      icon: '🔔',
      color: criticalAlerts > 0 ? 'text-red-400' : alerts.length > 0 ? 'text-amber-400' : 'text-accent',
      sub: criticalAlerts > 0 ? `${criticalAlerts} critical` : 'all clear',
    },
    {
      label: 'Empty Cells',
      value: emptyCount,
      icon: '⬜',
      color: emptyCount > 5 ? 'text-red-400' : emptyCount > 0 ? 'text-amber-400' : 'text-accent',
      sub: `${snapshotCount} snapshots`,
    },
  ];

  return (
    <div className="grid grid-cols-4 gap-3 mb-4">
      {cards.map((card) => (
        <div key={card.label} className="kpi-card group">
          <div className="text-lg mb-1 opacity-60">{card.icon}</div>
          <div className={`text-2xl font-extrabold ${card.color} transition-colors duration-500`}>
            {card.value}
          </div>
          <div className="text-[0.6rem] text-gray-600 font-semibold uppercase tracking-wider mt-1">
            {card.label}
          </div>
          <div className="text-[0.55rem] text-gray-700 mt-0.5">
            {card.sub}
          </div>
        </div>
      ))}
    </div>
  );
}
