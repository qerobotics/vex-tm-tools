import { useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { useWhoAmI } from '../../api/auth';
import { useAuthStore } from '../../stores/auth';
import { useCacheSync } from '../../hooks/useCacheSync';
import { PageLayout } from './PageLayout';

/**
 * Wraps every authenticated route. Runs `/api/v1/auth/whoami` once, pushes
 * the result into `useAuthStore` (plan §C.8.1: auth is "set at login, not
 * refreshed via WS"), and redirects to `/auth/login` (OIDC) if
 * unauthenticated — `/admin_login` is the break-glass path, reached via its
 * own link, not the default. Also mounts `useCacheSync()` once at this
 * root, per §C.8.3's instruction.
 */
export function ProtectedLayout() {
  const { data, isLoading } = useWhoAmI();
  const setAuth = useAuthStore((s) => s.setAuth);
  const hydrated = useAuthStore((s) => s.hydrated);
  useCacheSync();

  useEffect(() => {
    if (data) {
      setAuth({
        authenticated: data.authenticated,
        subject: data.subject,
        isAdminLocal: data.is_admin_local,
        permissions: data.permissions,
      });
    }
  }, [data, setAuth]);

  if (isLoading || !hydrated) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-vmd-bg text-vmd-textMuted">
        Loading…
      </div>
    );
  }

  if (!data?.authenticated) {
    window.location.href = '/auth/login';
    return null;
  }

  return (
    <PageLayout>
      <Outlet />
    </PageLayout>
  );
}
