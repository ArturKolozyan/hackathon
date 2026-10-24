import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BarChart3, ChevronLeft, ChevronRight, Paperclip, SearchX, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { ApiError, api, type Occurrence, type Stats, type StatsMonth, type StatsOperation, type Summary } from "../api";
import { useAuth } from "../auth";
import { DateField, MultiSelectField, SelectField } from "../components/fields";
import { OccurrenceCard } from "../components/OccurrenceCard";
import { PageControls } from "../components/PageControls";
import { PeriodNav } from "../components/PeriodNav";
import { EmptyState, ErrorState, LoadingBlock, Segmented } from "../components/ui";
import { capitalMonth, formatMoney, shiftMonthKey, shortDue, statusShort } from "../format";
import { HINTS } from "../hints";
import { useFresh } from "../fresh";

type Period = "open" | "month" | "range";
type Bucket = { currency: string; amount: string; count: number };

const MONTH_SHORT = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"];
const TONE: Record<StatsOperation["status"], string> = {
  overdue: "overdue",
  due_soon: "soon",
  upcoming: "neutral",
  paid: "paid",
};

function shortMonth(key: string): string {
  const [year, month] = key.split("-").map(Number);
  return `${MONTH_SHORT[month - 1]} ${year}`;
}

function currentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function monthName(key: string): string {
  const [year, month] = key.split("-").map(Number);
  return capitalMonth(year, month);
}

export function StatsPage() {
  const { switchTeam } = useAuth();
  const navigate = useNavigate();
  const [period, setPeriod] = useState<Period>("open");
  const [month, setMonth] = useState(currentMonth);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [currency, setCurrency] = useState("");
  const [teams, setTeams] = useState<string[]>([]);
  const [page, setPage] = useState(1);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<Occurrence | null>(null);
  const [opening, setOpening] = useState<string | null>(null);
  const listRef = useRef<HTMLElement>(null);
  const detailRef = useRef<HTMLElement>(null);
  const fresh = useFresh();

  const filterKey = JSON.stringify([teams, currency, period, month, dateFrom, dateTo]);
  useEffect(() => setPage(1), [filterKey]);

  const load = useCallback(async () => {
    const query = new URLSearchParams();
    for (const id of teams) query.append("team_id", id);
    if (currency) query.set("currency", currency);
    if (period === "month" && month) query.set("month", month);
    if (period === "range" && dateFrom && dateTo) {
      query.set("date_from", dateFrom);
      query.set("date_to", dateTo);
    }
    if (page > 1) query.set("page", String(page));
    const suffix = query.toString();
    setStats(await api<Stats>(`/api/v1/stats${suffix ? `?${suffix}` : ""}`));
  }, [teams, currency, period, month, dateFrom, dateTo, page]);

  useEffect(() => {
    setError(null);
    load().catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Статистика не загрузилась"));
  }, [load, fresh]);

  useEffect(() => {
    if (!picked) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setPicked(null);
    }
    document.addEventListener("keydown", onKey);
    detailRef.current?.querySelector<HTMLElement>("h2")?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [picked?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function openTeam(teamId: string) {
    await switchTeam(teamId);
    navigate("/");
  }

  async function fetchOccurrence(id: string, teamId: string): Promise<Occurrence> {
    return api<Occurrence>(`/api/v1/payment-occurrences/${id}`, { headers: { "X-Team-Id": teamId, "X-Team-Once": "1" } });
  }

  async function openOperation(row: StatsOperation) {
    if (row.planned) return;
    setOpening(row.occurrence_id);
    try {
      setPicked(await fetchOccurrence(row.occurrence_id, row.team_id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Платёж не открылся");
    } finally {
      setOpening(null);
    }
  }

  async function changed(item: Occurrence) {
    try {
      setPicked(await fetchOccurrence(item.id, item.team_id));
    } catch {
      setPicked(null);
    }
    await load().catch(() => undefined);
  }

  function turnPage(next: number) {
    setPage(next);
    listRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  }

  const departments = stats?.departments ?? [];
  const filtered = teams.length > 0 || Boolean(currency);
  const operations = stats?.operations;

  function resetFilters() {
    setTeams([]);
    setCurrency("");
  }

  const empty =
    stats && stats.to_pay.length === 0 && stats.paid.length === 0 && (operations?.total ?? 0) === 0 && stats.monthly.length === 0;

  const periodCaption =
    period === "month"
      ? monthName(month)
      : period === "range" && dateFrom && dateTo
        ? `${shortDue(dateFrom)} – ${shortDue(dateTo)}`
        : stats
          ? `открытые сроки, оплаты за ${monthName(stats.paid_from.slice(0, 7)).toLowerCase()}`
          : "";

  return (
    <div className="page">
      <PageControls
        center={
          <Segmented
            label="Период"
            value={period}
            options={[
              { value: "open", label: "Открытые", hint: HINTS.statsOpen },
              { value: "month", label: "Месяц", hint: HINTS.statsMonth },
              { value: "range", label: "Диапазон", hint: HINTS.statsRange },
            ]}
            onChange={setPeriod}
          />
        }
        left={
          period === "month" ? (
            <PeriodNav
              label="Месяц статистики"
              prevLabel="Предыдущий месяц"
              nextLabel="Следующий месяц"
              prevHint={HINTS.monthPrev}
              nextHint={HINTS.monthNext}
              onPrev={() => setMonth((key) => shiftMonthKey(key || currentMonth(), -1))}
              onNext={() => setMonth((key) => shiftMonthKey(key || currentMonth(), 1))}
              width="9.5rem"
            >
              <DateField mode="month" value={month} onChange={setMonth} ariaLabel="Месяц" />
            </PeriodNav>
          ) : undefined
        }
      />
      <div className="filter-bar filter-row" role="group" aria-label="Фильтры статистики">
        {period === "range" && (
          <div className="date-range" role="group" aria-label="Диапазон дат">
            <span className="date-range-label">с</span>
            <DateField value={dateFrom} onChange={setDateFrom} ariaLabel="Дата с" placeholder="дд.мм.гггг" max={dateTo || undefined} />
            <span className="date-range-label">по</span>
            <DateField value={dateTo} onChange={setDateTo} ariaLabel="Дата по" placeholder="дд.мм.гггг" min={dateFrom || undefined} />
          </div>
        )}
        {departments.length > 1 && (
          <MultiSelectField
            label="Отделы"
            value={teams}
            onChange={setTeams}
            options={departments.map((row) => ({ value: row.id, label: row.name }))}
          />
        )}
        <SelectField
          ariaLabel="Валюта"
          value={currency}
          onChange={setCurrency}
          options={[
            { value: "", label: "Все валюты" },
            { value: "RUB", label: "RUB" },
            { value: "USD", label: "USD" },
            { value: "EUR", label: "EUR" },
          ]}
        />
        {filtered && (
          <button type="button" className="ghost" data-hint={HINTS.filtersReset} onClick={resetFilters}>
            Сбросить
          </button>
        )}
      </div>
      {period === "range" && (!dateFrom || !dateTo) && (
        <p className="caption">Выберите обе даты: пока показаны открытые платежи и оплаты этого месяца.</p>
      )}
      {error && <ErrorState message={error} onRetry={() => void load().catch(() => undefined)} />}
      {!stats && !error && <LoadingBlock label="Загружаем статистику…" />}
      {empty && (
        <EmptyState
          icon={filtered || period !== "open" ? SearchX : BarChart3}
          title={filtered || period !== "open" ? "Ничего не нашлось" : "Статистики пока нет"}
          action={
            filtered ? (
              <button type="button" className="ghost" data-hint={HINTS.filtersReset} onClick={resetFilters}>
                Сбросить фильтры
              </button>
            ) : undefined
          }
        >
          {filtered || period !== "open"
            ? "За этот период и с этими фильтрами платежей нет."
            : "Цифры появятся, когда в отделах будут регулярные платежи."}
        </EmptyState>
      )}
      {stats && !empty && (
        <>
          <div className="kpi-grid">
            <Kpi title="К оплате" rows={stats.to_pay} />
            <Kpi title="Просрочено" rows={stats.overdue} tone="overdue" />
            <Kpi title="Оплачено" rows={stats.paid} tone="paid" />
            <article className="panel total kpi">
              <span className="code">Вовремя</span>
              <strong className="money">
                {stats.paid_count > 0 ? `${Math.round((stats.paid_on_time / stats.paid_count) * 100)}%` : "—"}
              </strong>
              <span className="kpi-sub">
                {stats.paid_count > 0 ? `${stats.paid_on_time} из ${stats.paid_count} оплат в срок` : "оплат за период нет"}
              </span>
            </article>
          </div>
          <p className="caption stats-caption">{periodCaption}</p>
          <TotalsOn fresh={fresh} />
          {stats.monthly.length > 0 && <MonthChart rows={stats.monthly} today={stats.today} preferred={currency} />}
          {stats.by_team.length > 1 && (
            <section className="group">
              <header>
                <h2>По отделам</h2>
              </header>
              <div className="panel dept-table" role="table" aria-label="Суммы по отделам">
                <div className="dept-row dept-head" role="row">
                  <span role="columnheader">Отдел</span>
                  <span role="columnheader">К оплате</span>
                  <span role="columnheader">Просрочено</span>
                  <span role="columnheader">Оплачено</span>
                  <span role="columnheader" className="sr-only">
                    Действие
                  </span>
                </div>
                {stats.by_team.map((row) => (
                  <div key={row.team_id} className="dept-row" role="row">
                    <strong role="cell" className="dept-name">
                      {row.team_name}
                    </strong>
                    <MoneyCell label="К оплате" rows={row.to_pay} />
                    <MoneyCell label="Просрочено" rows={row.overdue} tone="overdue" />
                    <MoneyCell label="Оплачено" rows={row.paid} />
                    <span role="cell" className="dept-action">
                      <button type="button" className="ghost" data-hint={HINTS.statsOpenTeam} onClick={() => void openTeam(row.team_id)}>
                        В инбокс
                      </button>
                    </span>
                  </div>
                ))}
              </div>
            </section>
          )}
          <section className="group" ref={listRef}>
            <header className="ops-head">
              <h2>Операции</h2>
              {operations && operations.total > operations.page_size && (
                <Pager
                  page={operations.page}
                  size={operations.page_size}
                  total={operations.total}
                  onTurn={turnPage}
                />
              )}
            </header>
            {!operations || operations.items.length === 0 ? (
              <EmptyState compact icon={SearchX} title="Операций нет">
                За этот период и с этими фильтрами платежей нет.
              </EmptyState>
            ) : (
              <>
                <ul className="ops-list">
                  {operations.items.map((row) => (
                    <li key={row.occurrence_id}>
                      <OperationRow
                        row={row}
                        showTeam={departments.length > 1}
                        busy={opening === row.occurrence_id}
                        onOpen={() => void openOperation(row)}
                      />
                    </li>
                  ))}
                </ul>
                {operations.total > operations.page_size && (
                  <div className="ops-foot">
                    <Pager page={operations.page} size={operations.page_size} total={operations.total} onTurn={turnPage} />
                  </div>
                )}
              </>
            )}
          </section>
        </>
      )}
      {picked && stats && (
        <div className="modal-back" onMouseDown={(event) => event.target === event.currentTarget && setPicked(null)}>
          <section className="modal cal-detail" ref={detailRef} role="dialog" aria-modal="true" aria-labelledby="stats-detail-title">
            <div className="modal-head">
              <h2 id="stats-detail-title" tabIndex={-1}>
                {picked.title}
              </h2>
              <button type="button" className="icon-btn" aria-label="Закрыть" data-hint={HINTS.close} onClick={() => setPicked(null)}>
                <X size={18} strokeWidth={1.75} aria-hidden />
              </button>
            </div>
            <OccurrenceCard
              key={picked.id}
              item={picked}
              today={stats.today}
              mode={picked.status === "paid" ? "history" : "inbox"}
              teamName={departments.length > 1 ? departments.find((row) => row.id === picked.team_id)?.name : undefined}
              onChanged={() => void changed(picked)}
            />
          </section>
        </div>
      )}
    </div>
  );
}

function Kpi({ title, rows, tone }: { title: string; rows: Bucket[]; tone?: "overdue" | "paid" }) {
  const count = rows.reduce((sum, row) => sum + row.count, 0);
  return (
    <article className={tone ? `panel total kpi kpi-${tone}` : "panel total kpi"}>
      <span className="code">{title}</span>
      {rows.length === 0 ? (
        <strong className="money">—</strong>
      ) : (
        rows.map((row) => (
          <strong key={row.currency} className="money">
            {formatMoney(row.amount, row.currency)}
          </strong>
        ))
      )}
      <span className="kpi-sub">{count > 0 ? plural(count, "платёж", "платежа", "платежей") : "нет платежей"}</span>
    </article>
  );
}

function plural(count: number, one: string, few: string, many: string): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  const word = mod10 === 1 && mod100 !== 11 ? one : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14) ? few : many;
  return `${count} ${word}`;
}

function MoneyCell({ label, rows, tone }: { label: string; rows: Bucket[]; tone?: "overdue" }) {
  return (
    <span role="cell" className={tone && rows.length > 0 ? `dept-cell is-${tone}` : "dept-cell"}>
      <span className="dept-cell-label">{label}</span>
      {rows.length === 0 ? (
        <span className="muted">—</span>
      ) : (
        <span className="dept-sums">
          {rows.map((row) => (
            <span key={row.currency} className="money">
              {formatMoney(row.amount, row.currency)}
            </span>
          ))}
        </span>
      )}
    </span>
  );
}

function Pager({ page, size, total, onTurn }: { page: number; size: number; total: number; onTurn: (page: number) => void }) {
  const from = (page - 1) * size + 1;
  const to = Math.min(total, page * size);
  return (
    <div className="tb-group cal-nav ops-pager">
      <span className="tb-label">
        {from}–{to} из {total}
      </span>
      <button type="button" className="icon-btn" aria-label="Предыдущие" data-hint={HINTS.statsPagePrev} disabled={page <= 1} onClick={() => onTurn(page - 1)}>
        <ChevronLeft size={18} strokeWidth={1.75} aria-hidden />
      </button>
      <button type="button" className="icon-btn" aria-label="Следующие" data-hint={HINTS.statsPageNext} disabled={to >= total} onClick={() => onTurn(page + 1)}>
        <ChevronRight size={18} strokeWidth={1.75} aria-hidden />
      </button>
    </div>
  );
}

function OperationRow({
  row,
  showTeam,
  busy,
  onOpen,
}: {
  row: StatsOperation;
  showTeam: boolean;
  busy: boolean;
  onOpen: () => void;
}) {
  const paid = row.status === "paid";
  const amount = paid && row.paid_amount ? row.paid_amount : row.amount;
  const when = paid && row.paid_on ? `оплачено ${shortDue(row.paid_on)}` : `до ${shortDue(row.due_date)}`;
  const late = paid && row.lateness_days !== null && row.lateness_days > 0 ? `позже на ${plural(row.lateness_days, "день", "дня", "дней")}` : null;
  const meta = [showTeam ? row.team_name : null, row.period_label, row.responsible?.full_name ?? null].filter(Boolean);
  const body = (
    <>
      <span className="op-row-main">
        <span className="op-row-title">
          {row.title}
          {row.has_receipt && <Paperclip size={14} strokeWidth={1.75} aria-label="есть чек" className="op-row-clip" />}
        </span>
        <span className="op-row-meta">
          {meta.map((part) => (
            <span key={part}>{part}</span>
          ))}
        </span>
      </span>
      <span className="op-row-when">
        <span className={`pill pill-${TONE[row.status]}`}>{statusShort(row.status)}</span>
        <span className="op-row-date">
          {when}
          {late && <span className="op-row-late">{late}</span>}
        </span>
      </span>
      <strong className="money op-row-sum">{formatMoney(amount, row.currency)}</strong>
    </>
  );
  const label = `${row.title}, ${row.planned ? "план" : statusShort(row.status)}, ${formatMoney(amount, row.currency)}, ${when}`;
  if (row.planned) {
    // Плановый период ещё не создан: строка только для обзора.
    return (
      <div className="op-row is-planned" role="group" aria-label={label}>
        {body}
      </div>
    );
  }
  return (
    <button type="button" className="op-row" data-hint={HINTS.statsOperation} aria-busy={busy} aria-label={label} onClick={onOpen}>
      {body}
    </button>
  );
}

/** Итоги текущего отдела на конец выбранной даты: что к оплате, что просрочено, что оплачено к этому дню. */
function TotalsOn({ fresh }: { fresh: number }) {
  const [asOf, setAsOf] = useState("");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    setFailed(false);
    api<Summary>(`/api/v1/payments/summary${asOf ? `?as_of=${asOf}` : ""}`)
      .then((body) => alive && setSummary(body))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [asOf, fresh]);

  return (
    <section className="group">
      <header className="ops-head">
        <h2>Итоги на дату</h2>
        <div className="tb-group tb-date">
          <DateField value={asOf} onChange={setAsOf} ariaLabel="Итоги на дату" placeholder="Сегодня" />
          {asOf && (
            <button type="button" className="icon-btn" aria-label="Сбросить дату" data-hint={HINTS.asOfReset} onClick={() => setAsOf("")}>
              <X size={16} strokeWidth={1.75} aria-hidden />
            </button>
          )}
        </div>
      </header>
      {failed && <p className="caption">Итоги не загрузились. Попробуйте выбрать дату ещё раз.</p>}
      {summary && summary.by_currency.length === 0 && <p className="caption">В текущем отделе платежей нет.</p>}
      {summary && summary.by_currency.length > 0 && (
        <div className="panel dept-table" role="table" aria-label="Итоги на дату по валютам">
          <div className="dept-row dept-head totals-on-row" role="row">
            <span role="columnheader">Валюта</span>
            <span role="columnheader">К оплате</span>
            <span role="columnheader">Просрочено</span>
            <span role="columnheader">Оплачено</span>
          </div>
          {summary.by_currency.map((row) => (
            <div key={row.currency} className="dept-row totals-on-row" role="row">
              <strong role="cell" className="dept-name">
                {row.currency}
              </strong>
              <MoneyCell label="К оплате" rows={Number(row.open_amount) > 0 ? [{ currency: row.currency, amount: row.open_amount, count: 0 }] : []} />
              <MoneyCell
                label="Просрочено"
                tone="overdue"
                rows={Number(row.overdue_amount) > 0 ? [{ currency: row.currency, amount: row.overdue_amount, count: 0 }] : []}
              />
              <MoneyCell label="Оплачено" rows={Number(row.paid_amount) > 0 ? [{ currency: row.currency, amount: row.paid_amount, count: 0 }] : []} />
            </div>
          ))}
        </div>
      )}
      <p className="caption">
        {summary?.as_of ? `На конец ${shortDue(summary.as_of)}: оплаты позже этой даты не засчитаны.` : "На сегодня."} Только текущий отдел.
      </p>
    </section>
  );
}

/** 12 месяцев столбиками: оплачено, просрочено, впереди. Без библиотек — CSS-высоты. */
function MonthChart({ rows, today, preferred }: { rows: StatsMonth[]; today: string; preferred: string }) {
  const currencies = useMemo(() => [...new Set(rows.map((row) => row.currency))], [rows]);
  const [picked, setPicked] = useState("");
  const active = currencies.includes(picked) ? picked : currencies.includes(preferred) ? preferred : currencies[0];
  const months = rows.filter((row) => row.currency === active);
  const max = Math.max(1, ...months.map((row) => Number(row.paid) + Number(row.overdue) + Number(row.planned)));
  const nowKey = today.slice(0, 7);
  const sum = (field: "paid" | "overdue" | "planned") =>
    months.reduce((total, row) => total + Number(row[field]), 0).toFixed(2);

  return (
    <section className="group">
      <header className="ops-head">
        <h2>
          По месяцам
          {months.length > 0 && (
            <span className="chart-range">
              {shortMonth(months[0].month)} – {shortMonth(months[months.length - 1].month)}
            </span>
          )}
        </h2>
        {currencies.length > 1 && (
          <Segmented
            label="Валюта графика"
            value={active}
            options={currencies.map((code) => ({ value: code, label: code, hint: HINTS.statsCurrency }))}
            onChange={setPicked}
          />
        )}
      </header>
      <div className="panel chart">
        <ul className="chart-legend" aria-label="Итого за 12 месяцев">
          <li>
            <i className="dot dot-paid" aria-hidden /> Оплачено <strong className="money">{formatMoney(sum("paid"), active)}</strong>
          </li>
          <li>
            <i className="dot dot-overdue" aria-hidden /> Просрочено <strong className="money">{formatMoney(sum("overdue"), active)}</strong>
          </li>
          <li>
            <i className="dot dot-planned" aria-hidden /> Впереди <strong className="money">{formatMoney(sum("planned"), active)}</strong>
          </li>
        </ul>
        <ol className="chart-bars" aria-label={`Платежи по месяцам, ${active}`}>
          {months.map((row) => {
            const [year, month] = row.month.split("-").map(Number);
            const paid = Number(row.paid);
            const overdue = Number(row.overdue);
            const planned = Number(row.planned);
            const label = `${capitalMonth(year, month)}: оплачено ${formatMoney(row.paid, active)}, просрочено ${formatMoney(row.overdue, active)}, впереди ${formatMoney(row.planned, active)}`;
            return (
              <li key={row.month} className={row.month === nowKey ? "chart-col is-now" : "chart-col"} aria-label={label}>
                <span className="chart-stack" aria-hidden>
                  <span className="chart-seg seg-planned" style={{ height: `${(planned / max) * 100}%` }} />
                  <span className="chart-seg seg-overdue" style={{ height: `${(overdue / max) * 100}%` }} />
                  <span className="chart-seg seg-paid" style={{ height: `${(paid / max) * 100}%` }} />
                </span>
                <span className="chart-month" aria-hidden>
                  {MONTH_SHORT[month - 1]}
                  {month === 1 && <small>{year}</small>}
                </span>
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}
