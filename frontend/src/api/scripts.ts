import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../lib/http';
import type { Script, ScriptCreate, ScriptUpdate } from '../types/api';

const KEY = ['scripts'] as const;

export function useScripts() {
  return useQuery({ queryKey: KEY, queryFn: () => apiFetch<Script[]>('/api/v1/scripts') });
}

export function useCreateScript() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ScriptCreate) => apiFetch<Script>('/api/v1/scripts', { method: 'POST', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useUpdateScript() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ScriptUpdate }) =>
      apiFetch<Script>(`/api/v1/scripts/${id}`, { method: 'PUT', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useDeleteScript() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiFetch<void>(`/api/v1/scripts/${id}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}
