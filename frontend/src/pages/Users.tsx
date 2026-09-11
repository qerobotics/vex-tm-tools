import { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { useReplaceRolePermissions, useRolePermissions } from '../api/settings';
import { usePermission } from '../hooks/usePermission';
import { useUiStore } from '../stores/ui';
import { ALL_PERMISSIONS } from '../stores/auth';
import { PageHeader, Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input, Select } from '../components/ui/Input';

/** Plan §12/§13 Users & Roles: Authentik group -> permission mappings.
 * `PUT /api/v1/users/roles` replaces the whole table in one call (per
 * `backend/routers/settings.py`'s docstring), so this page keeps the full
 * desired mapping locally and saves it as one list. */
export function UsersPage() {
  const { data: rolePermissions } = useRolePermissions();
  const replaceRolePermissions = useReplaceRolePermissions();
  const canEdit = usePermission('settings:edit');
  const pushToast = useUiStore((s) => s.pushToast);

  const [newGroup, setNewGroup] = useState('');
  const [newPermission, setNewPermission] = useState<string>(ALL_PERMISSIONS[0]);

  const groups = Array.from(new Set((rolePermissions ?? []).map((r) => r.authentik_group))).sort();

  function addMapping() {
    if (!newGroup) return;
    const current = rolePermissions ?? [];
    if (current.some((r) => r.authentik_group === newGroup && r.permission === newPermission)) return;
    save([...current, { authentik_group: newGroup, permission: newPermission }]);
  }

  function removeMapping(group: string, permission: string) {
    const current = rolePermissions ?? [];
    save(current.filter((r) => !(r.authentik_group === group && r.permission === permission)));
  }

  function save(next: { authentik_group: string; permission: string }[]) {
    replaceRolePermissions.mutate(next, {
      onError: (err) => pushToast(err instanceof Error ? err.message : 'Save failed', 'error'),
    });
  }

  return (
    <div>
      <PageHeader title="Users & Roles" subtitle="Authentik group -> permission mappings." />

      {canEdit && (
        <Card className="mb-4">
          <div className="flex flex-wrap items-end gap-2">
            <div>
              <label className="mb-1 block text-xs font-medium text-vmd-textMuted">Group</label>
              <Input
                value={newGroup}
                onChange={(e) => setNewGroup(e.target.value)}
                placeholder="qecomp-operator"
                className="w-56"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-vmd-textMuted">Permission</label>
              <Select value={newPermission} onChange={(e) => setNewPermission(e.target.value)} className="w-56">
                <option value="*">* (all permissions)</option>
                {ALL_PERMISSIONS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </Select>
            </div>
            <Button variant="primary" onClick={addMapping}>
              <Plus size={16} /> Add mapping
            </Button>
          </div>
        </Card>
      )}

      <div className="space-y-4">
        {groups.map((group) => (
          <Card key={group}>
            <h2 className="mb-2 font-medium text-vmd-textStrong">{group}</h2>
            <div className="flex flex-wrap gap-2">
              {(rolePermissions ?? [])
                .filter((r) => r.authentik_group === group)
                .map((r) => (
                  <span key={r.permission} className="vmd-chip">
                    {r.permission}
                    {canEdit && (
                      <button onClick={() => removeMapping(group, r.permission)} className="ml-1.5">
                        <Trash2 size={12} />
                      </button>
                    )}
                  </span>
                ))}
            </div>
          </Card>
        ))}
        {groups.length === 0 && <p className="text-sm text-vmd-textSubtle">No role mappings configured yet.</p>}
      </div>
    </div>
  );
}
