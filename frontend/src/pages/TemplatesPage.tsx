import { FormEvent, useCallback, useEffect, useState } from "react";
import { ApiError, api, type Template, type User } from "../api";
import { formatMoney } from "../format";

type Draft = {
  title: string;
  description: string;
  amount: string;
  currency: string;
  day_of_month: string;
  starts_on: string;
  responsible_user_id: string;
};

const emptyDraft: Draft = {
  title: "",
  description: "",
  amount: "",
  currency: "RUB",
  day_of_month: "5",
  starts_on: "",
  responsible_user_id: "",
};

export function TemplatesPage() {
  const [items, setItems] = useState<Template[]>([]);
  const [people, setPeople] = useState<User[]>([]);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [editing, setEditing] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [templates, users] = await Promise.all([
      api<Template[]>(`/api/v1/recurring-payments?include_archived=${showArchived ? "true" : "false"}`),
      api<User[]>("/api/v1/users"),
    ]);
    setItems(templates);
    setPeople(users.filter((person) => person.is_active));
  }, [showArchived]);

  useEffect(() => {
    load().catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Не загрузилось"));
  }, [load]);

  function update<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const payload = {
      title: draft.title,
      description: draft.description.trim() || null,
      amount: draft.amount.replace(",", "."),
      currency: draft.currency,
      day_of_month: Number(draft.day_of_month),
      starts_on: draft.starts_on,
      responsible_user_id: draft.responsible_user_id,
    };
    try {
      if (editing) {
        await api(`/api/v1/recurring-payments/${editing}`, { method: "PATCH", body: JSON.stringify(payload) });
      } else {
        await api("/api/v1/recurring-payments", { method: "POST", body: JSON.stringify(payload) });
      }
      setDraft(emptyDraft);
      setEditing(null);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не сохранилось");
    } finally {
      setBusy(false);
    }
  }

  async function archive(item: Template, archived: boolean) {
    setError(null);
    try {
      await api(`/api/v1/recurring-payments/${item.id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_archived: archived }),
      });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не получилось");
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="kicker">Шаблоны</p>
          <h1>Что платим регулярно</h1>
        </div>
        <button type="button" className="ghost" onClick={() => setShowArchived((value) => !value)}>
          {showArchived ? "Скрыть архив" : "Показать архив"}
        </button>
      </div>
      <form className="panel form-grid" onSubmit={submit}>
        <h2>{editing ? "Правка шаблона" : "Новый шаблон"}</h2>
        <label>
          Название
          <input value={draft.title} onChange={(event) => update("title", event.target.value)} required maxLength={200} />
        </label>
        <label>
          Комментарий
          <input value={draft.description} onChange={(event) => update("description", event.target.value)} />
        </label>
        <label>
          Сумма
          <input value={draft.amount} onChange={(event) => update("amount", event.target.value)} inputMode="decimal" required />
        </label>
        <label>
          Валюта
          <select value={draft.currency} onChange={(event) => update("currency", event.target.value)}>
            <option value="RUB">RUB</option>
            <option value="USD">USD</option>
            <option value="EUR">EUR</option>
          </select>
        </label>
        <label>
          День месяца
          <input
            type="number"
            min={1}
            max={31}
            value={draft.day_of_month}
            onChange={(event) => update("day_of_month", event.target.value)}
            required
          />
        </label>
        <label>
          С какого дня учитывать
          <input type="date" value={draft.starts_on} onChange={(event) => update("starts_on", event.target.value)} required />
        </label>
        <label className="span-2">
          Ответственный
          <select
            value={draft.responsible_user_id}
            onChange={(event) => update("responsible_user_id", event.target.value)}
            required
          >
            <option value="">Выберите</option>
            {people.map((person) => (
              <option key={person.id} value={person.id}>
                {person.full_name}
              </option>
            ))}
          </select>
        </label>
        {error && (
          <p className="error span-2" role="alert">
            {error}
          </p>
        )}
        <div className="row-actions span-2">
          <button type="submit" className="primary" disabled={busy}>
            {busy ? "Сохраняю…" : editing ? "Сохранить" : "Создать"}
          </button>
          {editing && (
            <button
              type="button"
              className="ghost"
              onClick={() => {
                setEditing(null);
                setDraft(emptyDraft);
              }}
            >
              Отмена
            </button>
          )}
        </div>
      </form>
      <div className="list">
        {items.map((item) => (
          <article key={item.id} className={`card tone-${item.is_archived ? "history" : "rest"}`}>
            <div className="card-main">
              <div className="card-top">
                <h3>{item.title}</h3>
                <strong className="money">{formatMoney(item.amount, item.currency)}</strong>
              </div>
              <p className="phrase">
                <span>{item.day_of_month}-е число</span>
                <span>{item.responsible.full_name}</span>
                <span>
                  {item.open_count} открыто · {item.paid_count} закрыто
                </span>
              </p>
              {item.description && <p className="desc">{item.description}</p>}
              {item.is_archived && <p className="meta">Архив: новые периоды не создаются, история на месте.</p>}
            </div>
            <div className="card-actions">
              <button
                type="button"
                className="ghost"
                onClick={() => {
                  setEditing(item.id);
                  setDraft({
                    title: item.title,
                    description: item.description ?? "",
                    amount: item.amount,
                    currency: item.currency,
                    day_of_month: String(item.day_of_month),
                    starts_on: item.starts_on,
                    responsible_user_id: item.responsible.id,
                  });
                }}
              >
                Изменить
              </button>
              <button type="button" className="ghost" onClick={() => void archive(item, !item.is_archived)}>
                {item.is_archived ? "Вернуть" : "В архив"}
              </button>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
