import { useCallback, useEffect, useState } from "react";
import { ApiError, api, downloadCsv, type OccurrenceList } from "../api";
import { OccurrenceCard } from "../components/OccurrenceCard";
import { EmptyState, ErrorState, LoadingBlock } from "../components/ui";

type Filters = {
  status: string;
  currency: string;
  date_from: string;
  date_to: string;
};

const emptyFilters: Filters = { status: "", currency: "", date_from: "", date_to: "" };

function queryOf(filters: Filters, view: string): string {
  const params = new URLSearchParams({ view });
  if (filters.status) params.set("status", filters.status);
  if (filters.currency) params.set("currency", filters.currency);
  if (filters.date_from) params.set("date_from", filters.date_from);
  if (filters.date_to) params.set("date_to", filters.date_to);
  return params.toString();
}

export function HistoryPage() {
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [data, setData] = useState<OccurrenceList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    const view = filters.status ? "all" : "history";
    try {
      setData(await api<OccurrenceList>(`/api/v1/payment-occurrences?${queryOf(filters, view)}`));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "История не загрузилась");
    }
  }, [filters]);

  useEffect(() => {
    void load();
  }, [load]);

  async function exportCsv() {
    setExportError(null);
    const view = filters.status ? "all" : "history";
    try {
      await downloadCsv(`/api/v1/payment-occurrences/export.csv?${queryOf(filters, view)}`);
    } catch (err) {
      setExportError(err instanceof ApiError ? err.message : "CSV не выгрузился");
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="kicker">История</p>
          <h1>Периоды для бухгалтерии</h1>
        </div>
        <button type="button" className="primary" onClick={() => void exportCsv()}>
          Выгрузить CSV
        </button>
      </div>
      <p className="caption">
        Правка фактической даты не меняет, кто оплатил. Фактическая сумма периода считается в бюджете отдельно от плана. Итоги по валютам не смешиваются.
      </p>
      <form className="panel form-grid" onSubmit={(event) => event.preventDefault()}>
        <label>
          Статус
          <select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}>
            <option value="">Оплаченные</option>
            <option value="paid">Оплачен</option>
            <option value="overdue">Просрочен</option>
            <option value="due_soon">Скоро</option>
            <option value="upcoming">Не наступил</option>
          </select>
        </label>
        <label>
          Валюта
          <select value={filters.currency} onChange={(event) => setFilters({ ...filters, currency: event.target.value })}>
            <option value="">Все</option>
            <option value="RUB">RUB</option>
            <option value="USD">USD</option>
            <option value="EUR">EUR</option>
          </select>
        </label>
        <label>
          Срок с
          <input type="date" value={filters.date_from} onChange={(event) => setFilters({ ...filters, date_from: event.target.value })} />
        </label>
        <label>
          Срок по
          <input type="date" value={filters.date_to} onChange={(event) => setFilters({ ...filters, date_to: event.target.value })} />
        </label>
      </form>
      {exportError && <p className="error">{exportError}</p>}
      {error && <ErrorState message={error} onRetry={() => void load()} />}
      {!data && !error && <LoadingBlock label="Загружаем историю…" />}
      {data && data.items.length === 0 && (
        <EmptyState title="Ничего не нашлось">По этим фильтрам периодов нет.</EmptyState>
      )}
      {data && (
        <div className="cards">
          {data.items.map((item) => (
            <OccurrenceCard
              key={item.id}
              item={item}
              today={data.today}
              mode={item.status === "paid" ? "history" : "inbox"}
              onChanged={load}
            />
          ))}
        </div>
      )}
    </div>
  );
}
