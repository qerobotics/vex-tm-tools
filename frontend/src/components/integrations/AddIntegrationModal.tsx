import { useMemo, useState } from 'react';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Input, Label, Select } from '../ui/Input';
import { TagsEditor } from './TagsEditor';
import { useCreateIntegration, useIntegrationSchemas } from '../../api/integrations';
import { useUiStore } from '../../stores/ui';

/** Plan §12 "Add Integration": choose a domain from
 * `GET /api/v1/integrations/schemas`, then render a form built from that
 * domain's `config_schema` (field name -> {type, label, secret}). */
export function AddIntegrationModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data: schemas } = useIntegrationSchemas();
  const createIntegration = useCreateIntegration();
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

  return (
    <Modal open={open} onClose={onClose} title="Add Integration" wide>
      <div className="space-y-3">
        <div>
          <Label>Domain</Label>
          <Select value={domain} onChange={(e) => setDomain(e.target.value)}>
            <option value="">Select a domain…</option>
            {Object.entries(schemas ?? {}).map(([key, s]) => (
              <option key={key} value={key}>
                {s.name} ({key})
              </option>
            ))}
          </Select>
          {schema?.description && <p className="mt-1 text-xs text-vmd-textSubtle">{schema.description}</p>}
        </div>

        <div>
          <Label>Entity ID</Label>
          <Input
            placeholder={domain ? `${domain}.my_instance` : 'domain.name'}
            value={entityId}
            onChange={(e) => setEntityId(e.target.value)}
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
          <Button variant="primary" onClick={handleSubmit} disabled={createIntegration.isPending}>
            {createIntegration.isPending ? 'Creating…' : 'Create'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
