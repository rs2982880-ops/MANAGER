/**
 * GridOverlay.jsx — SVG-based grid overlay on the video feed.
 *
 * Draws grid lines and highlights cells:
 *   - Green = occupied (product detected)
 *   - Red   = empty (no product)
 *   - Labels on occupied cells
 *
 * Positioned absolutely on top of the video <img>.
 */

export default function GridOverlay({ grid, rows, cols }) {
  if (!grid || grid.length === 0 || rows <= 0 || cols <= 0) {
    return null;
  }

  const cellW = 100 / cols;
  const cellH = 100 / rows;

  return (
    <svg
      className="absolute inset-0 w-full h-full pointer-events-none"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
    >
      {/* Grid lines */}
      {Array.from({ length: rows + 1 }, (_, i) => (
        <line
          key={`h-${i}`}
          x1="0"
          y1={i * cellH}
          x2="100"
          y2={i * cellH}
          stroke="rgba(255,255,255,0.15)"
          strokeWidth="0.15"
        />
      ))}
      {Array.from({ length: cols + 1 }, (_, j) => (
        <line
          key={`v-${j}`}
          x1={j * cellW}
          y1="0"
          x2={j * cellW}
          y2="100"
          stroke="rgba(255,255,255,0.15)"
          strokeWidth="0.15"
        />
      ))}

      {/* Cell highlights */}
      {grid.map((cell, idx) => {
        const r = cell.row;
        const c = cell.col;
        const x = c * cellW;
        const y = r * cellH;
        const isOccupied = cell.product !== 'empty';
        const isLow = cell.state === 'low';

        const fillColor = isOccupied
          ? isLow
            ? 'rgba(245, 158, 11, 0.15)'
            : 'rgba(16, 185, 129, 0.12)'
          : 'rgba(239, 68, 68, 0.12)';

        const borderColor = isOccupied
          ? isLow
            ? 'rgba(245, 158, 11, 0.4)'
            : 'rgba(16, 185, 129, 0.35)'
          : 'rgba(239, 68, 68, 0.3)';

        return (
          <g key={`cell-${r}-${c}`}>
            <rect
              x={x + 0.2}
              y={y + 0.2}
              width={cellW - 0.4}
              height={cellH - 0.4}
              fill={fillColor}
              stroke={borderColor}
              strokeWidth="0.15"
              rx="0.3"
            />
            {isOccupied && (
              <text
                x={x + cellW / 2}
                y={y + cellH / 2 + 1}
                textAnchor="middle"
                fill="white"
                fontSize="2"
                fontWeight="600"
                fontFamily="Inter, sans-serif"
                style={{ paintOrder: 'stroke', stroke: 'rgba(0,0,0,0.6)', strokeWidth: '0.4px' }}
              >
                {cell.product.length > 8 ? cell.product.slice(0, 8) + '…' : cell.product}
              </text>
            )}
            {!isOccupied && (
              <text
                x={x + cellW / 2}
                y={y + cellH / 2 + 1}
                textAnchor="middle"
                fill="rgba(239, 68, 68, 0.5)"
                fontSize="2.5"
                fontWeight="400"
              >
                ∅
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
