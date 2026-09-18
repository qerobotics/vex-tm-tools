import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../lib/http';
import type { ApiKey, ApiKeyCreate, ApiKeyCreateResponse, RolePermission, SystemSetting } from '../types/api';

export function useSettings() {
  return useQuery({ queryKey: ['settings'], queryFn: () => apiFetch<SystemSetting[]>('/api/v1/settings') });
}

export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Record<string, { value: Record<string, unknown> }>) =>
      apiFetch<SystemSetting[]>('/api/v1/settings', { method: 'PUT', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings'] }),
  });
}

export function useApiKeys() {
  return useQuery({ queryKey: ['api-keys'], queryFn: () => apiFetch<ApiKey[]>('/api/v1/api-keys') });
}

export function useCreateApiKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ApiKeyCreate) => apiFetch<ApiKeyCreateResponse>('/api/v1/api-keys', { method: 'POST', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['api-keys'] }),
  });
}

export function useRevokeApiKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch<void>(`/api/v1/api-keys/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['api-keys'] }),
  });
}

// ── Users & Roles ─────────────────────────────────────────────────────────

export function useRolePermissions() {
  return useQuery({ queryKey: ['role-permissions'], queryFn: () => apiFetch<RolePermission[]>('/api/v1/users/roles') });
}

export function useReplaceRolePermissions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RolePermission[]) =>
      apiFetch<RolePermission[]>('/api/v1/users/roles', { method: 'PUT', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['role-permissions'] }),
  });
}
