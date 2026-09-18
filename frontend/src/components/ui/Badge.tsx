import type { ReactNode } from 'react';

const STATUS_COLORS: Record<string, string> = {
  CONNECTED: 'text-vmd-success border-vmd-success/40',
  DEGRADED: 'text-amber-300 border-amber-300/40',
  DISCONNECTED: 'text-vmd-danger border-vmd-danger/40',
};

export function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_COLORS[status] ?? 'text-vmd-textMuted border-vmd-border';
  return <span className={`vmd-chip ${cls}`}>{status}</span>;
}

export function Chip({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <span className={`vmd-chip text-vmd-text ${className}`}>{children}</span>;
}
