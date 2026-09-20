import { useState } from 'react';
import { Pencil, Plus, Trash2, Zap } from 'lucide-react';
import { useWebSocket } from '../hooks/useWebSocket';
import { usePermission } from '../hooks/usePermission';
import {
  useIntegrations,
  useDeleteIntegration,
  useTestIntegrationConnection,
  useUpdateIntegration,
} from '../api/integrations';
import { useUiStore } from '../stores/ui';
import { PageHeader, Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { IntegrationStatusChip } from '../components/integrations/IntegrationStatusChip';
import { TagsEditor } from '../components/integrations/TagsEditor';
import { AddIntegrationModal } from '../components/integrations/AddIntegrationModal';
import { SpotifyAuthButton } from '../components/integrations/SpotifyAuthButton';
import { ZerosPresetsSection } from '../components/integrations/ZerosPresetsSection';
import type { IntegrationInstance } from '../types/api';

export function IntegrationsPage() {
  useWebSocket('/ws/events');
  const { data: integrations, isLoading } = useIntegrations();
  const canEdit = usePermission('integrations:edit');
  const [modalOpen, setModalOpen] = useState(false);
  const [editingInstance, setEditingInstance] = useState<IntegrationInstance | null>(null);

  function openCreate() {
    setEditingInstance(null);
    setModalOpen(true);
  }

  function openEdit(instance: IntegrationInstance) {
    setEditingInstance(instance);
    setModalOpen(true);
  }

  return (
    <div>
      <PageHeader
        title="Integrations"
        subtitle="VEX TM, Spotify, ATEM, ZerOS, and OBS instances."
        action={
          canEdit && (
            <Button variant="primary" onClick={openCreate}>
              <Plus size={16} /> Add Integration
            </Button>
          )
        }
      />

      {isLoading && <p className="text-sm text-vmd-textSubtle">Loading…</p>}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {integrations?.map((integration) => (
          <IntegrationRow
            key={integration.entity_id}
            integration={integration}
            canEdit={canEdit}
            onEdit={() => openEdit(integration)}
          />
        ))}
      </div>

      <AddIntegrationModal
        open={modalOpen}
        onClose={() => {
          setModalOpen(false);
          setEditingInstance(null);
        }}
        editing={editingInstance}
      />
    </div>
  );
}

function IntegrationRow({
  integration,
  canEdit,
  onEdit,
}: {
  integration: IntegrationInstance;
  canEdit: boolean;
  onEdit: () => void;
}) {
  const updateIntegration = useUpdateIntegration();
  const deleteIntegration = useDeleteIntegration();
  const testConnection = useTestIntegrationConnection();
  const pushToast = useUiStore((s) => s.pushToast);

  function handleDelete() {
    if (!window.confirm(`Delete integration "${integration.display_name}" (${integration.entity_id})?`)) {
      return;
    }
    deleteIntegration.mutate(integration.entity_id, {
      onSuccess: () => pushToast('Deleted', 'success'),
      onError: (err) => pushToast(err instanceof Error ? err.message : 'Failed to delete', 'error'),
    });
  }

  function handleTestConnection() {
    testConnection.mutate(integration.entity_id, {
      onSuccess: (result) =>
        pushToast(
          result.message ?? result.detail ?? (result.ok ? 'Connection OK' : 'Connection failed'),
          result.ok ? 'success' : 'error',
        ),
      onError: (err) =>
        pushToast(err instanceof Error ? err.message : 'Test connection failed', 'error'),
    });
  }

  return (
    <Card>
      <div className="mb-2 flex items-start justify-between">
        <div>
          <p className="font-medium text-vmd-textStrong">{integration.display_name}</p>
          <p className="text-xs text-vmd-textSubtle">
            {integration.entity_id} · {integration.domain}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <IntegrationStatusChip integration={integration} />
          <button
            onClick={handleTestConnection}
            disabled={testConnection.isPending}
            className="text-vmd-textSubtle hover:text-vmd-textStrong disabled:opacity-40"
            title="Test Connection"
          >
            <Zap size={16} />
          </button>
          {canEdit && (
            <>
              <button
                onClick={onEdit}
                className="text-vmd-textSubtle hover:text-vmd-textStrong"
                title="Edit"
              >
                <Pencil size={16} />
              </button>
              <button
                onClick={handleDelete}
                className="text-vmd-textSubtle hover:text-vmd-danger"
                title="Delete"
              >
                <Trash2 size={16} />
              </button>
            </>
          )}
        </div>
      </div>

      <div className="mb-2 text-xs text-vmd-textMuted">
        {Object.entries(integration.config).map(([k, v]) => (
          <div key={k}>
            <span className="text-vmd-textSubtle">{k}:</span> {String(v)}
          </div>
        ))}
      </div>

      <TagsEditor
        tags={integration.tags}
        disabled={!canEdit}
        onChange={(tags) =>
          updateIntegration.mutate({ entityId: integration.entity_id, body: { tags } })
        }
      />

      {integration.domain === 'spotify' && (
        <div className="mt-3">
          <SpotifyAuthButton integration={integration} />
        </div>
      )}

      {integration.domain === 'zeros' && <ZerosPresetsSection integration={integration} />}
    </Card>
  );
}
