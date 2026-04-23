/**
 * useWebSocket.js — WebSocket hook with auto-reconnect.
 *
 * Connects to ws://localhost:8000/ws/stream
 * Parses incoming JSON and pushes to Zustand store.
 * Reconnects automatically on disconnect with exponential backoff.
 */

import { useEffect, useRef, useCallback } from 'react';
import { WS_URL } from '../services/api';
import useStore from '../stores/useStore';

export default function useWebSocket() {
  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);
  const reconnectDelay = useRef(1000);
  const mountedRef = useRef(true);

  const setConnectionStatus = useStore((s) => s.setConnectionStatus);
  const setWsConnected = useStore((s) => s.setWsConnected);
  const updateFromWS = useStore((s) => s.updateFromWS);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setConnectionStatus('connecting');

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[WS] Connected');
      setConnectionStatus('live');
      setWsConnected(true);
      reconnectDelay.current = 1000; // Reset backoff
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        updateFromWS(data);
      } catch (e) {
        // Skip malformed messages
      }
    };

    ws.onclose = () => {
      console.log('[WS] Disconnected');
      setConnectionStatus('offline');
      setWsConnected(false);
      wsRef.current = null;

      // Auto-reconnect with exponential backoff
      if (mountedRef.current) {
        reconnectTimer.current = setTimeout(() => {
          reconnectDelay.current = Math.min(reconnectDelay.current * 1.5, 10000);
          connect();
        }, reconnectDelay.current);
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [setConnectionStatus, setWsConnected, updateFromWS]);

  // Send command over WebSocket
  const sendCommand = useCallback((cmd) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(cmd));
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  return { sendCommand };
}
