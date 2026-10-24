import { FormEvent, useCallback, useEffect, useState } from "react";
import { ApiError, api, type DirectoryUser, type Template } from "../api";
import { EmptyState, ErrorState, InlineConfirm, LoadingBlock } from "../components/ui";
import { formatMoney } from "../format";

type Draft = {
  title: string;
  description: string;
  amount: string;
  currency: string;
  next_payment_date: string;
  periodicity: string;
  interval_months: string;
  responsible_user_id: string;
  applies_from: string;
};

const emptyDraft: Draft = {
  title: "",
  description: "",
  amount: "",
  currency: "RUB",
  next_payment_date: "",
  periodicity: "monthly",
  interval_months: "2",
  responsible_user_id: "",
  applies_from: "",
};

function periodPhrase(item: Template): string {
  if (item.periodicity === "once") return "разово";
  if (item.periodicity === "yearly") return "ежегодно";
  if (item.periodicity === "quarterly") return "раз в квартал";
  if (item.periodicity === "semiannual") return "раз в полгода";
  if (item.periodicity === "every_n" && item.interval_months) return `каждые ${item.interval_months} мес.`;
  return "ежемесячно";
}

export function TemplatesPage() {
  const [items, setItems] = useState<Template[]>([]);
  const [people, setPeople] = useState<DirectoryUser[]>([]);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [editing, setEditing] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState<string | null>(null);
  const [remindOverdue, setRemindOverdue] = useState(true);
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
      periodicity: draft.periodicity,
      interval_months: draft.periodicity === "every_n" ? Number(draft.interval_months) : undefined,
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

  async function archive(item: Template, archived: boolean, remind = true) {
    setError(null);
    try {
      await api(`/api/v1/recurring-payments/${item.id}`, {
        method: "PATCH",
        body: JSON.stringify(
          archived ? { is_archived: true, remind_archived_overdue: remind } : { is_archived: false },
        ),
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
          <select value={draft.currency} onChange={(event) => update("currency", event.target.value)}>
            <option value="RUB">RUB</option>
            <option value="USD">USD</option>
            <option value="EUR">EUR</option>
          </select>
        </label>
        <label>
          Дата ближайшей оплаты
          <input
            type="date"
            value={draft.next_payment_date}
            onChange={(event) => update("next_payment_date", event.target.value)}
            required
          />
        </label>
        <label>
          Периодичность
          <select value={draft.periodicity} onChange={(event) => update("periodicity", event.target.value)}>
            <option value="monthly">Ежемесячно</option>
            <option value="quarterly">Раз в квартал</option>
            <option value="semiannual">Раз в полгода</option>
            <option value="yearly">Ежегодно</option>
            <option value="once">Разово</option>
            <option value="every_n">Каждые N месяцев</option>
          </select>
        </label>
        {draft.periodicity === "every_n" && (
          <label>
            Интервал, месяцев
            <input
              type="number"
              min={1}
              max={36}
              value={draft.interval_months}
              onChange={(event) => update("interval_months", event.target.value)}
              required
            />
          </label>
        )}
        <label className="span-2">
          Ответственный
          <select
            value={draft.responsible_user_id}
            onChange={(event) => update("responsible_user_id", event.target.value)}
          >
            <option value="">Без ответственного</option>
            {people.map((person) => (
              <option key={person.id} value={person.id}>
                {person.full_name}
              </option>
            ))}
          </select>
        </label>
        {editing && draft.applies_from && (
          <p className="caption span-2">Изменения применятся с периода {draft.applies_from}.</p>
        )}
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
                <span>{periodPhrase(item)}</span>
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
                <div className="stack">
                  {item.debt_count > 0 && (
                    <p className="error" role="alert">
                      Неоплаченных прошлых периодов: {item.debt_count}. Они останутся в инбоксе и итогах, их можно отметить
                      оплаченными. Новые периоды не создаются.
                    </p>
                  )}
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={remindOverdue}
                      onChange={(event) => setRemindOverdue(event.target.checked)}
                    />
                    Напоминать о просрочке архивного платежа
                  </label>
                  <InlineConfirm
                    title="Новые периоды не появятся. История и долг останутся."
                    confirmLabel="В архив"
                    onConfirm={() => {
                      setConfirmArchive(null);
                      void archive(item, true, remindOverdue);
                    }}
                    onCancel={() => setConfirmArchive(null)}
                  />
                </div>
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
                        periodicity: item.periodicity === "every_n" ? "every_n" : item.periodicity,
                        interval_months: String(item.interval_months ?? 2),
                        responsible_user_id: item.responsible?.id ?? "",
                        applies_from: item.applies_from ?? "",
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
                      setRemindOverdue(item.remind_archived_overdue);
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
