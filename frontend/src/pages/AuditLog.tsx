import { useState } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import { useWsStore } from '../stores/ws';
import { PageHeader, Card } from '../components/ui/Card';
import { Input } from '../components/ui/Input';

/**
 * GAP: plan §11/§12 describe a paginated `GET /api/v1/audit` REST endpoint
 * plus a live `audit_entry` WebSocket event (also referenced in §C.8.1's
 * data-ownership table). Neither exists in the merged backend as of this
 * wave — `backend/schemas/audit.py`'s `AuditLogRead` schema exists, but
 * there is no `backend/routers/audit.py` and `backend/models/audit.py`'s
 * table is never written to by any router (grepped across
 * `backend/routers/*.py`). Rather than fabricate history or a fake
 * endpoint, this page:
 *   1. Filters the same `/ws/events` live stream every other page uses for
 *      any event literally typed `audit_entry` (future-proofing — if a
 *      later wave starts publishing them, this page picks them up with no
 *      changes), and
 *   2. Clearly states that historical (paginated, filterable) audit data
 *      is not available yet, rather than silently showing an empty table
 *      that looks like "no audit activity has ever happened."
 */
export function AuditLogPage() {
  useWebSocket('/ws/events');
  const events = useWsStore((s) => s.recentEvents);
  const [userFilter, setUserFilter] = useState('');

  const auditEvents = events
    .filter((e) => e.type === 'audit_entry')
    .filter((e) => !userFilter || String(e.payload.user_id ?? '').includes(userFilter));

  return (
    <div>
      <PageHeader title="Audit Log" subtitle="Create/update/delete operations across the system." />

      <Card className="mb-4 border-amber-400/30 bg-amber-400/5">
        <p className="text-sm text-amber-200">
          No <code>GET /api/v1/audit</code> endpoint exists in the backend yet, so historical,
          paginated, filterable audit records aren't available from this page. Below is a
          best-effort live view of any <code>audit_entry</code> events seen on <code>/ws/events</code>{' '}
          since this page was opened (none are currently published by any router).
        </p>
      </Card>

      <Input
        placeholder="Filter by user (live events only)"
        value={userFilter}
        onChange={(e) => setUserFilter(e.target.value)}
        className="mb-4 max-w-xs"
      />

      <Card>
        {auditEvents.length === 0 ? (
          <p className="text-sm text-vmd-textSubtle">No audit_entry events observed this session.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase text-vmd-textSubtle">
                <th className="pb-2">Time</th>
                <th className="pb-2">User</th>
                <th className="pb-2">Action</th>
                <th className="pb-2">Resource</th>
              </tr>
            </thead>
            <tbody>
              {auditEvents.map((e, idx) => (
                <tr key={idx} className="border-t border-vmd-border">
                  <td className="py-1.5">{new Date(e.timestamp * 1000).toLocaleString()}</td>
                  <td className="py-1.5">{String(e.payload.user_id ?? '—')}</td>
                  <td className="py-1.5">{String(e.payload.action ?? '—')}</td>
                  <td className="py-1.5">
                    {String(e.payload.resource_type ?? '—')} / {String(e.payload.resource_id ?? '—')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
