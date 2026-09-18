import { create } from 'zustand';

/**
 * Auth store (plan §C.3): current user + permissions, set once at login
 * (OIDC redirect completes server-side then redirects to `/`, or the
 * emergency admin POST succeeds) and refreshed via `/api/v1/auth/whoami`
 * on app boot — never via WebSocket (plan §C.8.1: "Current logged-in user
 * and permissions | Zustand auth.ts | Set at login, not refreshed via WS").
 *
 * Per §C.3, stores/ may import nothing else in frontend/ — no api/,
 * components/, or hooks/ imports here. `useAuthQuery` in
 * `frontend/src/api/auth.ts` is what calls `/whoami` and pushes the result
 * into this store from the app root.
 */
export interface AuthState {
  authenticated: boolean;
  subject: string | null;
  isAdminLocal: boolean;
  permissions: Set<string>;
  /** Whether the initial /whoami check has completed. */
  hydrated: boolean;
  setAuth: (params: {
    authenticated: boolean;
    subject?: string | null;
    isAdminLocal?: boolean;
    permissions?: string[];
  }) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  authenticated: false,
  subject: null,
  isAdminLocal: false,
  permissions: new Set(),
  hydrated: false,
  setAuth: ({ authenticated, subject, isAdminLocal, permissions }) =>
    set({
      authenticated,
      subject: subject ?? null,
      isAdminLocal: Boolean(isAdminLocal),
      permissions: new Set(permissions ?? []),
      hydrated: true,
    }),
  clear: () =>
    set({
      authenticated: false,
      subject: null,
      isAdminLocal: false,
      permissions: new Set(),
      hydrated: true,
    }),
}));

/** All permission strings referenced anywhere in this frontend (plan §13). */
export const ALL_PERMISSIONS = [
  'integrations:read',
  'integrations:edit',
  'automations:read',
  'automations:edit',
  'automations:trigger',
  'timers:read',
  'timers:edit',
  'teams:read',
  'teams:edit',
  'video:upload',
  'overlays:read',
  'overlays:edit',
  'vfx:control',
  'video:control',
  'audio:control',
  'tm:control',
  'prompter:view',
  'prompter:control',
  'prompter:edit',
  'settings:read',
  'settings:edit',
] as const;

export type Permission = (typeof ALL_PERMISSIONS)[number];
