import { StatusBadge } from '../ui/Badge';
import { useWsStore } from '../../stores/ws';
import type { IntegrationInstance } from '../../types/api';

/**
 * Reads live status from the WS store, config (REST-owned) from the
 * `IntegrationInstance` prop passed in by the caller's `useIntegrations()`
 * query — never merges the two into one object (plan §C.8.4). Falls back
 * to the REST-provided `status` (populated by the router from
 * `loader.get_instance_status()` at fetch time) until a `integration_status`
 * WS event arrives for this entity.
 */
export function IntegrationStatusChip({ integration }: { integration: IntegrationInstance }) {
  const liveStatus = useWsStore((s) => s.integrationStatuses[integration.entity_id]);
  return <StatusBadge status={liveStatus ?? integration.status} />;
}
