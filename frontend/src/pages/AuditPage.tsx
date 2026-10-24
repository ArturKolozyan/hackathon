import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type AuditItem, type AuditList } from "../api";
import { actionLabel, metaPhrase } from "../auditCopy";
import { EmptyState, ErrorState, LoadingBlock } from "../components/ui";

const formatter = new Intl.DateTimeFormat("ru-RU", {
  timeZone: "Europe/Moscow",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

function Row({ item }: { item: AuditItem }) {
  const when = formatter.format(new Date(item.at));
  const who = item.actor_name ?? "—";
  const action = actionLabel(item.action);
  const detail = metaPhrase(item.meta);
  return (
    <tr>
      <td data-label="Когда">{when}</td>
      <td data-label="Кто">{who}</td>
      <td data-label="Действие">{action}</td>
      <td className="audit-detail" data-label="Детали">
        {detail}
      </td>
    </tr>
  );
}

export function AuditPage() {
  const [data, setData] = useState<AuditList | null>(null);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const limit = 50;

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await api<AuditList>(`/api/v1/audit-logs?limit=${limit}&offset=${offset}`));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Журнал не загрузился");
    }
  }, [offset]);

  useEffect(() => {
    void load();
  }, [load]);

  const shown = data ? offset + data.items.length : 0;

  return (
    <div className="page page-wide">
      {error && <ErrorState message={error} onRetry={() => void load()} />}
      {!data && !error && <LoadingBlock label="Загружаем журнал…" />}
      {data && data.items.length === 0 && <EmptyState title="Пока пусто">Входы, шаблоны, люди, оплаты и бюджет появятся здесь.</EmptyState>}
      {data && data.items.length > 0 && (
        <div className="table-wrap panel">
          <table className="table">
            <thead>
              <tr>
                <th>Когда</th>
                <th>Кто</th>
                <th>Действие</th>
                <th>Детали</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item) => (
                <Row key={item.id} item={item} />
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && data.total > limit && (
        <div className="row-actions pager">
          <button type="button" className="ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}>
            Новее
          </button>
          <span className="muted">
            {shown} из {data.total}
          </span>
          <button type="button" className="ghost" disabled={shown >= data.total} onClick={() => setOffset(offset + limit)}>
            Старее
          </button>
        </div>
      )}
    </div>
  );
}
