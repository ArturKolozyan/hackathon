import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ApiError, api, type Inbox, type Occurrence, type Summary } from "../api";
import { OccurrenceCard } from "../components/OccurrenceCard";
import { chipTone, formatMoney } from "../format";

export function InboxPage() {
  const [params, setParams] = useSearchParams();
  const mine = params.get("mine") === "1";
  const [inbox, setInbox] = useState<Inbox | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const query = mine ? "?mine=true" : "";
      const [nextInbox, nextSummary] = await Promise.all([
        api<Inbox>(`/api/v1/payment-occurrences/inbox${query}`),
        api<Summary>("/api/v1/payments/summary"),
      ]);
      setInbox(nextInbox);
      setSummary(nextSummary);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Инбокс не загрузился");
    }
  }, [mine]);

  useEffect(() => {
    void load();
  }, [load]);

  const totalOpen = inbox ? inbox.overdue.length + inbox.soon.length + inbox.rest.length : 0;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="kicker">Инбокс</p>
          <h1>Что сделать сейчас</h1>
        </div>
        <button
          type="button"
          className={mine ? "primary" : "ghost"}
          aria-pressed={mine}
          onClick={() => setParams(mine ? {} : { mine: "1" })}
        >
          {mine ? "Только мои" : "Вся команда"}
        </button>
      </div>
      {summary && (
        <>
          <div className="totals">
            {summary.by_currency.map((row) => {
              const chip = chipTone(row);
              const tone = chip.tone === "rest" ? "neutral" : chip.tone;
              const caption = chip.tone === "paid" ? "Закрыто" : "К оплате";
              return (
                <article key={row.currency} className="total">
                  <span className="code">
                    {caption} · {row.currency}
                  </span>
                  <strong className="money rule">{formatMoney(chip.amount, row.currency)}</strong>
                  <span className={`pill pill-${tone}`}>{chip.label}</span>
                </article>
              );
            })}
          </div>
          <p className="caption">
            Суммы по валютам, без пересчёта
            {mine ? ", по всей команде" : ""}. Скоро — в пределах {summary.soon_days} дней, включая день срока.
            {!mine && (
              <>
                {" "}
                {summary.counts.overdue} просрочено · {summary.counts.due_soon} скоро · {summary.counts.upcoming} впереди ·{" "}
                {summary.counts.paid} в истории
              </>
            )}
          </p>
        </>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!inbox && !error && <p className="muted">Загрузка…</p>}
      {inbox && totalOpen === 0 && <p className="panel empty">В очереди пусто. Либо всё закрыто, либо шаблонов ещё нет.</p>}
      {inbox && (
        <>
          <Group title="Просрочено" tone="overdue" items={inbox.overdue} today={inbox.today} onChanged={load} />
          <Group title="Скоро" tone="soon" items={inbox.soon} today={inbox.today} onChanged={load} />
          <Group title="Остальное" tone="rest" items={inbox.rest} today={inbox.today} onChanged={load} />
        </>
      )}
    </div>
  );
}

function Group({
  title,
  tone,
  items,
  today,
  onChanged,
}: {
  title: string;
  tone: string;
  items: Occurrence[];
  today: string;
  onChanged: () => void;
}) {
  if (items.length === 0) return null;
  return (
    <section className="group">
      <header>
        <h2>{title}</h2>
        <span className={`pill count pill-${tone === "rest" ? "neutral" : tone}`}>{items.length}</span>
      </header>
      <div className="cards">
        {items.map((item) => (
          <OccurrenceCard key={item.id} item={item} today={today} mode="inbox" onChanged={onChanged} />
        ))}
      </div>
    </section>
  );
}
