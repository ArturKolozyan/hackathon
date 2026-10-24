import { useCallback, useEffect, useState } from "react";
import { Download, History as HistoryIcon, SearchX } from "lucide-react";
import { ApiError, api, downloadCsv, type OccurrenceList } from "../api";
import { OccurrenceCard } from "../components/OccurrenceCard";
import { DateField, SelectField } from "../components/fields";
import { PageControls } from "../components/PageControls";
import { EmptyState, ErrorState, LoadingBlock } from "../components/ui";
import { HINTS } from "../hints";

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
  const dirty = Boolean(filters.status || filters.currency || filters.date_from || filters.date_to);

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
      <PageControls
        left={
        <>
        <SelectField
          className="tb-field"
          ariaLabel="Статус"
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
        <SelectField
          className="tb-field"
          ariaLabel="Валюта"
          value={filters.currency}
          onChange={(currency) => setFilters({ ...filters, currency })}
          options={[
            { value: "", label: "Все валюты" },
            { value: "RUB", label: "RUB" },
            { value: "USD", label: "USD" },
            { value: "EUR", label: "EUR" },
          ]}
        />
        <div className="tb-group tb-range">
          <DateField
            value={filters.date_from}
            onChange={(date_from) => setFilters({ ...filters, date_from })}
            ariaLabel="Срок с"
            placeholder="Срок с"
            max={filters.date_to || undefined}
          />
          <span className="tb-dash" aria-hidden="true">
            –
          </span>
          <DateField
            value={filters.date_to}
            onChange={(date_to) => setFilters({ ...filters, date_to })}
            ariaLabel="Срок по"
            placeholder="по"
            min={filters.date_from || undefined}
          />
        </div>
        {dirty && (
          <button type="button" className="ghost" data-hint={HINTS.filtersReset} onClick={() => setFilters(emptyFilters)}>
            Сбросить
          </button>
        )}
        </>
        }
      />
      {error && <ErrorState message={error} onRetry={() => void load()} />}
      {!data && !error && <LoadingBlock label="Загружаем историю…" />}
      {data && data.items.length === 0 && (
        dirty ? (
          <EmptyState
            icon={SearchX}
            title="Ничего не нашлось"
            action={
              <button type="button" className="ghost" data-hint={HINTS.filtersReset} onClick={() => setFilters(emptyFilters)}>
                Сбросить фильтры
              </button>
            }
          >
            Под эти фильтры платежей нет. Измените их или сбросьте.
          </EmptyState>
        ) : (
          <EmptyState icon={HistoryIcon} title="Оплат пока нет">
            Когда вы отметите платёж оплаченным, он появится здесь вместе с датой и суммой.
          </EmptyState>
        )
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
      {data && data.items.length > 0 && (
        <div className="page-foot">
          {exportError && <p className="error">{exportError}</p>}
          <button type="button" className="ghost" data-hint={HINTS.exportCsv} onClick={() => void exportCsv()}>
            <Download size={16} strokeWidth={1.75} aria-hidden />
            Выгрузить CSV
          </button>
        </div>
      )}
    </div>
  );
}
