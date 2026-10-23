import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type OccurrenceList } from "../api";
import { OccurrenceCard } from "../components/OccurrenceCard";

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
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!data && !error && <p className="muted">Загрузка…</p>}
      {data && data.items.length === 0 && <p className="panel empty">История пустая.</p>}
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
