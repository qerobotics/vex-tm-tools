import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/http';
import { useIntegrations } from '../api/integrations';
import { usePermission } from '../hooks/usePermission';
import { PageHeader, Card } from '../components/ui/Card';
import { Select } from '../components/ui/Input';

interface DebugLogEntry {
  timestamp: number;
  type: string;
  payload: Record<string, unknown>;
  [key: string]: unknown;
}

function useIntegrationDebugLog(entityId: string | null) {
  return useQuery({
    queryKey: ['debug', 'integrations', entityId, 'log'],
    queryFn: () =>
      apiFetch<DebugLogEntry[]>(`/api/v1/debug/integrations/${encodeURIComponent(entityId!)}/log`),
    enabled: Boolean(entityId),
    refetchInterval: 5000,
  });
}

function formatTime(ts: number): string {
  // Backend timestamps elsewhere in this app (EventBusMessage) are unix
  // seconds; guard against a ms-resolution value too.
  const ms = ts > 1e12 ? ts : ts * 1000;
  return new Date(ms).toLocaleString();
}

/** Appendix A.11 debug view: last 100 raw events per integration instance,
 * backed by `GET /api/v1/debug/integrations/{entity_id}/log` (a ring
 * buffer landing from a parallel backend agent — see AUDIT_FINDINGS.md
 * 1.10). Gated on `settings:edit` like the other debug views. */
export function DebugIntegrationLogPage() {
  const canView = usePermission('settings:edit');
  const { data: integrations } = useIntegrations();
  const [entityId, setEntityId] = useState<string | null>(null);
  const { data: log, isLoading, isError } = useIntegrationDebugLog(entityId);

  if (!canView) {
    return (
      <div>
        <PageHeader title="Integration Debug Log" subtitle="Developer view." />
        <p className="text-sm text-vmd-textSubtle">
          You lack the <code>settings:edit</code> permission required to view debug data.
        </p>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Integration Debug Log"
        subtitle="Last 100 raw events per integration instance (Appendix A.11)."
      />

      <div className="mb-4 max-w-xs">
        <Select value={entityId ?? ''} onChange={(e) => setEntityId(e.target.value || null)}>
          <option value="">Select an integration instance…</option>
          {(integrations ?? []).map((i) => (
            <option key={i.entity_id} value={i.entity_id}>
              {i.entity_id} ({i.domain})
            </option>
          ))}
        </Select>
      </div>

      {!entityId && <p className="text-sm text-vmd-textSubtle">Select an integration instance above.</p>}
      {entityId && isLoading && <p className="text-sm text-vmd-textSubtle">Loading…</p>}
      {entityId && isError && (
        <p className="text-sm text-vmd-danger">
          Failed to load the debug log — the backend's ring-buffer endpoint may not be deployed yet.
        </p>
      )}
      {entityId && log && log.length === 0 && (
        <p className="text-sm text-vmd-textSubtle">No events recorded yet for this instance.</p>
      )}

      {entityId && log && log.length > 0 && (
        <div className="space-y-2">
          {log.map((entry, idx) => (
            <Card key={idx}>
              <div className="mb-1 flex items-center justify-between text-sm">
                <span className="font-mono font-medium text-vmd-textStrong">{entry.type}</span>
                <span className="text-xs text-vmd-textSubtle">{formatTime(entry.timestamp)}</span>
              </div>
              <pre className="vmd-code-block max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs">
                {JSON.stringify(entry.payload, null, 2)}
              </pre>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
