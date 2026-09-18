import { useUiStore } from '../../stores/ui';

const VARIANT_CLASSES: Record<string, string> = {
  success: 'border-vmd-success/40 text-vmd-success',
  error: 'border-vmd-danger/40 text-vmd-danger',
  info: 'border-vmd-border text-vmd-text',
};

export function ToastContainer() {
  const toasts = useUiStore((s) => s.toasts);
  const dismiss = useUiStore((s) => s.dismissToast);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-[200] flex flex-col gap-2">
      {toasts.map((toast) => (
        <button
          key={toast.id}
          onClick={() => dismiss(toast.id)}
          className={`vmd-card max-w-sm text-left text-sm py-2 px-3.5 border ${VARIANT_CLASSES[toast.variant]}`}
        >
          {toast.message}
        </button>
      ))}
    </div>
  );
}
