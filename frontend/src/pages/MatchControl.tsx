import { useState } from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import { useIntegrations, useCallIntegrationService } from '../api/integrations';
import { useWsStore } from '../stores/ws';
import { usePermission } from '../hooks/usePermission';
import { useUiStore } from '../stores/ui';
import { PageHeader, Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input, Select } from '../components/ui/Input';
import { IntegrationStatusChip } from '../components/integrations/IntegrationStatusChip';
import type { IntegrationInstance } from '../types/api';

/** VEX TM's known audience-display modes. `backend/modules/integrations/
 * vex_tm/services.yaml`'s `set_audience_display` service declares `display`
 * as a required string with no enum/allowed-values list, so this is the
 * standard VEX TM display-mode set used as a reasonable default (finding
 * 3.5 in AUDIT_FINDINGS.md). */
const AUDIENCE_DISPLAY_MODES = [
  'BLANK',
  'LOGO',
  'SCHEDULE',
  'RANKINGS',
  'RANKINGS_SKILLS',
  'MATCH_PREVIEW',
  'IN_MATCH',
  'MATCH_RESULTS',
  'SEASON',
  'SKILLS',
  'SKILLS_RANKINGS',
  'ALLIANCE_SELECTION',
  'ELIMINATION_BRACKET',
] as const;

/** Plan §12/§5.16 Match Control, merged with the former Field Monitor page:
 * per `vex_tm.*` instance, manual override buttons
 * (`POST /api/v1/integrations/{entity_id}/service/{service}`, exactly the
 * service names in backend/modules/integrations/vex_tm/services.yaml)
 * followed by a live card per known field.
 *
 * The backend models one `vex_tm` instance = one field set (plan Appendix
 * B.5) with fields identified only by `fieldID` inside event payloads —
 * there's no `/api/v1/fields` listing endpoint, so the field cards show
 * any fieldID that has appeared in a `fieldMatchAssigned`/`upcoming_match`
 * WS event this session. Fields with no event yet simply don't appear
 * (there's no static field topology endpoint to seed an empty list from). */
export function MatchControlPage() {
  useWebSocket('/ws/events');
  const { data: integrations } = useIntegrations();
  const tmInstances = (integrations ?? []).filter((i) => i.domain === 'vex_tm');

  return (
    <div>
      <PageHeader
        title="Match Control"
        subtitle="Live field states and manual overrides for VEX TM instances."
      />
      {tmInstances.length === 0 && (
        <p className="text-sm text-vmd-textSubtle">No vex_tm integrations configured yet.</p>
      )}
      <div className="space-y-6">
        {tmInstances.map((instance) => (
          <section key={instance.entity_id}>
            <TmSectionHeader instance={instance} />
            <FieldCards />
          </section>
        ))}
      </div>
    </div>
  );
}

function FieldCards() {
  const currentMatches = useWsStore((s) => s.currentMatches);
  const recentEvents = useWsStore((s) => s.recentEvents);
  const fieldIds = Object.keys(currentMatches).filter((key) => !key.includes('.'));

  if (fieldIds.length === 0) {
    return <p className="text-sm text-vmd-textSubtle">No field events observed yet this session.</p>;
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {fieldIds.map((fieldId) => {
        const match = currentMatches[fieldId];
        const events = recentEvents.filter((e) => String(e.payload.fieldID ?? '') === fieldId).slice(0, 5);
        return (
          <Card key={fieldId}>
            <p className="mb-1 font-medium text-vmd-textStrong">Field {fieldId}</p>
            {match ? (
              <div className="mb-2 text-sm text-vmd-text">
                <p>
                  Match {String(match.matchNum ?? '?')} · {String(match.round ?? '')}
                </p>
                <p className="text-vmd-textMuted">Red: {(match.redTeams ?? []).join(', ') || '—'}</p>
                <p className="text-vmd-textMuted">Blue: {(match.blueTeams ?? []).join(', ') || '—'}</p>
              </div>
            ) : (
              <p className="mb-2 text-sm text-vmd-textSubtle">No match queued.</p>
            )}
            <p className="mb-1 text-xs font-semibold uppercase text-vmd-textSubtle">Recent events</p>
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
  );
}

/** Field Monitor's per-instance section heading (name + status chip), with
 * that field set's manual controls beside/under it. TM commands apply to
 * the whole field set (the websocket protocol has no per-field commands —
 * see `_SERVICE_COMMANDS` in the vex_tm integration), so the buttons live
 * here, above the set's field cards. */
function TmSectionHeader({ instance }: { instance: IntegrationInstance }) {
  const canControl = usePermission('tm:control');
  const pushToast = useUiStore((s) => s.pushToast);
  const callService = useCallIntegrationService();
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
    { label: 'Queue Prev', service: 'queue_prev_match' },
    { label: 'Queue Next', service: 'queue_next_match' },
    { label: 'Start Match', service: 'start_match' },
    { label: 'End Early', service: 'end_early' },
    { label: 'Abort', service: 'abort' },
    { label: 'Reset', service: 'reset' },
  ];

  return (
    <div className="mb-3">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-vmd-textMuted">
          {instance.display_name}
        </h2>
        <IntegrationStatusChip integration={instance} />
        <span className="text-xs text-vmd-textSubtle">{instance.entity_id}</span>
      </div>

      {!canControl && (
        <p className="mb-2 text-xs text-vmd-textSubtle">
          You lack the <code>tm:control</code> permission — controls are read-only.
        </p>
      )}

      <div className="flex flex-wrap items-center gap-2">
        {simpleServices.map(({ label, service }) => (
          <Button key={service} disabled={!canControl || callService.isPending} onClick={() => fire(service)}>
            {label}
          </Button>
        ))}

        <span className="mx-1 hidden h-6 w-px bg-vmd-border sm:block" />

        {/* GAP (AUDIT_FINDINGS.md 3.5): no backend "list skills runs" endpoint
            exists to populate a real dropdown of available skills-run IDs
            (checked backend/routers/teams.py and the vex_tm integration's
            exposed data — nothing fetchable). Using a numeric input with a
            sensible min/step instead of a fully free-text field. */}
        <Input
          type="number"
          min={1}
          step={1}
          placeholder="Skills ID"
          value={skillsId}
          onChange={(e) => setSkillsId(e.target.value)}
          className="w-28"
        />
        <Button
          disabled={!canControl || !skillsId || callService.isPending}
          onClick={() => fire('queue_skills', { skills_id: Number(skillsId) })}
        >
          Queue Skills
        </Button>

        <span className="mx-1 hidden h-6 w-px bg-vmd-border sm:block" />

        <Select value={display} onChange={(e) => setDisplay(e.target.value)} className="w-52">
          <option value="">Audience display…</option>
          {AUDIENCE_DISPLAY_MODES.map((mode) => (
            <option key={mode} value={mode}>
              {mode}
            </option>
          ))}
        </Select>
        <Button
          disabled={!canControl || !display || callService.isPending}
          onClick={() => fire('set_audience_display', { display })}
        >
          Set Display
        </Button>
      </div>
    </div>
  );
}
