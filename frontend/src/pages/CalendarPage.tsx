import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type CalendarMonth, type Occurrence } from "../api";
import { OccurrenceCard } from "../components/OccurrenceCard";
import { EmptyState, ErrorState, LoadingBlock } from "../components/ui";
import { formatMoney, longDue, monthTitle, shiftMonth, statusTone } from "../format";

const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];

function cellsOf(year: number, month: number): Array<string | null> {
  const first = new Date(Date.UTC(year, month - 1, 1));
  const offset = (first.getUTCDay() + 6) % 7;
  const days = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const cells: Array<string | null> = Array.from({ length: offset }, () => null);
  for (let day = 1; day <= days; day += 1) {
    cells.push(`${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`);
  }
  return cells;
}

export function CalendarPage() {
  const [cursor, setCursor] = useState<{ year: number; month: number } | null>(null);
  const [data, setData] = useState<CalendarMonth | null>(null);
  const [picked, setPicked] = useState<Occurrence | null>(null);
  const [dayIso, setDayIso] = useState<string | null>(null);
  const [narrow, setNarrow] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (keepId?: string) => {
    setError(null);
    try {
      const query = cursor ? `?year=${cursor.year}&month=${cursor.month}` : "";
      const next = await api<CalendarMonth>(`/api/v1/payments/calendar${query}`);
      if (!cursor) setCursor({ year: next.year, month: next.month });
      setData(next);
      setPicked((current) => {
        const id = keepId ?? current?.id;
        if (!id) return null;
        return next.days.flatMap((day) => day.items).find((item) => item.id === id) ?? null;
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Календарь не загрузился");
    }
  }, [cursor]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const query = window.matchMedia("(max-width: 640px)");
    const apply = () => setNarrow(query.matches);
    apply();
    query.addEventListener("change", apply);
    return () => query.removeEventListener("change", apply);
  }, []);

  useEffect(() => {
    if (!picked && !dayIso) return;
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setPicked(null);
      setDayIso(null);
    }
    document.addEventListener("keydown", onKey);
    document.getElementById("cal-detail-title")?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [picked, dayIso]);

  const byDate = new Map((data?.days ?? []).map((day) => [day.date, day.items]));
  const cells = data ? cellsOf(data.year, data.month) : [];
  const dayItems = dayIso ? byDate.get(dayIso) ?? [] : [];
  const monthHasItems = (data?.days ?? []).some((day) => day.items.length > 0);

  function openItem(item: Occurrence) {
    setDayIso(null);
    setPicked(item);
  }

  function openDay(iso: string) {
    setPicked(null);
    setDayIso(iso);
  }

  function closeDetail() {
    setPicked(null);
    setDayIso(null);
  }

  return (
    <div className="page page-wide">
      <div className="page-head">
        <div>
          <p className="kicker">Календарь</p>
          <h1>{cursor ? monthTitle(cursor.year, cursor.month) : "Оплаты"}</h1>
        </div>
        <div className="head-actions">
          <button
            type="button"
            className="ghost"
            disabled={!cursor}
            onClick={() => {
              if (!cursor) return;
              closeDetail();
              setCursor(shiftMonth(cursor.year, cursor.month, -1));
            }}
          >
            Назад
          </button>
          <button
            type="button"
            className="ghost"
            disabled={!cursor}
            onClick={() => {
              if (!cursor) return;
              closeDetail();
              setCursor(shiftMonth(cursor.year, cursor.month, 1));
            }}
          >
            Дальше
          </button>
        </div>
      </div>
      <p className="caption">Периоды по дате срока. Цвет тот же, что в инбоксе: просрочено, скоро, остальное, оплачено.</p>
      {error && <ErrorState message={error} onRetry={() => void load(picked?.id)} />}
      {!data && !error && <LoadingBlock label="Загружаем календарь…" />}
      {data && !monthHasItems && !error && (
        <EmptyState title="В этом месяце пусто">Нет периодов с таким сроком. Листайте месяц или заведите шаблон.</EmptyState>
      )}
      {data && monthHasItems && (
        <>
          <div className={narrow ? "cal-mobile" : "cal-desktop"}>
            <div className="cal-head">
              {WEEKDAYS.map((name) => (
                <span key={name} className="cal-dow">
                  {name}
                </span>
              ))}
            </div>
            <div className="cal-grid">
              {cells.map((iso, index) => {
                if (!iso) return <div key={`pad-${index}`} className="cal-pad" />;
                const items = byDate.get(iso) ?? [];
                const day = Number(iso.slice(-2));
                const today = iso === data.today;
                if (narrow) {
                  return (
                    <button
                      key={iso}
                      type="button"
                      className={today ? "cal-day-btn today" : "cal-day-btn"}
                      aria-pressed={dayIso === iso}
                      aria-label={`${longDue(iso)}, платежей: ${items.length}`}
                      onClick={() => openDay(iso)}
                    >
                      <span className="cal-num">{day}</span>
                      {items.length > 0 && (
                        <span className="cal-dots" aria-hidden="true">
                          {items.slice(0, 3).map((item) => (
                            <span key={item.id} className={`cal-dot tone-${statusTone(item.status)}`} />
                          ))}
                        </span>
                      )}
                    </button>
                  );
                }
                return (
                  <div key={iso} className={today ? "cal-day today" : "cal-day"}>
                    <span className="cal-num">{day}</span>
                    {items.slice(0, 3).map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        className={`cal-chip tone-${statusTone(item.status)}`}
                        aria-label={`${item.title}, ${formatMoney(item.amount, item.currency)}, ${longDue(iso)}`}
                        onClick={() => openItem(item)}
                      >
                        {item.title}
                        <span className="cal-money">{formatMoney(item.amount, item.currency)}</span>
                      </button>
                    ))}
                    {items.length > 3 && (
                      <button type="button" className="cal-more" onClick={() => openDay(iso)}>
                        +{items.length - 3}, все за день
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
          {(picked || dayIso) && (
            <section className="cal-detail" aria-labelledby="cal-detail-title">
              <div className="row-between">
                <h2 id="cal-detail-title" tabIndex={-1}>
                  {picked ? picked.title : dayIso ? longDue(dayIso) : "Период"}
                </h2>
                <button type="button" className="ghost" onClick={closeDetail}>
                  Закрыть
                </button>
              </div>
              {picked && (
                <OccurrenceCard
                  item={picked}
                  today={data.today}
                  mode={picked.status === "paid" ? "history" : "inbox"}
                  onChanged={() => void load(picked.id)}
                />
              )}
              {!picked && dayIso && dayItems.length === 0 && <p className="muted">В этот день платежей нет.</p>}
              {!picked && dayIso && dayItems.length > 0 && (
                <div className="cards">
                  {dayItems.map((item) => (
                    <OccurrenceCard
                      key={item.id}
                      item={item}
                      today={data.today}
                      mode={item.status === "paid" ? "history" : "inbox"}
                      onChanged={() => void load(item.id)}
                    />
                  ))}
                </div>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
}
