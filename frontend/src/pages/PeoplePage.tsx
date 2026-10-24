import { useCallback, useEffect, useMemo, useState } from "react";
import { Search, SearchX, UserPlus, Users } from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import { ApiError, api, type DirectoryUser, type InviteLink, type TelegramLink } from "../api";
import { PageControls } from "../components/PageControls";
import { EmptyState, ErrorState, InlineConfirm, LoadingBlock, Segmented, useToast } from "../components/ui";
import { initials } from "../format";
import { HINTS } from "../hints";
import { useFresh } from "../fresh";

export type ShownLink = { personId: string; kind: "invite" | "telegram"; url: string };

export function absoluteUrl(url: string): string {
  return url.startsWith("/") ? `${window.location.origin}${url}` : url;
}

function roleText(person: DirectoryUser): string {
  if (person.role === "owner" || person.is_owner) return "Владелец";
  if (person.role === "admin") return "Админ";
  return "Участник";
}

function statusPill(person: DirectoryUser): { tone: string; text: string } {
  if (person.invite_pending) return { tone: "soon", text: "ещё не вошёл" };
  return person.telegram_linked ? { tone: "paid", text: "Telegram привязан" } : { tone: "neutral", text: "Telegram не привязан" };
}

export function PeoplePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const [people, setPeople] = useState<DirectoryUser[]>([]);
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<"active" | "all">("active");
  const [error, setError] = useState<string | null>(null);
  const [shown, setShown] = useState<ShownLink | null>(
    () => (location.state as { shown?: ShownLink } | null)?.shown ?? null,
  );
  const [confirmOff, setConfirmOff] = useState<string | null>(null);
  const [confirmUnlink, setConfirmUnlink] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);

  const fresh = useFresh();
  const load = useCallback(async () => {
    setPeople(await api<DirectoryUser[]>("/api/v1/users"));
  }, []);

  useEffect(() => {
    load()
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Не загрузилось"))
      .finally(() => setReady(true));
  }, [load, fresh]);

  async function run(action: () => Promise<void>, fallback: string) {
    setBusy(true);
    setError(null);
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

  function showInvite(person: DirectoryUser, renew: boolean) {
    void run(async () => {
      const body = await api<InviteLink>(`/api/v1/users/${person.id}/invite`, { method: renew ? "POST" : "GET" });
      setShown({ personId: person.id, kind: "invite", url: absoluteUrl(body.url) });
      if (renew) toast?.push("Новая ссылка готова, старая больше не работает");
    }, "Ссылку получить не удалось");
  }

  function showTelegram(person: DirectoryUser, renew: boolean) {
    void run(async () => {
      const body = await api<TelegramLink>(`/api/v1/users/${person.id}/telegram-link`, { method: renew ? "POST" : "GET" });
      setShown({ personId: person.id, kind: "telegram", url: body.url });
      if (renew) toast?.push("Новая ссылка готова, старая больше не работает");
    }, "Ссылку получить не удалось");
  }

  function unlink(person: DirectoryUser) {
    void run(async () => {
      await api(`/api/v1/users/${person.id}/telegram`, { method: "DELETE" });
      setConfirmUnlink(null);
      toast?.push("Telegram отвязан");
      await load();
    }, "Не получилось отвязать");
  }

  function deactivate(person: DirectoryUser) {
    void run(async () => {
      await api(`/api/v1/users/${person.id}`, { method: "DELETE" });
      if (shown?.personId === person.id) setShown(null);
      await load();
    }, "Не получилось отключить");
  }

  const list = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return people.filter((person) => {
      if (scope === "active" && !person.is_active) return false;
      if (!needle) return true;
      return person.full_name.toLowerCase().includes(needle) || person.email.toLowerCase().includes(needle);
    });
  }, [people, query, scope]);

  return (
    <div className="page">
      <PageControls
        left={
          <label className="tb-search">
            <Search size={16} strokeWidth={1.75} aria-hidden />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Имя или почта"
              aria-label="Поиск по людям"
            />
          </label>
        }
        center={
          <Segmented
            label="Кого показать"
            value={scope}
            options={[
              { value: "active", label: "Активные", hint: HINTS.peopleActive },
              { value: "all", label: "Все", hint: HINTS.peopleAll },
            ]}
            onChange={setScope}
          />
        }
        right={
          <button type="button" className="primary" data-hint={HINTS.personNew} onClick={() => navigate("/people/new")}>
            <UserPlus size={16} strokeWidth={2} aria-hidden />
            Добавить человека
          </button>
        }
      />
      {error && <ErrorState message={error} onRetry={() => void load().catch(() => undefined)} />}
      {!ready && <LoadingBlock label="Загружаем людей…" />}
      {ready && list.length === 0 && (
        <EmptyState
          icon={query ? SearchX : Users}
          title={query ? "Никого не нашли" : "Людей пока нет"}
          action={
            query ? (
              <button type="button" className="ghost" data-hint={HINTS.searchClear} onClick={() => setQuery("")}>
                Очистить поиск
              </button>
            ) : (
              <button type="button" className="primary" data-hint={HINTS.personNew} onClick={() => navigate("/people/new")}>
                Добавить человека
              </button>
            )
          }
        >
          {query
            ? "Проверьте имя или почту."
            : "Пригласите коллег: они получат доступ к отделу и смогут отмечать оплаты."}
        </EmptyState>
      )}
      <div className="row-list">
        {list.map((person) => {
          const pill = statusPill(person);
          return (
            <article key={person.id} className={person.is_active ? "row-card" : "row-card is-muted"}>
              <span className="avatar" aria-hidden="true">
                {initials(person.full_name)}
              </span>
              <div className="row-main">
                <div className="row-title">
                  <h3>{person.full_name}</h3>
                  <span className="pill pill-neutral">{roleText(person)}</span>
                  {!person.is_active && <span className="pill pill-overdue">отключён</span>}
                </div>
                <p className="row-meta">{person.email}</p>
                <p className="row-meta">
                  {person.departments.length ? `Отделы: ${person.departments.map((row) => row.name).join(", ")}` : "Без отдела"}
                </p>
              </div>
              <span className={`pill pill-${pill.tone} row-value`}>{pill.text}</span>
              {!person.is_owner && person.is_active && (
                <div className="row-actions">
                  {confirmOff === person.id ? (
                    <InlineConfirm
                      title={`Отключить ${person.full_name}? Вход и напоминания прекратятся.`}
                      confirmLabel="Отключить"
                      busy={busy}
                      onConfirm={() => {
                        setConfirmOff(null);
                        deactivate(person);
                      }}
                      onCancel={() => setConfirmOff(null)}
                    />
                  ) : confirmUnlink === person.id ? (
                    <InlineConfirm
                      title={`Отвязать Telegram у ${person.full_name}? «Оплачено» в чате перестанет записываться на него.`}
                      confirmLabel="Отвязать"
                      busy={busy}
                      onConfirm={() => unlink(person)}
                      onCancel={() => setConfirmUnlink(null)}
                    />
                  ) : (
                    <>
                      {person.invite_pending ? (
                        <>
                          <button type="button" className="ghost" disabled={busy} data-hint={HINTS.inviteShow} onClick={() => showInvite(person, false)}>
                            Ссылка-приглашение
                          </button>
                          <button type="button" className="ghost" disabled={busy} data-hint={HINTS.linkRenew} onClick={() => showInvite(person, true)}>
                            Новая ссылка
                          </button>
                        </>
                      ) : person.telegram_linked ? (
                        <button type="button" className="ghost" data-hint={HINTS.personUnlinkTg} onClick={() => setConfirmUnlink(person.id)}>
                          Отвязать Telegram
                        </button>
                      ) : (
                        <>
                          <button type="button" className="ghost" disabled={busy} data-hint={HINTS.personTgLink} onClick={() => showTelegram(person, false)}>
                            Ссылка на Telegram
                          </button>
                          <button type="button" className="ghost" disabled={busy} data-hint={HINTS.linkRenew} onClick={() => showTelegram(person, true)}>
                            Новая ссылка
                          </button>
                        </>
                      )}
                      <button type="button" className="ghost" data-hint={HINTS.personDeactivate} onClick={() => setConfirmOff(person.id)}>
                        Отключить
                      </button>
                    </>
                  )}
                </div>
              )}
              {shown?.personId === person.id && (
                <div className="link-box row-link">
                  <p className="desc">
                    {shown.kind === "invite"
                      ? "Ссылка-приглашение: человек задаёт пароль и входит. Работает до использования или до новой ссылки. Письмо не уходит — отправьте её сами."
                      : "Ссылка привязки Telegram: открыть в Telegram и нажать «Старт». Работает до использования или до новой ссылки."}
                  </p>
                  <a href={shown.url} target="_blank" rel="noreferrer">
                    {shown.url}
                  </a>
                  <div className="row-actions">
                    <button type="button" className="ghost" data-hint={HINTS.copyLink} onClick={() => void copy(shown.url)}>
                      Скопировать
                    </button>
                    <button type="button" className="ghost" data-hint={HINTS.hide} onClick={() => setShown(null)}>
                      Скрыть
                    </button>
                  </div>
                </div>
              )}
            </article>
          );
        })}
      </div>
    </div>
  );
}
