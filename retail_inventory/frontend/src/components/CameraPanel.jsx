/**
 * CameraPanel.jsx — Left sidebar with camera controls and settings.
 */

import { useState } from 'react';
import useStore from '../stores/useStore';
import { startCamera, stopCamera, updateSettings, takeSnapshot } from '../services/api';

export default function CameraPanel() {
  const cameraType = useStore((s) => s.cameraType);
  const setCameraType = useStore((s) => s.setCameraType);
  const cameraSource = useStore((s) => s.cameraSource);
  const setCameraSource = useStore((s) => s.setCameraSource);
  const ipUrl = useStore((s) => s.ipUrl);
  const setIpUrl = useStore((s) => s.setIpUrl);
  const isStreaming = useStore((s) => s.isStreaming);
  const confidence = useStore((s) => s.confidence);
  const setConfidence = useStore((s) => s.setConfidence);
  const detectionOn = useStore((s) => s.detectionOn);
  const setDetectionOn = useStore((s) => s.setDetectionOn);
  const gridRows = useStore((s) => s.gridRows);
  const setGridRows = useStore((s) => s.setGridRows);
  const gridCols = useStore((s) => s.gridCols);
  const setGridCols = useStore((s) => s.setGridCols);
  const setIsStreaming = useStore((s) => s.setIsStreaming);
  const setCameraError = useStore((s) => s.setCameraError);
  const cameraError = useStore((s) => s.cameraError);

  const [loading, setLoading] = useState(false);

  const handleStart = async () => {
    setLoading(true);
    setCameraError('');
    try {
      const source = cameraType === 'device' ? parseInt(cameraSource) : ipUrl;
      const result = await startCamera(source);
      if (result.ok) {
        setIsStreaming(true);
      } else {
        setCameraError(result.message || 'Camera failed to start');
      }
    } catch (e) {
      setCameraError('Backend not reachable');
    }
    setLoading(false);
  };

  const handleStop = async () => {
    setLoading(true);
    try {
      await stopCamera();
      setIsStreaming(false);
    } catch (e) {
      setCameraError('Failed to stop camera');
    }
    setLoading(false);
  };

  const handleConfidenceChange = async (val) => {
    setConfidence(val);
    try {
      await updateSettings({ confidence: val });
    } catch (e) { /* ignore */ }
  };

  const handleDetectionToggle = async () => {
    const newVal = !detectionOn;
    setDetectionOn(newVal);
    try {
      await updateSettings({ detection_on: newVal });
    } catch (e) { /* ignore */ }
  };

  const handleGridChange = async (rows, cols) => {
    setGridRows(rows);
    setGridCols(cols);
    try {
      await updateSettings({ grid_rows: rows, grid_cols: cols });
    } catch (e) { /* ignore */ }
  };

  const handleSnapshot = async () => {
    try {
      await takeSnapshot();
    } catch (e) { /* ignore */ }
  };

  return (
    <div className="h-full flex flex-col gap-4 p-4 overflow-y-auto">
      {/* Camera Section */}
      <div>
        <div className="section-header">
          <span>📷</span>
          <span>Camera</span>
        </div>

        <div className="space-y-3">
          {/* Camera Type */}
          <div>
            <label className="label-dark">Source Type</label>
            <select
              className="select-dark"
              value={cameraType}
              onChange={(e) => setCameraType(e.target.value)}
              disabled={isStreaming}
            >
              <option value="device">Device Camera</option>
              <option value="ip">IP Camera</option>
            </select>
          </div>

          {/* Source Input */}
          {cameraType === 'device' ? (
            <div>
              <label className="label-dark">Device Index</label>
              <select
                className="select-dark"
                value={cameraSource}
                onChange={(e) => setCameraSource(e.target.value)}
                disabled={isStreaming}
              >
                <option value="0">Camera 0 (Laptop)</option>
                <option value="1">Camera 1 (USB)</option>
                <option value="2">Camera 2 (USB)</option>
              </select>
            </div>
          ) : (
            <div>
              <label className="label-dark">Stream URL</label>
              <input
                type="text"
                className="input-dark"
                value={ipUrl}
                onChange={(e) => setIpUrl(e.target.value)}
                disabled={isStreaming}
                placeholder="http://192.168.0.101:4747/video"
              />
            </div>
          )}

          {/* Error */}
          {cameraError && (
            <div className="text-[0.7rem] text-red-400 bg-red-500/5 border border-red-500/10 rounded-lg px-3 py-2">
              ❌ {cameraError}
            </div>
          )}

          {/* Start / Stop */}
          <div className="flex gap-2">
            <button
              className="btn-primary flex-1 flex items-center justify-center gap-2"
              onClick={handleStart}
              disabled={isStreaming || loading}
            >
              {loading && !isStreaming ? (
                <span className="animate-spin">⏳</span>
              ) : (
                <span>▶</span>
              )}
              Start
            </button>
            <button
              className="btn-danger flex-1"
              onClick={handleStop}
              disabled={!isStreaming || loading}
            >
              ■ Stop
            </button>
          </div>
        </div>
      </div>

      {/* Divider */}
      <hr className="border-white/[0.04]" />

      {/* Detection */}
      <div>
        <div className="section-header">
          <span>🎯</span>
          <span>Detection</span>
        </div>

        <div className="space-y-3">
          {/* Confidence */}
          <div>
            <div className="flex justify-between items-center mb-1.5">
              <label className="label-dark mb-0">Confidence</label>
              <span className="text-xs font-bold text-accent">{Math.round(confidence * 100)}%</span>
            </div>
            <input
              type="range"
              min="0.10"
              max="0.95"
              step="0.05"
              value={confidence}
              onChange={(e) => handleConfidenceChange(parseFloat(e.target.value))}
            />
          </div>

          {/* Detection Toggle */}
          <div className="flex items-center justify-between">
            <label className="label-dark mb-0">Overlay Boxes</label>
            <label className="toggle-switch">
              <input
                type="checkbox"
                checked={detectionOn}
                onChange={handleDetectionToggle}
              />
              <div className="toggle-track"></div>
              <div className="toggle-dot"></div>
            </label>
          </div>
        </div>
      </div>

      {/* Divider */}
      <hr className="border-white/[0.04]" />

      {/* Grid */}
      <div>
        <div className="section-header">
          <span>📐</span>
          <span>Grid</span>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="label-dark">Rows</label>
            <input
              type="number"
              className="input-dark"
              min="1"
              max="10"
              value={gridRows}
              onChange={(e) => handleGridChange(parseInt(e.target.value) || 1, gridCols)}
              disabled={isStreaming}
            />
          </div>
          <div>
            <label className="label-dark">Cols</label>
            <input
              type="number"
              className="input-dark"
              min="1"
              max="10"
              value={gridCols}
              onChange={(e) => handleGridChange(gridRows, parseInt(e.target.value) || 1)}
              disabled={isStreaming}
            />
          </div>
        </div>
      </div>

      {/* Divider */}
      <hr className="border-white/[0.04]" />

      {/* Actions */}
      <div>
        <div className="section-header">
          <span>📸</span>
          <span>Actions</span>
        </div>
        <button
          className="btn-secondary w-full"
          onClick={handleSnapshot}
          disabled={!isStreaming}
        >
          💾 Save Snapshot
        </button>
      </div>

      {/* Footer */}
      <div className="mt-auto pt-4 border-t border-white/[0.03] text-center">
        <p className="text-[0.6rem] text-gray-700">
          ShelfAI v3.0 · FastAPI + React · YOLOv8 · GPU
        </p>
      </div>
    </div>
  );
}
