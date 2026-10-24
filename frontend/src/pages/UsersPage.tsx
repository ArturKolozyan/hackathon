import { FormEvent, useCallback, useEffect, useState } from "react";
import { ApiError, api, type User } from "../api";
import { useAuth } from "../auth";
import { EmptyState, ErrorState, InlineConfirm, LoadingBlock } from "../components/ui";

type Draft = {
  full_name: string;
  email: string;
  password: string;
  role: "admin" | "user";
};

const emptyDraft: Draft = { full_name: "", email: "", password: "", role: "user" };

export function UsersPage() {
  const { user: actor } = useAuth();
  const [items, setItems] = useState<User[]>([]);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [editing, setEditing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [confirmOff, setConfirmOff] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setItems(await api<User[]>("/api/v1/users"));
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
    try {
      if (editing) {
        const payload: Record<string, string> = {
          full_name: draft.full_name,
          email: draft.email,
          role: draft.role,
        };
        if (draft.password) payload.password = draft.password;
        await api(`/api/v1/users/${editing}`, { method: "PATCH", body: JSON.stringify(payload) });
      } else {
        await api("/api/v1/users", {
          method: "POST",
          body: JSON.stringify(draft),
        });
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

  async function toggle(person: User) {
    setError(null);
    try {
      if (person.is_active) {
        await api(`/api/v1/users/${person.id}`, { method: "DELETE" });
      } else {
        await api(`/api/v1/users/${person.id}`, { method: "PATCH", body: JSON.stringify({ is_active: true }) });
      }
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не получилось");
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="kicker">Люди</p>
          <h1>Кто в команде</h1>
        </div>
      </div>
      <form id="user-form" className="panel form-grid" onSubmit={submit} aria-busy={busy}>
        <h2>{editing ? "Правка" : "Новый человек"}</h2>
        <label>
          Имя
          <input value={draft.full_name} onChange={(event) => setDraft({ ...draft, full_name: event.target.value })} required />
        </label>
        <label>
          Почта
          <input
            type="email"
            value={draft.email}
            onChange={(event) => setDraft({ ...draft, email: event.target.value })}
            required
          />
        </label>
        <label>
          Пароль
          <input
            type="password"
            value={draft.password}
            onChange={(event) => setDraft({ ...draft, password: event.target.value })}
            placeholder={editing ? "не менять" : "минимум 8 символов"}
            required={!editing}
            minLength={editing && !draft.password ? undefined : 8}
          />
        </label>
        <label>
          Роль
          <select value={draft.role} onChange={(event) => setDraft({ ...draft, role: event.target.value as Draft["role"] })}>
            <option value="user">участник</option>
            <option value="admin">админ</option>
          </select>
        </label>
        {error && (
          <div className="span-2">
            <ErrorState message={error} onRetry={() => void load().catch(() => undefined)} />
          </div>
        )}
        <div className="row-actions span-2">
          <button className="primary" disabled={busy} type="submit">
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
      {!ready && !error && <LoadingBlock label="Загружаем людей…" />}
      {ready && !error && items.length === 0 && <EmptyState title="В команде пока никого">Добавьте человека формой выше.</EmptyState>}
      <div className="list">
        {items.map((person) => (
          <article key={person.id} className="card">
            <div className="card-main">
              <div className="card-top">
                <h3>{person.full_name}</h3>
                <span className="role">{person.role === "admin" ? "админ" : "участник"}</span>
              </div>
              <p className="meta">
                <span>{person.email}</span>
                {!person.is_active && <span className="pill pill-neutral">отключён</span>}
              </p>
            </div>
            <div className="card-actions">
              {confirmOff === person.id ? (
                <InlineConfirm
                  title={`Отключить ${person.full_name}? Войти этот человек не сможет.`}
                  confirmLabel="Отключить"
                  onConfirm={() => {
                    setConfirmOff(null);
                    void toggle(person);
                  }}
                  onCancel={() => setConfirmOff(null)}
                />
              ) : (
                <>
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => {
                      setEditing(person.id);
                      document.getElementById("user-form")?.scrollIntoView({ block: "start" });
                      setDraft({ full_name: person.full_name, email: person.email, password: "", role: person.role });
                    }}
                  >
                    Изменить
                  </button>
                  <button
                    type="button"
                    className="ghost"
                    disabled={person.id === actor?.id}
                    onClick={() => {
                      if (person.is_active) {
                        setConfirmOff(person.id);
                        return;
                      }
                      void toggle(person);
                    }}
                  >
                    {person.is_active ? "Отключить" : "Включить"}
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
