import { useEffect, useState } from "react";
import { ChevronDown, Paperclip } from "lucide-react";
import { ApiError, api, type Occurrence } from "../api";
import { formatMoney, shortDue, statusPill } from "../format";
import { DateField } from "./fields";
import { ReceiptChip, ReceiptPicker } from "./ReceiptField";
import { InlineConfirm, useToast } from "./ui";
import { HINTS } from "../hints";
import { RubHint } from "../rates";

type Props = {
  item: Occurrence;
  today: string;
  mode: "inbox" | "history";
  onChanged: () => void;
  /** Подпись отдела: календарь и статистика показывают платежи нескольких отделов. */
  teamName?: string;
};

type Panel = "none" | "pay" | "receipt";

/** Upload a receipt file (and its comment) to one period. The period's own department goes in X-Team-Id; X-Team-Once keeps the active department as is. */
async function uploadReceipt(item: Occurrence, file: File, note: string | null): Promise<void> {
  const form = new FormData();
  form.append("file", file);
  if (note !== null) form.append("note", note);
  await api(`/api/v1/payment-occurrences/${item.id}/receipt`, {
    method: "POST",
    body: form,
    headers: { "X-Team-Id": item.team_id, "X-Team-Once": "1" },
  });
}

export function OccurrenceCard({ item, today, mode, onChanged, teamName }: Props) {
  const [panel, setPanel] = useState<Panel>("none");
  const [paidOn, setPaidOn] = useState(mode === "history" ? item.paid_on ?? today : today);
  const [paidAmount, setPaidAmount] = useState(item.paid_amount ?? item.amount);
  const [proofOpen, setProofOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [receiptNote, setReceiptNote] = useState(item.receipt_note ?? "");
  const [confirmRevoke, setConfirmRevoke] = useState(false);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const toast = useToast();
  const team = { "X-Team-Id": item.team_id, "X-Team-Once": "1" };

  useEffect(() => {
    setReceiptNote(item.receipt_note ?? "");
  }, [item.receipt_note]);

  function close() {
    setPanel("none");
    setFile(null);
    setProofOpen(false);
    setConfirmRemove(false);
    setReceiptNote(item.receipt_note ?? "");
    setError(null);
  }

  async function run(action: () => Promise<string>) {
    setBusy(true);
    setError(null);
    try {
      const done = await action();
      close();
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
  const noteChanged = (receiptNote.trim() || null) !== (item.receipt_note || null);

  async function submitPay() {
    if (mode === "history") {
      await api(`/api/v1/payment-occurrences/${item.id}`, {
        method: "PATCH",
        headers: team,
        body: JSON.stringify({ paid_at: paidOn, paid_amount: paidAmount.replace(",", ".") }),
      });
      return "Оплата сохранена";
    }
    const body: Record<string, string | null> = { paid_at: paidOn, paid_amount: paidAmount.replace(",", ".") };
    if (!file && noteChanged) body.receipt_note = receiptNote.trim() || null;
    await api(`/api/v1/payment-occurrences/${item.id}/confirm`, {
      method: "POST",
      headers: team,
      body: JSON.stringify(body),
    });
    if (!file) return "Оплата отмечена, платёж ушёл в историю";
    try {
      await uploadReceipt(item, file, receiptNote.trim());
    } catch (err) {
      onChanged();
      const reason = err instanceof ApiError ? err.message : "Чек не загрузился";
      throw new ApiError(0, `Оплата отмечена, но чек не прикрепился: ${reason}. Прикрепите его в истории`);
    }
    return "Оплата отмечена, чек прикреплён";
  }

  async function submitReceipt() {
    if (file) {
      await uploadReceipt(item, file, receiptNote.trim());
      return item.receipt ? "Чек заменён" : "Чек прикреплён";
    }
    await api(`/api/v1/payment-occurrences/${item.id}`, {
      method: "PATCH",
      headers: team,
      body: JSON.stringify({ receipt_note: receiptNote.trim() || null }),
    });
    return "Комментарий сохранён";
  }

  const proofFields = (
    <>
      {item.receipt && !file && (
        <div className="receipt-current">
          <ReceiptChip receipt={item.receipt} />
          {panel === "receipt" &&
            (confirmRemove ? (
              <InlineConfirm
                title={`Убрать чек «${item.receipt.name}»? Файл удалится.`}
                confirmLabel="Убрать чек"
                busy={busy}
                onConfirm={() =>
                  void run(async () => {
                    await api(`/api/v1/payment-occurrences/${item.id}/receipt`, { method: "DELETE", headers: team });
                    return "Чек убран";
                  })
                }
                onCancel={() => setConfirmRemove(false)}
              />
            ) : (
              <button
                type="button"
                className="ghost danger"
                disabled={busy}
                data-hint={HINTS.receiptRemove}
                onClick={() => setConfirmRemove(true)}
              >
                Убрать чек
              </button>
            ))}
        </div>
      )}
      <ReceiptPicker file={file} onFile={setFile} disabled={busy} />
      <label>
        Комментарий к чеку
        <input
          value={receiptNote}
          onChange={(event) => setReceiptNote(event.target.value)}
          maxLength={2000}
          placeholder="Номер счёта, платёжки или кто платил"
        />
      </label>
    </>
  );

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
            {teamName && <span className="card-team">{teamName}</span>}
            <span>{item.period_label}</span>
            <span>до {shortDue(item.due_date)}</span>
          </p>
          <span className={`pill pill-${pill.tone}`}>{pill.label}</span>
        </div>
        <p className="meta">
          <span>{item.responsible?.full_name ?? "без ответственного"}</span>
          {item.template_archived && <span className="pill pill-neutral">шаблон снят</span>}
          {item.note && <span>{item.note}</span>}
          <RubHint amount={item.status === "paid" && item.paid_amount ? item.paid_amount : item.amount} currency={item.currency} />
          {item.paid_amount && item.paid_amount !== item.amount && (
            <span>план {formatMoney(item.amount, item.currency)}</span>
          )}
          {item.paid_by && mode === "history" && <span>закрыл {item.paid_by.full_name}</span>}
        </p>
        {panel !== "receipt" && <ReceiptChip receipt={item.receipt} note={item.receipt_note} />}
        {item.description && <p className="desc">{item.description}</p>}
        {item.planned && <p className="muted planned-note">Плановый период. Отметить оплату можно будет ближе к сроку.</p>}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {confirmRevoke && (
          <InlineConfirm
            title={`Вернуть «${item.title}» в инбокс? Оплата снимется, чек останется.`}
            confirmLabel="Вернуть в инбокс"
            busy={busy}
            onConfirm={() => {
              void run(async () => {
                await api(`/api/v1/payment-occurrences/${item.id}/revoke`, { method: "POST", headers: team });
                return "Платёж снова в инбоксе";
              });
            }}
            onCancel={() => setConfirmRevoke(false)}
          />
        )}
        {panel === "pay" && (
          <form
            className="pay-form"
            onSubmit={(event) => {
              event.preventDefault();
              void run(submitPay);
            }}
          >
            <div className="pay-grid">
              <label>
                Фактическая дата
                <DateField required max={today} value={paidOn} onChange={setPaidOn} />
              </label>
              <label>
                Фактическая сумма, {item.currency}
                <input value={paidAmount} onChange={(event) => setPaidAmount(event.target.value)} inputMode="decimal" required />
                <RubHint amount={paidAmount} currency={item.currency} />
              </label>
            </div>
            {mode === "inbox" && (
              <div className={proofOpen ? "proof is-open" : "proof"}>
                <button
                  type="button"
                  className="proof-toggle"
                  aria-expanded={proofOpen}
                  data-hint={HINTS.receiptToggle}
                  onClick={() => setProofOpen((open) => !open)}
                >
                  <Paperclip size={16} strokeWidth={1.75} aria-hidden />
                  <span>Подтверждение оплаты</span>
                  <span className="proof-optional">{file ? file.name : "необязательно"}</span>
                  <ChevronDown size={16} strokeWidth={1.75} aria-hidden className="proof-chevron" />
                </button>
                {proofOpen && <div className="proof-body">{proofFields}</div>}
              </div>
            )}
            <div className="row-actions">
              <button
                type="submit"
                className="primary"
                disabled={busy}
                data-hint={mode === "history" ? HINTS.paidDateSave : HINTS.paidConfirm}
              >
                {busy ? "Сохраняю…" : mode === "history" ? "Сохранить" : "Подтвердить оплату"}
              </button>
              <button type="button" className="ghost" data-hint={HINTS.cancel} onClick={close}>
                Отмена
              </button>
            </div>
          </form>
        )}
        {panel === "receipt" && (
          <form
            className="pay-form"
            onSubmit={(event) => {
              event.preventDefault();
              void run(submitReceipt);
            }}
          >
            {proofFields}
            <div className="row-actions">
              <button
                type="submit"
                className="primary"
                disabled={busy || (!file && !noteChanged)}
                data-hint={HINTS.receiptSave}
              >
                {busy ? "Сохраняю…" : file ? (item.receipt ? "Заменить чек" : "Прикрепить чек") : "Сохранить"}
              </button>
              <button type="button" className="ghost" data-hint={HINTS.cancel} onClick={close}>
                Отмена
              </button>
            </div>
          </form>
        )}
      </div>
      {panel === "none" && !confirmRevoke && !item.planned && (
        <div className="card-actions">
          {mode === "inbox" ? (
            <button type="button" className="primary" data-hint={HINTS.paid} onClick={() => setPanel("pay")}>
              Оплачено
            </button>
          ) : (
            <>
              <button
                type="button"
                className={item.receipt ? "outline receipt-action has-file" : "outline receipt-action"}
                aria-label={item.receipt ? "Чек: заменить или убрать" : "Прикрепить чек"}
                data-hint={item.receipt ? HINTS.receiptReplace : HINTS.receiptAdd}
                onClick={() => setPanel("receipt")}
              >
                <Paperclip size={16} strokeWidth={1.75} aria-hidden />
                <span>{item.receipt ? "Чек" : "Прикрепить чек"}</span>
              </button>
              <button type="button" className="ghost" data-hint={HINTS.paidOtherDate} onClick={() => setPanel("pay")}>
                Изменить дату оплаты
              </button>
              <button type="button" className="ghost" disabled={busy} data-hint={HINTS.revoke} onClick={() => setConfirmRevoke(true)}>
                В инбокс
              </button>
            </>
          )}
        </div>
      )}
    </article>
  );
}
