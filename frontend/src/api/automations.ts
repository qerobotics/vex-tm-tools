import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../lib/http';
import type {
  Automation,
  AutomationCreate,
  AutomationFolder,
  AutomationFolderCreate,
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
