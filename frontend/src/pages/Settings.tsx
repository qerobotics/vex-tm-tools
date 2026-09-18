import { useEffect, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { useApiKeys, useCreateApiKey, useRevokeApiKey, useSettings, useUpdateSettings } from '../api/settings';
import { usePermission } from '../hooks/usePermission';
import { useUiStore } from '../stores/ui';
import { ALL_PERMISSIONS } from '../stores/auth';
import { PageHeader, Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input, Label } from '../components/ui/Input';
import { Modal } from '../components/ui/Modal';

function settingValue(settings: { key: string; value: Record<string, unknown> }[] | undefined, key: string): Record<string, unknown> {
  return settings?.find((s) => s.key === key)?.value ?? {};
}

export function SettingsPage() {
  const { data: settings } = useSettings();
  const updateSettings = useUpdateSettings();
  const canEdit = usePermission('settings:edit');
  const pushToast = useUiStore((s) => s.pushToast);

  const s3 = settingValue(settings, 's3');
  const robotEvents = settingValue(settings, 'robot_events_api');
  const predictor = settingValue(settings, 'predictor');
  const chromaKey = settingValue(settings, 'chroma_key_defaults');

  const [s3Endpoint, setS3Endpoint] = useState('');
  const [s3Bucket, setS3Bucket] = useState('');
  const [s3AccessKey, setS3AccessKey] = useState('');
  const [s3SecretKey, setS3SecretKey] = useState('');
  const [s3Region, setS3Region] = useState('');
  const [reToken, setReToken] = useState('');
  const [threshold, setThreshold] = useState(15);
  const [ckColour, setCkColour] = useState('#00B140');
  const [ckSimilarity, setCkSimilarity] = useState(0.1);
  const [ckBlend, setCkBlend] = useState(0.05);

  useEffect(() => {
    setS3Endpoint(String(s3.endpoint_url ?? ''));
    setS3Bucket(String(s3.bucket ?? ''));
    setS3AccessKey(String(s3.access_key ?? ''));
    setS3SecretKey(String(s3.secret_key ?? ''));
    setS3Region(String(s3.region ?? ''));
    setReToken(String(robotEvents.token ?? ''));
    setThreshold(Number(predictor.high_potential_threshold_pct ?? 15));
    setCkColour(String(chromaKey.colour ?? '#00B140'));
    setCkSimilarity(Number(chromaKey.similarity ?? 0.1));
    setCkBlend(Number(chromaKey.blend ?? 0.05));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings]);

  function save() {
    updateSettings.mutate(
      {
        s3: { value: { endpoint_url: s3Endpoint, bucket: s3Bucket, access_key: s3AccessKey, secret_key: s3SecretKey, region: s3Region } },
        robot_events_api: { value: { token: reToken } },
        predictor: { value: { high_potential_threshold_pct: threshold } },
        chroma_key_defaults: { value: { colour: ckColour, similarity: ckSimilarity, blend: ckBlend } },
      },
      {
        onSuccess: () => pushToast('Settings saved', 'success'),
        onError: (err) => pushToast(err instanceof Error ? err.message : 'Save failed', 'error'),
      },
    );
  }

  return (
    <div>
      <PageHeader title="Settings" subtitle="S3 storage, Robot Events, predictor, chroma key defaults, API keys." />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-vmd-textMuted">S3 Media Storage</h2>
          <div className="space-y-2">
            <div>
              <Label>Endpoint URL</Label>
              <Input value={s3Endpoint} onChange={(e) => setS3Endpoint(e.target.value)} disabled={!canEdit} />
            </div>
            <div>
              <Label>Bucket</Label>
              <Input value={s3Bucket} onChange={(e) => setS3Bucket(e.target.value)} disabled={!canEdit} />
            </div>
            <div>
              <Label>Access Key</Label>
              <Input value={s3AccessKey} onChange={(e) => setS3AccessKey(e.target.value)} disabled={!canEdit} />
            </div>
            <div>
              <Label>Secret Key</Label>
              <Input type="password" value={s3SecretKey} onChange={(e) => setS3SecretKey(e.target.value)} disabled={!canEdit} />
            </div>
            <div>
              <Label>Region</Label>
              <Input value={s3Region} onChange={(e) => setS3Region(e.target.value)} disabled={!canEdit} />
            </div>
          </div>
        </Card>

        <Card>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-vmd-textMuted">Robot Events API</h2>
          <Label>API Token</Label>
          <Input type="password" value={reToken} onChange={(e) => setReToken(e.target.value)} disabled={!canEdit} />

          <h2 className="mb-3 mt-5 text-sm font-semibold uppercase tracking-wide text-vmd-textMuted">
            AI Predictor
          </h2>
          <Label>High-potential threshold ({threshold}%)</Label>
          <input
            type="range"
            min={0}
            max={100}
            value={threshold}
            onChange={(e) => setThreshold(Number(e.target.value))}
            disabled={!canEdit}
            className="w-full"
          />

          <h2 className="mb-3 mt-5 text-sm font-semibold uppercase tracking-wide text-vmd-textMuted">
            Chroma Key Defaults
          </h2>
          <div className="grid grid-cols-3 gap-3">
            <div>
              <Label>Colour</Label>
              <input
                type="color"
                value={ckColour}
                onChange={(e) => setCkColour(e.target.value)}
                disabled={!canEdit}
                className="h-9 w-full rounded-lg border border-vmd-border bg-vmd-elevated"
              />
            </div>
            <div>
              <Label>Similarity ({ckSimilarity.toFixed(2)})</Label>
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={ckSimilarity}
                onChange={(e) => setCkSimilarity(Number(e.target.value))}
                disabled={!canEdit}
                className="w-full"
              />
            </div>
            <div>
              <Label>Blend ({ckBlend.toFixed(2)})</Label>
              <input
                type="range"
                min={0}
                max={1}
                step={0.01}
                value={ckBlend}
                onChange={(e) => setCkBlend(Number(e.target.value))}
                disabled={!canEdit}
                className="w-full"
              />
            </div>
          </div>
        </Card>
      </div>

      {canEdit && (
        <Button variant="primary" className="mt-4" onClick={save} disabled={updateSettings.isPending}>
          Save Settings
        </Button>
      )}

      <div className="mt-8">
        <ApiKeysSection canEdit={canEdit} />
      </div>
    </div>
  );
}

function ApiKeysSection({ canEdit }: { canEdit: boolean }) {
  const { data: keys } = useApiKeys();
  const createKey = useCreateApiKey();
  const revokeKey = useRevokeApiKey();
  const [modalOpen, setModalOpen] = useState(false);
  const [name, setName] = useState('');
  const [permissions, setPermissions] = useState<string[]>([]);
  const [createdKey, setCreatedKey] = useState<string | null>(null);

  function togglePermission(p: string) {
    setPermissions((prev) => (prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]));
  }

  function handleCreate() {
    createKey.mutate(
      { name, permissions },
      {
        onSuccess: (res) => {
          setCreatedKey(res.raw_key);
          setName('');
          setPermissions([]);
        },
      },
    );
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-vmd-textMuted">API Keys</h2>
        {canEdit && (
          <Button variant="primary" onClick={() => setModalOpen(true)}>
            <Plus size={16} /> New API Key
          </Button>
        )}
      </div>
      <Card>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase text-vmd-textSubtle">
              <th className="pb-2">Name</th>
              <th className="pb-2">Permissions</th>
              <th className="pb-2">Last Used</th>
              <th className="pb-2">Status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {keys?.map((key) => (
              <tr key={key.id} className="border-t border-vmd-border">
                <td className="py-1.5">{key.name}</td>
                <td className="py-1.5 text-xs text-vmd-textMuted">{key.permissions.join(', ') || '(none)'}</td>
                <td className="py-1.5 text-xs text-vmd-textSubtle">
                  {key.last_used_at ? new Date(key.last_used_at).toLocaleString() : 'never'}
                </td>
                <td className="py-1.5">{key.revoked ? 'Revoked' : 'Active'}</td>
                <td className="py-1.5 text-right">
                  {canEdit && !key.revoked && (
                    <button onClick={() => revokeKey.mutate(key.id)} className="text-vmd-textSubtle hover:text-vmd-danger">
                      <Trash2 size={14} />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Modal
        open={modalOpen}
        onClose={() => {
          setModalOpen(false);
          setCreatedKey(null);
        }}
        title="New API Key"
      >
        {createdKey ? (
          <div>
            <p className="mb-2 text-sm text-vmd-danger">
              This key is shown only once — copy it now. It cannot be retrieved again.
            </p>
            <p className="vmd-code-block break-all text-xs">{createdKey}</p>
          </div>
        ) : (
          <div className="space-y-3">
            <div>
              <Label>Name</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div>
              <Label>Permissions</Label>
              <div className="grid grid-cols-2 gap-1 text-sm">
                {ALL_PERMISSIONS.map((p) => (
                  <label key={p} className="flex items-center gap-1.5">
                    <input type="checkbox" checked={permissions.includes(p)} onChange={() => togglePermission(p)} />
                    {p}
                  </label>
                ))}
              </div>
            </div>
            <Button variant="primary" onClick={handleCreate} disabled={!name || createKey.isPending}>
              Create
            </Button>
          </div>
        )}
      </Modal>
    </div>
  );
}
