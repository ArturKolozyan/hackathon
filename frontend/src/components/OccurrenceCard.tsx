import { useState } from "react";
import { ApiError, api, type Occurrence } from "../api";
import { formatMoney, shortDue, urgency } from "../format";

type Props = {
  item: Occurrence;
  today: string;
  mode: "inbox" | "history";
  onChanged: () => void;
};

export function OccurrenceCard({ item, today, mode, onChanged }: Props) {
  const [open, setOpen] = useState(false);
  const [paidOn, setPaidOn] = useState(mode === "history" ? item.paid_on ?? today : today);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не сохранилось");
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className={`card tone-${item.bucket}`}>
      <div className="card-main">
        <div className="card-top">
          <h3>{item.title}</h3>
          <strong className="money">{formatMoney(item.amount, item.currency)}</strong>
        </div>
        <p className="phrase">
          <span>{item.period_label}</span>
          <span>до {shortDue(item.due_date)}</span>
          <span>{urgency(item)}</span>
        </p>
        <p className="meta">
          <span>{item.responsible.full_name}</span>
          {item.template_archived && <span className="badge">шаблон снят</span>}
          {item.note && <span className="note">{item.note}</span>}
          {item.paid_by && mode === "history" && <span>закрыл {item.paid_by.full_name}</span>}
        </p>
        {item.description && <p className="desc">{item.description}</p>}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {open && (
          <form
            className="pay-form"
            onSubmit={(event) => {
              event.preventDefault();
              void run(async () => {
                if (mode === "history") {
                  await api(`/api/v1/payment-occurrences/${item.id}`, {
                    method: "PATCH",
                    body: JSON.stringify({ paid_at: paidOn }),
                  });
                  return;
                }
                await api(`/api/v1/payment-occurrences/${item.id}/confirm`, {
                  method: "POST",
                  body: JSON.stringify({ paid_at: paidOn, note: note.trim() || null }),
                });
              });
            }}
          >
            <label>
              Фактическая дата
              <input type="date" value={paidOn} onChange={(event) => setPaidOn(event.target.value)} required />
            </label>
            {mode === "inbox" && (
              <label>
                Заметка
                <input value={note} onChange={(event) => setNote(event.target.value)} maxLength={2000} placeholder="необязательно" />
              </label>
            )}
            <div className="row-actions">
              <button type="submit" className="primary" disabled={busy}>
                {busy ? "Сохраняю…" : mode === "history" ? "Сохранить дату" : "Подтвердить"}
              </button>
              <button type="button" className="ghost" onClick={() => setOpen(false)}>
                Отмена
              </button>
            </div>
          </form>
        )}
      </div>
      {!open && (
        <div className="card-actions">
          {mode === "inbox" ? (
            <button type="button" className="primary" onClick={() => setOpen(true)}>
              Оплачено
            </button>
          ) : (
            <>
              <button type="button" className="ghost" onClick={() => setOpen(true)}>
                Дата
              </button>
              <button
                type="button"
                className="ghost"
                disabled={busy}
                onClick={() => {
                  if (!window.confirm("Вернуть период в инбокс?")) return;
                  void run(() => api(`/api/v1/payment-occurrences/${item.id}/revoke`, { method: "POST" }));
                }}
              >
                В инбокс
              </button>
            </>
          )}
        </div>
      )}
    </article>
  );
}
