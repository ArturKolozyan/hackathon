import { useEffect, useState } from "react";
import { ApiError, api, type Occurrence } from "../api";
import { formatMoney, shortDue, statusPill } from "../format";
import { InlineConfirm, useToast } from "./ui";

type Props = {
  item: Occurrence;
  today: string;
  mode: "inbox" | "history";
  onChanged: () => void;
};

export function OccurrenceCard({ item, today, mode, onChanged }: Props) {
  const [open, setOpen] = useState(false);
  const [receiptOpen, setReceiptOpen] = useState(false);
  const [paidOn, setPaidOn] = useState(mode === "history" ? item.paid_on ?? today : today);
  const [paidAmount, setPaidAmount] = useState(item.paid_amount ?? item.amount);
  const [note, setNote] = useState("");
  const [receiptUrl, setReceiptUrl] = useState(item.receipt_url ?? "");
  const [receiptNote, setReceiptNote] = useState(item.receipt_note ?? "");
  const [confirmRevoke, setConfirmRevoke] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();

  useEffect(() => {
    setReceiptUrl(item.receipt_url ?? "");
    setReceiptNote(item.receipt_note ?? "");
  }, [item.receipt_url, item.receipt_note]);

  async function run(action: () => Promise<void>, done: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
      setOpen(false);
      setReceiptOpen(false);
      setConfirmRevoke(false);
      toast?.push(done);
      onChanged();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не сохранилось");
    } finally {
      setBusy(false);
    }
  }

  const pill = statusPill(item);

  return (
    <article className="card">
      <div className="card-main">
        <div className="card-top">
          <h3>{item.title}</h3>
          <strong className={mode === "inbox" ? "money rule" : "money"}>
            {formatMoney(item.status === "paid" && item.paid_amount ? item.paid_amount : item.amount, item.currency)}
          </strong>
        </div>
        <div className="card-sub">
          <p className="phrase">
            <span>{item.period_label}</span>
            <span>до {shortDue(item.due_date)}</span>
          </p>
          <span className={`pill pill-${pill.tone}`}>{pill.label}</span>
        </div>
        <p className="meta">
          <span>{item.responsible?.full_name ?? "без ответственного"}</span>
          {item.template_archived && <span className="pill pill-neutral">шаблон снят</span>}
          {item.telegram_reminded_at && <span className="pill pill-neutral count">в Telegram</span>}
          {item.note && <span>{item.note}</span>}
          {item.paid_amount && item.paid_amount !== item.amount && (
            <span>план {formatMoney(item.amount, item.currency)}</span>
          )}
          {item.paid_by && mode === "history" && <span>закрыл {item.paid_by.full_name}</span>}
        </p>
        {(item.receipt_url || item.receipt_note) && (
          <p className="meta">
            {item.receipt_url && (
              <a className="text-link" href={item.receipt_url} target="_blank" rel="noreferrer">
                Чек
              </a>
            )}
            {item.receipt_note && <span>{item.receipt_note}</span>}
          </p>
        )}
        {item.description && <p className="desc">{item.description}</p>}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {confirmRevoke && (
          <InlineConfirm
            title={`Вернуть «${item.title}» в инбокс? Оплата снимется.`}
            confirmLabel="Вернуть в инбокс"
            busy={busy}
            onConfirm={() => {
              void run(() => api(`/api/v1/payment-occurrences/${item.id}/revoke`, { method: "POST" }), "Период снова в инбоксе");
            }}
            onCancel={() => setConfirmRevoke(false)}
          />
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
                    body: JSON.stringify({ paid_at: paidOn, paid_amount: paidAmount.replace(",", ".") }),
                  });
                  return;
                }
                const body: Record<string, string | null> = {
                  paid_at: paidOn,
                  note: note.trim() || null,
                  paid_amount: paidAmount.replace(",", "."),
                };
                if ((receiptUrl.trim() || null) !== (item.receipt_url || null)) body.receipt_url = receiptUrl.trim() || null;
                if ((receiptNote.trim() || null) !== (item.receipt_note || null)) body.receipt_note = receiptNote.trim() || null;
                await api(`/api/v1/payment-occurrences/${item.id}/confirm`, {
                  method: "POST",
                  body: JSON.stringify(body),
                });
              }, mode === "history" ? "Дата сохранена" : "Период закрыт и ушёл в историю");
            }}
          >
            <label>
              Фактическая дата
              <input type="date" max={today} value={paidOn} onChange={(event) => setPaidOn(event.target.value)} required />
            </label>
            <label>
              Фактическая сумма
              <input value={paidAmount} onChange={(event) => setPaidAmount(event.target.value)} inputMode="decimal" required />
            </label>
            {mode === "inbox" && (
              <>
                <label>
                  Заметка
                  <input value={note} onChange={(event) => setNote(event.target.value)} maxLength={2000} placeholder="необязательно" />
                </label>
                <label>
                  Ссылка на чек
                  <input
                    value={receiptUrl}
                    onChange={(event) => setReceiptUrl(event.target.value)}
                    inputMode="url"
                    placeholder="https://"
                    maxLength={2000}
                  />
                </label>
                <label>
                  Комментарий к чеку
                  <input value={receiptNote} onChange={(event) => setReceiptNote(event.target.value)} maxLength={2000} placeholder="необязательно" />
                </label>
              </>
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
        {receiptOpen && (
          <form
            className="pay-form"
            onSubmit={(event) => {
              event.preventDefault();
              void run(
                () =>
                  api(`/api/v1/payment-occurrences/${item.id}`, {
                    method: "PATCH",
                    body: JSON.stringify({
                      receipt_url: receiptUrl.trim() || null,
                      receipt_note: receiptNote.trim() || null,
                    }),
                  }),
                "Чек сохранён",
              );
            }}
          >
            <label>
              Ссылка на чек
              <input
                value={receiptUrl}
                onChange={(event) => setReceiptUrl(event.target.value)}
                inputMode="url"
                placeholder="https://"
                maxLength={2000}
              />
            </label>
            <label>
              Комментарий к чеку
              <input value={receiptNote} onChange={(event) => setReceiptNote(event.target.value)} maxLength={2000} placeholder="номер счёта, касса" />
            </label>
            <div className="row-actions">
              <button type="submit" className="primary" disabled={busy}>
                {busy ? "Сохраняю…" : "Сохранить чек"}
              </button>
              <button type="button" className="ghost" onClick={() => setReceiptOpen(false)}>
                Отмена
              </button>
            </div>
          </form>
        )}
      </div>
      {!open && !receiptOpen && !confirmRevoke && (
        <div className="card-actions">
          {mode === "inbox" ? (
            <button type="button" className="primary" onClick={() => setOpen(true)}>
              Оплачено
            </button>
          ) : (
            <>
              <button type="button" className="outline" onClick={() => setOpen(true)}>
                Дата
              </button>
              <button type="button" className="ghost" disabled={busy} onClick={() => setConfirmRevoke(true)}>
                В инбокс
              </button>
            </>
          )}
          <button type="button" className="ghost" onClick={() => setReceiptOpen(true)}>
            Чек
          </button>
        </div>
      )}
    </article>
  );
}
