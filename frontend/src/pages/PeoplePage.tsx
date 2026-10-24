import { FormEvent, useCallback, useEffect, useState } from "react";
import { ApiError, api, type DirectoryUser } from "../api";
import { useAuth } from "../auth";
import { ErrorState, LoadingBlock } from "../components/ui";

const empty = { email: "", full_name: "", password: "", role: "user" };

export function PeoplePage() {
  const { user } = useAuth();
  const [people, setPeople] = useState<DirectoryUser[]>([]);
  const [draft, setDraft] = useState(empty);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
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

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api("/api/v1/users", {
        method: "POST",
        body: JSON.stringify({
          email: draft.email,
          full_name: draft.full_name,
          password: draft.password,
          role: draft.role,
          department_id: user?.active_team_id,
        }),
      });
      setDraft(empty);
      setNotice("Человек добавлен. Временный пароль он сменит при первом входе.");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не получилось добавить");
    } finally {
      setBusy(false);
    }
  }

  async function resend(person: DirectoryUser) {
    setError(null);
    setNotice(null);
    try {
      const body = await api<{ url: string | null; message: string }>(`/api/v1/users/${person.id}/telegram-link`, {
        method: "POST",
      });
      setNotice(body.url ? `${body.message} ${body.url}` : body.message);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Ссылку отправить не удалось");
    }
  }

  async function deactivate(person: DirectoryUser) {
    setError(null);
    try {
      await api(`/api/v1/users/${person.id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не получилось отключить");
    }
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
          Временный пароль
          <input type="text" minLength={8} value={draft.password} onChange={(event) => setDraft({ ...draft, password: event.target.value })} required />
        </label>
        <label>
          Роль
          <select value={draft.role} onChange={(event) => setDraft({ ...draft, role: event.target.value })}>
            <option value="user">Пользователь</option>
            {user?.is_owner && <option value="admin">Админ отдела</option>}
          </select>
        </label>
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
                <span>{person.telegram_linked ? "Telegram привязан" : "Telegram не привязан"}</span>
                <span>{person.is_active ? "активен" : "отключён"}</span>
              </p>
              <p className="desc">{person.departments.map((row) => row.name).join(", ") || "без отдела"}</p>
            </div>
            {!person.is_owner && person.is_active && (
              <div className="card-actions">
                <button type="button" className="ghost" onClick={() => void resend(person)}>
                  Отправить ссылку на привязку ещё раз
                </button>
                <button type="button" className="ghost" onClick={() => void deactivate(person)}>
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
