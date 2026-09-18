import { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { useWebSocket } from '../hooks/useWebSocket';
import { usePermission } from '../hooks/usePermission';
import {
  useIntegrations,
  useDeleteIntegration,
  useUpdateIntegration,
} from '../api/integrations';
import { useUiStore } from '../stores/ui';
import { PageHeader, Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { IntegrationStatusChip } from '../components/integrations/IntegrationStatusChip';
import { TagsEditor } from '../components/integrations/TagsEditor';
import { AddIntegrationModal } from '../components/integrations/AddIntegrationModal';
import { SpotifyAuthButton } from '../components/integrations/SpotifyAuthButton';
import type { IntegrationInstance } from '../types/api';

export function IntegrationsPage() {
  useWebSocket('/ws/events');
  const { data: integrations, isLoading } = useIntegrations();
  const canEdit = usePermission('integrations:edit');
  const [modalOpen, setModalOpen] = useState(false);

  return (
    <div>
      <PageHeader
        title="Integrations"
        subtitle="VEX TM, Spotify, ATEM, ZerOS, and OBS instances."
        action={
          canEdit && (
            <Button variant="primary" onClick={() => setModalOpen(true)}>
              <Plus size={16} /> Add Integration
            </Button>
          )
        }
      />

      {isLoading && <p className="text-sm text-vmd-textSubtle">Loading…</p>}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {integrations?.map((integration) => (
          <IntegrationRow key={integration.entity_id} integration={integration} canEdit={canEdit} />
        ))}
      </div>

      <AddIntegrationModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </div>
  );
}

function IntegrationRow({ integration, canEdit }: { integration: IntegrationInstance; canEdit: boolean }) {
  const updateIntegration = useUpdateIntegration();
  const deleteIntegration = useDeleteIntegration();
  const pushToast = useUiStore((s) => s.pushToast);

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
          {canEdit && (
            <button
              onClick={() =>
                deleteIntegration.mutate(integration.entity_id, {
                  onSuccess: () => pushToast('Deleted', 'success'),
                })
              }
              className="text-vmd-textSubtle hover:text-vmd-danger"
              title="Delete"
            >
              <Trash2 size={16} />
            </button>
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
    </Card>
  );
}
