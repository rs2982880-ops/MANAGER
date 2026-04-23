/**
 * VideoFeed.jsx — Center panel displaying live camera feed with grid overlay.
 *
 * Receives base64 JPEG frames from the Zustand store (pushed by WebSocket).
 * Updates the <img> src directly — no DOM replacement, no flicker.
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

  const imgRef = useRef(null);

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
        <GridOverlay grid={grid} rows={gridRows} cols={gridCols} />

        {/* FPS Badge */}
        <div className="absolute top-3 left-3 flex items-center gap-2 px-2.5 py-1 rounded-lg bg-black/60 backdrop-blur-sm border border-white/10 text-[0.65rem] font-semibold">
          <div className="dot-live" style={{ width: '6px', height: '6px' }}></div>
          <span className="text-accent">{fps} FPS</span>
          <span className="text-gray-500">·</span>
          <span className="text-gray-400">F#{frameCount}</span>
        </div>

        {/* LIVE badge */}
        <div className="absolute top-3 right-3 flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-red-500/20 backdrop-blur-sm border border-red-500/30 text-[0.65rem] font-bold text-red-400">
          <div className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse"></div>
          LIVE
        </div>
      </div>
    </div>
  );
}
