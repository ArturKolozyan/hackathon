import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type OccurrenceList } from "../api";
import { OccurrenceCard } from "../components/OccurrenceCard";
import { EmptyState, ErrorState, LoadingBlock } from "../components/ui";

export function HistoryPage() {
  const [data, setData] = useState<OccurrenceList | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await api<OccurrenceList>("/api/v1/payment-occurrences?view=history"));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "История не загрузилась");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="kicker">История</p>
          <h1>Закрытые периоды</h1>
        </div>
      </div>
      <p className="caption">Правка фактической даты заново считает, вовремя закрыли или с опозданием. Сумма оплаченного периода не меняется вместе с шаблоном.</p>
      {error && <ErrorState message={error} onRetry={() => void load()} />}
      {!data && !error && <LoadingBlock label="Загружаем историю…" />}
      {data && data.items.length === 0 && (
        <EmptyState title="История пустая">Закрытых периодов ещё нет. Они появятся здесь после «Оплачено».</EmptyState>
      )}
      {data && (
        <div className="cards">
          {data.items.map((item) => (
            <OccurrenceCard key={item.id} item={item} today={data.today} mode="history" onChanged={load} />
          ))}
        </div>
      )}
    </div>
  );
}
