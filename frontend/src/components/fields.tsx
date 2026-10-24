import { useEffect, useId, useRef, useState, type RefObject } from "react";
import { Calendar, ChevronDown, ChevronLeft, ChevronRight } from "lucide-react";

export type FieldOption = { value: string; label: string };

const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const MONTHS = [
  "январь",
  "февраль",
  "март",
  "апрель",
  "май",
  "июнь",
  "июль",
  "август",
  "сентябрь",
  "октябрь",
  "ноябрь",
  "декабрь",
];

function todayIso(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

function parts(iso: string): { year: number; month: number; day: number } | null {
  const match = /^(\d{4})-(\d{2})(?:-(\d{2}))?$/.exec(iso);
  if (!match) return null;
  return { year: Number(match[1]), month: Number(match[2]), day: Number(match[3] ?? "1") };
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

function ruDate(iso: string): string {
  const parsed = parts(iso);
  if (!parsed) return "";
  return `${pad(parsed.day)}.${pad(parsed.month)}.${parsed.year}`;
}

function ruMonth(iso: string): string {
  const parsed = parts(iso);
  if (!parsed) return "";
  return `${MONTHS[parsed.month - 1]} ${parsed.year}`;
}

function shiftMonth(year: number, month: number, delta: number): { year: number; month: number } {
  const index = year * 12 + (month - 1) + delta;
  return { year: Math.floor(index / 12), month: (index % 12) + 1 };
}

function inRange(iso: string, min?: string, max?: string): boolean {
  if (min && iso < min) return false;
  if (max && iso > max) return false;
  return true;
}

function useDismiss(open: boolean, root: RefObject<HTMLElement | null>, close: () => void) {
  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) close();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, root, close]);
}

function useFixedBox(open: boolean, anchor: RefObject<HTMLElement | null>, align: "start" | "end") {
  const [box, setBox] = useState<{ top: number; left: number; width: number } | null>(null);
  useEffect(() => {
    if (!open) return;
    const place = () => {
      const node = anchor.current;
      if (!node) return;
      const rect = node.getBoundingClientRect();
      const width = Math.max(rect.width, align === "end" ? 220 : rect.width);
      const left = align === "end" ? Math.max(8, rect.right - width) : Math.min(rect.left, window.innerWidth - width - 8);
      const below = window.innerHeight - rect.bottom;
      const top = below < 220 && rect.top > below ? Math.max(8, rect.top - 8) : rect.bottom + 4;
      setBox({ top, left, width });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open, anchor, align]);
  return box;
}

export function SelectField({
  value,
  onChange,
  options,
  ariaLabel,
  required,
  className,
  align = "start",
}: {
  value: string;
  onChange: (value: string) => void;
  options: FieldOption[];
  ariaLabel?: string;
  required?: boolean;
  className?: string;
  align?: "start" | "end";
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const listId = useId();
  const selected = options.find((option) => option.value === value);
  const box = useFixedBox(open, buttonRef, align);
  const close = () => {
    setOpen(false);
    buttonRef.current?.focus();
  };
  useDismiss(open, rootRef, close);

  useEffect(() => {
    if (!open) return;
    const index = Math.max(0, options.findIndex((option) => option.value === value));
    setActive(index);
    listRef.current?.focus();
  }, [open, options, value]);

  function choose(next: string) {
    onChange(next);
    setOpen(false);
    buttonRef.current?.focus();
  }

  function move(delta: number) {
    setActive((current) => {
      const count = options.length;
      if (count === 0) return 0;
      return (current + delta + count) % count;
    });
  }

  return (
    <div className={className ? `field ${className}` : "field"} ref={rootRef}>
      <button
        ref={buttonRef}
        type="button"
        className="field-btn"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((next) => !next)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        <span>{selected?.label ?? "Выберите"}</span>
        <ChevronDown size={16} strokeWidth={1.75} aria-hidden />
      </button>
      {required && (
        <input className="field-proxy" tabIndex={-1} aria-hidden value={value} required onChange={() => undefined} />
      )}
      {open && box && (
        <div
          ref={listRef}
          id={listId}
          className="field-pop"
          role="listbox"
          tabIndex={0}
          aria-label={ariaLabel}
          style={{ top: box.top, left: box.left, width: box.width }}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              move(1);
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              move(-1);
            } else if (event.key === "Home") {
              event.preventDefault();
              setActive(0);
            } else if (event.key === "End") {
              event.preventDefault();
              setActive(Math.max(0, options.length - 1));
            } else if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              const option = options[active];
              if (option) choose(option.value);
            }
          }}
        >
          {options.map((option, index) => (
            <button
              key={option.value || `empty-${index}`}
              type="button"
              role="option"
              aria-selected={option.value === value}
              className={index === active ? "field-option is-active" : "field-option"}
              onMouseEnter={() => setActive(index)}
              onClick={() => choose(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function DateField({
  value,
  onChange,
  ariaLabel,
  required,
  min,
  max,
  mode = "date",
}: {
  value: string;
  onChange: (value: string) => void;
  ariaLabel?: string;
  required?: boolean;
  min?: string;
  max?: string;
  mode?: "date" | "month";
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const parsed = parts(value) ?? parts(mode === "month" ? `${todayIso().slice(0, 7)}` : todayIso());
  const [cursor, setCursor] = useState({ year: parsed?.year ?? 2026, month: parsed?.month ?? 1 });
  const box = useFixedBox(open, buttonRef, "start");
  const close = () => {
    setOpen(false);
    buttonRef.current?.focus();
  };
  useDismiss(open, rootRef, close);

  useEffect(() => {
    if (!open) return;
    const next = parts(value);
    if (next) setCursor({ year: next.year, month: next.month });
  }, [open, value]);

  const label = value ? (mode === "month" ? ruMonth(value) : ruDate(value)) : mode === "month" ? "мм.гггг" : "дд.мм.гггг";
  const days = mode === "date" ? daysOf(cursor.year, cursor.month) : [];

  function pick(iso: string) {
    if (!inRange(iso, min, max)) return;
    onChange(iso);
    close();
  }

  return (
    <div className="field" ref={rootRef}>
      <button
        ref={buttonRef}
        type="button"
        className={value ? "field-btn" : "field-btn is-placeholder"}
        aria-label={ariaLabel}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((next) => !next)}
      >
        <span>{label}</span>
        <Calendar size={16} strokeWidth={1.75} aria-hidden />
      </button>
      {required && (
        <input className="field-proxy" tabIndex={-1} aria-hidden value={value} required onChange={() => undefined} />
      )}
      {open && box && (
        <div className="field-pop date-pop" role="dialog" aria-label={ariaLabel ?? "Дата"} style={{ top: box.top, left: box.left, width: Math.max(box.width, 280) }}>
          <div className="date-nav">
            <button
              type="button"
              className="icon-btn"
              aria-label="Назад"
              onClick={() => setCursor((current) => shiftMonth(current.year, current.month, mode === "month" ? -12 : -1))}
            >
              <ChevronLeft size={16} strokeWidth={1.75} aria-hidden />
            </button>
            <span>{mode === "month" ? cursor.year : `${MONTHS[cursor.month - 1]} ${cursor.year}`}</span>
            <button
              type="button"
              className="icon-btn"
              aria-label="Дальше"
              onClick={() => setCursor((current) => shiftMonth(current.year, current.month, mode === "month" ? 12 : 1))}
            >
              <ChevronRight size={16} strokeWidth={1.75} aria-hidden />
            </button>
          </div>
          {mode === "month" ? (
            <div className="month-pick">
              {MONTHS.map((name, index) => {
                const iso = `${cursor.year}-${pad(index + 1)}`;
                const disabled = !inRange(iso, min?.slice(0, 7), max?.slice(0, 7));
                return (
                  <button
                    key={name}
                    type="button"
                    className={value.slice(0, 7) === iso ? "date-day is-selected" : "date-day"}
                    disabled={disabled}
                    onClick={() => pick(iso)}
                  >
                    {name.slice(0, 3)}
                  </button>
                );
              })}
            </div>
          ) : (
            <>
              <div className="date-grid date-dows">
                {WEEKDAYS.map((name) => (
                  <span key={name}>{name}</span>
                ))}
              </div>
              <div className="date-grid">
                {days.map((iso, index) =>
                  iso ? (
                    <button
                      key={iso}
                      type="button"
                      className={[
                        "date-day",
                        iso === todayIso() ? "is-today" : "",
                        iso === value ? "is-selected" : "",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                      disabled={!inRange(iso, min, max)}
                      onClick={() => pick(iso)}
                    >
                      {Number(iso.slice(-2))}
                    </button>
                  ) : (
                    <span key={`pad-${index}`} />
                  ),
                )}
              </div>
            </>
          )}
          {value && !required && (
            <button
              type="button"
              className="ghost date-clear"
              onClick={() => {
                onChange("");
                close();
              }}
            >
              Сбросить
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function daysOf(year: number, month: number): Array<string | null> {
  const first = new Date(Date.UTC(year, month - 1, 1));
  const offset = (first.getUTCDay() + 6) % 7;
  const count = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const cells: Array<string | null> = Array.from({ length: offset }, () => null);
  for (let day = 1; day <= count; day += 1) cells.push(`${year}-${pad(month)}-${pad(day)}`);
  return cells;
}
