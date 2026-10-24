import { useEffect, useRef, useState, type PointerEvent } from "react";
import {
  ApiError,
  api,
  streamAssistant,
  transcribe,
  type AssistantAction,
  type AssistantConfirm,
  type AssistantMessage,
} from "../api";
import { EmptyState, ErrorState, LoadingBlock } from "../components/ui";

const MAX_SECONDS = 25;

type Draft = {
  title: string;
  amount: string;
  currency: string;
  day: string;
  startsOn: string;
  responsibleId: string;
  occurrenceId: string;
};

function textOf(value: unknown): string {
  if (typeof value === "string" || typeof value === "number") return String(value);
  return "";
}

function record(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) return value as Record<string, unknown>;
  return {};
}

function draftFrom(action: AssistantAction): Draft {
  const fields = record(action.payload.fields);
  const before = record(fields.before);
  const changes = record(fields.changes);
  const pick = (key: string) => textOf(changes[key] ?? fields[key] ?? before[key]);
  return {
    title: pick("title"),
    amount: pick("amount"),
    currency: pick("currency") || "RUB",
    day: pick("day_of_month"),
    startsOn: pick("starts_on"),
    responsibleId: pick("responsible_user_id"),
    occurrenceId: pick("occurrence_id"),
  };
}

function clock(total: number): string {
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export function AssistantPage() {
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [pending, setPending] = useState(false);
  const [live, setLive] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [form, setForm] = useState<Draft | null>(null);
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const logRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const recordingRef = useRef(false);
  const holdTimer = useRef<number | null>(null);
  const modeRef = useRef<"hold" | "click" | null>(null);
  const startedAt = useRef(0);
  const tickRef = useRef<number | null>(null);

  useEffect(() => {
    api<AssistantMessage[]>("/api/v1/assistant/messages")
      .then(setMessages)
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Не загрузилось"))
      .finally(() => setReady(true));
  }, []);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [messages, live]);

  useEffect(() => {
    return () => {
      stopTracks();
    };
  }, []);

  function stopTracks() {
    if (tickRef.current) window.clearInterval(tickRef.current);
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    recorderRef.current = null;
    recordingRef.current = false;
  }

  async function send(text: string) {
    const cleaned = text.trim();
    if (!cleaned || pending) return;
    setError(null);
    setDraft("");
    setPending(true);
    setLive("");
    const optimistic: AssistantMessage = {
      id: `local-${Date.now()}`,
      role: "user",
      content: cleaned,
      created_at: new Date().toISOString(),
      action: null,
    };
    setMessages((current) => [...current, optimistic]);
    try {
      const reply = await streamAssistant(cleaned, (chunk) => setLive((value) => value + chunk));
      setMessages((current) => [...current.filter((item) => item.id !== optimistic.id), optimistic, reply]);
      setLive("");
    } catch (err: unknown) {
      setMessages((current) => current.filter((item) => item.id !== optimistic.id));
      setDraft(cleaned);
      setError(err instanceof ApiError ? err.message : "Сеть не ответила. Напишите текстом.");
      setLive("");
    } finally {
      setPending(false);
    }
  }

  async function confirm(action: AssistantAction) {
    setError(null);
    setPending(true);
    try {
      const reply = await api<AssistantConfirm>(`/api/v1/assistant/actions/${action.id}/confirm`, { method: "POST" });
      setMessages((current) =>
        current
          .map((item) => (item.action?.id === action.id ? { ...item, action: reply.action } : item))
          .concat(reply.message),
      );
      setEditing(null);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Не получилось подтвердить");
    } finally {
      setPending(false);
    }
  }

  async function saveEdit(action: AssistantAction) {
    if (!form) return;
    setPending(true);
    setError(null);
    const body: Record<string, string | number> = {};
    if (action.kind === "mark_paid") body.occurrence_id = form.occurrenceId;
    else {
      if (form.title) body.title = form.title;
      if (form.amount) body.amount = form.amount;
      if (form.currency) body.currency = form.currency;
      if (form.day) body.day_of_month = Number(form.day);
      if (form.startsOn) body.starts_on = form.startsOn;
      if (form.responsibleId) body.responsible_user_id = form.responsibleId;
    }
    try {
      const updated = await api<AssistantAction>(`/api/v1/assistant/actions/${action.id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      setMessages((current) =>
        current.map((item) => {
          if (item.action?.id !== action.id) return item;
          return { ...item, content: updated.summary, action: updated };
        }),
      );
      setEditing(null);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Не получилось сохранить правку");
    } finally {
      setPending(false);
    }
  }

  async function beginRecording() {
    if (recordingRef.current || transcribing) return;
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("Браузер не записывает звук. Напишите текстом.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"].find((item) =>
        MediaRecorder.isTypeSupported(item),
      );
      const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
        const elapsed = (Date.now() - startedAt.current) / 1000;
        stopTracks();
        setRecording(false);
        setSeconds(0);
        if (elapsed < 0.4 || blob.size < 32) {
          setError("Слишком короткая запись. Повторите или напишите текстом.");
          return;
        }
        void upload(blob);
      };
      recorderRef.current = recorder;
      recorder.start();
      recordingRef.current = true;
      startedAt.current = Date.now();
      setRecording(true);
      setSeconds(0);
      setError(null);
      tickRef.current = window.setInterval(() => {
        const next = Math.floor((Date.now() - startedAt.current) / 1000);
        setSeconds(next);
        if (next >= MAX_SECONDS) stopRecording();
      }, 200);
    } catch (err: unknown) {
      stopTracks();
      setRecording(false);
      const name = err instanceof DOMException ? err.name : "";
      if (name === "NotAllowedError" || name === "SecurityError") {
        setError("Нет доступа к микрофону. Разрешите его в браузере или напишите текстом.");
      } else if (name === "NotFoundError") {
        setError("Микрофон не найден. Можно написать текстом.");
      } else {
        setError("Не удалось включить микрофон. Напишите текстом.");
      }
    }
  }

  function stopRecording() {
    if (tickRef.current) window.clearInterval(tickRef.current);
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") recorder.stop();
    else {
      stopTracks();
      setRecording(false);
    }
  }

  async function upload(blob: Blob) {
    setTranscribing(true);
    try {
      const text = await transcribe(blob);
      if (!text.trim()) {
        setError("Не распознано. Повторите или напишите текстом.");
        return;
      }
      setDraft(text);
      inputRef.current?.focus();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Сеть не ответила. Напишите текстом.");
    } finally {
      setTranscribing(false);
    }
  }

  function onPointerDown(event: PointerEvent<HTMLButtonElement>) {
    event.currentTarget.setPointerCapture(event.pointerId);
    modeRef.current = null;
    if (holdTimer.current) window.clearTimeout(holdTimer.current);
    holdTimer.current = window.setTimeout(() => {
      modeRef.current = "hold";
      void beginRecording();
    }, 280);
  }

  function onPointerUp() {
    if (holdTimer.current) window.clearTimeout(holdTimer.current);
    if (modeRef.current === "hold") {
      stopRecording();
      modeRef.current = null;
      return;
    }
    if (recordingRef.current) stopRecording();
    else {
      modeRef.current = "click";
      void beginRecording();
    }
  }

  if (!ready) return <LoadingBlock label="Загрузка ассистента" />;
  if (error && messages.length === 0 && !draft) {
    return <ErrorState message={error} onRetry={() => window.location.reload()} />;
  }

  return (
    <section className="assistant">
      <header className="page-head">
        <div>
          <p className="kicker">Ассистент</p>
          <h1>Спроси или надиктуй</h1>
        </div>
      </header>
      <div className="assistant-log" ref={logRef} aria-live="polite">
        {messages.length === 0 && !live && (
          <EmptyState title="Пока пусто">
            Спроси, что горит на этой неделе, или надиктуй новый платёж. Изменения появятся карточкой — в базу попадут
            только после «Подтвердить».
          </EmptyState>
        )}
        {messages.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            editing={editing === message.action?.id}
            form={form}
            busy={pending}
            onConfirm={() => message.action && void confirm(message.action)}
            onEdit={() => {
              if (!message.action) return;
              if (message.action.payload.editable === false || message.action.kind === "archive_payment") {
                inputRef.current?.focus();
                return;
              }
              setEditing(message.action.id);
              setForm(draftFrom(message.action));
            }}
            onCancelEdit={() => setEditing(null)}
            onSave={() => message.action && void saveEdit(message.action)}
            onForm={(next) => setForm(next)}
          />
        ))}
        {live && (
          <p className="bubble assistant-bubble">
            {live}
            <span className="caret" aria-hidden="true" />
          </p>
        )}
      </div>
      {error && messages.length > 0 && <p className="error">{error}</p>}
      <form
        className="assistant-compose"
        onSubmit={(event) => {
          event.preventDefault();
          void send(draft);
        }}
      >
        <label className="sr-only" htmlFor="assistant-input">
          Сообщение ассистенту
        </label>
        <textarea
          id="assistant-input"
          ref={inputRef}
          rows={2}
          value={draft}
          placeholder="Что горит на этой неделе?"
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send(draft);
            }
          }}
        />
        <button
          type="button"
          className={recording ? "primary mic" : "ghost mic"}
          aria-pressed={recording}
          aria-label="Голосовой ввод, до 25 секунд"
          disabled={transcribing || pending}
          onPointerDown={onPointerDown}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
        >
          {transcribing ? "…" : recording ? clock(seconds) : "Микрофон"}
        </button>
        <button type="submit" className="primary" disabled={pending || !draft.trim()}>
          Отправить
        </button>
      </form>
      <p className="muted assistant-hint">
        {recording
          ? `Запись ${clock(seconds)} / ${clock(MAX_SECONDS)}. Отпусти или нажми ещё раз.`
          : "Зажми микрофон или нажми, чтобы начать и остановить. Текст можно поправить перед отправкой."}
      </p>
    </section>
  );
}

function MessageBubble({
  message,
  editing,
  form,
  busy,
  onConfirm,
  onEdit,
  onCancelEdit,
  onSave,
  onForm,
}: {
  message: AssistantMessage;
  editing: boolean;
  form: Draft | null;
  busy: boolean;
  onConfirm: () => void;
  onEdit: () => void;
  onCancelEdit: () => void;
  onSave: () => void;
  onForm: (next: Draft) => void;
}) {
  if (message.role === "user") return <p className="bubble user-bubble">{message.content}</p>;
  const action = message.action;
  if (!action || action.status === "cancelled") return <p className="bubble assistant-bubble">{message.content}</p>;
  const pendingCard = action.status === "pending" || action.status === "running";
  return (
    <article className="card assistant-card">
      <p className="assistant-card-text">{action.status === "pending" ? action.summary : message.content}</p>
      {pendingCard && editing && form && (
        <EditForm action={action} form={form} onForm={onForm} />
      )}
      {pendingCard && (
        <div className="card-actions">
          {editing ? (
            <>
              <button type="button" className="primary" disabled={busy} onClick={onSave}>
                Готово
              </button>
              <button type="button" className="ghost" disabled={busy} onClick={onCancelEdit}>
                Назад
              </button>
            </>
          ) : (
            <>
              <button type="button" className="primary" disabled={busy || action.status === "running"} onClick={onConfirm}>
                Подтвердить
              </button>
              <button type="button" className="outline" disabled={busy} onClick={onEdit}>
                Изменить
              </button>
            </>
          )}
        </div>
      )}
      {action.status === "confirmed" && <p className="muted">Готово</p>}
      {action.status === "failed" && <p className="error">Не записалось</p>}
    </article>
  );
}

function EditForm({
  action,
  form,
  onForm,
}: {
  action: AssistantAction;
  form: Draft;
  onForm: (next: Draft) => void;
}) {
  const people = action.payload.people ?? [];
  const alternatives = action.payload.alternatives ?? [];
  if (action.kind === "mark_paid") {
    const current = textOf(record(action.payload.fields).occurrence_id);
    const options = [
      {
        occurrence_id: current,
        period_label: textOf(record(action.payload.fields).period_label),
      },
      ...alternatives,
    ];
    return (
      <label>
        Период
        <select value={form.occurrenceId} onChange={(event) => onForm({ ...form, occurrenceId: event.target.value })}>
          {options.map((item) => (
            <option key={item.occurrence_id} value={item.occurrence_id}>
              {item.period_label}
            </option>
          ))}
        </select>
      </label>
    );
  }
  return (
    <div className="assistant-edit">
      <label>
        Название
        <input value={form.title} onChange={(event) => onForm({ ...form, title: event.target.value })} />
      </label>
      <label>
        Сумма
        <input value={form.amount} inputMode="decimal" onChange={(event) => onForm({ ...form, amount: event.target.value })} />
      </label>
      <label>
        Валюта
        <select value={form.currency} onChange={(event) => onForm({ ...form, currency: event.target.value })}>
          <option value="RUB">RUB</option>
          <option value="USD">USD</option>
          <option value="EUR">EUR</option>
        </select>
      </label>
      <label>
        День месяца
        <input value={form.day} inputMode="numeric" onChange={(event) => onForm({ ...form, day: event.target.value })} />
      </label>
      {action.kind === "create_payment" && (
        <label>
          С
          <input type="date" value={form.startsOn} onChange={(event) => onForm({ ...form, startsOn: event.target.value })} />
        </label>
      )}
      {people.length > 0 && (
        <label>
          Ответственный
          <select
            value={form.responsibleId}
            onChange={(event) => onForm({ ...form, responsibleId: event.target.value })}
          >
            {people.map((person) => (
              <option key={person.id} value={person.id}>
                {person.full_name}
              </option>
            ))}
          </select>
        </label>
      )}
    </div>
  );
}
