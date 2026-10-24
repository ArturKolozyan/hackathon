import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { CalendarCheck, X } from "lucide-react";
import { ApiError, api, type CalendarMonth, type Occurrence } from "../api";
import { OccurrenceCard } from "../components/OccurrenceCard";
import { SelectField } from "../components/fields";
import { PageControls } from "../components/PageControls";
import { PeriodNav } from "../components/PeriodNav";
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
import { useAuth } from "../auth";
import { useMediaQuery } from "../useMediaQuery";
import { HINTS } from "../hints";
import { useFresh } from "../fresh";

const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

type View = "week" | "month";

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

function compactWeek(startIso: string, endIso: string): string {
  const start = isoParts(startIso);
  const end = isoParts(endIso);
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${pad(start.day)}.${pad(start.month)}–${pad(end.day)}.${pad(end.month)}`;
}

const MONTH_SHORT = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];

/** Неделя на стыке лет длиннее остальных — сокращаем месяцы, чтобы влезла в ту же ширину. */
function wideWeek(startIso: string, endIso: string): string {
  const start = isoParts(startIso);
  const end = isoParts(endIso);
  if (start.year === end.year) return weekLabel(startIso, endIso);
  return `${start.day} ${MONTH_SHORT[start.month - 1]} ${start.year} – ${end.day} ${MONTH_SHORT[end.month - 1]} ${end.year}`;
}

/** Ширина середины навигатора: стрелки не прыгают между периодами. */
const LABEL_WIDTH: Record<View, { wide: string; narrow: string }> = {
  week: { wide: "17.5rem", narrow: "8rem" },
  month: { wide: "10.5rem", narrow: "9rem" },
};

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
  const { user } = useAuth();
  // Несколько отделов (владелец или человек в двух отделах) — календарь сразу по всем, с фильтром.
  const multi = Boolean(user?.is_owner) || (user?.memberships.length ?? 0) > 1;
  const scope = multi ? "&scope=all" : "";
  const [teamFilter, setTeamFilter] = useState("");
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
  const fresh = useFresh();
  cacheRef.current = cache;

  useEffect(() => {
    let cancelled = false;
    async function run() {
      setError(null);
      try {
        if (!anchor) {
          setLoading(true);
          const first = await api<CalendarMonth>(`/api/v1/payments/calendar${multi ? "?scope=all" : ""}`);
          if (cancelled) return;
          const next = { ...cacheRef.current, [monthKey(first.year, first.month)]: first };
          cacheRef.current = next;
          setCache(next);
          setToday(first.today);
          setAnchor(first.today);
          setLoading(false);
          return;
        }
        // Уже виденный месяц показывается сразу и тут же сверяется с сервером.
        const months = monthsFor(view, anchor);
        setLoading(months.some((item) => !cacheRef.current[monthKey(item.year, item.month)]));
        const loaded = await Promise.all(
          months.map((item) => api<CalendarMonth>(`/api/v1/payments/calendar?year=${item.year}&month=${item.month}${scope}`)),
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
  }, [anchor, view, fresh]);

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

  const teams = useMemo(() => {
    const map = new Map<string, string>();
    for (const month of Object.values(cache)) for (const team of month.teams ?? []) map.set(team.id, team.name);
    return map;
  }, [cache]);
  const showTeam = multi && teams.size > 1 && !teamFilter;

  const byDate = useMemo(() => {
    const map = new Map<string, Occurrence[]>();
    for (const month of Object.values(cache)) {
      for (const day of month.days) {
        const items = teamFilter ? day.items.filter((item) => item.team_id === teamFilter) : day.items;
        if (items.length > 0) map.set(day.date, items);
      }
    }
    return map;
  }, [cache, teamFilter]);

  async function reload(keepId?: string) {
    if (!anchor) return;
    setError(null);
    try {
      const loaded = await Promise.all(
        monthsFor(view, anchor).map((item) =>
          api<CalendarMonth>(`/api/v1/payments/calendar?year=${item.year}&month=${item.month}${scope}`),
        ),
      );
      // Изменение могло задеть и другие месяцы: старые снимки выбрасываем.
      const next: Record<string, CalendarMonth> = {};
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
    if (view === "week") setAnchor(addIsoDays(anchor, delta * 7));
    else setAnchor(shiftAnchorMonth(anchor, delta));
  }

  const label = !anchor
    ? "Календарь"
    : view === "month"
      ? capitalMonth(isoParts(anchor).year, isoParts(anchor).month)
      : narrow
        ? compactWeek(weekStart(anchor), addIsoDays(weekStart(anchor), 6))
        : wideWeek(weekStart(anchor), addIsoDays(weekStart(anchor), 6));
  const fullLabel = anchor && view === "week" ? weekLabel(weekStart(anchor), addIsoDays(weekStart(anchor), 6)) : label;
  const teamSelect =
    multi && teams.size > 1 ? (
      <SelectField
        ariaLabel="Отдел"
        align="end"
        value={teamFilter}
        onChange={setTeamFilter}
        options={[
          { value: "", label: "Все отделы" },
          ...[...teams.entries()]
            .sort((a, b) => a[1].localeCompare(b[1], "ru"))
            .map(([id, name]) => ({ value: id, label: name })),
        ]}
      />
    ) : null;

  const weekDays = anchor ? Array.from({ length: 7 }, (_, index) => addIsoDays(weekStart(anchor), index)) : [];
  const month = anchor ? isoParts(anchor) : null;
  const cells = month ? cellsOf(month.year, month.month) : [];
  const rows = Math.max(1, Math.ceil(cells.length / 7));

  function openWeek(iso: string) {
    setView("week");
    setAnchor(iso);
  }

  return (
    <div className={`page page-cal view-${view}`}>
      <PageControls
        left={
        <PeriodNav
          label="Период календаря"
          prevLabel={view === "week" ? "Предыдущая неделя" : "Предыдущий месяц"}
          nextLabel={view === "week" ? "Следующая неделя" : "Следующий месяц"}
          prevHint={HINTS.calPrev}
          nextHint={HINTS.calNext}
          disabled={!anchor}
          onPrev={() => step(-1)}
          onNext={() => step(1)}
          width={narrow ? LABEL_WIDTH[view].narrow : LABEL_WIDTH[view].wide}
        >
          <button
            type="button"
            className="cal-label"
            disabled={!today}
            data-hint={HINTS.calToday}
            aria-label={`${fullLabel}. Перейти к сегодня`}
            aria-live="polite"
            onClick={() => today && setAnchor(today)}
          >
            {label}
          </button>
        </PeriodNav>
        }
        right={!narrow && teamSelect ? teamSelect : undefined}
        center={
        <Segmented
          label="Вид календаря"
          value={view}
          options={[
            { value: "week", label: "Неделя", hint: HINTS.calViewWeek },
            { value: "month", label: "Месяц", hint: HINTS.calViewMonth },
          ]}
          onChange={setView}
        />
        }
      />
      {narrow && teamSelect && <div className="cal-filter">{teamSelect}</div>}
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
                        onClick={() => openWeek(iso)}
                      >
                        <span className="sr-only">{longDue(iso)}</span>
                        <span aria-hidden="true">{day}</span>
                      </button>
                    )}
                    {items.length > 0 && <span className="cal-count">{items.length}</span>}
                  </div>
                  {!narrow &&
                    items.slice(0, 2).map((item) => (
                      <OperationCard key={item.id} item={item} iso={iso} compact team={showTeam ? teams.get(item.team_id) : undefined} onOpen={setPicked} />
                    ))}
                  {!narrow && items.length > 2 && (
                    <button type="button" className="cal-more" data-hint={HINTS.calMore} onClick={() => openWeek(iso)}>
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
                <EmptyState compact icon={CalendarCheck} title="Платежей нет">
                  В этот день сроков нет. Выберите другую дату.
                </EmptyState>
              ) : (
                (byDate.get(agenda) ?? []).map((item) => (
                  <OperationCard key={item.id} item={item} iso={agenda} team={showTeam ? teams.get(item.team_id) : undefined} onOpen={setPicked} />
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
                    onClick={() => openWeek(iso)}
                  >
                    {isoParts(iso).day}
                  </button>
                </header>
                <div className="week-body">
                  {items.length === 0 && <p className="muted week-empty">Пусто</p>}
                  {items.map((item) => (
                    <OperationCard key={item.id} item={item} iso={iso} team={showTeam ? teams.get(item.team_id) : undefined} onOpen={setPicked} />
                  ))}
                </div>
              </section>
            );
          })}
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
              teamName={multi && teams.size > 1 ? teams.get(picked.team_id) : undefined}
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
  team,
  onOpen,
}: {
  item: Occurrence;
  iso: string;
  compact?: boolean;
  team?: string;
  onOpen: (item: Occurrence) => void;
}) {
  const tone = statusTone(item.status);
  if (item.planned) {
    // Плановый период ещё не открыт: только показать, без действий.
    return (
      <div
        className={`op-card tone-${tone} is-planned`}
        role="group"
        aria-label={`${item.title}${team ? `, ${team}` : ""}, план, ${formatMoney(item.amount, item.currency)}, ${longDue(iso)}`}
      >
        <span className="pill pill-neutral">План</span>
        <span className="op-meta">
          {formatMoney(item.amount, item.currency)}, до {shortDue(iso)}
        </span>
        <span className="op-title">{item.title}</span>
        {!compact && team && <span className="op-who op-team">{team}</span>}
        {!compact && item.responsible && <span className="op-who">{item.responsible.full_name}</span>}
      </div>
    );
  }
  return (
    <button
      type="button"
      className={`op-card tone-${tone}`}
      data-hint={HINTS.calOperation}
      onClick={() => onOpen(item)}
      aria-label={`${item.title}${team ? `, ${team}` : ""}, ${statusShort(item.status)}, ${formatMoney(item.amount, item.currency)}, ${longDue(iso)}`}
    >
      <span className={`pill pill-${tone}`}>{statusShort(item.status)}</span>
      <span className="op-meta">
        {formatMoney(item.amount, item.currency)}, до {shortDue(iso)}
      </span>
      <span className="op-title">{item.title}</span>
      {!compact && team && <span className="op-who op-team">{team}</span>}
      {!compact && item.responsible && <span className="op-who">{item.responsible.full_name}</span>}
    </button>
  );
}
