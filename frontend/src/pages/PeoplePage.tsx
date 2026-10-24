import { FormEvent, useCallback, useEffect, useState } from "react";
import { ApiError, api, type DirectoryUser, type InviteLink, type TelegramLink } from "../api";
import { useAuth } from "../auth";
import { SelectField } from "../components/fields";
import { ErrorState, LoadingBlock, useToast } from "../components/ui";

const empty = { email: "", full_name: "", role: "user" };

type Shown = { personId: string; kind: "invite" | "telegram"; url: string };

function absolute(url: string): string {
  return url.startsWith("/") ? `${window.location.origin}${url}` : url;
}

function status(person: DirectoryUser): string {
  if (person.invite_pending) return "ещё не вошёл";
  return person.telegram_linked ? "Telegram привязан" : "Telegram не привязан";
}

export function PeoplePage() {
  const { user } = useAuth();
  const toast = useToast();
  const [people, setPeople] = useState<DirectoryUser[]>([]);
  const [draft, setDraft] = useState(empty);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [shown, setShown] = useState<Shown | null>(null);
  const [confirmUnlink, setConfirmUnlink] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setPeople(await api<DirectoryUser[]>("/api/v1/users"));
  }, []);

  useEffect(() => {
    load()
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Не загрузилось"))
      .finally(() => setReady(true));
  }, [load]);

  async function run(action: () => Promise<void>, fallback: string) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : fallback);
    } finally {
      setBusy(false);
    }
  }

  async function copy(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      toast?.push("Ссылка скопирована");
    } catch {
      toast?.push("Скопируйте ссылку вручную");
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    await run(async () => {
      const created = await api<DirectoryUser>("/api/v1/users", {
        method: "POST",
        body: JSON.stringify({
          email: draft.email,
          full_name: draft.full_name,
          role: draft.role,
          department_id: user?.active_team_id,
        }),
      });
      setDraft(empty);
      if (created.invite_url) {
        setShown({ personId: created.id, kind: "invite", url: absolute(created.invite_url) });
        setNotice("Человек добавлен. Скопируйте ссылку-приглашение в его карточке и отправьте любым способом.");
      } else {
        setShown(null);
        setNotice("Человек добавлен в отдел.");
      }
      await load();
    }, "Не получилось добавить");
  }

  async function showInvite(person: DirectoryUser, renew: boolean) {
    await run(async () => {
      const body = await api<InviteLink>(`/api/v1/users/${person.id}/invite`, { method: renew ? "POST" : "GET" });
      setShown({ personId: person.id, kind: "invite", url: absolute(body.url) });
      if (renew) toast?.push("Новая ссылка готова, старая больше не работает");
    }, "Ссылку получить не удалось");
  }

  async function showTelegram(person: DirectoryUser, renew: boolean) {
    await run(async () => {
      const body = await api<TelegramLink>(`/api/v1/users/${person.id}/telegram-link`, { method: renew ? "POST" : "GET" });
      setShown({ personId: person.id, kind: "telegram", url: body.url });
      if (renew) toast?.push("Новая ссылка готова, старая больше не работает");
    }, "Ссылку получить не удалось");
  }

  async function unlink(person: DirectoryUser) {
    await run(async () => {
      await api(`/api/v1/users/${person.id}/telegram`, { method: "DELETE" });
      setConfirmUnlink(null);
      toast?.push("Telegram отвязан");
      await load();
    }, "Не получилось отвязать");
  }

  async function deactivate(person: DirectoryUser) {
    await run(async () => {
      await api(`/api/v1/users/${person.id}`, { method: "DELETE" });
      if (shown?.personId === person.id) setShown(null);
      await load();
    }, "Не получилось отключить");
  }

  if (!ready) return <LoadingBlock label="Загружаем людей…" />;

  return (
    <div className="page">
      {error && <ErrorState message={error} />}
      {notice && <p className="caption">{notice}</p>}
      <form className="panel form-grid" onSubmit={submit}>
        <h2>Добавить человека</h2>
        <label>
          Имя
          <input value={draft.full_name} onChange={(event) => setDraft({ ...draft, full_name: event.target.value })} required />
        </label>
        <label>
          Почта
          <input type="email" value={draft.email} onChange={(event) => setDraft({ ...draft, email: event.target.value })} required />
        </label>
        <label>
          Роль
          <SelectField
            value={draft.role}
            onChange={(role) => setDraft({ ...draft, role })}
            options={[
              { value: "user", label: "Пользователь" },
              ...(user?.is_owner ? [{ value: "admin", label: "Админ отдела" }] : []),
            ]}
          />
        </label>
        <p className="desc span-2">Письмо не уходит. После добавления появится личная ссылка-приглашение: по ней человек сам задаст пароль.</p>
        <div className="span-2">
          <button type="submit" className="primary" disabled={busy}>
            {busy ? "Добавляю…" : "Добавить"}
          </button>
        </div>
      </form>
      <div className="list">
        {people.map((person) => (
          <article key={person.id} className="card">
            <div className="card-main">
              <div className="card-top">
                <h3>{person.full_name}</h3>
                <span className="pill">{person.role === "owner" ? "владелец" : person.role === "admin" ? "админ" : "пользователь"}</span>
              </div>
              <p className="phrase">
                <span>{person.email}</span>
                <span>{status(person)}</span>
                <span>{person.is_active ? "активен" : "отключён"}</span>
              </p>
              <p className="desc">{person.departments.map((row) => row.name).join(", ") || "без отдела"}</p>
              {shown?.personId === person.id && (
                <div className="link-box">
                  <p className="desc">
                    {shown.kind === "invite"
                      ? "Ссылка-приглашение: человек задаёт пароль и входит. Работает до использования или до новой ссылки."
                      : "Ссылка привязки Telegram: открыть в Telegram и нажать «Старт». Работает до использования или до новой ссылки."}
                  </p>
                  <a href={shown.url} target="_blank" rel="noreferrer">
                    {shown.url}
                  </a>
                  <button type="button" className="ghost" onClick={() => void copy(shown.url)}>
                    Скопировать
                  </button>
                </div>
              )}
            </div>
            {!person.is_owner && person.is_active && (
              <div className="card-actions">
                {person.invite_pending ? (
                  <>
                    <button type="button" className="ghost" disabled={busy} onClick={() => void showInvite(person, false)}>
                      Ссылка-приглашение
                    </button>
                    <button type="button" className="ghost" disabled={busy} onClick={() => void showInvite(person, true)}>
                      Новая ссылка
                    </button>
                  </>
                ) : person.telegram_linked ? (
                  confirmUnlink === person.id ? (
                    <>
                      <button type="button" className="primary" disabled={busy} onClick={() => void unlink(person)}>
                        Отвязать
                      </button>
                      <button type="button" className="ghost" onClick={() => setConfirmUnlink(null)}>
                        Отмена
                      </button>
                    </>
                  ) : (
                    <button type="button" className="ghost" onClick={() => setConfirmUnlink(person.id)}>
                      Отвязать Telegram
                    </button>
                  )
                ) : (
                  <>
                    <button type="button" className="ghost" disabled={busy} onClick={() => void showTelegram(person, false)}>
                      Ссылка на Telegram
                    </button>
                    <button type="button" className="ghost" disabled={busy} onClick={() => void showTelegram(person, true)}>
                      Новая ссылка
                    </button>
                  </>
                )}
                <button type="button" className="ghost" disabled={busy} onClick={() => void deactivate(person)}>
                  Отключить
                </button>
              </div>
            )}
          </article>
        ))}
      </div>
    </div>
  );
}
