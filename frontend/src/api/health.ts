import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/http';
import type { ReadyResponse } from '../types/api';

/**
 * GAP (plan §11 lists `GET /api/v1/status` for "Cluster status, leader,
 * integration health" — no such route exists anywhere under
 * `backend/routers/` as of this wave; only `/healthz` and `/readyz` are
 * wired in `backend/main.py`). The Dashboard's "Cluster status" card is
 * built from `/readyz` (db/redis reachability) instead of leader/heartbeat
 * data, which simply isn't exposed yet — see the note rendered on the
 * Dashboard page itself.
 */
export function useReadyz() {
  return useQuery({
    queryKey: ['readyz'],
    queryFn: () => apiFetch<ReadyResponse>('/readyz'),
    refetchInterval: 10_000,
    retry: false,
  });
}
