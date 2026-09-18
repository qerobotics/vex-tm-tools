import { useWebSocket } from '../hooks/useWebSocket';
import { useIntegrations } from '../api/integrations';
import { useReadyz } from '../api/health';
import { PageHeader, Card } from '../components/ui/Card';
import { TelemetryCard } from '../components/integrations/TelemetryCard';
import { LiveEventFeed } from '../components/ws/LiveEventFeed';
import { StatusBadge } from '../components/ui/Badge';

/**
 * Plan §12 Dashboard. Integration health/telemetry cards read config from
 * TanStack Query (`useIntegrations`) and live status from the WS store
 * (via `TelemetryCard`/`IntegrationStatusChip`) — never merged, per §C.8.4.
 *
 * GAP: plan §11 lists `GET /api/v1/status` for cluster/leader status; no
 * such route exists in the merged backend (grep of backend/routers/ and
 * backend/main.py confirms it). This card is built from `/readyz` (db/redis
 * reachability) instead, with an explicit note rather than fabricated
 * leader/heartbeat data.
 */
export function DashboardPage() {
  useWebSocket('/ws/events');
  const { data: integrations, isLoading } = useIntegrations();
  const { data: ready } = useReadyz();

  return (
    <div>
      <PageHeader title="Dashboard" subtitle="Live integration health, telemetry, and event stream." />

      <section className="mb-6">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-vmd-textMuted">
          Cluster Status
        </h2>
        <Card>
          {ready ? (
            <div className="flex flex-wrap items-center gap-4 text-sm">
              <StatusBadge status={ready.status === 'ok' ? 'CONNECTED' : 'DEGRADED'} />
              <span>Postgres: {ready.db ? 'reachable' : 'unreachable'}</span>
              <span>Redis: {ready.redis ? 'reachable' : 'unreachable'}</span>
            </div>
          ) : (
            <p className="text-sm text-vmd-textSubtle">Loading readiness…</p>
          )}
          <p className="mt-2 text-xs text-vmd-textSubtle">
            Note: the plan's §11 <code>GET /api/v1/status</code> (leader node, both node
            heartbeats) is not implemented in the current backend — this card shows{' '}
            <code>/readyz</code>'s DB/Redis reachability instead.
          </p>
        </Card>
      </section>

      <section className="mb-6">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-vmd-textMuted">
          Integration Telemetry
        </h2>
        {isLoading && <p className="text-sm text-vmd-textSubtle">Loading integrations…</p>}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {integrations?.map((integration) => (
            <TelemetryCard key={integration.entity_id} integration={integration} />
          ))}
        </div>
        {integrations && integrations.length === 0 && (
          <p className="text-sm text-vmd-textSubtle">
            No integrations configured yet — add one from the Integrations page.
          </p>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-vmd-textMuted">
          Recent Events
        </h2>
        <Card>
          <LiveEventFeed limit={50} />
        </Card>
      </section>
    </div>
  );
}
