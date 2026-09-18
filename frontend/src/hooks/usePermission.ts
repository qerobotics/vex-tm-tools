import { useAuthStore } from '../stores/auth';

/** Reads from the auth store (plan §C.3 hooks/ contract). `admin_local`
 * (is_admin_local) and any principal holding the `"*"` sentinel permission
 * always pass, mirroring `backend/core/dependencies.py`'s
 * `CurrentPrincipal.has_permission`. */
export function usePermission(permission: string): boolean {
  const isAdminLocal = useAuthStore((s) => s.isAdminLocal);
  const permissions = useAuthStore((s) => s.permissions);
  if (isAdminLocal || permissions.has('*')) return true;
  return permissions.has(permission);
}
