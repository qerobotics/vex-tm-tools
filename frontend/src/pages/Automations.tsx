import { useState } from 'react';
import { Plus, Play, Trash2, FolderPlus } from 'lucide-react';
import {
  useAutomationFolders,
  useAutomations,
  useCreateAutomationFolder,
  useDeleteAutomation,
  useTriggerAutomation,
  useUpdateAutomation,
} from '../api/automations';
import { usePermission } from '../hooks/usePermission';
import { useUiStore } from '../stores/ui';
import { PageHeader, Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Toggle } from '../components/ui/Toggle';
import { AutomationEditorModal } from '../components/automations/AutomationEditorModal';
import type { Automation } from '../types/api';

export function AutomationsPage() {
  const { data: folders } = useAutomationFolders();
  const { data: automations, isLoading } = useAutomations();
  const createFolder = useCreateAutomationFolder();
  const deleteAutomation = useDeleteAutomation();
  const updateAutomation = useUpdateAutomation();
  const triggerAutomation = useTriggerAutomation();
  const canEdit = usePermission('automations:edit');
  const canTrigger = usePermission('automations:trigger');
  const pushToast = useUiStore((s) => s.pushToast);

  const [selectedFolder, setSelectedFolder] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Automation | null>(null);

  const filtered = (automations ?? []).filter((a) =>
    selectedFolder === null ? true : a.folder_id === selectedFolder,
  );

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[220px_1fr]">
      <aside>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-vmd-textMuted">Folders</h2>
          {canEdit && (
            <button
              onClick={() => {
                const name = window.prompt('Folder name');
                if (name) createFolder.mutate({ name });
              }}
              className="text-vmd-textSubtle hover:text-vmd-textStrong"
            >
              <FolderPlus size={16} />
            </button>
          )}
        </div>
        <ul className="space-y-1 text-sm">
          <li>
            <button
              onClick={() => setSelectedFolder(null)}
              className={`w-full rounded-lg px-2 py-1 text-left ${selectedFolder === null ? 'bg-vmd-surfaceSubtle text-vmd-textStrong' : 'text-vmd-textMuted'}`}
            >
              All automations
            </button>
          </li>
          {folders?.map((f) => (
            <li key={f.id}>
              <button
                onClick={() => setSelectedFolder(f.id)}
                className={`w-full rounded-lg px-2 py-1 text-left ${selectedFolder === f.id ? 'bg-vmd-surfaceSubtle text-vmd-textStrong' : 'text-vmd-textMuted'}`}
              >
                {f.name}
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <div>
        <PageHeader
          title="Automations"
          subtitle="YAML/Jinja2 trigger-condition-action rules."
          action={
            canEdit && (
              <Button
                variant="primary"
                onClick={() => {
                  setEditing(null);
                  setModalOpen(true);
                }}
              >
                <Plus size={16} /> New Automation
              </Button>
            )
          }
        />

        {isLoading && <p className="text-sm text-vmd-textSubtle">Loading…</p>}
        <div className="space-y-3">
          {filtered.map((automation) => (
            <Card key={automation.id} className="flex items-center justify-between">
              <div>
                <p className="font-medium text-vmd-textStrong">{automation.alias}</p>
                <p className="text-xs text-vmd-textSubtle">
                  {automation.last_triggered_at
                    ? `Last triggered ${new Date(automation.last_triggered_at).toLocaleString()}`
                    : 'Never triggered'}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <Toggle
                  checked={automation.enabled}
                  disabled={!canEdit}
                  onChange={(enabled) => updateAutomation.mutate({ id: automation.id, body: { enabled } })}
                />
                {canTrigger && (
                  <button
                    onClick={() =>
                      triggerAutomation.mutate(automation.id, {
                        onSuccess: (res) => pushToast(`Test run: ${res.status}`, res.status === 'success' ? 'success' : 'error'),
                      })
                    }
                    className="text-vmd-textSubtle hover:text-vmd-textStrong"
                    title="Test Run"
                  >
                    <Play size={16} />
                  </button>
                )}
                <button
                  onClick={() => {
                    setEditing(automation);
                    setModalOpen(true);
                  }}
                  className="text-sm text-vmd-link hover:underline"
                >
                  Edit
                </button>
                {canEdit && (
                  <button
                    onClick={() => deleteAutomation.mutate(automation.id)}
                    className="text-vmd-textSubtle hover:text-vmd-danger"
                  >
                    <Trash2 size={16} />
                  </button>
                )}
              </div>
            </Card>
          ))}
          {filtered.length === 0 && !isLoading && (
            <p className="text-sm text-vmd-textSubtle">No automations in this folder yet.</p>
          )}
        </div>
      </div>

      <AutomationEditorModal open={modalOpen} onClose={() => setModalOpen(false)} editing={editing} />
    </div>
  );
}
