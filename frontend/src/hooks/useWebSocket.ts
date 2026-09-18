import { useEffect, useRef } from 'react';
import { useUiStore } from '../stores/ui';
import { useWsStore } from '../stores/ws';
import type { EventBusMessage } from '../types/api';

const BACKOFF_STEPS_MS = [1000, 2000, 4000, 8000, 16000, 30000];

function resolveWsUrl(path: string): string {
  // path is like '/ws/events' or '/ws/prompter/timer.fs1_field1?token=...'.
  // In dev, Vite's proxy (vite.config.ts) forwards /ws/* with ws:true to
  // the backend; in prod the SPA is served from the same origin as the
  // backend (Traefik IngressRoute, Appendix A.9), so a same-origin
  // ws(s):// URL works in both cases without an env var.
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}${path}`;
}

/**
 * Native WebSocket hook (plan Appendix B.2 / §C.8.5). Side-effect only —
 * never returns data. Consumers read live state from `useWsStore`, per the
 * hard rule in §C.8.5: "Never return data directly."
 *
 * - Opens a WebSocket to `path` (e.g. '/ws/events').
 * - On message: parses JSON and calls `useWsStore.getState().dispatch(...)`.
 * - On disconnect: sets the UI store's `reconnecting` flag and retries with
 *   exponential backoff (1s, 2s, 4s, 8s, 16s, 30s cap — Appendix A.14).
 * - On unmount: closes cleanly and cancels any pending reconnect.
 */
export function useWebSocket(path: string | null): void {
  const attemptRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const closedByUsRef = useRef(false);

  useEffect(() => {
    if (!path) return undefined;
    closedByUsRef.current = false;

    function connect() {
      const url = resolveWsUrl(path!);
      const ws = new WebSocket(url);
      socketRef.current = ws;

      ws.onopen = () => {
        attemptRef.current = 0;
        useUiStore.getState().setReconnecting(false);
        useWsStore.getState().setConnected(true);
      };

      ws.onmessage = (ev) => {
        try {
          const parsed = JSON.parse(ev.data) as EventBusMessage;
          useWsStore.getState().dispatch(parsed);
        } catch {
          // Ignore malformed frames (e.g. a stray non-JSON ping payload).
        }
      };

      ws.onclose = () => {
        useWsStore.getState().setConnected(false);
        if (closedByUsRef.current) return;
        useUiStore.getState().setReconnecting(true);
        const delay = BACKOFF_STEPS_MS[Math.min(attemptRef.current, BACKOFF_STEPS_MS.length - 1)];
        attemptRef.current += 1;
        timerRef.current = setTimeout(connect, delay);
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    connect();

    return () => {
      closedByUsRef.current = true;
      if (timerRef.current) clearTimeout(timerRef.current);
      socketRef.current?.close();
      useUiStore.getState().setReconnecting(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path]);
}
