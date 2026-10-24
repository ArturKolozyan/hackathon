import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type BudgetLine, type BudgetReport } from "../api";
import { canManage, useAuth } from "../auth";
import { ErrorState, LoadingBlock, Segmented } from "../components/ui";
import { formatMoney } from "../format";

type Kind = "month" | "year";

function currentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

export function BudgetPage() {
  const { user } = useAuth();
  const admin = canManage(user);
  const [kind, setKind] = useState<Kind>("month");
  const [monthKey, setMonthKey] = useState(currentMonth);
  const [yearKey, setYearKey] = useState(String(new Date().getFullYear()));
  const [report, setReport] = useState<BudgetReport | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const periodKey = kind === "month" ? monthKey : yearKey;

  const load = useCallback(async () => {
    setError(null);
    try {
      const next = await api<BudgetReport>(
        `/api/v1/budgets/report?period_type=${kind}&period_key=${encodeURIComponent(periodKey)}`,
      );
      setReport(next);
      const values: Record<string, string> = {};
      for (const row of next.rows) values[row.currency] = row.plan_amount ?? "";
      setDrafts(values);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Бюджет не загрузился");
    }
  }, [kind, periodKey]);

  useEffect(() => {
    void load();
  }, [load]);

  async function save(row: BudgetLine) {
    const raw = (drafts[row.currency] ?? "").trim().replace(",", ".");
    setBusy(row.currency);
    setError(null);
    try {
      if (!raw) {
        if (row.id) {
          await api(`/api/v1/budgets/${row.id}`, { method: "DELETE" });
        }
      } else if (row.id) {
        await api(`/api/v1/budgets/${row.id}`, { method: "PATCH", body: JSON.stringify({ amount: raw }) });
      } else {
        await api("/api/v1/budgets", {
          method: "POST",
          body: JSON.stringify({ period_type: kind, period_key: periodKey, currency: row.currency, amount: raw }),
        });
      }
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не сохранилось");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="page">
      <div className="page-toolbar">
        <Segmented
          label="Масштаб плана"
          value={kind}
          options={[
            { value: "month", label: "Месяц" },
            { value: "year", label: "Год" },
          ]}
          onChange={setKind}
        />
      </div>
      <div className="head-actions period-pick">
        {kind === "month" ? (
          <label>
            Месяц
            <input type="month" value={monthKey} onChange={(event) => setMonthKey(event.target.value)} />
          </label>
        ) : (
          <label>
            Год
            <input
              inputMode="numeric"
              value={yearKey}
              maxLength={4}
              onChange={(event) => setYearKey(event.target.value.replace(/\D/g, "").slice(0, 4))}
            />
          </label>
        )}
      </div>
      {error && <ErrorState message={error} onRetry={() => void load()} />}
      {!report && !error && <LoadingBlock label="Загружаем бюджет…" />}
      {report && (
        <div className="budget-grid">
          {report.rows.map((row) => {
            const plan = row.plan_amount ? Number(row.plan_amount) : 0;
            const fact = Number(row.fact_amount);
            const width = plan > 0 ? Math.min(100, (fact / plan) * 100) : 0;
            const over = plan > 0 && fact > plan;
            return (
              <article key={row.currency} className="panel budget-card">
                <header className="card-top">
                  <h2>{row.currency}</h2>
                  <span className="muted">{row.plan_amount ? "план задан" : "без плана"}</span>
                </header>
                <p className="budget-fact">
                  <span>Факт</span>
                  <strong className="money">{formatMoney(row.fact_amount, row.currency)}</strong>
                </p>
                <p className="budget-fact">
                  <span>Ожидается</span>
                  <strong className="money">{formatMoney(row.expected_amount, row.currency)}</strong>
                </p>
                <p className="budget-fact">
                  <span>План</span>
                  <strong className="money">{row.plan_amount ? formatMoney(row.plan_amount, row.currency) : "—"}</strong>
                </p>
                {plan > 0 && (
                  <div
                    className={over ? "bar over" : "bar"}
                    role="meter"
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={Math.round(width)}
                    aria-label={over ? `${row.currency}: факт выше плана` : `${row.currency}: факт от плана`}
                  >
                    <span style={{ width: `${width}%` }} />
                  </div>
                )}
                {admin && (
                  <form
                    className="pay-form"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void save(row);
                    }}
                  >
                    <label>
                      Сумма плана
                      <input
                        inputMode="decimal"
                        value={drafts[row.currency] ?? ""}
                        placeholder="пусто — убрать план"
                        onChange={(event) => setDrafts((prev) => ({ ...prev, [row.currency]: event.target.value }))}
                      />
                    </label>
                    <button type="submit" className="primary" disabled={busy === row.currency}>
                      {busy === row.currency ? "Сохраняю…" : "Сохранить"}
                    </button>
                  </form>
                )}
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
