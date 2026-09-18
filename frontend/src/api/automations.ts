import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../lib/http';
import type {
  Automation,
  AutomationCreate,
  AutomationFolder,
  AutomationFolderCreate,
  AutomationFolderUpdate,
  AutomationRun,
  AutomationUpdate,
  TriggerResponse,
  ValidateRequest,
  ValidateResponse,
} from '../types/api';

export function useAutomationFolders() {
  return useQuery({
    queryKey: ['automation-folders'],
    queryFn: () => apiFetch<AutomationFolder[]>('/api/v1/automations/folders'),
  });
}

export function useCreateAutomationFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AutomationFolderCreate) =>
      apiFetch<AutomationFolder>('/api/v1/automations/folders', { method: 'POST', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['automation-folders'] }),
  });
}

// TODO(backend-parallel): `backend/routers/automations.py` currently only
// implements GET/POST for `/folders` (plan finding 2.4 / audit finding
// 2.4) — no PUT/DELETE route exists yet. Wired here against the plan's
// expected `PUT`/`DELETE /api/v1/automations/folders/{id}` shape (mirroring
// the automation-level update/delete routes just below), on the assumption
// a parallel backend wave adds them; this is a one-line fix if the final
// path/verb differs.
export function useUpdateAutomationFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: AutomationFolderUpdate }) =>
      apiFetch<AutomationFolder>(`/api/v1/automations/folders/${id}`, { method: 'PUT', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['automation-folders'] }),
  });
}

export function useDeleteAutomationFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch<void>(`/api/v1/automations/folders/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['automation-folders'] });
      qc.invalidateQueries({ queryKey: ['automations'] });
    },
  });
}

export function useAutomations() {
  return useQuery({
    queryKey: ['automations'],
    queryFn: () => apiFetch<Automation[]>('/api/v1/automations'),
  });
}

export function useCreateAutomation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AutomationCreate) => apiFetch<Automation>('/api/v1/automations', { method: 'POST', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['automations'] }),
  });
}

export function useUpdateAutomation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: AutomationUpdate }) =>
      apiFetch<Automation>(`/api/v1/automations/${id}`, { method: 'PUT', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['automations'] }),
  });
}

export function useDeleteAutomation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch<void>(`/api/v1/automations/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['automations'] }),
  });
}

export function useTriggerAutomation() {
  return useMutation({
    mutationFn: (id: string) => apiFetch<TriggerResponse>(`/api/v1/automations/${id}/trigger`, { method: 'POST' }),
  });
}

export function useAutomationRuns(automationId: string | null) {
  return useQuery({
    queryKey: ['automations', automationId, 'runs'],
    queryFn: () => apiFetch<AutomationRun[]>(`/api/v1/automations/${automationId}/runs`),
    enabled: Boolean(automationId),
  });
}

export function useValidateAutomation() {
  return useMutation({
    mutationFn: (body: ValidateRequest) =>
      apiFetch<ValidateResponse>('/api/v1/automations/validate', { method: 'POST', body }),
  });
}
