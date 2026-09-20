import { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { useZerosPresets, useCreateZerosPreset, useDeleteZerosPreset } from '../../api/integrations';
import { useUiStore } from '../../stores/ui';
import { Button } from '../ui/Button';
import { Input, Label } from '../ui/Input';
import type { IntegrationInstance } from '../../types/api';

/** Plan §11's ZerOS presets CRUD (`GET/POST/PUT/DELETE /api/v1/zeros/presets`)
 * had a complete backend + a complete set of TanStack Query hooks
 * (`useZerosPresets`/`useCreateZerosPreset`/`useDeleteZerosPreset` in
 * `api/integrations.ts`) but no page or component anywhere called them — the
 * only way to manage a preset was a raw API request. This renders them per
 * ZerOS integration instance on the Integrations page, mirroring
 * `SpotifyAuthButton`'s per-domain-section pattern. */
export function ZerosPresetsSection({ integration }: { integration: IntegrationInstance }) {
  const { data: presets, isLoading } = useZerosPresets();
  const createPreset = useCreateZerosPreset();
  const deletePreset = useDeleteZerosPreset();
  const pushToast = useUiStore((s) => s.pushToast);

  const [presetNumber, setPresetNumber] = useState('');
  const [presetName, setPresetName] = useState('');

  const instancePresets = (presets ?? [])
    .filter((p) => p.integration_id === integration.entity_id)
    .sort((a, b) => a.preset_number - b.preset_number);

  function handleCreate() {
    const number = Number(presetNumber);
    if (!Number.isFinite(number) || !presetName.trim()) {
      pushToast('Preset number and name are required.', 'error');
      return;
    }
    createPreset.mutate(
      { integration_id: integration.entity_id, preset_number: number, preset_name: presetName.trim() },
      {
        onSuccess: () => {
          setPresetNumber('');
          setPresetName('');
          pushToast('Preset created', 'success');
        },
        onError: (err) => pushToast(err instanceof Error ? err.message : 'Failed to create preset', 'error'),
      },
    );
  }

  function handleDelete(id: string) {
    deletePreset.mutate(id, {
      onError: (err) => pushToast(err instanceof Error ? err.message : 'Failed to delete preset', 'error'),
    });
  }

  return (
    <div className="mt-3 border-t border-vmd-border pt-3">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-vmd-textMuted">ZerOS Presets</p>

      {isLoading ? (
        <p className="text-sm text-vmd-textSubtle">Loading…</p>
      ) : instancePresets.length === 0 ? (
        <p className="text-sm text-vmd-textSubtle">No presets yet.</p>
      ) : (
        <ul className="mb-2 space-y-1">
          {instancePresets.map((preset) => (
            <li key={preset.id} className="flex items-center justify-between text-sm">
              <span>
                <span className="text-vmd-textSubtle">#{preset.preset_number}</span> {preset.preset_name}
              </span>
              <button
                onClick={() => handleDelete(preset.id)}
                className="text-vmd-textSubtle hover:text-vmd-danger"
                title="Delete preset"
              >
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex items-end gap-2">
        <div className="w-20">
          <Label>#</Label>
          <Input
            type="number"
            value={presetNumber}
            onChange={(e) => setPresetNumber(e.target.value)}
          />
        </div>
        <div className="flex-1">
          <Label>Name</Label>
          <Input value={presetName} onChange={(e) => setPresetName(e.target.value)} />
        </div>
        <Button variant="secondary" onClick={handleCreate} disabled={createPreset.isPending}>
          <Plus size={14} /> Add
        </Button>
      </div>
    </div>
  );
}
