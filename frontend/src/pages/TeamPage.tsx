import { FormEvent, useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api, type Member } from "../api";
import { roleLabel, roleOf, useAuth } from "../auth";

type Invite = {
  id: string;
  email: string;
  role: string;
  expires_at: string;
  expired: boolean;
};

type InviteCreated = Invite & { url: string; delivery: string };
type LinkOut = { url: string; token: string };

export function TeamPage() {
  const { user, refresh } = useAuth();
  const navigate = useNavigate();
  const teamId = user?.active_team_id ?? "";
  const mine = roleOf(user);
  const owner = mine === "owner";
  const teamName = user?.memberships.find((row) => row.team_id === teamId)?.team_name ?? "";
  const [members, setMembers] = useState<Member[]>([]);
  const [invites, setInvites] = useState<Invite[]>([]);
  const [link, setLink] = useState<LinkOut | null>(null);
  const [rename, setRename] = useState(teamName);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"admin" | "member">("member");
  const [sent, setSent] = useState<InviteCreated | null>(null);
  const [deleteName, setDeleteName] = useState("");
  const [transferId, setTransferId] = useState("");
  const [confirmRotate, setConfirmRotate] = useState(false);
  const [confirmLeave, setConfirmLeave] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!teamId) return;
    const [people, letters, shared] = await Promise.all([
      api<Member[]>(`/api/v1/teams/${teamId}/members`),
      api<Invite[]>(`/api/v1/teams/${teamId}/invites`),
      api<LinkOut>(`/api/v1/teams/${teamId}/invite-link`),
    ]);
    setMembers(people);
    setInvites(letters);
    setLink(shared);
  }, [teamId]);

  useEffect(() => {
    load().catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Не загрузилось"));
  }, [load]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не получилось");
    } finally {
      setBusy(false);
    }
  }

  function canTouch(person: Member): boolean {
    if (person.id === user?.id || person.role === "owner") return false;
    if (owner) return true;
    return person.role === "member";
  }

  async function copy(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      setNotice("Ссылка скопирована");
    } catch {
      setNotice("Скопируйте ссылку вручную");
    }
  }

  async function afterMembershipChange() {
    await refresh();
    const me = await api<{ memberships: { team_id: string }[]; active_team_id: string | null }>("/api/v1/auth/me");
    if (!me.active_team_id || me.memberships.length === 0) navigate("/start", { replace: true });
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="kicker">Команда</p>
          <h1>{teamName || "Состав"}</h1>
        </div>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {notice && <p className="caption">{notice}</p>}

      <section className="panel settings-card">
        <h2>Общая ссылка</h2>
        <p className="desc">Кто откроет её, входит как участник. Старая ссылка после смены умирает.</p>
        {link ? (
          <div className="link-box">
            <a href={link.url}>{link.url}</a>
            <div className="row-actions">
              <button type="button" className="ghost" onClick={() => void copy(link.url)}>Скопировать</button>
              {confirmRotate ? (
                <>
                  <button
                    type="button"
                    className="primary"
                    disabled={busy}
                    onClick={() =>
                      void run(async () => {
                        setLink(await api<LinkOut>(`/api/v1/teams/${teamId}/invite-link/rotate`, { method: "POST" }));
                        setConfirmRotate(false);
                        setNotice("Ссылка сменена, старая больше не работает");
                      })
                    }
                  >
                    Сменить
                  </button>
                  <button type="button" className="ghost" onClick={() => setConfirmRotate(false)}>Отмена</button>
                </>
              ) : (
                <button type="button" className="ghost" onClick={() => setConfirmRotate(true)}>Сменить ссылку</button>
              )}
            </div>
          </div>
        ) : (
          <p className="muted">Ссылка ещё не загрузилась.</p>
        )}
      </section>

      <form
        className="panel form-grid"
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
          void run(async () => {
            const created = await api<InviteCreated>(`/api/v1/teams/${teamId}/invites`, {
              method: "POST",
              body: JSON.stringify({ email: inviteEmail, role: inviteRole }),
            });
            setSent(created);
            setInviteEmail("");
            setNotice(created.delivery === "log" ? "Почта не подключена: приглашение записано в лог API." : "Письмо уходит.");
            await load();
          });
        }}
      >
        <h2>Пригласить письмом</h2>
        <label>
          Почта
          <input type="email" value={inviteEmail} onChange={(event) => setInviteEmail(event.target.value)} required />
        </label>
        <label>
          Роль
          <select value={inviteRole} onChange={(event) => setInviteRole(event.target.value as "admin" | "member")}>
            <option value="member">Участник</option>
            {owner && <option value="admin">Админ</option>}
          </select>
        </label>
        <div className="row-actions span-2">
          <button type="submit" className="primary" disabled={busy}>Отправить</button>
        </div>
        {sent && (
          <p className="caption span-2">
            Ссылка на 7 дней: <a href={sent.url}>{sent.url}</a>
          </p>
        )}
      </form>

      <section className="group">
        <header>
          <h2>Люди</h2>
          <span className="pill count pill-neutral">{members.length}</span>
        </header>
        {members.length === 0 ? (
          <p className="panel empty">В команде пока никого.</p>
        ) : (
          <div className="cards">
            {members.map((person) => (
              <article key={person.id} className="card">
                <div className="card-main">
                  <div className="card-top">
                    <h3>{person.full_name}</h3>
                    <span className="pill pill-neutral">{roleLabel(person.role)}</span>
                  </div>
                  <p className="meta">
                    <span>{person.email}</span>
                    {!person.is_active && <span className="pill pill-neutral">не активен</span>}
                  </p>
                </div>
                {canTouch(person) && (
                  <div className="card-actions">
                    {owner && (
                      <button
                        type="button"
                        className="ghost"
                        disabled={busy}
                        onClick={() =>
                          void run(async () => {
                            await api(`/api/v1/teams/${teamId}/members/${person.id}`, {
                              method: "PATCH",
                              body: JSON.stringify({ role: person.role === "admin" ? "member" : "admin" }),
                            });
                            await load();
                          })
                        }
                      >
                        {person.role === "admin" ? "Сделать участником" : "Сделать админом"}
                      </button>
                    )}
                    <button
                      type="button"
                      className="ghost"
                      disabled={busy}
                      onClick={() =>
                        void run(async () => {
                          await api(`/api/v1/teams/${teamId}/members/${person.id}`, { method: "DELETE" });
                          setNotice("Платежи этого человека остались без ответственного");
                          await load();
                        })
                      }
                    >
                      Убрать
                    </button>
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="group">
        <header>
          <h2>Письма</h2>
        </header>
        {invites.length === 0 ? (
          <p className="panel empty">Приглашений по почте нет.</p>
        ) : (
          <div className="cards">
            {invites.map((row) => (
              <article key={row.id} className="card">
                <div className="card-main">
                  <div className="card-top">
                    <h3>{row.email}</h3>
                    <span className="pill pill-neutral">{roleLabel(row.role === "admin" ? "admin" : "member")}</span>
                  </div>
                  <p className="meta">
                    <span>{row.expired ? "срок вышел" : `до ${row.expires_at.slice(0, 10)}`}</span>
                  </p>
                </div>
                <div className="card-actions">
                  <button
                    type="button"
                    className="ghost"
                    disabled={busy}
                    onClick={() =>
                      void run(async () => {
                        await api(`/api/v1/teams/${teamId}/invites/${row.id}`, { method: "DELETE" });
                        await load();
                      })
                    }
                  >
                    Отменить
                  </button>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>

      {owner && (
        <form
          className="panel form-grid"
          onSubmit={(event) => {
            event.preventDefault();
            void run(async () => {
              await api(`/api/v1/teams/${teamId}`, { method: "PATCH", body: JSON.stringify({ name: rename }) });
              await refresh();
              setNotice("Название сохранено");
            });
          }}
        >
          <h2>Название</h2>
          <label className="span-2">
            Как команда называется
            <input value={rename} onChange={(event) => setRename(event.target.value)} required maxLength={120} />
          </label>
          <div className="row-actions span-2">
            <button type="submit" className="primary" disabled={busy}>Переименовать</button>
          </div>
        </form>
      )}

      {owner && (
        <form
          className="panel form-grid"
          onSubmit={(event) => {
            event.preventDefault();
            void run(async () => {
              await api(`/api/v1/teams/${teamId}/transfer`, {
                method: "POST",
                body: JSON.stringify({ user_id: transferId }),
              });
              await refresh();
              setNotice("Владение передано. Вы остались админом.");
              await load();
            });
          }}
        >
          <h2>Передать владение</h2>
          <label className="span-2">
            Новый владелец
            <select value={transferId} onChange={(event) => setTransferId(event.target.value)} required>
              <option value="">Выберите</option>
              {members
                .filter((person) => person.id !== user?.id && person.is_active)
                .map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.full_name}
                  </option>
                ))}
            </select>
          </label>
          <div className="row-actions span-2">
            <button type="submit" className="ghost" disabled={busy || !transferId}>Передать</button>
          </div>
        </form>
      )}

      <section className="panel settings-card">
        <h2>Выйти</h2>
        <p className="desc">
          {owner
            ? "Владелец выходит только после передачи владения."
            : "Платежи, где вы ответственный, останутся в команде без ответственного."}
        </p>
        {confirmLeave ? (
          <div className="row-actions">
            <button
              type="button"
              className="primary"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  await api(`/api/v1/teams/${teamId}/leave`, { method: "POST" });
                  await afterMembershipChange();
                })
              }
            >
              Выйти из команды
            </button>
            <button type="button" className="ghost" onClick={() => setConfirmLeave(false)}>Отмена</button>
          </div>
        ) : (
          <button type="button" className="ghost" onClick={() => setConfirmLeave(true)}>Выйти из команды</button>
        )}
      </section>

      {owner && (
        <form
          className="panel form-grid"
          onSubmit={(event) => {
            event.preventDefault();
            void run(async () => {
              await api(`/api/v1/teams/${teamId}`, { method: "DELETE", body: JSON.stringify({ name: deleteName }) });
              await afterMembershipChange();
            });
          }}
        >
          <h2>Удалить команду</h2>
          <p className="desc span-2">Вместе с шаблонами и периодами. Введите название «{teamName}».</p>
          <label className="span-2">
            Название
            <input value={deleteName} onChange={(event) => setDeleteName(event.target.value)} placeholder={teamName} />
          </label>
          <div className="row-actions span-2">
            <button type="submit" className="ghost" disabled={busy || deleteName.trim() !== teamName}>
              Удалить навсегда
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
