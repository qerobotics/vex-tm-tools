import { useEffect, useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Input, Label } from '../ui/Input';
import { TagsEditor } from '../integrations/TagsEditor';
import { useCreateOverlay, useUpdateOverlay } from '../../api/overlays';
import { useUiStore } from '../../stores/ui';
import type { OverlayInstance } from '../../types/api';

export function OverlayEditorModal({
  open,
  onClose,
  editing,
}: {
  open: boolean;
  onClose: () => void;
  editing: OverlayInstance | null;
}) {
  const createOverlay = useCreateOverlay();
  const updateOverlay = useUpdateOverlay();
  const pushToast = useUiStore((s) => s.pushToast);

  const [entityId, setEntityId] = useState(editing?.entity_id ?? '');
  const [displayName, setDisplayName] = useState(editing?.display_name ?? '');
  const [fieldSetId, setFieldSetId] = useState(String(editing?.field_set_id ?? ''));
  const [tags, setTags] = useState<string[]>(editing?.tags ?? []);

  useEffect(() => {
    setEntityId(editing?.entity_id ?? '');
    setDisplayName(editing?.display_name ?? '');
    setFieldSetId(String(editing?.field_set_id ?? ''));
    setTags(editing?.tags ?? []);
  }, [editing, open]);

  function handleSave() {
    if (!entityId || !displayName || fieldSetId === '') {
      pushToast('Entity ID, display name, and field set are required.', 'error');
      return;
    }
    const common = { display_name: displayName, field_set_id: Number(fieldSetId), tags };
    const mutation = editing
      ? updateOverlay.mutateAsync({ entityId: editing.entity_id, body: common })
      : createOverlay.mutateAsync({ entity_id: entityId, ...common });
    mutation
      .then(() => {
        pushToast('Saved', 'success');
        onClose();
      })
      .catch((err: unknown) => pushToast(err instanceof Error ? err.message : 'Save failed', 'error'));
  }

  return (
    <Modal open={open} onClose={onClose} title={editing ? `Edit: ${editing.display_name}` : 'New Overlay Instance'}>
      <div className="space-y-3">
        <div>
          <Label>Entity ID</Label>
          <Input
            value={entityId}
            onChange={(e) => setEntityId(e.target.value)}
            disabled={Boolean(editing)}
            placeholder="overlay.main_stream"
          />
        </div>
        <div>
          <Label>Display Name</Label>
          <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        </div>
        <div>
          <Label>Field Set ID</Label>
          <Input type="number" value={fieldSetId} onChange={(e) => setFieldSetId(e.target.value)} />
        </div>
        <div>
          <Label>Tags</Label>
          <TagsEditor tags={tags} onChange={setTags} />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" onClick={handleSave} disabled={createOverlay.isPending || updateOverlay.isPending}>
            Save
          </Button>
        </div>
      </div>
    </Modal>
  );
}
