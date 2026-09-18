import { useWsStore } from '../../stores/ws';

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString();
}

/** Renders the rolling last-50 `qecomp:events` buffer from `useWsStore`
 * (plan §C.8.1: "Recent event stream" is WS-owned, never REST). */
export function LiveEventFeed({ limit = 50 }: { limit?: number }) {
  const events = useWsStore((s) => s.recentEvents);
  const shown = events.slice(0, limit);

  if (shown.length === 0) {
    return <p className="text-sm text-vmd-textSubtle">No events received yet this session.</p>;
  }

  return (
    <ul className="max-h-[28rem] space-y-1.5 overflow-y-auto text-sm">
      {shown.map((event, idx) => (
        <li
          key={`${event.timestamp}-${idx}`}
          className="flex items-start justify-between gap-3 rounded-lg border border-vmd-border bg-vmd-surfaceSubtle px-3 py-1.5"
        >
          <div>
            <span className="font-mono text-vmd-textStrong">{event.type}</span>
            <span className="ml-2 text-vmd-textSubtle">{event.entity_id}</span>
          </div>
          <span className="shrink-0 text-xs text-vmd-textSubtle">{formatTime(event.timestamp)}</span>
        </li>
      ))}
    </ul>
  );
}
