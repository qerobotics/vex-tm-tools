import { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { useScripts, useDeleteScript } from '../api/scripts';
import { usePermission } from '../hooks/usePermission';
import { PageHeader, Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { ScriptEditorModal } from '../components/automations/ScriptEditorModal';
import type { Script } from '../types/api';

export function ScriptsPage() {
  const { data: scripts, isLoading } = useScripts();
  const deleteScript = useDeleteScript();
  const canEdit = usePermission('automations:edit');
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Script | null>(null);

  return (
    <div>
      <PageHeader
        title="Scripts"
        subtitle="Reusable action sequences, callable from automations via `script: <name>`."
        action={
          canEdit && (
            <Button
              variant="primary"
              onClick={() => {
                setEditing(null);
                setModalOpen(true);
              }}
            >
              <Plus size={16} /> New Script
            </Button>
          )
        }
      />

      {isLoading && <p className="text-sm text-vmd-textSubtle">Loading…</p>}
      <div className="space-y-3">
        {scripts?.map((script) => (
          <Card key={script.id} className="flex items-center justify-between">
            <div>
              <p className="font-medium text-vmd-textStrong">{script.name}</p>
              {script.description && <p className="text-xs text-vmd-textSubtle">{script.description}</p>}
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => {
                  setEditing(script);
                  setModalOpen(true);
                }}
                className="text-sm text-vmd-link hover:underline"
              >
                Edit
              </button>
              {canEdit && (
                <button onClick={() => deleteScript.mutate(script.id)} className="text-vmd-textSubtle hover:text-vmd-danger">
                  <Trash2 size={16} />
                </button>
              )}
            </div>
          </Card>
        ))}
        {scripts && scripts.length === 0 && <p className="text-sm text-vmd-textSubtle">No scripts yet.</p>}
      </div>

      <ScriptEditorModal open={modalOpen} onClose={() => setModalOpen(false)} editing={editing} />
    </div>
  );
}
