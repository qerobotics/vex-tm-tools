import { create } from 'zustand';
import type { EventBusMessage } from '../types/api';

/**
 * WebSocket Zustand store (plan §C.3 / §C.8). ALL live-pushed data lives
 * here and ONLY here — REST config/identity data lives in TanStack Query
 * (see `frontend/src/api/*`). Nothing in this file ever calls
 * `queryClient.setQueryData` (that would violate §C.8.2's "never write to
 * each other" rule) — the only permitted cross-channel interaction is
 * `useCacheSync()` (`frontend/src/hooks/useCacheSync.ts`) invalidating
 * queries in reaction to a dispatched event.
 *
 * `dispatch()` is the single entry point `useWebSocket` calls with every
 * parsed message (plan §C.8.5) — a reducer-style function routing each
 * event to the right state slice.
 */

export interface TimerLiveState {
  phase?: string;
  running?: boolean;
  elapsed?: number;
  remaining?: number;
  [key: string]: unknown;
}

export interface UpcomingMatchPayload {
  matchNum?: number;
  round?: string;
  redTeams?: string[];
  blueTeams?: string[];
  high_potential?: boolean;
  fieldID?: number;
  divisionId?: number;
  [key: string]: unknown;
}

export interface CuesSnapshot {
  active: { id: string; content: string; type: string } | null;
  next: { id: string; content: string; type: string } | null;
}

export interface WsState {
  /** Raw connection status per useWebSocket URL, for debugging/UI use. */
  connected: boolean;

  /** integration_status events, keyed by entity_id. */
  integrationStatuses: Record<string, string>;

  /** timer_started/milestone/finished/stopped + timer_state, keyed by entity_id. */
  timerStates: Record<string, TimerLiveState>;

  /** cues events (prompter), keyed by entity_id. */
  cues: Record<string, CuesSnapshot>;

  /** fieldMatchAssigned / upcoming_match, keyed by fieldID (Field Monitor / Match Control)
   *  or by entity_id (Timer/Overlay-scoped upcoming_match messages). */
  currentMatches: Record<string, UpcomingMatchPayload>;

  /** Rolling buffer of the last 50 raw events (Dashboard / Audit Log live feed). */
  recentEvents: EventBusMessage[];

  /** automation_executed-equivalent: last-run result per automation id, if published. */
  automationLastRun: Record<string, { status: string; triggered_at: number }>;

  setConnected: (value: boolean) => void;
  dispatch: (event: EventBusMessage) => void;
  clearRecentEvents: () => void;
}

export const useWsStore = create<WsState>((set) => ({
  connected: false,
  integrationStatuses: {},
  timerStates: {},
  cues: {},
  currentMatches: {},
  recentEvents: [],
  automationLastRun: {},

  setConnected: (value) => set({ connected: value }),

  dispatch: (event) =>
    set((state) => {
      const next: Partial<WsState> = {
        recentEvents: [event, ...state.recentEvents].slice(0, 50),
      };

      switch (event.type) {
        case 'integration_status': {
          const status = String(event.payload.status ?? 'DISCONNECTED');
          next.integrationStatuses = { ...state.integrationStatuses, [event.entity_id]: status };
          break;
        }
        case 'timer_started':
        case 'timer_milestone':
        case 'timer_finished':
        case 'timer_stopped':
        case 'timer_state': {
          next.timerStates = {
            ...state.timerStates,
            [event.entity_id]: event.payload as TimerLiveState,
          };
          break;
        }
        case 'cues': {
          next.cues = { ...state.cues, [event.entity_id]: event.payload as unknown as CuesSnapshot };
          break;
        }
        case 'fieldMatchAssigned': {
          const fieldId = event.payload.fieldID;
          if (fieldId !== undefined && fieldId !== null) {
            next.currentMatches = {
              ...state.currentMatches,
              [String(fieldId)]: event.payload as UpcomingMatchPayload,
            };
          }
          break;
        }
        case 'upcoming_match': {
          next.currentMatches = {
            ...state.currentMatches,
            [event.entity_id]: event.payload as UpcomingMatchPayload,
          };
          break;
        }
        case 'automation_executed': {
          const automationId = String(event.payload.automation_id ?? event.entity_id);
          next.automationLastRun = {
            ...state.automationLastRun,
            [automationId]: {
              status: String(event.payload.status ?? 'unknown'),
              triggered_at: event.timestamp,
            },
          };
          break;
        }
        default:
          break;
      }

      return next;
    }),

  clearRecentEvents: () => set({ recentEvents: [] }),
}));
