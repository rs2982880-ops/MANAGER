/**
 * StockPanel.jsx — Product stock summary with status badges and sales rates.
 */

import useStore from '../stores/useStore';

const STATUS_BADGE = {
  ok: { class: 'badge-ok', label: 'OK' },
  low: { class: 'badge-low', label: 'LOW' },
  urgent: { class: 'badge-urgent', label: 'URGENT' },
  high: { class: 'badge-high', label: 'HIGH' },
};

export default function StockPanel() {
  const products = useStore((s) => s.products);
  const totalSalesMap = useStore((s) => s.totalSalesMap);

  if (products.length === 0) {
    return (
      <div className="glass-panel p-4">
        <div className="section-header">
          <span>📦</span>
          <span>Stock Summary</span>
        </div>
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <div className="text-3xl opacity-20 mb-2">📦</div>
          <p className="text-sm text-gray-600">No products detected yet</p>
          <p className="text-[0.65rem] text-gray-700 mt-1">Start the camera to begin monitoring</p>
        </div>
      </div>
    );
  }

  return (
    <div className="glass-panel p-4">
      <div className="section-header">
        <span>📦</span>
        <span>Stock Summary</span>
        <span className="ml-auto text-gray-600 font-normal normal-case tracking-normal">
          {products.length} items
        </span>
      </div>

      <div className="space-y-1">
        {products.map((product) => {
          const badge = STATUS_BADGE[product.status] || STATUS_BADGE.ok;
          const cumulSold = totalSalesMap[product.name] || 0;

          return (
            <div
              key={product.name}
              className="flex items-center justify-between px-3 py-2.5 rounded-xl
                         bg-white/[0.015] border border-white/[0.03]
                         hover:border-accent/10 hover:bg-accent/[0.02]
                         transition-all duration-200 group"
            >
              {/* Product name */}
              <div className="flex-1 min-w-0">
                <div className="text-sm font-semibold text-gray-300 truncate">
                  {product.name}
                </div>
                <div className="text-[0.6rem] text-gray-600 mt-0.5">
                  {product.rate > 0 ? `${product.rate}/hr` : 'no sales'}{' '}
                  {cumulSold > 0 && (
                    <span className="text-amber-500/70">· {cumulSold} sold</span>
                  )}
                </div>
              </div>

              {/* Right side */}
              <div className="flex items-center gap-3">
                <span className={`badge ${badge.class}`}>{badge.label}</span>
                <div className="text-right">
                  <div className="text-base font-extrabold text-gray-100">{product.stock}</div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Sales summary */}
      {Object.keys(totalSalesMap).length > 0 && (
        <div className="mt-3 pt-3 border-t border-white/[0.04]">
          <div className="text-[0.6rem] font-bold text-gray-600 uppercase tracking-wider mb-2">
            Cumulative Sales
          </div>
          <div className="space-y-1">
            {Object.entries(totalSalesMap).map(([item, qty]) => (
              <div
                key={item}
                className="flex items-center justify-between px-2.5 py-1.5 rounded-lg
                           bg-amber-500/[0.04] border border-amber-500/[0.08]
                           text-[0.75rem] text-amber-300"
              >
                <span>{item}</span>
                <span className="font-extrabold text-amber-400">-{qty}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
