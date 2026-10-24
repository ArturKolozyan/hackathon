import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api, type Stats } from "../api";
import { useAuth } from "../auth";
import { DateField, SelectField } from "../components/fields";
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
          <SelectField
            value={status}
            onChange={setStatus}
            options={[
              { value: "", label: "Все" },
              { value: "overdue", label: "Просрочено" },
              { value: "due_soon", label: "Скоро" },
              { value: "upcoming", label: "Впереди" },
              { value: "paid", label: "Оплачено" },
            ]}
          />
        </label>
        <label>
          Валюта
          <SelectField
            value={currency}
            onChange={setCurrency}
            options={[
              { value: "", label: "Все" },
              { value: "RUB", label: "RUB" },
              { value: "USD", label: "USD" },
              { value: "EUR", label: "EUR" },
            ]}
          />
        </label>
        <label>
          Ответственный
          <SelectField
            value={responsible}
            onChange={setResponsible}
            options={[{ value: "", label: "Все" }, ...people.map((person) => ({ value: person.id, label: person.full_name }))]}
          />
        </label>
        <label>
          Период
          <SelectField
            value={period}
            onChange={(value) => setPeriod(value as Period)}
            options={[
              { value: "open", label: "Открытые" },
              { value: "month", label: "Месяц" },
              { value: "range", label: "Диапазон" },
            ]}
          />
        </label>
        {period === "month" && (
          <label>
            Месяц
            <DateField mode="month" value={month} onChange={setMonth} />
          </label>
        )}
        {period === "range" && (
          <>
            <label>
              С
              <DateField value={dateFrom} onChange={setDateFrom} />
            </label>
            <label>
              По
              <DateField value={dateTo} onChange={setDateTo} />
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
