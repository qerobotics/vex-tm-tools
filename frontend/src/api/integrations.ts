import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../lib/http';
import type {
  IntegrationInstance,
  IntegrationInstanceCreate,
  IntegrationInstanceUpdate,
  IntegrationSchemasResponse,
  IntegrationTestResult,
  ZerosPreset,
  ZerosPresetCreate,
} from '../types/api';

const KEY = ['integrations'] as const;

export function useIntegrations() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => apiFetch<IntegrationInstance[]>('/api/v1/integrations'),
  });
}

export function useIntegrationSchemas() {
  return useQuery({
    queryKey: ['integrations', 'schemas'],
    queryFn: () => apiFetch<IntegrationSchemasResponse>('/api/v1/integrations/schemas'),
    staleTime: Infinity,
  });
}

export function useCreateIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: IntegrationInstanceCreate) =>
      apiFetch<IntegrationInstance>('/api/v1/integrations', { method: 'POST', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useUpdateIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ entityId, body }: { entityId: string; body: IntegrationInstanceUpdate }) =>
      apiFetch<IntegrationInstance>(`/api/v1/integrations/${encodeURIComponent(entityId)}`, {
        method: 'PUT',
        body,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useDeleteIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (entityId: string) =>
      apiFetch<void>(`/api/v1/integrations/${encodeURIComponent(entityId)}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

// TODO(backend-parallel): the plan (finding 1.11) calls for
// `POST /api/v1/integrations/{entity_id}/test`; as of this wave it is not
// yet registered in `backend/routers/integrations.py`, but a parallel wave
// is expected to land it at exactly this path/method — this is a one-line
// fix (or none at all) once it does. Kept defensive: any error surfaces via
// the mutation's onError, same as every other integration mutation here.
export function useTestIntegrationConnection() {
  return useMutation({
    mutationFn: (entityId: string) =>
      apiFetch<IntegrationTestResult>(
        `/api/v1/integrations/${encodeURIComponent(entityId)}/test`,
        { method: 'POST' },
      ),
  });
}

export function useCallIntegrationService() {
  return useMutation({
    mutationFn: ({
      entityId,
      service,
      data,
    }: {
      entityId: string;
      service: string;
      data?: Record<string, unknown>;
    }) =>
      apiFetch<Record<string, unknown>>(
        `/api/v1/integrations/${encodeURIComponent(entityId)}/service/${encodeURIComponent(service)}`,
        { method: 'POST', body: data ?? {} },
      ),
  });
}

export function useSetOauthToken() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      entityId,
      accessToken,
      refreshToken,
      expiresIn,
    }: {
      entityId: string;
      accessToken: string;
      refreshToken?: string;
      expiresIn?: number;
    }) =>
      apiFetch<{ ok: boolean }>(`/api/v1/integrations/${encodeURIComponent(entityId)}/oauth_token`, {
        method: 'POST',
        body: { access_token: accessToken, refresh_token: refreshToken, expires_in: expiresIn },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useIntegrationState(entityId: string | null) {
  return useQuery({
    queryKey: ['integrations', entityId, 'state'],
    queryFn: () =>
      apiFetch<{ entity_id: string; status: string; state: Record<string, unknown> }>(
        `/api/v1/integrations/${encodeURIComponent(entityId!)}/state`,
      ),
    enabled: Boolean(entityId),
    refetchInterval: 5000,
  });
}

export function useSpotifyLibrary(entityId: string | null) {
  return useQuery({
    queryKey: ['integrations', entityId, 'spotify-library'],
    queryFn: () =>
      apiFetch<Record<string, unknown>>(
        `/api/v1/integrations/${encodeURIComponent(entityId!)}/spotify/library`,
      ),
    enabled: Boolean(entityId),
  });
}

// ── ZerOS presets ─────────────────────────────────────────────────────────

export function useZerosPresets() {
  return useQuery({
    queryKey: ['zeros-presets'],
    queryFn: () => apiFetch<ZerosPreset[]>('/api/v1/zeros/presets'),
  });
}

export function useCreateZerosPreset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ZerosPresetCreate) =>
      apiFetch<ZerosPreset>('/api/v1/zeros/presets', { method: 'POST', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['zeros-presets'] }),
  });
}

export function useDeleteZerosPreset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch<void>(`/api/v1/zeros/presets/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['zeros-presets'] }),
  });
}
