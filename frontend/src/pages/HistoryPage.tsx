import { useCallback, useEffect, useState } from "react";
import { ApiError, api, downloadCsv, type OccurrenceList } from "../api";
import { OccurrenceCard } from "../components/OccurrenceCard";
import { DateField, SelectField } from "../components/fields";
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
      <div className="page-toolbar">
        <button type="button" className="primary" onClick={() => void exportCsv()}>
          Выгрузить CSV
        </button>
      </div>
      <form className="panel form-grid" onSubmit={(event) => event.preventDefault()}>
        <label>
          Статус
          <SelectField
            value={filters.status}
            onChange={(status) => setFilters({ ...filters, status })}
            options={[
              { value: "", label: "Оплаченные" },
              { value: "paid", label: "Оплачен" },
              { value: "overdue", label: "Просрочен" },
              { value: "due_soon", label: "Скоро" },
              { value: "upcoming", label: "Не наступил" },
            ]}
          />
        </label>
        <label>
          Валюта
          <SelectField
            value={filters.currency}
            onChange={(currency) => setFilters({ ...filters, currency })}
            options={[
              { value: "", label: "Все" },
              { value: "RUB", label: "RUB" },
              { value: "USD", label: "USD" },
              { value: "EUR", label: "EUR" },
            ]}
          />
        </label>
        <label>
          Срок с
          <DateField value={filters.date_from} onChange={(date_from) => setFilters({ ...filters, date_from })} />
        </label>
        <label>
          Срок по
          <DateField value={filters.date_to} onChange={(date_to) => setFilters({ ...filters, date_to })} />
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
