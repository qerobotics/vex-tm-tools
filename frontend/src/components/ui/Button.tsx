import type { ButtonHTMLAttributes } from 'react';

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost';

const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    'bg-vmd-textStrong text-black hover:bg-white border border-transparent',
  secondary:
    'bg-vmd-surfaceSubtle text-vmd-text hover:text-vmd-textStrong border border-vmd-border',
  danger: 'bg-vmd-danger/90 text-black hover:bg-vmd-danger border border-transparent',
  ghost: 'bg-transparent text-vmd-textMuted hover:text-vmd-textStrong border border-transparent',
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

export function Button({ variant = 'secondary', className = '', ...props }: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-sm font-medium
        transition-all duration-200 shadow-vmdChip hover:shadow-vmdChip disabled:opacity-40
        disabled:cursor-not-allowed ${VARIANT_CLASSES[variant]} ${className}`}
      {...props}
    />
  );
}
