import { useState } from 'react';
import { Plus, Trash2, RotateCw } from 'lucide-react';
import { useWebSocket } from '../hooks/useWebSocket';
import { useTimers, useDeleteTimer, useUpdateTimer, useStartTimer, useStopTimer, useResetTimer } from '../api/timers';
import { useWsStore } from '../stores/ws';
import { usePermission } from '../hooks/usePermission';
import { useUiStore } from '../stores/ui';
import { PageHeader, Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { CopyButton } from '../components/ui/CopyButton';
import { TimerEditorModal } from '../components/timers/TimerEditorModal';
import { CuesPanel } from '../components/timers/CuesPanel';
import type { TimerInstance } from '../types/api';

export function TimersPage() {
  useWebSocket('/ws/events');
  const { data: timers, isLoading } = useTimers();
  const deleteTimer = useDeleteTimer();
  const updateTimer = useUpdateTimer();
  const canEdit = usePermission('timers:edit');
  const canControl = usePermission('prompter:control');
  const pushToast = useUiStore((s) => s.pushToast);
  const startTimer = useStartTimer();
  const stopTimer = useStopTimer();
  const resetTimer = useResetTimer();
  const liveTimerStates = useWsStore((s) => s.timerStates);

  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<TimerInstance | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <div>
      <PageHeader
        title="Timer-Teleprompter"
        subtitle="EMCEE countdown + teleprompter instances."
        action={
          canEdit && (
            <Button
              variant="primary"
              onClick={() => {
                setEditing(null);
                setModalOpen(true);
              }}
            >
              <Plus size={16} /> New Timer
            </Button>
          )
        }
      />

      {isLoading && <p className="text-sm text-vmd-textSubtle">Loading…</p>}
      <div className="space-y-3">
        {timers?.map((timer) => {
          const live = liveTimerStates[timer.entity_id];
          const prompterUrl = `${window.location.origin}/prompter/${timer.entity_id}?token=${timer.prompter_token}`;
          return (
            <Card key={timer.entity_id}>
              <div className="flex items-start justify-between">
                <div>
                  <p className="font-medium text-vmd-textStrong">{timer.display_name}</p>
                  <p className="text-xs text-vmd-textSubtle">
                    {timer.entity_id} · fieldset {timer.field_set_id} / field {timer.field_id} ·{' '}
                    {timer.duration_s}s
                  </p>
                  {live && (
                    <p className="mt-1 text-xs text-vmd-success">
                      {String(live.phase ?? (live.running ? 'running' : 'idle'))}
                      {live.remaining !== undefined ? ` · remaining ${live.remaining}` : ''}
                      {live.elapsed !== undefined ? ` · elapsed ${live.elapsed}` : ''}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {canControl && (
                    <>
                      <Button onClick={() => startTimer.mutate(timer.entity_id)}>Start</Button>
                      <Button onClick={() => stopTimer.mutate(timer.entity_id)}>Stop</Button>
                      <Button onClick={() => resetTimer.mutate(timer.entity_id)}>
                        <RotateCw size={14} />
                      </Button>
                    </>
                  )}
                  <button
                    onClick={() => {
                      setEditing(timer);
                      setModalOpen(true);
                    }}
                    className="text-sm text-vmd-link hover:underline"
                  >
                    Edit
                  </button>
                  {canEdit && (
                    <button
                      onClick={() => deleteTimer.mutate(timer.entity_id)}
                      className="text-vmd-textSubtle hover:text-vmd-danger"
                    >
                      <Trash2 size={16} />
                    </button>
                  )}
                </div>
              </div>

              <div className="mt-2 flex items-center gap-2 text-xs text-vmd-textMuted">
                <span className="truncate">{prompterUrl}</span>
                <CopyButton value={prompterUrl} />
                {canEdit && (
                  <Button
                    variant="ghost"
                    onClick={() =>
                      updateTimer.mutate(
                        { entityId: timer.entity_id, body: { regenerate_token: true } },
                        { onSuccess: () => pushToast('Token regenerated — old links are now invalid', 'success') },
                      )
                    }
                  >
                    Regenerate token
                  </Button>
                )}
              </div>

              <button
                onClick={() => setExpanded(expanded === timer.entity_id ? null : timer.entity_id)}
                className="mt-2 text-xs text-vmd-link hover:underline"
              >
                {expanded === timer.entity_id ? 'Hide cues' : 'Manage cues'}
              </button>

              {expanded === timer.entity_id && (
                <div className="mt-3 border-t border-vmd-border pt-3">
                  <CuesPanel entityId={timer.entity_id} />
                </div>
              )}
            </Card>
          );
        })}
        {timers && timers.length === 0 && <p className="text-sm text-vmd-textSubtle">No timer instances yet.</p>}
      </div>

      <TimerEditorModal open={modalOpen} onClose={() => setModalOpen(false)} editing={editing} />
    </div>
  );
}
