import { Card } from '../ui/Card';
import { IntegrationStatusChip } from './IntegrationStatusChip';
import { useIntegrationState } from '../../api/integrations';
import type { IntegrationInstance } from '../../types/api';

/** Renders whatever `call_service('get_state')`-equivalent
 * `GET /integrations/{id}/state` returns for one integration instance
 * (plan §12 Dashboard "Live telemetry"). The shape of `state` is
 * integration-specific and only loosely typed in the backend
 * (`Integration.get_state() -> dict`), so this renders it generically
 * (key/value rows) rather than assuming Spotify/ATEM/ZerOS/TM-specific
 * fields exist — each domain's `get_state()` implementation decides what
 * keys are present. */
export function TelemetryCard({ integration }: { integration: IntegrationInstance }) {
  const { data } = useIntegrationState(integration.entity_id);
  const state = data?.state ?? {};
  const entries = Object.entries(state);

  return (
    <Card>
      <div className="mb-2 flex items-center justify-between">
        <div>
          <p className="font-medium text-vmd-textStrong">{integration.display_name}</p>
          <p className="text-xs text-vmd-textSubtle">{integration.entity_id}</p>
        </div>
        <IntegrationStatusChip integration={integration} />
      </div>
      {entries.length === 0 ? (
        <p className="text-sm text-vmd-textSubtle">No telemetry reported.</p>
      ) : (
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
          {entries.map(([key, value]) => (
            <div key={key} className="contents">
              <dt className="text-vmd-textMuted">{key}</dt>
              <dd className="truncate text-right text-vmd-text">{String(value)}</dd>
            </div>
          ))}
        </dl>
      )}
    </Card>
  );
}
