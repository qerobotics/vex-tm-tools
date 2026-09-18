import { useWebSocket } from '../hooks/useWebSocket';
import { useIntegrations } from '../api/integrations';
import { useReadyz } from '../api/health';
import { useClusterStatus } from '../api/status';
import { PageHeader, Card } from '../components/ui/Card';
import { TelemetryCard } from '../components/integrations/TelemetryCard';
import { LiveEventFeed } from '../components/ws/LiveEventFeed';
import { StatusBadge } from '../components/ui/Badge';

/**
 * Plan §12 Dashboard. Integration health/telemetry cards read config from
 * TanStack Query (`useIntegrations`) and live status from the WS store
 * (via `TelemetryCard`/`IntegrationStatusChip`) — never merged, per §C.8.4.
 *
 * Cluster Status now reads the real `GET /api/v1/status` endpoint (plan
 * §11, audit finding 1.7) for leader node info and per-integration health,
 * with `/readyz`'s db/redis reachability kept alongside it (a distinct
 * concern — process-level readiness, not cluster leadership). The
 * dedicated Redis-unavailable warning banner (Appendix A.10 / audit finding
 * 3.7) is mounted globally in `PageLayout`, not here.
 */
export function DashboardPage() {
  useWebSocket('/ws/events');
  const { data: integrations, isLoading } = useIntegrations();
  const { data: ready } = useReadyz();
  const { data: status, isLoading: statusLoading, isError: statusError } = useClusterStatus();

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

          <div className="mt-3 border-t border-vmd-border pt-3 text-sm">
            {statusLoading && <p className="text-vmd-textSubtle">Loading cluster status…</p>}
            {statusError && (
              <p className="text-vmd-textSubtle">Cluster status is currently unavailable.</p>
            )}
            {status && (
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-4">
                  <span>
                    Leader:{' '}
                    {status.leader?.is_leader === undefined ? (
                      'unknown'
                    ) : status.leader.is_leader ? (
                      'this node'
                    ) : (
                      `${status.leader.leader_address ?? 'unknown address'}`
                    )}
                  </span>
                </div>
                {status.integrations && status.integrations.length > 0 && (
                  <div className="flex flex-wrap gap-3">
                    {status.integrations.map((entry) => (
                      <span key={entry.entity_id ?? Math.random()} className="flex items-center gap-1.5">
                        <StatusBadge status={entry.status ?? 'DISCONNECTED'} />
                        <span className="text-xs text-vmd-textSubtle">{entry.entity_id ?? '—'}</span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
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
