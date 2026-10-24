import { useEffect, useId, useMemo, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { localTime, mskLabel, sortedZones, zoneCity } from "../timezones";
import { useDismiss, useFixedBox } from "./fields";

/**
 * Выбор часового пояса как список городов: слева город, в середине смещение от Москвы,
 * справа текущее местное время (обновляется, пока список открыт). На телефоне — шторка снизу.
 */
export function TimezoneField({
  id,
  value,
  onChange,
  disabled,
  hint,
}: {
  id?: string;
  value: string;
  onChange: (zone: string) => void;
  disabled?: boolean;
  hint?: string;
}) {
  const [open, setOpen] = useState(false);
  const [now, setNow] = useState(() => new Date());
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const listId = useId();
  const box = useFixedBox(open, buttonRef, "end");
  const zones = useMemo(() => sortedZones(now), [now]);
  const close = () => {
    setOpen(false);
    buttonRef.current?.focus();
  };
  useDismiss(open, rootRef, close);

  useEffect(() => {
    if (!open) return;
    setNow(new Date());
    const timer = window.setInterval(() => setNow(new Date()), 15000);
    return () => window.clearInterval(timer);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const index = Math.max(0, zones.findIndex((zone) => zone.id === value));
    setActive(index);
    const list = listRef.current;
    list?.focus();
    list?.querySelector<HTMLElement>('[aria-selected="true"]')?.scrollIntoView({ block: "center" });
    // Только при открытии: дальше список двигает клавиатура.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open) return;
    listRef.current?.querySelectorAll<HTMLElement>(".tz-option")[active]?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  function choose(zone: string) {
    setOpen(false);
    buttonRef.current?.focus();
    if (zone !== value) onChange(zone);
  }

  const width = box ? Math.min(Math.max(box.width, 360), window.innerWidth - 16) : 0;
  const left = box ? Math.max(8, Math.min(box.left + box.width - width, window.innerWidth - width - 8)) : 0;

  return (
    <div className="field tz-field" ref={rootRef}>
      <button
        ref={buttonRef}
        id={id}
        type="button"
        className="field-btn tz-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        data-hint={hint}
        disabled={disabled}
        onClick={() => setOpen((next) => !next)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        <span className="tz-trigger-city">{zoneCity(value)}</span>
        <span className="tz-off">{mskLabel(value, now)}</span>
        <ChevronDown size={16} strokeWidth={1.75} aria-hidden />
      </button>
      {open && box && <div className="field-scrim" aria-hidden="true" onClick={close} />}
      {open && box && (
        <div
          ref={listRef}
          id={listId}
          className="field-pop tz-pop"
          role="listbox"
          tabIndex={0}
          aria-label="Часовой пояс"
          style={{ top: box.top, left, width }}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setActive((current) => (current + 1) % zones.length);
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              setActive((current) => (current - 1 + zones.length) % zones.length);
            } else if (event.key === "Home") {
              event.preventDefault();
              setActive(0);
            } else if (event.key === "End") {
              event.preventDefault();
              setActive(zones.length - 1);
            } else if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              const zone = zones[active];
              if (zone) choose(zone.id);
            }
          }}
        >
          {zones.map((zone, index) => (
            <button
              key={zone.id}
              type="button"
              role="option"
              aria-selected={zone.id === value}
              className={index === active ? "tz-option is-active" : "tz-option"}
              onMouseEnter={() => setActive(index)}
              onClick={() => choose(zone.id)}
            >
              <span className="tz-city">{zone.city}</span>
              <span className="tz-off">{mskLabel(zone.id, now)}</span>
              <span className="tz-time">{localTime(zone.id, now)}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
