import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/http';
import type { ClusterStatus } from '../types/api';

/**
 * `GET /api/v1/status` (plan §11 — cluster/leader/integration-health;
 * audit finding 1.7). As of this wave the exact response shape is still
 * being finalized by a parallel backend wave, so `ClusterStatus` types
 * every field as optional and this hook is read defensively (optional
 * chaining) wherever it's consumed — see `frontend/src/pages/Dashboard.tsx`.
 */
export function useClusterStatus() {
  return useQuery({
    queryKey: ['status'],
    queryFn: () => apiFetch<ClusterStatus>('/api/v1/status'),
    refetchInterval: 10_000,
    retry: false,
  });
}
