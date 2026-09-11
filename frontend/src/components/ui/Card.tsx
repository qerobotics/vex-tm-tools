import type { HTMLAttributes, ReactNode } from 'react';

export function Card({ className = '', ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={`vmd-card ${className}`} {...props} />;
}

export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return (
    <div className="mb-6 flex items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold text-vmd-textStrong">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-vmd-textMuted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}
