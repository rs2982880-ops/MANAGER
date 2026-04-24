/**
 * VideoFeed.jsx — Center panel displaying live camera feed with grid overlay.
 *
 * Shows a warning overlay when system detects NO_SHELF state
 * (camera not pointing at a shelf area).
 */

import { useRef, useEffect } from 'react';
import useStore from '../stores/useStore';
import GridOverlay from './GridOverlay';

export default function VideoFeed() {
  const frame = useStore((s) => s.frame);
  const isStreaming = useStore((s) => s.isStreaming);
  const grid = useStore((s) => s.grid);
  const gridRows = useStore((s) => s.gridRows);
  const gridCols = useStore((s) => s.gridCols);
  const fps = useStore((s) => s.fps);
  const frameCount = useStore((s) => s.frameCount);
  const alerts = useStore((s) => s.alerts);

  const imgRef = useRef(null);

  // Check for NO_SHELF state from backend alerts
  const noShelf = alerts.some(
    (a) => a.item === 'SYSTEM' && a.action?.includes('No shelf')
  );

  // Direct src update for zero-flicker rendering
  useEffect(() => {
    if (imgRef.current && frame) {
      imgRef.current.src = frame;
    }
  }, [frame]);

  if (!isStreaming || !frame) {
    return (
      <div className="h-full flex flex-col items-center justify-center glass-panel">
        <div className="text-center">
          <div className="text-5xl mb-4 opacity-30">📷</div>
          <h3 className="text-lg font-bold text-gray-500 mb-2">No Active Feed</h3>
          <p className="text-sm text-gray-600 max-w-xs">
            Select a camera source and click{' '}
            <span className="text-accent font-semibold">Start</span>{' '}
            to begin monitoring
          </p>
          <div className="mt-6 flex items-center justify-center gap-4 text-[0.65rem] text-gray-700">
            <span>Supports: Device Cameras</span>
            <span>·</span>
            <span>IP Cameras (DroidCam)</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* Video Container */}
      <div className="relative flex-1 rounded-2xl overflow-hidden bg-black/30 border border-white/[0.04]">
        {/* The actual video frame */}
        <img
          ref={imgRef}
          alt="Live camera feed"
          className="w-full h-full object-contain"
          style={{ imageRendering: 'auto' }}
        />

        {/* Grid Overlay (SVG on top of image) */}
        {!noShelf && <GridOverlay grid={grid} rows={gridRows} cols={gridCols} />}

        {/* NO SHELF WARNING OVERLAY */}
        {noShelf && (
          <div className="absolute inset-0 flex items-center justify-center z-10">
            <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px]" />
            <div className="relative flex flex-col items-center gap-3 px-8 py-6 rounded-2xl
                            bg-dark-800/90 border border-amber-500/30 shadow-2xl
                            animate-fade-in max-w-sm text-center">
              <div className="text-4xl">⚠️</div>
              <h3 className="text-base font-bold text-amber-400">
                No Shelf Detected
              </h3>
              <p className="text-xs text-gray-400 leading-relaxed">
                The camera doesn't see a shelf with products.
                Tracking is <span className="text-amber-400 font-semibold">paused</span> to prevent false inventory updates.
              </p>
              <div className="mt-1 px-3 py-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20
                              text-[0.65rem] text-amber-300 font-medium">
                Adjust camera → point at shelf area
              </div>
            </div>
          </div>
        )}

        {/* FPS Badge */}
        <div className="absolute top-3 left-3 flex items-center gap-2 px-2.5 py-1 rounded-lg bg-black/60 backdrop-blur-sm border border-white/10 text-[0.65rem] font-semibold">
          <div className="dot-live" style={{ width: '6px', height: '6px' }}></div>
          <span className="text-accent">{fps} FPS</span>
          <span className="text-gray-500">·</span>
          <span className="text-gray-400">F#{frameCount}</span>
        </div>

        {/* LIVE / NO SHELF badge */}
        <div className={`absolute top-3 right-3 flex items-center gap-1.5 px-2.5 py-1 rounded-lg
                         backdrop-blur-sm text-[0.65rem] font-bold ${
          noShelf
            ? 'bg-amber-500/20 border border-amber-500/30 text-amber-400'
            : 'bg-red-500/20 border border-red-500/30 text-red-400'
        }`}>
          <div className={`w-1.5 h-1.5 rounded-full animate-pulse ${
            noShelf ? 'bg-amber-500' : 'bg-red-500'
          }`}></div>
          {noShelf ? 'PAUSED' : 'LIVE'}
        </div>
      </div>
    </div>
  );
}
