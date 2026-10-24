import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { createContext, useContext } from "react";
import { Check, type LucideIcon } from "lucide-react";
import { HINTS } from "../hints";

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

/** Empty page or list: icon, short title, one line on what to do, and the action if the role allows it. */
export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
  compact,
}: {
  icon: LucideIcon;
  title: string;
  children: ReactNode;
  action?: ReactNode;
  compact?: boolean;
}) {
  return (
    <div className={compact ? "panel empty-state is-compact" : "panel empty-state"}>
      <span className="empty-icon" aria-hidden="true">
        <Icon size={compact ? 20 : 24} strokeWidth={1.75} />
      </span>
      <h2>{title}</h2>
      <p>{children}</p>
      {action && <div className="row-actions">{action}</div>}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="panel error-state" role="alert">
      <p>{message}</p>
      {onRetry && (
        <button type="button" className="ghost" data-hint={HINTS.retry} onClick={onRetry}>
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
  options: { value: T; label: string; hint?: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={option.value === value}
          data-hint={option.hint}
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

/* ---------- Switch ---------- */

export function Switch({
  checked,
  onChange,
  disabled,
  label,
  labelledBy,
  describedBy,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  label?: string;
  labelledBy?: string;
  describedBy?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      className="switch"
      aria-checked={checked}
      aria-label={label}
      aria-labelledby={labelledBy}
      aria-describedby={describedBy}
      disabled={disabled}
      onClick={() => onChange(!checked)}
    >
      <span className="switch-thumb" aria-hidden="true" />
    </button>
  );
}

/** Row card: title + muted one-line description on the left, switch on the right. */
export function SwitchCard({
  title,
  description,
  checked,
  onChange,
  disabled,
  status,
  children,
}: {
  title: string;
  description?: ReactNode;
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  status?: ReactNode;
  children?: ReactNode;
}) {
  const id = useId();
  return (
    <div className={checked ? "switch-card is-on" : "switch-card"}>
      <div className="switch-row">
        <div
          className={disabled ? "switch-text" : "switch-text is-clickable"}
          onClick={() => {
            if (!disabled) onChange(!checked);
          }}
        >
          <span id={`${id}-t`} className="switch-title">
            {title}
          </span>
          {description && (
            <span id={`${id}-d`} className="switch-desc">
              {description}
            </span>
          )}
        </div>
        {status}
        <Switch
          checked={checked}
          onChange={onChange}
          disabled={disabled}
          labelledBy={`${id}-t`}
          describedBy={description ? `${id}-d` : undefined}
        />
      </div>
      {checked && children && <div className="switch-body">{children}</div>}
    </div>
  );
}

/* ---------- Instant save ---------- */

export type SaveState = "idle" | "saving" | "saved" | "error";

export type SaveApi = {
  state: SaveState;
  message: string | null;
  /** Runs a save. On failure calls rollback and keeps a retry. Resolves true on success. */
  run: (action: () => Promise<void>, rollback?: () => void) => Promise<boolean>;
  retry: () => void;
};

export function useSaveState(): SaveApi {
  const [state, setState] = useState<SaveState>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const retryRef = useRef<(() => void) | null>(null);
  const timerRef = useRef<number | undefined>(undefined);
  const runRef = useRef<SaveApi["run"]>(async () => false);

  runRef.current = async (action, rollback) => {
    window.clearTimeout(timerRef.current);
    setState("saving");
    setMessage(null);
    try {
      await action();
      retryRef.current = null;
      setState("saved");
      timerRef.current = window.setTimeout(() => setState("idle"), 2200);
      return true;
    } catch (err) {
      rollback?.();
      setMessage(err instanceof Error && err.message ? err.message : null);
      retryRef.current = () => void runRef.current(action, rollback);
      setState("error");
      return false;
    }
  };

  useEffect(() => () => window.clearTimeout(timerRef.current), []);

  return useMemo<SaveApi>(
    () => ({
      state,
      message,
      run: (action, rollback) => runRef.current(action, rollback),
      retry: () => retryRef.current?.(),
    }),
    [state, message],
  );
}

export function SaveStatus({ save }: { save: SaveApi }) {
  if (save.state === "idle") return <span className="save-status" aria-live="polite" />;
  if (save.state === "saving") {
    return (
      <span className="save-status is-saving" aria-live="polite">
        Сохраняю…
      </span>
    );
  }
  if (save.state === "saved") {
    return (
      <span className="save-status is-saved" aria-live="polite">
        <Check size={14} strokeWidth={2.25} aria-hidden />
        Сохранено
      </span>
    );
  }
  return (
    <span className="save-status is-error" aria-live="assertive">
      Ошибка —{" "}
      <button type="button" className="save-retry" data-hint={HINTS.saveRetry} onClick={save.retry}>
        повторить
      </button>
    </span>
  );
}

/** Debounced callback with flush (for save-on-blur). */
export function useDebounced<T>(fn: (value: T) => void, delay = 600) {
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const timerRef = useRef<number | undefined>(undefined);
  const pendingRef = useRef<{ value: T } | null>(null);

  useEffect(() => () => window.clearTimeout(timerRef.current), []);

  return useMemo(
    () => ({
      schedule(value: T) {
        pendingRef.current = { value };
        window.clearTimeout(timerRef.current);
        timerRef.current = window.setTimeout(() => {
          const pending = pendingRef.current;
          pendingRef.current = null;
          if (pending) fnRef.current(pending.value);
        }, delay);
      },
      flush() {
        window.clearTimeout(timerRef.current);
        const pending = pendingRef.current;
        pendingRef.current = null;
        if (pending) fnRef.current(pending.value);
      },
      cancel() {
        window.clearTimeout(timerRef.current);
        pendingRef.current = null;
      },
    }),
    [delay],
  );
}
