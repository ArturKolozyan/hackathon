import { useCallback, useEffect, useState } from "react";
import { CircleCheck, Inbox as InboxIcon, X } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError, api, type Inbox, type Occurrence, type Summary, type TeamTelegram, type TelegramSelf } from "../api";
import { canManage, useAuth } from "../auth";
import { DateField } from "../components/fields";
import { OccurrenceCard } from "../components/OccurrenceCard";
import { PageControls } from "../components/PageControls";
import { EmptyState, ErrorState, LoadingBlock, Segmented } from "../components/ui";
import { chipTone, formatMoney } from "../format";
import { HINTS } from "../hints";
import { useTelegramLink } from "../useTelegramLink";

export function InboxPage() {
  const { user } = useAuth();
  const manage = canManage(user);
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const mine = params.get("mine") === "1";
  const [asOf, setAsOf] = useState("");
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
    if (!manage) return;
    api<TeamTelegram>("/api/v1/telegram/status")
      .then(setTeamTg)
      .catch(() => setTeamTg(null));
  }, [manage]);

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
        left={
        <div className="tb-group tb-date">
          {asOf && <span className="tb-label">Итоги на</span>}
          <DateField value={asOf} onChange={setAsOf} ariaLabel="Итоги на дату" placeholder="Итоги на дату" hint={HINTS.asOfDate} />
          {asOf && (
            <button type="button" className="icon-btn" aria-label="Сбросить дату" data-hint={HINTS.asOfReset} onClick={() => setAsOf("")}>
              <X size={16} strokeWidth={1.75} aria-hidden />
            </button>
          )}
        </div>
        }
      />
      {summary && (
        <>
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
                    {closed ? "Закрыто" : "К оплате"}
                    <span className="code-cur">{row.currency}</span>
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
            {mine ? ", по всему отделу" : ""}. Скоро — в пределах {summary.soon_days} дней, включая день срока.
            {summary.as_of
              ? ` Итоги на конец ${summary.as_of}: оплата позже этой даты ещё не засчитана. Очередь ниже — на сегодня.`
              : ""}
            {!mine && (
              <>
                {" "}
                Просрочено: {summary.counts.overdue}, скоро: {summary.counts.due_soon}, позже: {summary.counts.upcoming}, в
                истории: {summary.counts.paid}.
              </>
            )}
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
              <Link className="ghost" to="/history">
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
