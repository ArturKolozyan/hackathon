import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type CalendarMonth, type Occurrence } from "../api";
import { OccurrenceCard } from "../components/OccurrenceCard";
import { formatMoney, monthTitle, shiftMonth, statusTone } from "../format";

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

  const byDate = new Map((data?.days ?? []).map((day) => [day.date, day.items]));
  const cells = data ? cellsOf(data.year, data.month) : [];

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
              setPicked(null);
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
              setPicked(null);
              setCursor(shiftMonth(cursor.year, cursor.month, 1));
            }}
          >
            Дальше
          </button>
        </div>
      </div>
      <p className="caption">Периоды по дате срока. Цвет тот же, что в инбоксе: просрочено, скоро, впереди, оплачено.</p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!data && !error && <p className="muted">Загрузка…</p>}
      {data && (
        <>
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
              return (
                <div key={iso} className={iso === data.today ? "cal-day today" : "cal-day"}>
                  <span className="cal-num">{day}</span>
                  {items.slice(0, 3).map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className={`cal-chip tone-${statusTone(item.status)}`}
                      onClick={() => setPicked(item)}
                    >
                      {item.title}
                      <span className="cal-money">{formatMoney(item.amount, item.currency)}</span>
                    </button>
                  ))}
                  {items.length > 3 && <span className="cal-more">+{items.length - 3}</span>}
                </div>
              );
            })}
          </div>
        </>
      )}
      {picked && data && (
        <div className="modal-back" role="presentation" onClick={() => setPicked(null)}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="cal-dialog-title"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="modal-head">
              <h2 id="cal-dialog-title">Период</h2>
              <button type="button" className="ghost" onClick={() => setPicked(null)}>
                Закрыть
              </button>
            </div>
            <OccurrenceCard
              item={picked}
              today={data.today}
              mode={picked.status === "paid" ? "history" : "inbox"}
              onChanged={() => void load(picked.id)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
