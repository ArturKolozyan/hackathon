import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { ApiError, api, type CalendarMonth, type Occurrence } from "../api";
import { OccurrenceCard } from "../components/OccurrenceCard";
import { PageControls } from "../components/PageControls";
import { EmptyState, ErrorState, LoadingBlock, Segmented } from "../components/ui";
import {
  addIsoDays,
  capitalMonth,
  formatMoney,
  isWeekend,
  isoParts,
  longDue,
  shiftAnchorMonth,
  shortDue,
  statusShort,
  statusTone,
  weekLabel,
  weekStart,
} from "../format";
import { useMediaQuery } from "../useMediaQuery";
import { HINTS } from "../hints";

const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

type View = "day" | "week" | "month";

function monthKey(year: number, month: number): string {
  return `${year}-${month}`;
}

function monthOf(iso: string): { year: number; month: number } {
  const { year, month } = isoParts(iso);
  return { year, month };
}

function monthsFor(view: View, iso: string): { year: number; month: number }[] {
  if (view !== "week") return [monthOf(iso)];
  const start = weekStart(iso);
  const end = addIsoDays(start, 6);
  const first = monthOf(start);
  const last = monthOf(end);
  if (first.year === last.year && first.month === last.month) return [first];
  return [first, last];
}

function dowIndex(iso: string): number {
  const { year, month, day } = isoParts(iso);
  return (new Date(Date.UTC(year, month - 1, day)).getUTCDay() + 6) % 7;
}

function cellsOf(year: number, month: number): Array<string | null> {
  const first = new Date(Date.UTC(year, month - 1, 1));
  const offset = (first.getUTCDay() + 6) % 7;
  const days = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const cells: Array<string | null> = Array.from({ length: offset }, () => null);
  for (let day = 1; day <= days; day += 1) {
    cells.push(`${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`);
  }
  while (cells.length % 7 !== 0) cells.push(null);
  return cells;
}

export function CalendarPage() {
  const narrow = useMediaQuery("(max-width: 720px)");
  const [view, setView] = useState<View>("month");
  const [anchor, setAnchor] = useState<string | null>(null);
  const [today, setToday] = useState<string | null>(null);
  const [cache, setCache] = useState<Record<string, CalendarMonth>>({});
  const [picked, setPicked] = useState<Occurrence | null>(null);
  const [agenda, setAgenda] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const cacheRef = useRef(cache);
  const detailRef = useRef<HTMLElement>(null);
  cacheRef.current = cache;

  useEffect(() => {
    let cancelled = false;
    async function run() {
      setError(null);
      try {
        if (!anchor) {
          setLoading(true);
          const first = await api<CalendarMonth>("/api/v1/payments/calendar");
          if (cancelled) return;
          const next = { ...cacheRef.current, [monthKey(first.year, first.month)]: first };
          cacheRef.current = next;
          setCache(next);
          setToday(first.today);
          setAnchor(first.today);
          setLoading(false);
          return;
        }
        const missing = monthsFor(view, anchor).filter((item) => !cacheRef.current[monthKey(item.year, item.month)]);
        if (missing.length === 0) {
          setLoading(false);
          return;
        }
        setLoading(true);
        const loaded = await Promise.all(
          missing.map((item) => api<CalendarMonth>(`/api/v1/payments/calendar?year=${item.year}&month=${item.month}`)),
        );
        if (cancelled) return;
        const next = { ...cacheRef.current };
        for (const month of loaded) {
          next[monthKey(month.year, month.month)] = month;
          setToday(month.today);
        }
        cacheRef.current = next;
        setCache(next);
        setLoading(false);
      } catch (err) {
        if (cancelled) return;
        setLoading(false);
        setError(err instanceof ApiError ? err.message : "Календарь не загрузился");
      }
    }
    void run();
    return () => {
      cancelled = true;
    };
  }, [anchor, view]);

  useEffect(() => {
    setPicked(null);
  }, [anchor, view]);

  useEffect(() => {
    if (!anchor || view !== "month") return;
    const prefix = anchor.slice(0, 7);
    setAgenda((current) => {
      if (current && current.startsWith(prefix)) return current;
      if (today && today.startsWith(prefix)) return today;
      return `${prefix}-01`;
    });
  }, [anchor, view, today]);

  useEffect(() => {
    if (!picked) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setPicked(null);
    }
    document.addEventListener("keydown", onKey);
    detailRef.current?.querySelector<HTMLElement>("h2")?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [picked]);

  const byDate = useMemo(() => {
    const map = new Map<string, Occurrence[]>();
    for (const month of Object.values(cache)) {
      for (const day of month.days) map.set(day.date, day.items);
    }
    return map;
  }, [cache]);

  async function reload(keepId?: string) {
    if (!anchor) return;
    setError(null);
    try {
      const loaded = await Promise.all(
        monthsFor(view, anchor).map((item) =>
          api<CalendarMonth>(`/api/v1/payments/calendar?year=${item.year}&month=${item.month}`),
        ),
      );
      const next = { ...cacheRef.current };
      const items: Occurrence[] = [];
      for (const month of loaded) {
        next[monthKey(month.year, month.month)] = month;
        setToday(month.today);
        for (const day of month.days) items.push(...day.items);
      }
      cacheRef.current = next;
      setCache(next);
      const id = keepId ?? picked?.id;
      setPicked(id ? items.find((item) => item.id === id) ?? null : null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Календарь не загрузился");
    }
  }

  function step(delta: number) {
    if (!anchor) return;
    if (view === "day") setAnchor(addIsoDays(anchor, delta));
    else if (view === "week") setAnchor(addIsoDays(anchor, delta * 7));
    else setAnchor(shiftAnchorMonth(anchor, delta));
  }

  const label = !anchor
    ? "Календарь"
    : view === "month"
      ? capitalMonth(isoParts(anchor).year, isoParts(anchor).month)
      : view === "week"
        ? weekLabel(weekStart(anchor), addIsoDays(weekStart(anchor), 6))
        : longDue(anchor);

  const dayItems = anchor ? byDate.get(anchor) ?? [] : [];
  const weekDays = anchor ? Array.from({ length: 7 }, (_, index) => addIsoDays(weekStart(anchor), index)) : [];
  const month = anchor ? isoParts(anchor) : null;
  const cells = month ? cellsOf(month.year, month.month) : [];
  const rows = Math.max(1, Math.ceil(cells.length / 7));

  function openDay(iso: string) {
    setView("day");
    setAnchor(iso);
  }

  return (
    <div className={`page page-cal view-${view}`}>
      <PageControls
        left={
        <div className="tb-group cal-nav">
          <button type="button" className="icon-btn" aria-label="Назад" data-hint={HINTS.calPrev} disabled={!anchor} onClick={() => step(-1)}>
            <ChevronLeft size={18} strokeWidth={1.75} aria-hidden />
          </button>
          <button type="button" className="icon-btn" aria-label="Дальше" data-hint={HINTS.calNext} disabled={!anchor} onClick={() => step(1)}>
            <ChevronRight size={18} strokeWidth={1.75} aria-hidden />
          </button>
          <button
            type="button"
            className="cal-label"
            disabled={!today}
            data-hint={HINTS.calToday}
            aria-label={`${label}. Перейти к сегодня`}
            onClick={() => today && setAnchor(today)}
          >
            {label}
          </button>
        </div>
        }
        center={
        <Segmented
          label="Вид календаря"
          value={view}
          options={[
            { value: "day", label: "День" },
            { value: "week", label: "Неделя" },
            { value: "month", label: "Месяц" },
          ]}
          onChange={setView}
        />
        }
      />
      {error && <ErrorState message={error} onRetry={() => void reload(picked?.id)} />}
      {loading && !anchor && <LoadingBlock label="Загружаем календарь…" />}
      {anchor && view === "month" && month && (
        <div className="month-board">
          <div className="cal-head">
            {WEEKDAYS.map((name, index) => (
              <span key={name} className={index >= 5 ? "cal-dow weekend" : "cal-dow"}>
                {name}
              </span>
            ))}
          </div>
          <div className="month-grid" style={{ "--rows": rows } as CSSProperties}>
            {cells.map((iso, index) => {
              if (!iso) return <div key={`pad-${index}`} className="month-cell is-pad" aria-hidden="true" />;
              const items = byDate.get(iso) ?? [];
              const day = Number(iso.slice(-2));
              const classes = [
                "month-cell",
                iso === today ? "today" : "",
                isWeekend(iso) ? "weekend" : "",
                narrow && agenda === iso ? "is-selected" : "",
              ]
                .filter(Boolean)
                .join(" ");
              return (
                <div key={iso} className={classes}>
                  <div className="month-top">
                    {narrow ? (
                      <button
                        type="button"
                        className="cal-num"
                        aria-pressed={agenda === iso}
                        data-hint={HINTS.calAgenda}
                        aria-label={`${longDue(iso)}, платежей: ${items.length}`}
                        onClick={() => setAgenda(iso)}
                      >
                        {day}
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="cal-num"
                        aria-current={iso === today ? "date" : undefined}
                        data-hint={HINTS.calOpenDay}
                        onClick={() => openDay(iso)}
                      >
                        <span className="sr-only">{longDue(iso)}</span>
                        <span aria-hidden="true">{day}</span>
                      </button>
                    )}
                    {items.length > 0 && <span className="cal-count">{items.length}</span>}
                  </div>
                  {!narrow &&
                    items.slice(0, 2).map((item) => (
                      <OperationCard key={item.id} item={item} iso={iso} compact onOpen={setPicked} />
                    ))}
                  {!narrow && items.length > 2 && (
                    <button type="button" className="cal-more" data-hint={HINTS.calMore} onClick={() => openDay(iso)}>
                      ещё {items.length - 2}
                    </button>
                  )}
                </div>
              );
            })}
          </div>
          {narrow && agenda && (
            <section className="cal-agenda" aria-label={longDue(agenda)}>
              <h2>{longDue(agenda)}</h2>
              {(byDate.get(agenda) ?? []).length === 0 ? (
                <p className="muted">В этот день платежей нет.</p>
              ) : (
                (byDate.get(agenda) ?? []).map((item) => (
                  <OperationCard key={item.id} item={item} iso={agenda} onOpen={setPicked} />
                ))
              )}
            </section>
          )}
        </div>
      )}
      {anchor && view === "week" && (
        <div className="week-board">
          {weekDays.map((iso, index) => {
            const items = byDate.get(iso) ?? [];
            const classes = ["week-col", isWeekend(iso) ? "weekend" : "", iso === today ? "today" : ""]
              .filter(Boolean)
              .join(" ");
            return (
              <section key={iso} className={classes} aria-label={longDue(iso)}>
                <header className="week-head">
                  <span className="cal-dow">{WEEKDAYS[index]}</span>
                  <button
                    type="button"
                    className={iso === today ? "cal-num today-num" : "cal-num"}
                    aria-current={iso === today ? "date" : undefined}
                    data-hint={HINTS.calOpenDay}
                    onClick={() => openDay(iso)}
                  >
                    {isoParts(iso).day}
                  </button>
                </header>
                <div className="week-body">
                  {items.length === 0 && <p className="muted week-empty">Пусто</p>}
                  {items.map((item) => (
                    <OperationCard key={item.id} item={item} iso={iso} onOpen={setPicked} />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      )}
      {anchor && view === "day" && (
        <div className={isWeekend(anchor) ? "day-board weekend" : "day-board"}>
          <header className="day-head">
            <span className="cal-dow">{WEEKDAYS[dowIndex(anchor)]}</span>
            <span className={anchor === today ? "cal-num today-num" : "cal-num"}>{isoParts(anchor).day}</span>
            {dayItems.length > 0 && <span className="cal-count">платежей: {dayItems.length}</span>}
          </header>
          <div className="day-body">
            {dayItems.length === 0 && !loading && (
              <EmptyState title="В этот день пусто">Периодов с таким сроком нет. Листайте день или откройте месяц.</EmptyState>
            )}
            {dayItems.map((item) => (
              <OperationCard key={item.id} item={item} iso={anchor} onOpen={setPicked} />
            ))}
          </div>
        </div>
      )}
      {picked && today && (
        <div className="modal-back" onMouseDown={(event) => event.target === event.currentTarget && setPicked(null)}>
          <section
            className="modal cal-detail"
            ref={detailRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="cal-detail-title"
          >
            <div className="modal-head">
              <h2 id="cal-detail-title" tabIndex={-1}>
                {picked.title}
              </h2>
              <button type="button" className="icon-btn" aria-label="Закрыть" data-hint={HINTS.close} onClick={() => setPicked(null)}>
                <X size={18} strokeWidth={1.75} aria-hidden />
              </button>
            </div>
            <OccurrenceCard
              item={picked}
              today={today}
              mode={picked.status === "paid" ? "history" : "inbox"}
              onChanged={() => void reload(picked.id)}
            />
          </section>
        </div>
      )}
    </div>
  );
}

function OperationCard({
  item,
  iso,
  compact,
  onOpen,
}: {
  item: Occurrence;
  iso: string;
  compact?: boolean;
  onOpen: (item: Occurrence) => void;
}) {
  const tone = statusTone(item.status);
  return (
    <button
      type="button"
      className={`op-card tone-${tone}`}
      data-hint={HINTS.calOperation}
      onClick={() => onOpen(item)}
      aria-label={`${item.title}, ${statusShort(item.status)}, ${formatMoney(item.amount, item.currency)}, ${longDue(iso)}`}
    >
      <span className={`pill pill-${tone}`}>{statusShort(item.status)}</span>
      <span className="op-meta">
        {shortDue(iso)} · {formatMoney(item.amount, item.currency)}
      </span>
      <span className="op-title">{item.title}</span>
      {!compact && item.responsible && <span className="op-who">{item.responsible.full_name}</span>}
    </button>
  );
}
