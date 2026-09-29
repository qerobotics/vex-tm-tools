import { create } from 'zustand';

export interface Toast {
  id: number;
  message: string;
  variant: 'success' | 'error' | 'info';
}

let toastCounter = 0;

export interface UiState {
  sidebarOpen: boolean;
  toggleSidebar: () => void;
  /** True while any mounted useWebSocket instance is reconnecting (plan Appendix A.14). */
  reconnecting: boolean;
  setReconnecting: (value: boolean) => void;
  toasts: Toast[];
  pushToast: (message: string, variant?: Toast['variant']) => void;
  dismissToast: (id: number) => void;
}

/** How long a toast stays on screen before dismissing itself. */
export const TOAST_DURATION_MS = 5000;

export const useUiStore = create<UiState>((set) => ({
  sidebarOpen: true,
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  reconnecting: false,
  setReconnecting: (value) => set({ reconnecting: value }),
  toasts: [],
  pushToast: (message, variant = 'info') => {
    const id = ++toastCounter;
    set((s) => ({ toasts: [...s.toasts, { id, message, variant }] }));
    // Harmless if the user already clicked it away: filtering by id is a no-op.
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), TOAST_DURATION_MS);
  },
  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
