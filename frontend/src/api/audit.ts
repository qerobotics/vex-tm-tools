import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/http';
import type { AuditLogEntry, AuditLogFilters } from '../types/api';

/**
 * `GET /api/v1/audit` (plan §11/§12, audit findings 1.5). Gated on
 * `settings:read` by the backend (`backend/routers/audit.py`) — callers
 * should check `usePermission('settings:read')` before rendering the page,
 * same pattern as the Settings page's read-only views.
 *
 * Per Appendix C.8: this is the sole REST-owned source of audit history.
 * Live WS events (`useCacheSync`) may invalidate this query key but must
 * never be merged into its data.
 */
export const AUDIT_KEY = ['audit'] as const;

export function useAuditLog(filters: AuditLogFilters) {
  return useQuery({
    queryKey: [...AUDIT_KEY, filters],
    queryFn: () =>
      apiFetch<AuditLogEntry[]>('/api/v1/audit', {
        query: {
          user: filters.user || undefined,
          action: filters.action || undefined,
          resource_type: filters.resource_type || undefined,
          start_date: filters.start_date || undefined,
          end_date: filters.end_date || undefined,
          limit: filters.limit,
          offset: filters.offset,
        },
      }),
  });
}
