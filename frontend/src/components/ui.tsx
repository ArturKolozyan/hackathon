import { useEffect, useMemo, useState, type ReactNode } from "react";
import { createContext, useContext } from "react";

const ToastContext = createContext<{ push: (message: string) => void } | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!message) return;
    const timer = window.setTimeout(() => setMessage(null), 4200);
    return () => window.clearTimeout(timer);
  }, [message]);

  const api = useMemo(() => ({ push: (next: string) => setMessage(next) }), []);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-region" aria-live="polite">
        {message && <p className="toast">{message}</p>}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}

export function LoadingBlock({ label = "Загрузка…" }: { label?: string }) {
  return (
    <div className="skeleton-stack" role="status" aria-live="polite" aria-busy="true">
      <span className="sr-only">{label}</span>
      <span className="skeleton skeleton-line" />
      <span className="skeleton skeleton-card" />
      <span className="skeleton skeleton-card short" />
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="panel empty-state">
      <h2>{title}</h2>
      <p>{children}</p>
      {action}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="panel error-state" role="alert">
      <p>{message}</p>
      {onRetry && (
        <button type="button" className="ghost" onClick={onRetry}>
          Повторить
        </button>
      )}
    </div>
  );
}

export function InlineConfirm({
  title,
  confirmLabel,
  busy,
  onConfirm,
  onCancel,
}: {
  title: string;
  confirmLabel: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="inline-confirm" role="group" aria-label={title}>
      <p>{title}</p>
      <div className="row-actions">
        <button type="button" className="primary" disabled={busy} onClick={onConfirm}>
          {busy ? "Сохраняю…" : confirmLabel}
        </button>
        <button type="button" className="ghost" onClick={onCancel}>
          Отмена
        </button>
      </div>
    </div>
  );
}

export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((option) => (
        <button key={option.value} type="button" aria-pressed={option.value === value} onClick={() => onChange(option.value)}>
          {option.label}
        </button>
      ))}
    </div>
  );
}
