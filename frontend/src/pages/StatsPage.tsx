import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api, type Stats } from "../api";
import { useAuth } from "../auth";
import { formatMoney, shortDue } from "../format";

type Period = "open" | "month" | "range";

function currentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export function StatsPage() {
  const { user, switchTeam } = useAuth();
  const navigate = useNavigate();
  const [period, setPeriod] = useState<Period>("open");
  const [month, setMonth] = useState(currentMonth);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [status, setStatus] = useState("");
  const [currency, setCurrency] = useState("");
  const [responsible, setResponsible] = useState("");
  const [teams, setTeams] = useState<string[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const query = new URLSearchParams();
    for (const id of teams) query.append("team_id", id);
    if (status) query.set("status", status);
    if (currency) query.set("currency", currency);
    if (responsible) query.set("responsible_id", responsible);
    if (period === "month" && month) query.set("month", month);
    if (period === "range" && dateFrom && dateTo) {
      query.set("date_from", dateFrom);
      query.set("date_to", dateTo);
    }
    const suffix = query.toString();
    setStats(await api<Stats>(`/api/v1/stats${suffix ? `?${suffix}` : ""}`));
  }, [teams, status, currency, responsible, period, month, dateFrom, dateTo]);

  useEffect(() => {
    setError(null);
    load().catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Статистика не загрузилась"));
  }, [load]);

  function toggleTeam(id: string) {
    setTeams((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
  }

  async function openTeam(teamId: string) {
    await switchTeam(teamId);
    navigate("/");
  }

  const people = stats?.people ?? [];
  const empty =
    stats &&
    stats.to_pay.length === 0 &&
    stats.overdue.length === 0 &&
    stats.paid.length === 0 &&
    stats.nearest.length === 0;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="kicker">Статистика</p>
          <h1>Все ваши отделы</h1>
        </div>
      </div>
      <p className="caption">
        К оплате и просрочка — открытые периоды. Оплачено — по дате оплаты
        {period === "open" ? " за текущий месяц" : " в выбранном окне"}. Суммы по валютам, без курса.
      </p>
      <div className="panel filters">
        <div className="check-row">
          {(user?.memberships ?? []).map((row) => (
            <label key={row.team_id}>
              <input
                type="checkbox"
                checked={teams.includes(row.team_id)}
                onChange={() => toggleTeam(row.team_id)}
              />
              {row.team_name}
            </label>
          ))}
        </div>
        <label>
          Статус
          <select value={status} onChange={(event) => setStatus(event.target.value)}>
            <option value="">Все</option>
            <option value="overdue">Просрочено</option>
            <option value="due_soon">Скоро</option>
            <option value="upcoming">Впереди</option>
            <option value="paid">Оплачено</option>
          </select>
        </label>
        <label>
          Валюта
          <select value={currency} onChange={(event) => setCurrency(event.target.value)}>
            <option value="">Все</option>
            <option value="RUB">RUB</option>
            <option value="USD">USD</option>
            <option value="EUR">EUR</option>
          </select>
        </label>
        <label>
          Ответственный
          <select value={responsible} onChange={(event) => setResponsible(event.target.value)}>
            <option value="">Все</option>
            {people.map((person) => (
              <option key={person.id} value={person.id}>
                {person.full_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Период
          <select value={period} onChange={(event) => setPeriod(event.target.value as Period)}>
            <option value="open">Открытые</option>
            <option value="month">Месяц</option>
            <option value="range">Диапазон</option>
          </select>
        </label>
        {period === "month" && (
          <label>
            Месяц
            <input type="month" value={month} onChange={(event) => setMonth(event.target.value)} />
          </label>
        )}
        {period === "range" && (
          <>
            <label>
              С
              <input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
            </label>
            <label>
              По
              <input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
            </label>
          </>
        )}
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {!stats && !error && <p className="muted">Загрузка…</p>}
      {empty && <p className="panel empty">По этим фильтрам пусто.</p>}
      {stats && !empty && (
        <>
          <div className="stat-grid">
            <Bucket title="К оплате" rows={stats.to_pay} />
            <Bucket title="Просрочено" rows={stats.overdue} />
            <Bucket title="Оплачено" rows={stats.paid} />
          </div>
          <section className="group">
            <header>
              <h2>Ближайшие сроки</h2>
            </header>
            {stats.nearest.length === 0 ? (
              <p className="panel empty">Открытых сроков нет.</p>
            ) : (
              <div className="cards">
                {stats.nearest.map((item) => (
                  <article key={item.occurrence_id} className="card">
                    <div className="card-main">
                      <div className="card-top">
                        <h3>{item.title}</h3>
                        <strong className="money rule">{formatMoney(item.amount, item.currency)}</strong>
                      </div>
                      <p className="phrase">
                        <span>{item.team_name}</span>
                        <span>до {shortDue(item.due_date)}</span>
                        <span>{item.responsible?.full_name ?? "без ответственного"}</span>
                      </p>
                    </div>
                    <div className="card-actions">
                      <button type="button" className="outline" onClick={() => void openTeam(item.team_id)}>
                        В инбокс
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>
          <section className="group">
            <header>
              <h2>По отделам</h2>
            </header>
            <div className="stat-grid">
              {stats.by_team.map((row) => (
                <button key={row.team_id} type="button" className="panel stat-team" onClick={() => void openTeam(row.team_id)}>
                  <h3>{row.team_name}</h3>
                  <p className="meta">
                    {row.to_pay.length === 0
                      ? "к оплате ничего"
                      : row.to_pay.map((bucket) => formatMoney(bucket.amount, bucket.currency)).join(" · ")}
                  </p>
                  {row.overdue.length > 0 && (
                    <p className="meta">
                      просрочено {row.overdue.map((bucket) => formatMoney(bucket.amount, bucket.currency)).join(" · ")}
                    </p>
                  )}
                </button>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

function Bucket({ title, rows }: { title: string; rows: { currency: string; amount: string; count: number }[] }) {
  return (
    <article className="panel total">
      <span className="code">{title}</span>
      {rows.length === 0 ? (
        <strong className="money">—</strong>
      ) : (
        rows.map((row) => (
          <strong key={row.currency} className="money rule">
            {formatMoney(row.amount, row.currency)}
            <span className="pill pill-neutral count">{row.count}</span>
          </strong>
        ))
      )}
    </article>
  );
}
