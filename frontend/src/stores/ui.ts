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

export const useUiStore = create<UiState>((set) => ({
  sidebarOpen: true,
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  reconnecting: false,
  setReconnecting: (value) => set({ reconnecting: value }),
  toasts: [],
  pushToast: (message, variant = 'info') =>
    set((s) => ({ toasts: [...s.toasts, { id: ++toastCounter, message, variant }] })),
  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
