import { useId, type FormEvent, type ReactNode } from "react";
import { ArrowLeft } from "lucide-react";
import { HINTS } from "../hints";

/**
 * Dedicated create/edit screen: centered narrow column, form name as H1,
 * grouped sections, sticky bottom bar with «Назад» left and the primary action right.
 */
export function FormScreen({
  title,
  onBack,
  onSubmit,
  submitLabel,
  submitHint,
  busy,
  busyLabel = "Сохраняю…",
  error,
  children,
}: {
  title: string;
  onBack: () => void;
  onSubmit: () => void;
  submitLabel: string;
  submitHint?: string;
  busy?: boolean;
  busyLabel?: string;
  error?: string | null;
  children: ReactNode;
}) {
  function submit(event: FormEvent) {
    event.preventDefault();
    if (!busy) onSubmit();
  }
  return (
    <form className="form-screen" onSubmit={submit} noValidate aria-busy={busy}>
      <div className="form-column">
        <h1 className="form-title">{title}</h1>
        {children}
        {error && (
          <p className="error form-error" role="alert">
            {error}
          </p>
        )}
      </div>
      <div className="form-bar">
        <div className="form-bar-inner">
          <button type="button" className="ghost" data-hint={HINTS.back} onClick={onBack}>
            <ArrowLeft size={16} strokeWidth={1.75} aria-hidden />
            Назад
          </button>
          <button type="submit" className="primary" disabled={busy} data-hint={submitHint}>
            {busy ? busyLabel : submitLabel}
          </button>
        </div>
      </div>
    </form>
  );
}

export function FormSection({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <section className="form-section">
      {title && <h2 className="form-section-title">{title}</h2>}
      <div className="form-section-body">{children}</div>
    </section>
  );
}

/** Question-style label above the control, optional unit suffix, hint and inline error. */
export function FormField({
  label,
  hint,
  error,
  suffix,
  optional,
  children,
}: {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  suffix?: ReactNode;
  optional?: boolean;
  children: (props: { id: string; describedBy?: string; invalid: boolean }) => ReactNode;
}) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [errorId, hintId].filter(Boolean).join(" ") || undefined;
  return (
    <div className={error ? "form-field is-invalid" : "form-field"}>
      <label className="form-label" htmlFor={id}>
        {label}
        {optional && <span className="form-optional"> — необязательно</span>}
      </label>
      <div className={suffix ? "input-with-suffix" : "input-plain"}>
        {children({ id, describedBy, invalid: Boolean(error) })}
        {suffix && (
          <span className="input-suffix" aria-hidden="true">
            {suffix}
          </span>
        )}
      </div>
      {error && (
        <p id={errorId} className="field-error" role="alert">
          {error}
        </p>
      )}
      {hint && (
        <p id={hintId} className="field-hint">
          {hint}
        </p>
      )}
    </div>
  );
}
