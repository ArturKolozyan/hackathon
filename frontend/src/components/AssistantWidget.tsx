import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { Mic, SendHorizontal, Settings, Trash2, X } from "lucide-react";
import { canManage, useAuth } from "../auth";
import { useFeatures } from "../features";
import {
  ApiError,
  api,
  clearAssistant,
  streamAssistant,
  transcribe,
  type AssistantAction,
  type AssistantConfirm,
  type AssistantMessage,
} from "../api";
import { DateField, SelectField } from "./fields";
import { MarkdownMessage } from "./MarkdownMessage";
import { HINTS } from "../hints";
import { notifyChanged } from "../fresh";
import { RubHint } from "../rates";
import { Kip, type KipState } from "./Kip";

const MAX_SECONDS = 25;
const SUGGESTIONS = ["Что просрочено?", "Итоги за месяц", "Как приложить чек?"];
const MANAGER_SUGGESTIONS = [...SUGGESTIONS, "Кто в отделе?"];

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

function stamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Moscow",
  }).format(date);
}

export function AssistantWidget({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const { user } = useAuth();
  const features = useFeatures();
  const teamId = user?.active_team_id ?? "";
  const manager = canManage(user);
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
  const [menu, setMenu] = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [happy, setHappy] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const launcherRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const wasOpen = useRef(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const recordingRef = useRef(false);
  const holdTimer = useRef<number | null>(null);
  const modeRef = useRef<"hold" | "click" | null>(null);
  const startedAt = useRef(0);
  const tickRef = useRef<number | null>(null);

  useEffect(() => {
    if (!features.loaded) return;
    if (!features.assistant || !features.assistant_available) {
      setMessages([]);
      setReady(true);
      return;
    }
    let cancelled = false;
    setReady(false);
    setError(null);
    setMessages([]);
    api<AssistantMessage[]>("/api/v1/assistant/messages")
      .then((rows) => {
        if (!cancelled) setMessages(rows);
      })
      .catch(() => {
        if (!cancelled) setError("Кип временно недоступен");
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, [features.loaded, features.assistant, features.assistant_available, teamId]);

  useEffect(() => {
    const log = logRef.current;
    if (!log) return;
    log.scrollTop = log.scrollHeight;
  }, [messages, live, pending, open]);

  useEffect(() => {
    const field = inputRef.current;
    if (!field) return;
    field.style.height = "auto";
    field.style.height = `${Math.min(field.scrollHeight, 120)}px`;
  }, [draft, open]);

  useEffect(() => {
    return () => {
      stopTracks();
    };
  }, []);

  useEffect(() => {
    if (open) {
      wasOpen.current = true;
      const timer = window.setTimeout(() => {
        if (inputRef.current) inputRef.current.focus();
        else panelRef.current?.focus();
      }, 0);
      return () => window.clearTimeout(timer);
    }
    if (wasOpen.current) {
      wasOpen.current = false;
      launcherRef.current?.focus();
    }
    return undefined;
  }, [open, ready]);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Tab") {
        const panel = panelRef.current;
        if (!panel) return;
        const nodes = [...panel.querySelectorAll<HTMLElement>("button, textarea, input, select, a[href]")].filter(
          (node) => !node.hasAttribute("disabled") && node.tabIndex !== -1,
        );
        if (nodes.length === 0) return;
        const first = nodes[0];
        const last = nodes[nodes.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
        return;
      }
      if (event.key !== "Escape") return;
      if (menu) {
        setMenu(false);
        setConfirmClear(false);
        return;
      }
      onOpenChange(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, menu, onOpenChange]);

  useEffect(() => {
    if (!menu) return;
    function onPointer(event: globalThis.PointerEvent) {
      if (!menuRef.current?.contains(event.target as Node)) {
        setMenu(false);
        setConfirmClear(false);
      }
    }
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [menu]);

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
      setError(err instanceof ApiError && err.status < 500 ? err.message : "Кип временно недоступен");
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
      // Ассистент поменял данные: открытая страница перечитает своё.
      if (reply.action.status === "confirmed") {
        notifyChanged();
        setHappy(true);
        window.setTimeout(() => setHappy(false), 1300);
      }
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

  function onPointerDown(event: ReactPointerEvent<HTMLButtonElement>) {
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

  async function clearChat() {
    if (recordingRef.current) stopRecording();
    setClearing(true);
    setError(null);
    try {
      await clearAssistant();
      setMessages([]);
      setLive("");
      setEditing(null);
      setForm(null);
      setMenu(false);
      setConfirmClear(false);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Не получилось очистить чат");
    } finally {
      setClearing(false);
    }
  }

  const available = features.assistant && features.assistant_available;
  const kipState: KipState = pending && !live ? "thinking" : live ? "talking" : happy ? "happy" : "idle";
  const suggestions = manager ? MANAGER_SUGGESTIONS : SUGGESTIONS;
  const canSend = Boolean(draft.trim()) && !pending && !transcribing;

  return (
    <>
      {!open && (
        <button
          ref={launcherRef}
          type="button"
          className="chat-launcher"
          aria-expanded={false}
          aria-controls="assistant-panel"
          data-hint={HINTS.assistant}
          onClick={() => onOpenChange(true)}
        >
          <Kip state={kipState} size={46} />
          <span className="sr-only">Открыть Кипа, помощника</span>
        </button>
      )}
      {open && (
        <div
          ref={panelRef}
          id="assistant-panel"
          className="chat-panel"
          role="dialog"
          aria-modal="true"
          aria-labelledby="assistant-title"
          tabIndex={-1}
        >
          <header className="chat-head">
            <h2 id="assistant-title" className="chat-title">
              <Kip state={kipState} size={28} quiet={kipState === "idle"} />
              Кип
            </h2>
            <div className="chat-tools" ref={menuRef}>
              {available && (
                <button
                  type="button"
                  className="icon-btn chat-icon"
                  aria-expanded={menu}
                  aria-haspopup="menu"
                  aria-label="Настройки чата"
                  data-hint={HINTS.chatSettings}
                  onClick={() => {
                    setMenu((value) => !value);
                    setConfirmClear(false);
                  }}
                >
                  <Settings size={18} strokeWidth={1.75} aria-hidden />
                </button>
              )}
              <button type="button" className="icon-btn chat-icon" aria-label="Закрыть чат" data-hint={HINTS.chatClose} onClick={() => onOpenChange(false)}>
                <X size={18} strokeWidth={1.75} aria-hidden />
              </button>
              {menu && (
                <div className="chat-menu" role="menu" aria-label="Настройки чата">
                  {confirmClear ? (
                    <div className="chat-menu-confirm">
                      <p>Очистить историю этого отдела? Висящая карточка тоже скроется.</p>
                      <div className="row-actions">
                        <button type="button" className="chat-danger" disabled={clearing} data-hint={HINTS.chatClearConfirm} onClick={() => void clearChat()}>
                          <Trash2 size={16} strokeWidth={1.75} aria-hidden />
                          {clearing ? "Очищаю…" : "Очистить"}
                        </button>
                        <button type="button" className="ghost" disabled={clearing} data-hint={HINTS.cancel} onClick={() => setConfirmClear(false)}>
                          Отмена
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button type="button" className="chat-danger" role="menuitem" data-hint={HINTS.chatClear} onClick={() => setConfirmClear(true)}>
                      <Trash2 size={16} strokeWidth={1.75} aria-hidden />
                      Очистить чат
                    </button>
                  )}
                </div>
              )}
            </div>
          </header>
          {!features.loaded || !ready ? (
            <div className="chat-log">
              <p className="sr-only">Кип загружается</p>
              <span className="skeleton skeleton-line" />
              <span className="skeleton skeleton-card short" />
            </div>
          ) : !available ? (
            <div className="chat-log">
              <div className="panel empty-state">
                <h3>Кип временно недоступен</h3>
                <p>Платежи, люди и остальные разделы работают.</p>
              </div>
            </div>
          ) : (
            <>
              <div className="chat-log" ref={logRef} aria-live="polite">
                {messages.length === 0 && !live && !pending && (
                  <div className="chat-empty">
                    <Kip state={kipState} size={104} />
                    <p className="chat-greet">Привет! Я Кип, помогу разобраться в продукте</p>
                    <p>
                      Подскажу, что просрочено и сколько платим, отмечу оплату или заведу платёж. В базу всё попадёт только после
                      вашего «Подтвердить».
                    </p>
                    <div className="chat-suggest">
                      {suggestions.map((prompt) => (
                        <button key={prompt} type="button" data-hint={HINTS.chatSuggest} onClick={() => void send(prompt)}>
                          {prompt}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {messages.map((message) => (
                  <MessageView
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
                    onForm={setForm}
                  />
                ))}
                {live && (
                  <div className="msg msg-assistant">
                    <Kip state="talking" size={28} className="msg-avatar" />
                    <div className="bubble assistant-bubble">
                      <MarkdownMessage text={live} />
                      <span className="caret" aria-hidden="true" />
                    </div>
                  </div>
                )}
                {pending && !live && (
                  <div className="msg msg-assistant">
                    <Kip state="thinking" size={28} className="msg-avatar" />
                    <div className="typing" role="status" aria-label="Кип думает">
                      <span />
                      <span />
                      <span />
                    </div>
                  </div>
                )}
              </div>
              {error && (
                <p className="error chat-error" role="alert">
                  {error}
                </p>
              )}
              {(recording || transcribing) && (
                <p className="muted chat-status" role="status">
                  {transcribing
                    ? "Распознаю речь…"
                    : `Запись ${clock(seconds)} / ${clock(MAX_SECONDS)}. Отпустите или нажмите ещё раз.`}
                </p>
              )}
              <form
                className="chat-compose"
                onSubmit={(event) => {
                  event.preventDefault();
                  void send(draft);
                }}
              >
                <label className="sr-only" htmlFor="assistant-input">
                  Сообщение Кипу
                </label>
                <textarea
                  id="assistant-input"
                  ref={inputRef}
                  rows={1}
                  value={draft}
                  placeholder="Спросите Кипа"
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                      event.preventDefault();
                      void send(draft);
                    }
                  }}
                />
                {features.voice && (
                  <button
                    type="button"
                    className={recording ? "chat-round is-recording" : "chat-round"}
                    aria-pressed={recording}
                    aria-label={
                      recording
                        ? `Идёт запись, ${clock(seconds)} из ${clock(MAX_SECONDS)}. Нажмите, чтобы остановить`
                        : "Голосовой ввод, до 25 секунд"
                    }
                    disabled={transcribing || pending}
                    data-hint={HINTS.chatMic}
                    onPointerDown={onPointerDown}
                    onPointerUp={onPointerUp}
                    onPointerCancel={onPointerUp}
                  >
                    <Mic size={18} strokeWidth={1.75} aria-hidden />
                  </button>
                )}
                <button type="submit" className="chat-round chat-send" disabled={!canSend} aria-label="Отправить" data-hint={HINTS.chatSend}>
                  <SendHorizontal size={18} strokeWidth={1.75} aria-hidden />
                </button>
              </form>
            </>
          )}
        </div>
      )}
    </>
  );
}

function MessageView({
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
  const time = stamp(message.created_at);
  if (message.role === "user") {
    return (
      <div className="msg msg-user">
        <p className="bubble user-bubble">{message.content}</p>
        <time dateTime={message.created_at}>{time}</time>
      </div>
    );
  }
  const action = message.action;
  if (!action || action.status === "cancelled") {
    return (
      <div className="msg msg-assistant">
<Kip quiet size={28} className="msg-avatar" />
        <div className="bubble assistant-bubble">
          <MarkdownMessage text={message.content} />
        </div>
        <time dateTime={message.created_at}>{time}</time>
      </div>
    );
  }
  const pendingCard = action.status === "pending" || action.status === "running";
  const body = action.status === "pending" ? action.summary : message.content;
  return (
    <div className="msg msg-assistant">
<Kip quiet size={28} className="msg-avatar" />
      <article className="card assistant-card">
        <MarkdownMessage text={body} />
        {pendingCard && editing && form && <EditForm action={action} form={form} onForm={onForm} />}
        {pendingCard && (
          <div className="card-actions">
            {editing ? (
              <>
                <button type="button" className="primary" disabled={busy} data-hint={HINTS.chatEditDone} onClick={onSave}>
                  Готово
                </button>
                <button type="button" className="ghost" disabled={busy} data-hint={HINTS.chatEditBack} onClick={onCancelEdit}>
                  Назад
                </button>
              </>
            ) : (
              <>
                <button type="button" className="primary" disabled={busy || action.status === "running"} data-hint={HINTS.chatConfirm} onClick={onConfirm}>
                  Подтвердить
                </button>
                <button type="button" className="outline" disabled={busy} data-hint={HINTS.chatEdit} onClick={onEdit}>
                  Изменить
                </button>
              </>
            )}
          </div>
        )}
        {action.status === "confirmed" && <p className="muted">Готово</p>}
        {action.status === "failed" && <p className="error">Не записалось</p>}
      </article>
      <time dateTime={message.created_at}>{time}</time>
    </div>
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
        <SelectField
          value={form.occurrenceId}
          onChange={(occurrenceId) => onForm({ ...form, occurrenceId })}
          options={options.map((item) => ({ value: item.occurrence_id, label: item.period_label }))}
        />
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
        <RubHint amount={form.amount} currency={form.currency} />
      </label>
      <label>
        Валюта
        <SelectField
          value={form.currency}
          onChange={(currency) => onForm({ ...form, currency })}
          options={[
            { value: "RUB", label: "RUB" },
            { value: "USD", label: "USD" },
            { value: "EUR", label: "EUR" },
          ]}
        />
      </label>
      <label>
        День месяца
        <input value={form.day} inputMode="numeric" onChange={(event) => onForm({ ...form, day: event.target.value })} />
      </label>
      {action.kind === "create_payment" && (
        <label>
          С
          <DateField value={form.startsOn} onChange={(startsOn) => onForm({ ...form, startsOn })} />
        </label>
      )}
      {people.length > 0 && (
        <label>
          Ответственный
          <SelectField
            value={form.responsibleId}
            onChange={(responsibleId) => onForm({ ...form, responsibleId })}
            options={people.map((person) => ({ value: person.id, label: person.full_name }))}
          />
        </label>
      )}
    </div>
  );
}
