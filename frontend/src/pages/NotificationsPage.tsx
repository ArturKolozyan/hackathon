import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  api,
  type NotificationsView,
  type Probe,
  type TeamTelegram,
  type TelegramLink,
  type TelegramSelf,
} from "../api";
import { SelectField } from "../components/fields";
import { ErrorState, LoadingBlock, useToast } from "../components/ui";

function personLabel(self: NotificationsView["telegram"]): string {
  if (self.username) return `@${self.username}`;
  return self.display_name || "Telegram привязан";
}

function toggleId(list: string[], id: string): string[] {
  return list.includes(id) ? list.filter((item) => item !== id) : [...list, id];
}

export function NotificationsPage() {
  const toast = useToast();
  const [data, setData] = useState<NotificationsView | null>(null);
  const [emailOn, setEmailOn] = useState(true);
  const [emailTeams, setEmailTeams] = useState<string[]>([]);
  const [tgOn, setTgOn] = useState(true);
  const [tgTeams, setTgTeams] = useState<string[]>([]);
  const [scope, setScope] = useState<"mine" | "department">("mine");
  const [overdueOn, setOverdueOn] = useState(true);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [personalLink, setPersonalLink] = useState<TelegramLink | null>(null);
  const [teamLink, setTeamLink] = useState<TelegramLink | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirmUnlink, setConfirmUnlink] = useState(false);
  const [confirmTeam, setConfirmTeam] = useState(false);

  const apply = useCallback((next: NotificationsView) => {
    setData(next);
    setEmailOn(next.email.enabled);
    setEmailTeams(next.email.team_ids);
    setTgOn(next.telegram.enabled);
    setTgTeams(next.telegram.team_ids);
    setScope(next.telegram.notify_scope || "mine");
    setOverdueOn(next.telegram.notify_overdue);
    setWebhookUrl(next.team.webhook_url ?? "");
    if (next.telegram.linked) setPersonalLink(null);
    if (next.team.telegram.status === "connected" && next.team.telegram.source === "database") setTeamLink(null);
  }, []);

  const load = useCallback(async () => {
    const next = await api<NotificationsView>("/api/v1/notifications");
    apply(next);
  }, [apply]);

  useEffect(() => {
    load()
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Не загрузилось"))
      .finally(() => setReady(true));
  }, [load]);

  const pending = Boolean(personalLink || teamLink || data?.telegram.test_pending || data?.team.telegram.test_pending);
  useEffect(() => {
    if (!pending) return;
    const timer = window.setInterval(() => {
      load().catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [load, pending]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не получилось");
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

  async function savePersonal() {
    await run(async () => {
      apply(
        await api<NotificationsView>("/api/v1/notifications/personal", {
          method: "PATCH",
          body: JSON.stringify({
            email_enabled: emailOn,
            email_team_ids: emailTeams,
            telegram_enabled: tgOn,
            telegram_team_ids: tgTeams,
            notify_scope: scope,
            notify_overdue: overdueOn,
          }),
        }),
      );
      toast?.push("Личные каналы сохранены");
    });
  }

  if (!data && error) {
    return (
      <div className="page">
        <ErrorState message={error} onRetry={() => void load().catch(() => undefined)} />
      </div>
    );
  }
  if (!ready || !data) {
    return (
      <div className="page">
        <LoadingBlock label="Загружаем уведомления…" />
      </div>
    );
  }

  const teamTg = data.team.telegram;
  const manage = data.team.can_manage;
  const teamLabel =
    teamTg.status === "connected"
      ? teamTg.chat_title || (teamTg.source === "env" ? "Чат из настроек сервера" : "Чат подключён")
      : teamTg.status === "disconnected"
        ? "Чат отключён"
        : "Чат не подключён";

  return (
    <div className="page">
      {error && <ErrorState message={error} onRetry={() => void load().catch(() => undefined)} />}
      <div className="stack">
        <section className="panel settings-card">
          <div className="row-between">
            <h2>Личный Telegram</h2>
            <span className={`pill ${data.telegram.linked ? "pill-paid" : "pill-neutral"}`}>
              {data.telegram.linked ? "привязан" : "не привязан"}
            </span>
          </div>
          <p className="desc">
            {data.telegram.linked
              ? `${personLabel(data.telegram)}. Кнопка «Оплачено» записывается на вас.`
              : "Привяжите Telegram, чтобы закрывать платежи из чата своим именем и получать личные напоминания."}
          </p>
          <p className="desc">По платежам, где вы ответственный, напоминание в личку приходит всегда, если Telegram привязан.</p>
          {data.telegram.linked ? (
            <div className="row-actions">
              {confirmUnlink ? (
                <>
                  <button
                    type="button"
                    className="primary"
                    disabled={busy}
                    onClick={() =>
                      run(async () => {
                        await api<TelegramSelf>("/api/v1/me/telegram", { method: "DELETE" });
                        setConfirmUnlink(false);
                        await load();
                      })
                    }
                  >
                    Отвязать
                  </button>
                  <button type="button" className="ghost" onClick={() => setConfirmUnlink(false)}>
                    Отмена
                  </button>
                </>
              ) : (
                <button type="button" className="ghost" onClick={() => setConfirmUnlink(true)}>
                  Отвязать
                </button>
              )}
              <button
                type="button"
                className="outline"
                disabled={busy || data.telegram.test_pending}
                onClick={() =>
                  run(async () => {
                    const probe = await api<Probe>("/api/v1/notifications/personal/telegram/test", { method: "POST" });
                    toast?.push(probe.detail);
                    await load();
                  })
                }
              >
                {data.telegram.test_pending ? "Отправляем…" : "Отправить тестовое"}
              </button>
            </div>
          ) : (
            <div className="row-actions">
              <button
                type="button"
                className="primary"
                disabled={busy || !data.telegram.bot_ready}
                onClick={() =>
                  run(async () => {
                    setPersonalLink(await api<TelegramLink>("/api/v1/me/telegram/link", { method: "POST" }));
                  })
                }
              >
                Привязать Telegram
              </button>
            </div>
          )}
          {!data.telegram.bot_ready && (
            <p className="desc">Telegram не настроен или бот не запущен. Остальные каналы и панель работают.</p>
          )}
          {data.telegram.bot_ready && (
            <p className="desc">{data.telegram.bot_alive ? "Бот на связи." : "Бот не отвечает. Напоминания в Telegram копятся и уйдут, когда он поднимется."}</p>
          )}
          {data.telegram.test_error && (
            <p className="error" role="alert">
              {data.telegram.test_error}
            </p>
          )}
          {personalLink && (
            <div className="link-box">
              <p className="desc">Ссылка действует 15 минут. Откройте её в Telegram.</p>
              <a href={personalLink.url} target="_blank" rel="noreferrer">
                Открыть в Telegram
              </a>
              <button type="button" className="ghost" onClick={() => copy(personalLink.url)}>
                Скопировать
              </button>
            </div>
          )}
          <div className="check-row">
            <label>
              <input type="checkbox" checked={tgOn} onChange={(event) => setTgOn(event.target.checked)} />
              Личные сообщения в Telegram
            </label>
          </div>
          <label>
            Какие платежи
            <SelectField
              value={scope}
              onChange={(value) => setScope(value as "mine" | "department")}
              options={[
                { value: "mine", label: "Только мои" },
                { value: "department", label: "Все платежи отдела" },
              ]}
            />
          </label>
          <div className="check-row">
            <label>
              <input type="checkbox" checked={overdueOn} onChange={(event) => setOverdueOn(event.target.checked)} />
              Писать о просрочке
            </label>
          </div>
          <TeamChecks teams={data.teams} selected={tgTeams} onToggle={(id) => setTgTeams(toggleId(tgTeams, id))} />
        </section>

        <section className="panel settings-card">
          <div className="row-between">
            <h2>Почта</h2>
            <span className="muted">{data.email.address}</span>
          </div>
          <p className="desc">Письма уходят на почту аккаунта через SMTP. Адрес меняется в профиле. Кнопка ниже сохраняет и Telegram, и почту.</p>
          <div className="check-row">
            <label>
              <input type="checkbox" checked={emailOn} onChange={(event) => setEmailOn(event.target.checked)} />
              Получать по выбранным командам
            </label>
          </div>
          <TeamChecks teams={data.teams} selected={emailTeams} onToggle={(id) => setEmailTeams(toggleId(emailTeams, id))} />
          <div className="row-actions">
            <button type="button" className="primary" disabled={busy} onClick={() => void savePersonal()}>
              Сохранить
            </button>
            <button
              type="button"
              className="outline"
              disabled={busy}
              onClick={() =>
                run(async () => {
                  const probe = await api<Probe>("/api/v1/notifications/personal/email/test", { method: "POST" });
                  toast?.push(probe.detail);
                })
              }
            >
              Отправить тестовое
            </button>
          </div>
        </section>

        <section className="panel settings-card">
          <div className="row-between">
            <h2>Чат команды · {data.team.team_name}</h2>
            <span className={`pill ${teamTg.status === "connected" ? "pill-paid" : "pill-neutral"}`}>
              {teamTg.status === "connected" ? "подключён" : teamTg.status === "disconnected" ? "отключено" : "не подключён"}
            </span>
          </div>
          <p className="desc">{teamLabel}</p>
          {!manage && <p className="desc">Подключает владелец или админ. Участник видит канал только для чтения.</p>}
          {teamTg.source === "env" && (
            <p className="desc">Сейчас напоминания идут в чат из TELEGRAM_CHAT_ID. Подключение из веба его заменит.</p>
          )}
          {manage && (
            <div className="row-actions">
              <button
                type="button"
                className="primary"
                disabled={busy || !teamTg.bot_ready}
                onClick={() =>
                  run(async () => {
                    setTeamLink(await api<TelegramLink>("/api/v1/telegram/team-chat/link", { method: "POST" }));
                  })
                }
              >
                Подключить чат команды
              </button>
              <button
                type="button"
                className="outline"
                disabled={busy || teamTg.status !== "connected" || teamTg.test_pending}
                onClick={() =>
                  run(async () => {
                    const next = await api<TeamTelegram>("/api/v1/telegram/team-chat/test", { method: "POST" });
                    setData({ ...data, team: { ...data.team, telegram: next } });
                    toast?.push("Сообщение уйдёт в чат в ближайшие секунды");
                  })
                }
              >
                {teamTg.test_pending ? "Отправляем…" : "Отправить тестовое"}
              </button>
              {teamTg.status === "connected" &&
                (confirmTeam ? (
                  <>
                    <button
                      type="button"
                      className="ghost"
                      disabled={busy}
                      onClick={() =>
                        run(async () => {
                          const next = await api<TeamTelegram>("/api/v1/telegram/team-chat", { method: "DELETE" });
                          setData({ ...data, team: { ...data.team, telegram: next } });
                          setConfirmTeam(false);
                        })
                      }
                    >
                      Отключить
                    </button>
                    <button type="button" className="ghost" onClick={() => setConfirmTeam(false)}>
                      Отмена
                    </button>
                  </>
                ) : (
                  <button type="button" className="ghost" onClick={() => setConfirmTeam(true)}>
                    Отключить
                  </button>
                ))}
            </div>
          )}
          {teamTg.test_error && (
            <p className="error" role="alert">
              {teamTg.test_error}
            </p>
          )}
          {teamLink && (
            <div className="link-box">
              <p className="desc">Ссылка действует 15 минут. Добавьте бота в группу. В чат придёт одна сводка, не карточки по всем платежам.</p>
              <a href={teamLink.url} target="_blank" rel="noreferrer">
                Открыть в Telegram
              </a>
              <button type="button" className="ghost" onClick={() => copy(teamLink.url)}>
                Скопировать
              </button>
            </div>
          )}
        </section>

        <section className="panel settings-card">
          <h2>Webhook команды</h2>
          <p className="desc">POST JSON на адрес команды: напоминание, просрочка, оплата. «Проверить» шлёт тестовое событие.</p>
          <form
            className="pay-form"
            onSubmit={(event) => {
              event.preventDefault();
              if (!manage) return;
              void run(async () => {
                apply(
                  await api<NotificationsView>("/api/v1/notifications/team/webhook", {
                    method: "PUT",
                    body: JSON.stringify({ url: webhookUrl }),
                  }),
                );
                toast?.push(webhookUrl.trim() ? "Webhook сохранён" : "Webhook снят");
              });
            }}
          >
            <label>
              URL
              <input
                value={webhookUrl}
                onChange={(event) => setWebhookUrl(event.target.value)}
                placeholder="https://hooks.example/rekeeper"
                disabled={!manage}
                inputMode="url"
              />
            </label>
            {manage && (
              <div className="row-actions">
                <button type="submit" className="primary" disabled={busy}>
                  Сохранить
                </button>
                <button
                  type="button"
                  className="outline"
                  disabled={busy || !data.team.webhook_url}
                  onClick={() =>
                    run(async () => {
                      const probe = await api<Probe>("/api/v1/notifications/team/webhook/test", { method: "POST" });
                      toast?.push(probe.detail);
                      await load();
                    })
                  }
                >
                  Проверить
                </button>
                <button
                  type="button"
                  className="ghost"
                  disabled={busy || !data.team.webhook_url}
                  onClick={() =>
                    run(async () => {
                      const probe = await api<Probe>("/api/v1/notifications/team/webhook/test", { method: "POST" });
                      toast?.push(probe.detail);
                      await load();
                    })
                  }
                >
                  Отправить тестовое
                </button>
              </div>
            )}
          </form>
          {data.team.webhook_check_error && (
            <p className="error" role="alert">
              {data.team.webhook_check_error}
            </p>
          )}
          {data.team.webhook_checked_at && !data.team.webhook_check_error && (
            <p className="desc">Последняя проверка прошла.</p>
          )}
        </section>
      </div>
    </div>
  );
}

function TeamChecks({
  teams,
  selected,
  onToggle,
}: {
  teams: NotificationsView["teams"];
  selected: string[];
  onToggle: (id: string) => void;
}) {
  if (teams.length === 0) return <p className="desc">Вы ещё не в команде.</p>;
  return (
    <div className="check-row">
      {teams.map((team) => (
        <label key={team.id}>
          <input type="checkbox" checked={selected.includes(team.id)} onChange={() => onToggle(team.id)} />
          {team.name}
        </label>
      ))}
    </div>
  );
}
