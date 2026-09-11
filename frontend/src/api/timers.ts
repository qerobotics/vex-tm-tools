import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../lib/http';
import type {
  PrompterCue,
  PrompterCueCreate,
  PrompterCueUpdate,
  TimerInstance,
  TimerInstanceCreate,
  TimerInstanceUpdate,
} from '../types/api';

const KEY = ['timers'] as const;

export function useTimers() {
  return useQuery({ queryKey: KEY, queryFn: () => apiFetch<TimerInstance[]>('/api/v1/timers') });
}

export function useCreateTimer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TimerInstanceCreate) => apiFetch<TimerInstance>('/api/v1/timers', { method: 'POST', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useUpdateTimer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ entityId, body }: { entityId: string; body: TimerInstanceUpdate }) =>
      apiFetch<TimerInstance>(`/api/v1/timers/${encodeURIComponent(entityId)}`, { method: 'PUT', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useDeleteTimer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (entityId: string) =>
      apiFetch<void>(`/api/v1/timers/${encodeURIComponent(entityId)}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useStartTimer() {
  return useMutation({
    mutationFn: (entityId: string) =>
      apiFetch(`/api/v1/timers/${encodeURIComponent(entityId)}/start`, { method: 'POST' }),
  });
}

export function useStopTimer() {
  return useMutation({
    mutationFn: (entityId: string) =>
      apiFetch(`/api/v1/timers/${encodeURIComponent(entityId)}/stop`, { method: 'POST' }),
  });
}

export function useResetTimer() {
  return useMutation({
    mutationFn: (entityId: string) =>
      apiFetch(`/api/v1/timers/${encodeURIComponent(entityId)}/reset`, { method: 'POST' }),
  });
}

// ── Prompter cues ─────────────────────────────────────────────────────────

export function useCues(entityId: string | null) {
  return useQuery({
    queryKey: ['timers', entityId, 'cues'],
    queryFn: () => apiFetch<PrompterCue[]>(`/api/v1/timers/${encodeURIComponent(entityId!)}/cues`),
    enabled: Boolean(entityId),
  });
}

export function useCreateCue(entityId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PrompterCueCreate) =>
      apiFetch<PrompterCue>(`/api/v1/timers/${encodeURIComponent(entityId)}/cues`, { method: 'POST', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['timers', entityId, 'cues'] }),
  });
}

export function useUpdateCue(entityId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ cueId, body }: { cueId: string; body: PrompterCueUpdate }) =>
      apiFetch<PrompterCue>(`/api/v1/timers/${encodeURIComponent(entityId)}/cues/${cueId}`, {
        method: 'PUT',
        body,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['timers', entityId, 'cues'] }),
  });
}

export function useDeleteCue(entityId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (cueId: string) =>
      apiFetch<void>(`/api/v1/timers/${encodeURIComponent(entityId)}/cues/${cueId}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['timers', entityId, 'cues'] }),
  });
}
