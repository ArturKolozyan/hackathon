import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError, api, type Inbox, type Occurrence, type Summary, type TeamTelegram, type TelegramSelf } from "../api";
import { useAuth } from "../auth";
import { OccurrenceCard } from "../components/OccurrenceCard";
import { EmptyState, ErrorState, LoadingBlock, Segmented } from "../components/ui";
import { chipTone, formatMoney } from "../format";

export function InboxPage() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const mine = params.get("mine") === "1";
  const [asOf, setAsOf] = useState("");
  const [inbox, setInbox] = useState<Inbox | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [selfTg, setSelfTg] = useState<TelegramSelf | null>(null);
  const [teamTg, setTeamTg] = useState<TeamTelegram | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const query = mine ? "?mine=true" : "";
      const summaryQuery = asOf ? `?as_of=${asOf}` : "";
      const [nextInbox, nextSummary] = await Promise.all([
        api<Inbox>(`/api/v1/payment-occurrences/inbox${query}`),
        api<Summary>(`/api/v1/payments/summary${summaryQuery}`),
      ]);
      setInbox(nextInbox);
      setSummary(nextSummary);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Инбокс не загрузился");
    }
  }, [mine, asOf]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    api<TelegramSelf>("/api/v1/me/telegram")
      .then(setSelfTg)
      .catch(() => setSelfTg(null));
    if (user?.role !== "admin") return;
    api<TeamTelegram>("/api/v1/telegram/status")
      .then(setTeamTg)
      .catch(() => setTeamTg(null));
  }, [user?.role]);

  const totalOpen = inbox ? inbox.overdue.length + inbox.soon.length + inbox.rest.length : 0;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="kicker">Инбокс</p>
          <h1>Что сделать сейчас</h1>
        </div>
        <Segmented
          label="Чья очередь"
          value={mine ? "mine" : "all"}
          options={[
            { value: "all", label: "Вся команда" },
            { value: "mine", label: "Только мои" },
          ]}
          onChange={(value) => setParams(value === "mine" ? { mine: "1" } : {})}
        />
      </div>
      {summary && (
        <>
          <div className="head-actions totals-tools">
            <label className="as-of">
              Итоги на дату
              <input type="date" value={asOf} onChange={(event) => setAsOf(event.target.value)} />
            </label>
            {asOf && (
              <button type="button" className="ghost" onClick={() => setAsOf("")}>
                Сбросить дату
              </button>
            )}
          </div>
          <div className="totals">
            {summary.by_currency.map((row) => {
              const chip = chipTone(row);
              const open = Number(row.open_amount);
              const closed = !(open > 0);
              const tone = closed ? "paid" : chip.tone === "rest" ? "neutral" : chip.tone;
              const slice =
                chip.tone === "overdue" ? "просрочено" : chip.tone === "soon" ? "скоро" : chip.tone === "paid" ? "закрыто" : "остальное";
              const differs = !closed && Number(chip.amount) !== open;
              return (
                <article key={row.currency} className="total">
                  <span className="code">
                    {closed ? "Закрыто" : "К оплате"} · {row.currency}
                  </span>
                  <strong className="money rule">{formatMoney(closed ? row.paid_amount : row.open_amount, row.currency)}</strong>
                  <span className={`pill pill-${tone}`}>{closed ? "закрыто" : slice}</span>
                  {differs && (
                    <span className="muted slice-note">
                      из них {slice} {formatMoney(chip.amount, row.currency)}
                    </span>
                  )}
                </article>
              );
            })}
          </div>
          <p className="caption">
            Суммы по валютам, без пересчёта
            {mine ? ", по всей команде" : ""}. Скоро — в пределах {summary.soon_days} дней, включая день срока.
            {summary.as_of
              ? ` Итоги на конец ${summary.as_of}: оплата позже этой даты ещё не засчитана. Очередь ниже — на сегодня.`
              : ""}
            {!mine && (
              <>
                {" "}
                {summary.counts.overdue} просрочено · {summary.counts.due_soon} скоро · {summary.counts.upcoming} ещё не скоро ·{" "}
                {summary.counts.paid} в истории
              </>
            )}
          </p>
        </>
      )}
      {user?.role === "admin" && teamTg && teamTg.status !== "connected" && (
        <aside className="panel hint">
          <p>Подключи Telegram, чтобы получать напоминания.</p>
          <Link className="outline" to="/settings">
            Подключить
          </Link>
        </aside>
      )}
      {selfTg && !selfTg.linked && (
        <aside className="panel hint">
          <p>Привяжи Telegram, чтобы кнопка «Оплачено» была твоей.</p>
          <Link className="outline" to="/settings">
            Привязать
          </Link>
        </aside>
      )}
      {error && <ErrorState message={error} onRetry={() => void load()} />}
      {!inbox && !error && <LoadingBlock label="Загружаем очередь…" />}
      {inbox && totalOpen === 0 && (
        <EmptyState
          title={mine ? "У вас в очереди пусто" : "В очереди пусто"}
          action={
            mine ? (
              <button type="button" className="ghost" onClick={() => setParams({})}>
                Показать всю команду
              </button>
            ) : undefined
          }
        >
          {mine
            ? "Чужие платежи скрыты фильтром. Снимите его или закройте свои, когда появятся."
            : "Либо всё закрыто, либо шаблонов ещё нет. История хранит то, что уже оплатили."}
        </EmptyState>
      )}
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
