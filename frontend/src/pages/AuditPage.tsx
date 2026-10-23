import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type AuditItem, type AuditList } from "../api";

const LABELS: Record<string, string> = {
  "auth.login.success": "Вход",
  "auth.login.failure": "Неудачный вход",
  "auth.logout": "Выход",
  "template.create": "Шаблон создан",
  "template.update": "Шаблон изменён",
  "template.delete": "Шаблон в архиве",
  "user.create": "Человек создан",
  "user.update": "Человек изменён",
  "user.delete": "Человек отключён",
  "occurrence.paid": "Оплата",
  "occurrence.unpaid": "Оплата снята",
  "occurrence.paid_at": "Дата оплаты",
  "occurrence.receipt": "Чек",
  "budget.create": "Бюджет задан",
  "budget.update": "Бюджет изменён",
  "budget.delete": "Бюджет удалён",
};

const formatter = new Intl.DateTimeFormat("ru-RU", {
  timeZone: "Europe/Moscow",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

function metaText(meta: Record<string, unknown>): string {
  const parts = Object.entries(meta).map(([key, value]) => {
    const shown = Array.isArray(value) ? value.join(", ") : String(value);
    return `${key}: ${shown}`;
  });
  return parts.join(" · ") || "—";
}

function Row({ item }: { item: AuditItem }) {
  return (
    <tr>
      <td>{formatter.format(new Date(item.at))}</td>
      <td>{item.actor_name ?? "—"}</td>
      <td>{LABELS[item.action] ?? item.action}</td>
      <td className="meta">{metaText(item.meta)}</td>
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
      <div className="page-head">
        <div>
          <p className="kicker">Журнал</p>
          <h1>Кто что сделал</h1>
        </div>
      </div>
      <p className="caption">Вход, шаблоны, люди, оплаты и бюджет. Пароли и токены сюда не пишутся. Время — Москва.</p>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {!data && !error && <p className="muted">Загрузка…</p>}
      {data && data.items.length === 0 && <p className="panel empty">Пока пусто.</p>}
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
