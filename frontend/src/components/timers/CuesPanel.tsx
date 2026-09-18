import { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { useCreateCue, useCues, useDeleteCue, useUpdateCue } from '../../api/timers';
import { usePermission } from '../../hooks/usePermission';
import { Button } from '../ui/Button';
import { Textarea } from '../ui/Input';

/**
 * Plan §5.10/§12 Runsheet + Live Cues tabs. Both tabs operate on the same
 * `PrompterCue` REST resource (`type: 'runsheet'` for the pre-built
 * ordered list, anything else — 'script'/'note' — pushed ad-hoc during the
 * event); they're split into two tabs here purely as a UX grouping, not a
 * backend distinction.
 */
export function CuesPanel({ entityId }: { entityId: string }) {
  const [tab, setTab] = useState<'runsheet' | 'live'>('runsheet');
  const { data: cues } = useCues(entityId);
  const createCue = useCreateCue(entityId);
  const updateCue = useUpdateCue(entityId);
  const deleteCue = useDeleteCue(entityId);
  const canEdit = usePermission('prompter:edit');
  const [draft, setDraft] = useState('');

  const runsheetCues = (cues ?? []).filter((c) => c.type === 'runsheet');
  const liveCues = (cues ?? []).filter((c) => c.type !== 'runsheet');
  const shown = tab === 'runsheet' ? runsheetCues : liveCues;

  function addCue() {
    if (!draft.trim()) return;
    createCue.mutate(
      {
        timer_entity_id: entityId,
        content: draft,
        type: tab === 'runsheet' ? 'runsheet' : 'note',
        sort_order: shown.length,
      },
      { onSuccess: () => setDraft('') },
    );
  }

  return (
    <div>
      <div className="mb-3 flex gap-2 border-b border-vmd-border">
        {(['runsheet', 'live'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-1.5 text-sm ${tab === t ? 'border-b-2 border-vmd-textStrong text-vmd-textStrong' : 'text-vmd-textMuted'}`}
          >
            {t === 'runsheet' ? 'Runsheet' : 'Live Cues'}
          </button>
        ))}
      </div>

      {canEdit && (
        <div className="mb-3 flex items-start gap-2">
          <Textarea
            rows={2}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Markdown cue content…"
            className="flex-1"
          />
          <Button onClick={addCue} disabled={createCue.isPending}>
            <Plus size={14} /> Push
          </Button>
        </div>
      )}

      <ul className="space-y-2">
        {shown.map((cue) => (
          <li key={cue.id} className="rounded-lg border border-vmd-border bg-vmd-surfaceSubtle p-3">
            <div className="mb-1 flex items-center justify-between">
              <span className={`text-xs ${cue.is_active ? 'text-vmd-success' : 'text-vmd-textSubtle'}`}>
                {cue.is_active ? 'Active' : 'Inactive'}
              </span>
              {canEdit && (
                <div className="flex gap-2">
                  <button
                    onClick={() => updateCue.mutate({ cueId: cue.id, body: { is_active: !cue.is_active } })}
                    className="text-xs text-vmd-link hover:underline"
                  >
                    Toggle
                  </button>
                  <button onClick={() => deleteCue.mutate(cue.id)} className="text-vmd-textSubtle hover:text-vmd-danger">
                    <Trash2 size={14} />
                  </button>
                </div>
              )}
            </div>
            <div className="markdown-cue text-sm text-vmd-text [&_p]:my-1 [&_ul]:list-disc [&_ul]:pl-5 [&_strong]:text-vmd-textStrong">
              <ReactMarkdown>{cue.content}</ReactMarkdown>
            </div>
          </li>
        ))}
        {shown.length === 0 && <p className="text-sm text-vmd-textSubtle">No cues yet.</p>}
      </ul>
    </div>
  );
}
