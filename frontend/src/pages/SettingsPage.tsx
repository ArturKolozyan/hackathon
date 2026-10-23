import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type TeamTelegram, type TelegramLink, type TelegramSelf } from "../api";
import { useAuth } from "../auth";

function personLabel(self: TelegramSelf): string {
  if (self.username) return `@${self.username}`;
  return self.display_name || "Telegram привязан";
}

export function SettingsPage() {
  const { user } = useAuth();
  const admin = user?.role === "admin";
  const [self, setSelf] = useState<TelegramSelf | null>(null);
  const [team, setTeam] = useState<TeamTelegram | null>(null);
  const [personalLink, setPersonalLink] = useState<TelegramLink | null>(null);
  const [teamLink, setTeamLink] = useState<TelegramLink | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmUnlink, setConfirmUnlink] = useState(false);
  const [confirmTeam, setConfirmTeam] = useState(false);

  const load = useCallback(async () => {
    const me = await api<TelegramSelf>("/api/v1/me/telegram");
    setSelf(me);
    if (me.linked) setPersonalLink(null);
    if (admin) {
      const status = await api<TeamTelegram>("/api/v1/telegram/status");
      setTeam(status);
      if (status.status === "connected" && status.source === "database") setTeamLink(null);
    }
  }, [admin]);

  useEffect(() => {
    load().catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Не загрузилось"));
  }, [load]);

  useEffect(() => {
    if (!personalLink && !teamLink && !team?.test_pending) return;
    const timer = window.setInterval(() => {
      load().catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [load, personalLink, teamLink, team?.test_pending]);

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

  async function copy(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      setNotice("Ссылка скопирована");
    } catch {
      setNotice("Скопируйте ссылку вручную");
    }
  }

  const teamLabel =
    team?.status === "connected"
      ? team.chat_title || (team.source === "env" ? "Чат из настроек сервера" : "Чат подключён")
      : team?.status === "disconnected"
        ? team.chat_title
          ? `Бот удалён из «${team.chat_title}»`
          : "Чат отключён"
        : "Чат не подключён";

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="kicker">Настройки</p>
          <h1>Telegram</h1>
        </div>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && <p className="caption">{notice}</p>}
      <div className="stack">
        <section className="panel settings-card">
          <div className="row-between">
            <h2>Личный аккаунт</h2>
            <span className={`pill ${self?.linked ? "pill-paid" : "pill-neutral"}`}>
              {self?.linked ? "привязан" : "не привязан"}
            </span>
          </div>
          <p className="desc">
            {self?.linked
              ? `${personLabel(self)}. Кнопка «Оплачено» записывается на вас.`
              : "Привяжите Telegram, чтобы закрывать платежи из чата своим именем."}
          </p>
          {self?.linked ? (
            <div className="row-actions">
              {confirmUnlink ? (
                <>
                  <button type="button" className="primary" disabled={busy} onClick={() => run(async () => {
                    setSelf(await api<TelegramSelf>("/api/v1/me/telegram", { method: "DELETE" }));
                    setConfirmUnlink(false);
                  })}>
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
            </div>
          ) : (
            <div className="row-actions">
              <button
                type="button"
                className="primary"
                disabled={busy || self?.bot_ready === false}
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
          {self && !self.bot_ready && (
            <p className="desc">Бот ещё не на связи. Нужен TELEGRAM_BOT_TOKEN и запущенный worker.</p>
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
          <div className="row-between">
            <div>
              <strong>Личные напоминания</strong>
              <p className="desc">Если вы ответственный и срок близко — дубль в личку.</p>
            </div>
            <button
              type="button"
              className="ghost"
              aria-pressed={self?.reminders_enabled ?? true}
              disabled={!self || busy}
              onClick={() =>
                run(async () => {
                  setSelf(
                    await api<TelegramSelf>("/api/v1/me/notifications", {
                      method: "PATCH",
                      body: JSON.stringify({ telegram_reminders: !self?.reminders_enabled }),
                    }),
                  );
                })
              }
            >
              {self?.reminders_enabled ? "Включены" : "Выключены"}
            </button>
          </div>
        </section>

        {admin && (
          <section className="panel settings-card">
            <div className="row-between">
              <h2>Чат команды</h2>
              <span className={`pill ${team?.status === "connected" ? "pill-paid" : "pill-neutral"}`}>
                {team?.status === "connected" ? "подключён" : team?.status === "disconnected" ? "отключено" : "не подключён"}
              </span>
            </div>
            <p className="desc">{teamLabel}</p>
            {team?.source === "env" && (
              <p className="desc">Сейчас напоминания идут в чат из TELEGRAM_CHAT_ID. Подключение из веба его заменит.</p>
            )}
            <div className="row-actions">
              <button
                type="button"
                className="primary"
                disabled={busy || team?.bot_ready === false}
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
                disabled={busy || team?.status !== "connected" || team.test_pending}
                onClick={() =>
                  run(async () => {
                    setTeam(await api<TeamTelegram>("/api/v1/telegram/team-chat/test", { method: "POST" }));
                    setNotice("Сообщение уйдёт в чат в ближайшие секунды");
                  })
                }
              >
                {team?.test_pending ? "Отправляем…" : "Отправить тестовое"}
              </button>
              {team?.status === "connected" &&
                (confirmTeam ? (
                  <>
                    <button
                      type="button"
                      className="ghost"
                      disabled={busy}
                      onClick={() =>
                        run(async () => {
                          setTeam(await api<TeamTelegram>("/api/v1/telegram/team-chat", { method: "DELETE" }));
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
            {team && !team.bot_ready && (
              <p className="desc">Бот ещё не представился. Подождите, пока worker вызовет getMe.</p>
            )}
            {team?.test_error && <p className="error">{team.test_error}</p>}
            {team?.test_sent_at && !team.test_pending && !team.test_error && (
              <p className="desc">Тестовое отправлено.</p>
            )}
            {teamLink && (
              <div className="link-box">
                <p className="desc">Ссылка действует 15 минут. Добавьте бота в группу.</p>
                <a href={teamLink.url} target="_blank" rel="noreferrer">
                  Открыть в Telegram
                </a>
                <button type="button" className="ghost" onClick={() => copy(teamLink.url)}>
                  Скопировать
                </button>
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
