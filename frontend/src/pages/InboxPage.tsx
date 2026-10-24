import { useCallback, useEffect, useState } from "react";
import { CircleCheck, Inbox as InboxIcon } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError, api, type Inbox, type Occurrence, type Summary, type TeamTelegram, type TelegramSelf } from "../api";
import { canManage, useAuth } from "../auth";
import { OccurrenceCard } from "../components/OccurrenceCard";
import { PageControls } from "../components/PageControls";
import { EmptyState, ErrorState, LoadingBlock, Segmented } from "../components/ui";
import { chipTone, daysWord, formatMoney } from "../format";
import { HINTS } from "../hints";
import { useFresh } from "../fresh";
import { useTelegramLink } from "../useTelegramLink";

export function InboxPage() {
  const { user } = useAuth();
  const manage = canManage(user);
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const mine = params.get("mine") === "1";
  const fresh = useFresh();
  const [inbox, setInbox] = useState<Inbox | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [selfTg, setSelfTg] = useState<TelegramSelf | null>(null);
  const [teamTg, setTeamTg] = useState<TeamTelegram | null>(null);
  const [error, setError] = useState<string | null>(null);
  const binding = useTelegramLink(() => setSelfTg((self) => (self ? { ...self, linked: true } : self)));

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
  }, [load, fresh]);

  useEffect(() => {
    api<TelegramSelf>("/api/v1/me/telegram")
      .then(setSelfTg)
      .catch(() => setSelfTg(null));
    if (!manage) return;
    api<TeamTelegram>("/api/v1/telegram/status")
      .then(setTeamTg)
      .catch(() => setTeamTg(null));
  }, [manage, fresh]);

  const totalOpen = inbox ? inbox.overdue.length + inbox.soon.length + inbox.rest.length : 0;
  const paidBefore = (summary?.counts.paid ?? 0) > 0;

  return (
    <div className="page">
      <PageControls
        center={
        <Segmented
          label="Чья очередь"
          value={mine ? "mine" : "all"}
          options={[
            { value: "all", label: "Весь отдел", hint: HINTS.scopeAll },
            { value: "mine", label: "Только мои", hint: HINTS.scopeMine },
          ]}
          onChange={(value) => setParams(value === "mine" ? { mine: "1" } : {})}
        />
        }
      />
      {summary && (
        <>
          <div className="totals">
            {summary.by_currency.map((row) => {
              const chip = chipTone(row);
              const open = Number(row.open_amount);
              const closed = !(open > 0);
              const slice = chip.tone === "overdue" ? "просрочено" : chip.tone === "soon" ? "скоро" : null;
              const differs = !closed && slice !== null && Number(chip.amount) !== open;
              return (
                <article key={row.currency} className="total">
                  <span className="code">
                    {closed ? "Закрыто" : "К оплате"}
                    <span className="code-cur">{row.currency}</span>
                  </span>
                  <strong className="money rule">{formatMoney(closed ? row.paid_amount : row.open_amount, row.currency)}</strong>
                  {!closed && slice && (
                    <span className={`slice-note tone-${chip.tone}`}>
                      {differs ? `из них ${slice} ${formatMoney(chip.amount, row.currency)}` : `всё ${slice}`}
                    </span>
                  )}
                </article>
              );
            })}
          </div>
          <p className="caption">
            Итоги {mine ? "всего отдела" : "отдела"} по валютам без пересчёта, «скоро» — в ближайшие {summary.soon_days} {daysWord(summary.soon_days)}.
          </p>
        </>
      )}
      {selfTg && !selfTg.linked && selfTg.bot_ready && (
        <aside className="panel hint">
          <div className="hint-text">
            <strong>Подключите Telegram</strong>
            <span className="desc">
              {binding.url
                ? "Откройте бота и нажмите «Старт». Карточка исчезнет сама, как только привязка пройдёт."
                : "Напоминания будут приходить вам в личные сообщения, а «Оплачено» в чате отдела запишется на вас."}
              {manage && teamTg && teamTg.status !== "connected" && !binding.url && " Чат отдела подключается в настройках."}
            </span>
            {binding.error && (
              <span className="field-error" role="alert">
                {binding.error}
              </span>
            )}
          </div>
          <div className="row-actions">
            {binding.url ? (
              <a className="primary" href={binding.url} target="_blank" rel="noreferrer">
                Открыть бота
              </a>
            ) : (
              <button type="button" className="primary" disabled={binding.busy} data-hint={HINTS.tgLink} onClick={() => void binding.request()}>
                Привязать
              </button>
            )}
            {manage && teamTg && teamTg.status !== "connected" && (
              <Link className="ghost" to="/settings#team-chat" data-hint={HINTS.toNotifications}>
                Чат отдела
              </Link>
            )}
          </div>
        </aside>
      )}
      {error && <ErrorState message={error} onRetry={() => void load()} />}
      {!inbox && !error && <LoadingBlock label="Загружаем очередь…" />}
      {inbox && totalOpen === 0 && (
        <EmptyState
          icon={mine || paidBefore ? CircleCheck : InboxIcon}
          title={mine ? "На вас сейчас ничего нет" : paidBefore ? "Всё оплачено" : "Платежей пока нет"}
          action={
            mine ? (
              <button type="button" className="ghost" data-hint={HINTS.scopeAll} onClick={() => setParams({})}>
                Показать весь отдел
              </button>
            ) : paidBefore ? (
              <Link className="ghost" to="/history" data-hint={HINTS.openHistory}>
                Открыть историю
              </Link>
            ) : manage ? (
              <button type="button" className="primary" data-hint={HINTS.templateNew} onClick={() => navigate("/templates/new")}>
                Создать шаблон
              </button>
            ) : undefined
          }
        >
          {mine
            ? "Открытых платежей, где вы ответственный, нет. Остальные платежи отдела видны во вкладке «Весь отдел»."
            : paidBefore
              ? "Открытых платежей нет. Оплаченные хранятся в истории."
              : manage
                ? "Добавьте регулярный платёж, и его периоды появятся в этой очереди."
                : "Когда администратор отдела добавит платежи, они появятся здесь."}
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
