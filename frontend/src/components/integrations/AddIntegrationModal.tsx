import { useEffect, useMemo, useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Input, Label, Select } from '../ui/Input';
import { TagsEditor } from './TagsEditor';
import { useCreateIntegration, useIntegrationSchemas, useUpdateIntegration } from '../../api/integrations';
import { useUiStore } from '../../stores/ui';
import type { IntegrationInstance } from '../../types/api';

/** Plan §12 "Add Integration" / audit finding 2.3 "Edit... existing
 * instances": choose a domain from `GET /api/v1/integrations/schemas`,
 * then render a form built from that domain's `config_schema` (field name
 * -> {type, label, secret}). When `editing` is passed, the same
 * schema-driven form is pre-filled from the instance's current config and
 * the domain/entity-ID fields are locked (both are immutable after
 * creation per the backend's `IntegrationInstanceUpdate` schema, which
 * only accepts display_name/config/enabled/tags), and submit calls
 * `PUT /api/v1/integrations/{entity_id}` instead of `POST`. */
export function AddIntegrationModal({
  open,
  onClose,
  editing = null,
}: {
  open: boolean;
  onClose: () => void;
  editing?: IntegrationInstance | null;
}) {
  const { data: schemas } = useIntegrationSchemas();
  const createIntegration = useCreateIntegration();
  const updateIntegration = useUpdateIntegration();
  const pushToast = useUiStore((s) => s.pushToast);

  const [domain, setDomain] = useState('');
  const [entityId, setEntityId] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [config, setConfig] = useState<Record<string, string>>({});

  const schema = domain && schemas ? schemas[domain] : undefined;
  const fields = useMemo(() => Object.entries(schema?.config_schema ?? {}), [schema]);

  function reset() {
    setDomain('');
    setEntityId('');
    setDisplayName('');
    setTags([]);
    setConfig({});
  }

  // Pre-fill from the instance being edited whenever the modal opens (or
  // reset to a blank create-form when opened with no `editing` instance).
  useEffect(() => {
    if (!open) return;
    if (editing) {
      setDomain(editing.domain);
      setEntityId(editing.entity_id);
      setDisplayName(editing.display_name);
      setTags(editing.tags);
      const stringified: Record<string, string> = {};
      for (const [key, value] of Object.entries(editing.config)) {
        stringified[key] = value === null || value === undefined ? '' : String(value);
      }
      setConfig(stringified);
    } else {
      reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, editing]);

  function handleSubmit() {
    if (!domain || !entityId || !displayName) {
      pushToast('Domain, entity ID, and display name are required.', 'error');
      return;
    }
    const parsedConfig: Record<string, unknown> = {};
    for (const [key, spec] of fields) {
      const raw = config[key] ?? '';
      if (spec.type === 'integer') parsedConfig[key] = raw === '' ? undefined : Number(raw);
      else if (spec.type === 'boolean') parsedConfig[key] = raw === 'true';
      else parsedConfig[key] = raw;
    }

    if (editing) {
      updateIntegration.mutate(
        { entityId: editing.entity_id, body: { display_name: displayName, config: parsedConfig, tags } },
        {
          onSuccess: () => {
            pushToast(`Updated ${editing.entity_id}`, 'success');
            onClose();
          },
          onError: (err) =>
            pushToast(err instanceof Error ? err.message : 'Failed to update integration', 'error'),
        },
      );
      return;
    }

    createIntegration.mutate(
      { entity_id: entityId, domain, display_name: displayName, config: parsedConfig, tags },
      {
        onSuccess: () => {
          pushToast(`Created ${entityId}`, 'success');
          reset();
          onClose();
        },
        onError: (err) => pushToast(err instanceof Error ? err.message : 'Failed to create integration', 'error'),
      },
    );
  }

  const isSaving = createIntegration.isPending || updateIntegration.isPending;

  return (
    <Modal open={open} onClose={onClose} title={editing ? `Edit ${editing.entity_id}` : 'Add Integration'} wide>
      <div className="space-y-3">
        <div>
          <Label>Domain</Label>
          {editing ? (
            <Input value={`${schema?.name ?? domain} (${domain})`} disabled readOnly />
          ) : (
            <Select value={domain} onChange={(e) => setDomain(e.target.value)}>
              <option value="">Select a domain…</option>
              {Object.entries(schemas ?? {}).map(([key, s]) => (
                <option key={key} value={key}>
                  {s.name} ({key})
                </option>
              ))}
            </Select>
          )}
          {schema?.description && <p className="mt-1 text-xs text-vmd-textSubtle">{schema.description}</p>}
        </div>

        <div>
          <Label>Entity ID</Label>
          <Input
            placeholder={domain ? `${domain}.my_instance` : 'domain.name'}
            value={entityId}
            onChange={(e) => setEntityId(e.target.value)}
            disabled={Boolean(editing)}
            readOnly={Boolean(editing)}
          />
        </div>

        <div>
          <Label>Display Name</Label>
          <Input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        </div>

        {fields.map(([key, spec]) => (
          <div key={key}>
            <Label>
              {spec.label} {spec.secret && <span className="text-vmd-textSubtle">(secret)</span>}
            </Label>
            {spec.type === 'boolean' ? (
              <Select
                value={config[key] ?? 'false'}
                onChange={(e) => setConfig((c) => ({ ...c, [key]: e.target.value }))}
              >
                <option value="false">False</option>
                <option value="true">True</option>
              </Select>
            ) : (
              <Input
                type={spec.secret ? 'password' : spec.type === 'integer' ? 'number' : 'text'}
                value={config[key] ?? ''}
                onChange={(e) => setConfig((c) => ({ ...c, [key]: e.target.value }))}
                placeholder={spec.secret && editing ? '(unchanged — enter to replace)' : undefined}
              />
            )}
          </div>
        ))}

        <div>
          <Label>Tags</Label>
          <TagsEditor tags={tags} onChange={setTags} />
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" onClick={handleSubmit} disabled={isSaving}>
            {isSaving ? 'Saving…' : editing ? 'Save Changes' : 'Create'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
