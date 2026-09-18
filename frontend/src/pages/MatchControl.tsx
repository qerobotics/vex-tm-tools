import { useState } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import { useIntegrations, useCallIntegrationService } from '../api/integrations';
import { useWsStore } from '../stores/ws';
import { usePermission } from '../hooks/usePermission';
import { useUiStore } from '../stores/ui';
import { PageHeader, Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { IntegrationStatusChip } from '../components/integrations/IntegrationStatusChip';
import type { IntegrationInstance } from '../types/api';

/** Plan §12/§5.16 Match Control: manual override buttons per `vex_tm.*`
 * instance, calling `POST /api/v1/integrations/{entity_id}/service/{service}`
 * (backend/modules/integrations/vex_tm/services.yaml's exact service names). */
export function MatchControlPage() {
  useWebSocket('/ws/events');
  const { data: integrations } = useIntegrations();
  const tmInstances = (integrations ?? []).filter((i) => i.domain === 'vex_tm');

  return (
    <div>
      <PageHeader title="Match Control" subtitle="Manual field overrides for VEX TM instances." />
      {tmInstances.length === 0 && (
        <p className="text-sm text-vmd-textSubtle">No vex_tm integrations configured yet.</p>
      )}
      <div className="space-y-4">
        {tmInstances.map((instance) => (
          <TmControlCard key={instance.entity_id} instance={instance} />
        ))}
      </div>
    </div>
  );
}

function TmControlCard({ instance }: { instance: IntegrationInstance }) {
  const canControl = usePermission('tm:control');
  const pushToast = useUiStore((s) => s.pushToast);
  const callService = useCallIntegrationService();
  const currentMatches = useWsStore((s) => s.currentMatches);
  const [skillsId, setSkillsId] = useState('');
  const [display, setDisplay] = useState('');

  function fire(service: string, data?: Record<string, unknown>) {
    callService.mutate(
      { entityId: instance.entity_id, service, data },
      {
        onSuccess: () => pushToast(`${service} sent to ${instance.entity_id}`, 'success'),
        onError: (err) => pushToast(err instanceof Error ? err.message : 'Service call failed', 'error'),
      },
    );
  }

  const simpleServices: { label: string; service: string }[] = [
    { label: 'Queue Next', service: 'queue_next_match' },
    { label: 'Queue Prev', service: 'queue_prev_match' },
    { label: 'Start Match', service: 'start_match' },
    { label: 'End Early', service: 'end_early' },
    { label: 'Abort', service: 'abort' },
    { label: 'Reset', service: 'reset' },
  ];

  const matchKeys = Object.keys(currentMatches).filter((k) => !k.includes('.'));

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <div>
          <p className="font-medium text-vmd-textStrong">{instance.display_name}</p>
          <p className="text-xs text-vmd-textSubtle">{instance.entity_id}</p>
        </div>
        <IntegrationStatusChip integration={instance} />
      </div>

      {!canControl && (
        <p className="mb-3 text-xs text-vmd-textSubtle">
          You lack the <code>tm:control</code> permission — controls are read-only.
        </p>
      )}

      <div className="mb-4 flex flex-wrap gap-2">
        {simpleServices.map(({ label, service }) => (
          <Button key={service} disabled={!canControl || callService.isPending} onClick={() => fire(service)}>
            {label}
          </Button>
        ))}
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Input
          placeholder="Skills ID"
          value={skillsId}
          onChange={(e) => setSkillsId(e.target.value)}
          className="w-32"
        />
        <Button
          disabled={!canControl || !skillsId || callService.isPending}
          onClick={() => fire('queue_skills', { skills_id: Number(skillsId) })}
        >
          Queue Skills
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Input
          placeholder="Audience display mode"
          value={display}
          onChange={(e) => setDisplay(e.target.value)}
          className="w-56"
        />
        <Button
          disabled={!canControl || !display || callService.isPending}
          onClick={() => fire('set_audience_display', { display })}
        >
          Set Audience Display
        </Button>
      </div>

      {matchKeys.length > 0 && (
        <div className="mt-4 border-t border-vmd-border pt-3 text-sm text-vmd-textMuted">
          <p className="mb-1 text-xs font-semibold uppercase text-vmd-textSubtle">Live queued matches</p>
          {matchKeys.map((k) => {
            const m = currentMatches[k];
            return (
              <p key={k}>
                Field {k}: Match {String(m.matchNum ?? '?')} — Red {(m.redTeams ?? []).join(',')} vs Blue{' '}
                {(m.blueTeams ?? []).join(',')}
              </p>
            );
          })}
        </div>
      )}
    </Card>
  );
}
