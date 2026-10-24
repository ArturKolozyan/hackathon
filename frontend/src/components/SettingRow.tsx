import { useId, type ReactNode } from "react";
import { Switch } from "./ui";

/** Settings group: small title (+ save status) above one card of divided rows. */
export function SettingGroup({
  id,
  title,
  status,
  aside,
  children,
}: {
  id?: string;
  title: string;
  status?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
}) {
  const titleId = useId();
  return (
    <section className="settings-group" id={id} aria-labelledby={titleId}>
      <header className="group-head">
        <h2 id={titleId} className="group-title">
          {title}
        </h2>
        {status}
        {aside && <span className="group-aside">{aside}</span>}
      </header>
      <div className="group-card">{children}</div>
    </section>
  );
}

/**
 * One setting: LEFT = title + muted one-line description (+ inline error/hint),
 * RIGHT = the control. Optional expansion below (e.g. a revealed field).
 */
export function SettingRow({
  title,
  description,
  control,
  error,
  hint,
  htmlFor,
  wide,
  children,
}: {
  title: string;
  description?: ReactNode;
  control?: ReactNode;
  error?: string | null;
  hint?: ReactNode;
  htmlFor?: string;
  wide?: boolean;
  children?: ReactNode;
}) {
  return (
    <div className={error ? "set-row is-invalid" : "set-row"}>
      <div className="set-main">
        <div className="set-text">
          {htmlFor ? (
            <label className="set-title" htmlFor={htmlFor}>
              {title}
            </label>
          ) : (
            <span className="set-title">{title}</span>
          )}
          {description && <span className="set-desc">{description}</span>}
          {error ? (
            <span className="field-error" role="alert">
              {error}
            </span>
          ) : (
            hint && <span className="field-hint">{hint}</span>
          )}
        </div>
        {control && <div className={wide ? "set-control is-wide" : "set-control"}>{control}</div>}
      </div>
      {children && <div className="set-extra">{children}</div>}
    </div>
  );
}

export function SwitchRow({
  title,
  description,
  checked,
  onChange,
  disabled,
  children,
}: {
  title: string;
  description?: ReactNode;
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  children?: ReactNode;
}) {
  const id = useId();
  return (
    <div className="set-row">
      <div className="set-main">
        <div
          className={disabled ? "set-text" : "set-text is-clickable"}
          onClick={() => {
            if (!disabled) onChange(!checked);
          }}
        >
          <span id={`${id}-t`} className="set-title">
            {title}
          </span>
          {description && (
            <span id={`${id}-d`} className="set-desc">
              {description}
            </span>
          )}
        </div>
        <div className="set-control is-switch">
          <Switch
            checked={checked}
            onChange={onChange}
            disabled={disabled}
            labelledBy={`${id}-t`}
            describedBy={description ? `${id}-d` : undefined}
            hint={title}
          />
        </div>
      </div>
      {checked && children && <div className="set-extra">{children}</div>}
    </div>
  );
}

/** Text/number input with optional unit suffix, for the right side of a row. */
export function RowInput({
  id,
  value,
  onChange,
  onBlur,
  placeholder,
  suffix,
  inputMode,
  invalid,
  disabled,
  type = "text",
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  placeholder?: string;
  suffix?: string;
  inputMode?: "numeric" | "text" | "url" | "decimal";
  invalid?: boolean;
  disabled?: boolean;
  type?: string;
}) {
  return (
    <div className={suffix ? "input-with-suffix" : "input-plain"}>
      <input
        id={id}
        type={type}
        value={value}
        placeholder={placeholder}
        inputMode={inputMode}
        aria-invalid={invalid}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
        onBlur={onBlur}
      />
      {suffix && (
        <span className="input-suffix" aria-hidden="true">
          {suffix}
        </span>
      )}
    </div>
  );
}
