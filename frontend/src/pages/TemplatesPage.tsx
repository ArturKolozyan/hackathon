import { FormEvent, useCallback, useEffect, useState } from "react";
import { ApiError, api, type DirectoryUser, type Template } from "../api";
import { DateField, SelectField } from "../components/fields";
import { EmptyState, ErrorState, InlineConfirm, LoadingBlock } from "../components/ui";
import { formatMoney } from "../format";

type Draft = {
  title: string;
  description: string;
  amount: string;
  currency: string;
  next_payment_date: string;
  responsible_user_id: string;
};

const emptyDraft: Draft = {
  title: "",
  description: "",
  amount: "",
  currency: "RUB",
  next_payment_date: "",
  responsible_user_id: "",
};

export function TemplatesPage() {
  const [items, setItems] = useState<Template[]>([]);
  const [people, setPeople] = useState<DirectoryUser[]>([]);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [editing, setEditing] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [templates, users] = await Promise.all([
      api<Template[]>(`/api/v1/recurring-payments?include_archived=${showArchived ? "true" : "false"}`),
      api<DirectoryUser[]>("/api/v1/users"),
    ]);
    setItems(templates);
    setPeople(users.filter((person) => person.is_active));
  }, [showArchived]);

  useEffect(() => {
    load()
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Не загрузилось"))
      .finally(() => setReady(true));
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
      next_payment_date: draft.next_payment_date,
      periodicity: "monthly",
      responsible_user_id: draft.responsible_user_id || null,
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
      <div className="page-toolbar">
        <button type="button" className="ghost" onClick={() => setShowArchived((value) => !value)}>
          {showArchived ? "Скрыть архив" : "Показать архив"}
        </button>
      </div>
      <form id="template-form" className="panel form-grid" onSubmit={submit} aria-busy={busy}>
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
          <SelectField
            value={draft.currency}
            onChange={(currency) => update("currency", currency)}
            options={[
              { value: "RUB", label: "RUB" },
              { value: "USD", label: "USD" },
              { value: "EUR", label: "EUR" },
            ]}
          />
        </label>
        <label>
          Дата ближайшей оплаты
          <DateField required value={draft.next_payment_date} onChange={(value) => update("next_payment_date", value)} />
        </label>
        <label>
          Периодичность
          <input value="Ежемесячно" readOnly />
        </label>
        <label className="span-2">
          Ответственный
          <SelectField
            value={draft.responsible_user_id}
            onChange={(id) => update("responsible_user_id", id)}
            options={[
              { value: "", label: "Без ответственного" },
              ...people.map((person) => ({ value: person.id, label: person.full_name })),
            ]}
          />
        </label>
        {error && (
          <div className="span-2">
            <ErrorState message={error} onRetry={() => void load().catch(() => undefined)} />
          </div>
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
      {!ready && !error && <LoadingBlock label="Загружаем шаблоны…" />}
      {ready && !error && items.length === 0 && (
        <EmptyState title={showArchived ? "Архив пуст" : "Шаблонов ещё нет"}>
          {showArchived ? "Снятых шаблонов нет." : "Создайте первый — периоды появятся в инбоксе."}
        </EmptyState>
      )}
      <div className="list">
        {items.map((item) => (
          <article key={item.id} className="card">
            <div className="card-main">
              <div className="card-top">
                <h3>{item.title}</h3>
                <strong className="money">{formatMoney(item.amount, item.currency)}</strong>
              </div>
              <p className="phrase">
                <span>{item.next_payment_date ? `ближайшая ${item.next_payment_date}` : `${item.day_of_month}-е число`}</span>
                <span>ежемесячно</span>
                <span>{item.responsible?.full_name ?? "без ответственного"}</span>
                <span>
                  {item.open_count} открыто · {item.paid_count} закрыто
                </span>
              </p>
              {item.description && <p className="desc">{item.description}</p>}
              {item.is_archived && (
                <p className="meta">
                  <span className="pill pill-neutral">архив</span>
                  <span>новые периоды не создаются, история на месте</span>
                </p>
              )}
            </div>
            <div className="card-actions">
              {confirmArchive === item.id ? (
                <InlineConfirm
                  title="Новые периоды не появятся. История останется."
                  confirmLabel="В архив"
                  onConfirm={() => {
                    setConfirmArchive(null);
                    void archive(item, true);
                  }}
                  onCancel={() => setConfirmArchive(null)}
                />
              ) : (
                <>
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => {
                      setEditing(item.id);
                      document.getElementById("template-form")?.scrollIntoView({ block: "start" });
                      setDraft({
                        title: item.title,
                        description: item.description ?? "",
                        amount: item.amount,
                        currency: item.currency,
                        next_payment_date: item.next_payment_date ?? item.starts_on,
                        responsible_user_id: item.responsible?.id ?? "",
                      });
                    }}
                  >
                    Изменить
                  </button>
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => {
                      if (item.is_archived) {
                        void archive(item, false);
                        return;
                      }
                      setConfirmArchive(item.id);
                    }}
                  >
                    {item.is_archived ? "Вернуть" : "В архив"}
                  </button>
                </>
              )}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
