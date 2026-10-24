import { useCallback, useEffect, useState } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { ApiError, api, type BudgetLine, type BudgetReport } from "../api";
import { canManage, useAuth } from "../auth";
import { DateField } from "../components/fields";
import { PageControls } from "../components/PageControls";
import { ErrorState, LoadingBlock, SaveStatus, Segmented, useDebounced, useSaveState } from "../components/ui";
import { formatMoney } from "../format";
import { HINTS } from "../hints";

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
  const [error, setError] = useState<string | null>(null);
  const periodKey = kind === "month" ? monthKey : yearKey;

  const load = useCallback(async () => {
    setError(null);
    try {
      const next = await api<BudgetReport>(
        `/api/v1/budgets/report?period_type=${kind}&period_key=${encodeURIComponent(periodKey)}`,
      );
      setReport(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Бюджет не загрузился");
    }
  }, [kind, periodKey]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="page">
      <PageControls
        center={
        <Segmented
          label="Масштаб плана"
          value={kind}
          options={[
            { value: "month", label: "Месяц" },
            { value: "year", label: "Год" },
          ]}
          onChange={setKind}
        />
        }
        left={
        kind === "month" ? (
          <DateField mode="month" value={monthKey} onChange={setMonthKey} ariaLabel="Месяц" />
        ) : (
          <div className="tb-group cal-nav">
            <button
              type="button"
              className="icon-btn"
              aria-label="Предыдущий год"
              data-hint={HINTS.yearPrev}
              onClick={() => setYearKey(String((Number(yearKey) || new Date().getFullYear()) - 1))}
            >
              <ChevronLeft size={18} strokeWidth={1.75} aria-hidden />
            </button>
            <input
              className="tb-year"
              aria-label="Год"
              inputMode="numeric"
              value={yearKey}
              maxLength={4}
              onChange={(event) => setYearKey(event.target.value.replace(/\D/g, "").slice(0, 4))}
            />
            <button
              type="button"
              className="icon-btn"
              aria-label="Следующий год"
              data-hint={HINTS.yearNext}
              onClick={() => setYearKey(String((Number(yearKey) || new Date().getFullYear()) + 1))}
            >
              <ChevronRight size={18} strokeWidth={1.75} aria-hidden />
            </button>
          </div>
        )
        }
      />
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
                  <PlanInput key={`${periodKey}-${row.currency}-${row.id ?? "new"}`} row={row} kind={kind} periodKey={periodKey} onSaved={load} />
                )}
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}

const CURRENCY_SIGN: Record<string, string> = { RUB: "₽", USD: "$", EUR: "€" };

/** Plan amount saved on blur / after a pause; empty removes the plan. */
function PlanInput({
  row,
  kind,
  periodKey,
  onSaved,
}: {
  row: BudgetLine;
  kind: Kind;
  periodKey: string;
  onSaved: () => Promise<void>;
}) {
  const [value, setValue] = useState(row.plan_amount ?? "");
  const [problem, setProblem] = useState<string | null>(null);
  const save = useSaveState();
  const id = `plan-${row.currency}`;

  const saver = useDebounced<string>((next) => {
    const raw = next.trim().replace(/\s/g, "").replace(",", ".");
    if (raw && (!Number.isFinite(Number(raw)) || Number(raw) <= 0)) {
      setProblem("Сумма — положительное число");
      return;
    }
    setProblem(null);
    if (raw === (row.plan_amount ?? "") || (raw && Number(raw) === Number(row.plan_amount ?? NaN))) return;
    void save.run(async () => {
      if (!raw) {
        if (row.id) await api(`/api/v1/budgets/${row.id}`, { method: "DELETE" });
      } else if (row.id) {
        await api(`/api/v1/budgets/${row.id}`, { method: "PATCH", body: JSON.stringify({ amount: raw }) });
      } else {
        await api("/api/v1/budgets", {
          method: "POST",
          body: JSON.stringify({ period_type: kind, period_key: periodKey, currency: row.currency, amount: raw }),
        });
      }
      await onSaved();
    });
  }, 800);

  return (
    <div className={problem ? "form-field plan-field is-invalid" : "form-field plan-field"}>
      <div className="plan-head">
        <label className="form-label" htmlFor={id}>
          План на {kind === "month" ? "месяц" : "год"}
        </label>
        <SaveStatus save={save} />
      </div>
      <div className="input-with-suffix">
        <input
          id={id}
          inputMode="decimal"
          value={value}
          placeholder="Без плана"
          aria-invalid={Boolean(problem)}
          onChange={(event) => {
            setValue(event.target.value);
            saver.schedule(event.target.value);
          }}
          onBlur={() => saver.flush()}
        />
        <span className="input-suffix" aria-hidden="true">
          {CURRENCY_SIGN[row.currency] ?? row.currency}
        </span>
      </div>
      {problem ? (
        <p className="field-error" role="alert">
          {problem}
        </p>
      ) : (
        <p className="field-hint">Сохраняется само. Очистите поле, чтобы убрать план.</p>
      )}
    </div>
  );
}
