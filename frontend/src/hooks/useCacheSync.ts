import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { useWsStore } from '../stores/ws';

/**
 * The ONLY place a WebSocket event is allowed to influence TanStack Query
 * (plan §C.8.3): a `config_change` event means some REST-owned resource is
 * now stale, so we invalidate its query key and let TanStack Query refetch
 * — we never call `queryClient.setQueryData(...)` with the WS payload
 * itself (that's explicitly forbidden by §C.8.2).
 *
 * Mounted once at the app root (see `frontend/src/App.tsx`).
 */
const RESOURCE_TYPE_TO_QUERY_KEY: Record<string, string> = {
  integration_instance: 'integrations',
  timer_instance: 'timers',
  overlay_instance: 'overlays',
  automation: 'automations',
  script: 'scripts',
};

export function useCacheSync(): void {
  const queryClient = useQueryClient();

  useEffect(() => {
    const unsubscribe = useWsStore.subscribe((state, prevState) => {
      const event = state.recentEvents[0];
      if (!event || event === prevState.recentEvents[0]) return;

      if (event.type === 'config_change') {
        const resourceType = String(event.payload.resource_type ?? '');
        const queryKey = RESOURCE_TYPE_TO_QUERY_KEY[resourceType];
        if (queryKey) {
          void queryClient.invalidateQueries({ queryKey: [queryKey] });
        }
      }

      if (event.type === 'team_profile_updated') {
        void queryClient.invalidateQueries({ queryKey: ['teams'] });
      }
    });
    return unsubscribe;
  }, [queryClient]);
}
