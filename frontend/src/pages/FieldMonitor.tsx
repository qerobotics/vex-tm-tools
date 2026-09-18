import { useWebSocket } from '../hooks/useWebSocket';
import { useIntegrations } from '../api/integrations';
import { useWsStore } from '../stores/ws';
import { PageHeader, Card } from '../components/ui/Card';
import { IntegrationStatusChip } from '../components/integrations/IntegrationStatusChip';

/**
 * Plan §12 Field Monitor: one card per field across all `vex_tm.*`
 * instances. The backend models one `vex_tm` instance = one field set
 * (plan Appendix B.5) with fields identified only by `fieldID` inside
 * event payloads — there's no `/api/v1/fields` listing endpoint, so this
 * page shows a card per *currently known* field: any fieldID that has
 * shown up in a `fieldMatchAssigned`/`upcoming_match` WS event for a given
 * `vex_tm` instance, grouped under that instance. Fields with no event yet
 * this session simply haven't appeared (there's no static field topology
 * endpoint to seed an empty list from).
 */
export function FieldMonitorPage() {
  useWebSocket('/ws/events');
  const { data: integrations } = useIntegrations();
  const currentMatches = useWsStore((s) => s.currentMatches);
  const recentEvents = useWsStore((s) => s.recentEvents);

  const tmInstances = (integrations ?? []).filter((i) => i.domain === 'vex_tm');

  return (
    <div>
      <PageHeader title="Field Monitor" subtitle="Live field states across all VEX TM instances." />

      {tmInstances.length === 0 && (
        <p className="text-sm text-vmd-textSubtle">No vex_tm integrations configured yet.</p>
      )}

      <div className="space-y-6">
        {tmInstances.map((instance) => {
          const fieldIds = Object.keys(currentMatches).filter((key) => !key.includes('.'));
          return (
            <section key={instance.entity_id}>
              <div className="mb-2 flex items-center gap-2">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-vmd-textMuted">
                  {instance.display_name}
                </h2>
                <IntegrationStatusChip integration={instance} />
              </div>
              {fieldIds.length === 0 ? (
                <p className="text-sm text-vmd-textSubtle">No field events observed yet this session.</p>
              ) : (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {fieldIds.map((fieldId) => {
                    const match = currentMatches[fieldId];
                    const events = recentEvents
                      .filter((e) => String(e.payload.fieldID ?? '') === fieldId)
                      .slice(0, 5);
                    return (
                      <Card key={fieldId}>
                        <p className="mb-1 font-medium text-vmd-textStrong">Field {fieldId}</p>
                        {match ? (
                          <div className="mb-2 text-sm text-vmd-text">
                            <p>
                              Match {String(match.matchNum ?? '?')} · {String(match.round ?? '')}
                            </p>
                            <p className="text-vmd-textMuted">
                              Red: {(match.redTeams ?? []).join(', ') || '—'}
                            </p>
                            <p className="text-vmd-textMuted">
                              Blue: {(match.blueTeams ?? []).join(', ') || '—'}
                            </p>
                          </div>
                        ) : (
                          <p className="mb-2 text-sm text-vmd-textSubtle">No match queued.</p>
                        )}
                        <p className="mb-1 text-xs font-semibold uppercase text-vmd-textSubtle">
                          Recent events
                        </p>
                        <ul className="space-y-0.5 text-xs text-vmd-textMuted">
                          {events.length === 0 && <li>—</li>}
                          {events.map((e, idx) => (
                            <li key={idx} className="font-mono">
                              {e.type}
                            </li>
                          ))}
                        </ul>
                      </Card>
                    );
                  })}
                </div>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
