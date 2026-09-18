import { useEffect, useRef, useState } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import { useWsStore } from '../stores/ws';
import { usePermission } from '../hooks/usePermission';
import { PageHeader, Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import type { EventBusMessage } from '../types/api';

const CAP = 200;

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString();
}

/** Appendix A.11 "Live Event Bus" debug view: a raw, unfiltered feed of
 * everything flowing over `/ws/events`, for developers (AUDIT_FINDINGS.md
 * 1.10). Unlike `LiveEventFeed` (Dashboard's rolling last-50 buffer shared
 * via `useWsStore`), this page keeps its own capped-at-200 client-side
 * buffer so bursts aren't silently dropped by the shared store's smaller
 * cap, and renders every field verbatim (entity_id, type, timestamp, full
 * payload) rather than the trimmed summary other pages show. It needs no
 * new backend endpoint — it just consumes the same `/ws/events` feed other
 * pages already partially render. Gated on `settings:edit`. */
export function DebugEventBusPage() {
  const canView = usePermission('settings:edit');
  useWebSocket(canView ? '/ws/events' : null);
  const connected = useWsStore((s) => s.connected);
  const storeEvents = useWsStore((s) => s.recentEvents);

  const [captured, setCaptured] = useState<EventBusMessage[]>([]);
  const [paused, setPaused] = useState(false);
  const lastSeenRef = useRef<EventBusMessage | null>(null);

  useEffect(() => {
    if (paused || storeEvents.length === 0) return;
    const lastSeen = lastSeenRef.current;
    const idx = lastSeen ? storeEvents.indexOf(lastSeen) : -1;
    const newOnes = idx === -1 ? storeEvents : storeEvents.slice(0, idx);
    lastSeenRef.current = storeEvents[0];
    if (newOnes.length === 0) return;
    setCaptured((prev) => [...newOnes, ...prev].slice(0, CAP));
  }, [storeEvents, paused]);

  if (!canView) {
    return (
      <div>
        <PageHeader title="Live Event Bus" subtitle="Developer view." />
        <p className="text-sm text-vmd-textSubtle">
          You lack the <code>settings:edit</code> permission required to view debug data.
        </p>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Live Event Bus"
        subtitle={`Raw, unfiltered /ws/events feed — capped at ${CAP} client-side (Appendix A.11).`}
      />

      <div className="mb-3 flex items-center gap-2">
        <span className={`text-xs ${connected ? 'text-vmd-success' : 'text-vmd-danger'}`}>
          {connected ? 'Connected' : 'Disconnected'}
        </span>
        <Button variant="ghost" onClick={() => setPaused((p) => !p)}>
          {paused ? 'Resume' : 'Pause'}
        </Button>
        <Button variant="ghost" onClick={() => setCaptured([])}>
          Clear
        </Button>
        <span className="text-xs text-vmd-textSubtle">{captured.length} captured</span>
      </div>

      {captured.length === 0 && (
        <p className="text-sm text-vmd-textSubtle">No events received yet this session.</p>
      )}

      <div className="space-y-2">
        {captured.map((event, idx) => (
          <Card key={`${event.timestamp}-${idx}`}>
            <div className="mb-1 flex flex-wrap items-center justify-between gap-2 text-sm">
              <span className="font-mono font-medium text-vmd-textStrong">{event.type}</span>
              <span className="text-xs text-vmd-textSubtle">{event.entity_id}</span>
              <span className="text-xs text-vmd-textSubtle">{formatTime(event.timestamp)}</span>
            </div>
            {event.entity_tags.length > 0 && (
              <p className="mb-1 text-xs text-vmd-textSubtle">tags: {event.entity_tags.join(', ')}</p>
            )}
            <pre className="vmd-code-block max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs">
              {JSON.stringify(event.payload, null, 2)}
            </pre>
          </Card>
        ))}
      </div>
    </div>
  );
}
