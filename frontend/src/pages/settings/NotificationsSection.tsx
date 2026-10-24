import { useCallback, useEffect, useRef, useState } from "react";
import { Send } from "lucide-react";
import {
  ApiError,
  api,
  type EmailTeam,
  type NotificationsView,
  type Probe,
  type TeamTelegram,
  type TelegramLink,
  type TelegramSelf,
} from "../../api";
import { SelectField } from "../../components/fields";
import { RowInput, SettingGroup, SettingRow, SwitchRow } from "../../components/SettingRow";
import { ErrorState, LoadingBlock, SaveStatus, useDebounced, useSaveState, useToast } from "../../components/ui";
import { HINTS } from "../../hints";
import { useFresh } from "../../fresh";

type Personal = {
  emailOn: boolean;
  tgOn: boolean;
  scope: "mine" | "department";
  overdueOn: boolean;
};

function personalOf(view: NotificationsView): Personal {
  return {
    emailOn: view.email.enabled,
    tgOn: view.telegram.enabled,
    scope: view.telegram.notify_scope || "mine",
    overdueOn: view.telegram.notify_overdue,
  };
}

function personLabel(self: NotificationsView["telegram"]): string {
  if (self.username) return `@${self.username}`;
  return self.display_name || "аккаунт Telegram";
}

const timeFormat = new Intl.DateTimeFormat("ru-RU", {
  timeZone: "Europe/Moscow",
  day: "2-digit",
  month: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

export function webhookError(url: string): string | null {
  const value = url.trim();
  if (!value) return null;
  if (!/^https:\/\//i.test(value)) return "Ссылка должна начинаться с https://";
  try {
    new URL(value);
  } catch {
    return "Похоже, в ссылке ошибка";
  }
  return null;
}

/** Telegram, email, team chat and webhook groups of Settings. Every control saves instantly. */
export function NotificationsSection() {
  const toast = useToast();
  const [data, setData] = useState<NotificationsView | null>(null);
  const [personal, setPersonal] = useState<Personal | null>(null);
  const [webhookOn, setWebhookOn] = useState(false);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [personalLink, setPersonalLink] = useState<TelegramLink | null>(null);
  const [teamLink, setTeamLink] = useState<TelegramLink | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmUnlink, setConfirmUnlink] = useState(false);
  const [confirmTeam, setConfirmTeam] = useState(false);
  const [mailTeamId, setMailTeamId] = useState<string | null>(null);
  const webhookDirty = useRef(false);
  const tgSave = useSaveState();
  const mailSave = useSaveState();
  const hookSave = useSaveState();

  const apply = useCallback((next: NotificationsView) => {
    setData(next);
    setPersonal(personalOf(next));
    if (!webhookDirty.current) {
      setWebhookUrl(next.team.webhook_url ?? "");
      setWebhookOn(Boolean(next.team.webhook_url));
    }
    if (next.telegram.linked) setPersonalLink(null);
    if (next.team.telegram.status === "connected" && next.team.telegram.source === "database") setTeamLink(null);
  }, []);

  const fresh = useFresh();
  const load = useCallback(async () => {
    apply(await api<NotificationsView>("/api/v1/notifications"));
  }, [apply]);

  useEffect(() => {
    load().catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Не загрузилось"));
  }, [load, fresh]);

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
    setActionError(null);
    try {
      await action();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Не получилось");
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

  /** Optimistic personal-channel change: update UI, PATCH, roll back on failure. */
  function savePersonal(patch: Partial<Personal>, save: typeof tgSave) {
    if (!personal) return;
    const before = personal;
    const next = { ...personal, ...patch };
    setPersonal(next);
    void save.run(
      async () => {
        apply(
          await api<NotificationsView>("/api/v1/notifications/personal", {
            method: "PATCH",
            body: JSON.stringify({
              email_enabled: next.emailOn,
              telegram_enabled: next.tgOn,
              notify_scope: next.scope,
              notify_overdue: next.overdueOn,
            }),
          }),
        );
      },
      () => setPersonal(before),
    );
  }

  /** Письма по одному отделу: тумблер и охват. Оптимистично, с откатом. */
  function saveMailTeam(team: EmailTeam, patch: Partial<Pick<EmailTeam, "enabled" | "scope">>) {
    if (!data) return;
    const before = data;
    const next = { ...team, ...patch };
    setData({
      ...data,
      email: { ...data.email, teams: data.email.teams.map((row) => (row.id === team.id ? next : row)) },
    });
    void mailSave.run(
      async () => {
        apply(
          await api<NotificationsView>(`/api/v1/notifications/personal/email/teams/${team.id}`, {
            method: "PUT",
            body: JSON.stringify({ enabled: next.enabled, scope: next.scope }),
          }),
        );
      },
      () => setData(before),
    );
  }

  function saveWebhook(url: string, rollback?: () => void) {
    void hookSave.run(async () => {
      apply(
        await api<NotificationsView>("/api/v1/notifications/team/webhook", {
          method: "PUT",
          body: JSON.stringify({ url: url.trim() }),
        }),
      );
      webhookDirty.current = false;
    }, rollback);
  }

  const urlSaver = useDebounced<string>((url) => {
    if (webhookError(url) || !url.trim()) return;
    if (url.trim() === (data?.team.webhook_url ?? "")) {
      webhookDirty.current = false;
      return;
    }
    saveWebhook(url);
  }, 800);

  if (!data && error) return <ErrorState message={error} onRetry={() => void load().catch(() => undefined)} />;
  if (!data || !personal) return <LoadingBlock label="Загружаем уведомления…" />;

  const teamTg = data.team.telegram;
  const manage = data.team.can_manage;
  const mailTeams = data.email.teams;
  const mailTeam =
    mailTeams.find((team) => team.id === mailTeamId) ??
    mailTeams.find((team) => team.id === data.team.team_id) ??
    mailTeams[0] ??
    null;
  const urlProblem = webhookError(webhookUrl);
  const tgReady = data.telegram.bot_ready;

  return (
    <>
      {actionError && <ErrorState message={actionError} />}

      <SettingGroup id="notifications" title="Telegram" status={<SaveStatus save={tgSave} />}>
        <SettingRow
          title="Привязка"
          description={
            data.telegram.linked
              ? `Привязан: ${personLabel(data.telegram)}. «Оплачено» в чате отдела записывается на вас, личные напоминания приходят сюда`
              : "Одна привязка на всё: «Оплачено» в чате отдела записывается на вас, личные напоминания приходят в Telegram"
          }
          hint={
            !tgReady
              ? "Бот не настроен или не запущен. Остальные каналы работают."
              : !data.telegram.bot_alive
                ? "Бот не отвечает. Напоминания копятся и уйдут, когда он поднимется."
                : undefined
          }
          control={
            data.telegram.linked ? (
              confirmUnlink ? (
                <div className="row-actions">
                  <button
                    type="button"
                    className="ghost danger"
                    disabled={busy}
                    data-hint={HINTS.tgUnlinkConfirm}
                    onClick={() =>
                      run(async () => {
                        await api<TelegramSelf>("/api/v1/me/telegram", { method: "DELETE" });
                        setConfirmUnlink(false);
                        await load();
                      })
                    }
                  >
                    Да, отвязать
                  </button>
                  <button type="button" className="ghost" data-hint={HINTS.cancel} onClick={() => setConfirmUnlink(false)}>
                    Отмена
                  </button>
                </div>
              ) : (
                <button type="button" className="ghost" data-hint={HINTS.tgUnlink} onClick={() => setConfirmUnlink(true)}>
                  Отвязать
                </button>
              )
            ) : (
              <button
                type="button"
                className="primary"
                data-hint={HINTS.tgLink}
                disabled={busy || !tgReady}
                onClick={() =>
                  run(async () => {
                    setPersonalLink(await api<TelegramLink>("/api/v1/me/telegram/link", { method: "POST" }));
                  })
                }
              >
                Привязать
              </button>
            )
          }
        >
          {personalLink && (
            <div className="link-box">
              <p className="desc">Откройте ссылку в Telegram и нажмите «Старт». Она работает, пока ею не воспользуются.</p>
              <a href={personalLink.url} target="_blank" rel="noreferrer">
                Открыть в Telegram
              </a>
              <button type="button" className="ghost" data-hint={HINTS.copyLink} onClick={() => copy(personalLink.url)}>
                Скопировать
              </button>
            </div>
          )}
        </SettingRow>
        <SwitchRow
          title="Личные сообщения"
          description="Напоминания о сроках в личку. Выключение не отвязывает Telegram: «Оплачено» продолжит работать"
          checked={personal.tgOn}
          onChange={(tgOn) => savePersonal({ tgOn }, tgSave)}
        />
        <SettingRow
          title="Какие платежи"
          description="В Telegram: только те, где вы ответственный, или все платежи ваших отделов"
          control={
            <SelectField
              ariaLabel="Какие платежи"
              align="end"
              value={personal.scope}
              onChange={(value) => savePersonal({ scope: value as Personal["scope"] }, tgSave)}
              options={[
                { value: "mine", label: "Только мои" },
                { value: "department", label: "Все платежи отдела" },
              ]}
            />
          }
        />
        <SwitchRow
          title="Мне о просрочках"
          description="Каждый день, пока срок прошёл, а оплаты нет. Действует и для писем"
          checked={personal.overdueOn}
          onChange={(overdueOn) => savePersonal({ overdueOn }, tgSave)}
        />
        {data.telegram.linked && (
          <SettingRow
            title="Проверка"
            description="Пробное сообщение в ваш Telegram"
            error={data.telegram.test_error}
            control={
              <button
                type="button"
                className="ghost"
                data-hint={HINTS.tgTest}
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
            }
          />
        )}
      </SettingGroup>

      <SettingGroup title="Почта" status={<SaveStatus save={mailSave} />} aside={data.email.address}>
        <SwitchRow
          title="Письма о платежах"
          description="Главный выключатель писем на почту аккаунта. Адрес меняется в профиле"
          checked={personal.emailOn}
          onChange={(emailOn) => savePersonal({ emailOn }, mailSave)}
        />
        {mailTeam && (
          <SettingRow
            title="Отдел"
            description="Письма настраиваются отдельно для каждого отдела. Выберите отдел, ниже его настройки"
            control={
              <SelectField
                ariaLabel="Отдел для писем"
                align="end"
                value={mailTeam.id}
                onChange={setMailTeamId}
                options={mailTeams.map((team) => ({
                  value: team.id,
                  label: team.enabled ? team.name : `${team.name} (письма выключены)`,
                }))}
              />
            }
          />
        )}
        {mailTeam && (
          <fieldset className="set-sub" disabled={!personal.emailOn}>
            <legend className="set-sub-head">
              <span>Отдел «{mailTeam.name}»</span>
              <span className={mailTeam.enabled && personal.emailOn ? "pill pill-paid" : "pill pill-neutral"}>
                {!personal.emailOn ? "письма выключены везде" : mailTeam.enabled ? "письма приходят" : "письма выключены"}
              </span>
            </legend>
            <SwitchRow
              title="Письма по этому отделу"
              description={`Напоминания о сроках и просрочке по платежам отдела «${mailTeam.name}»`}
              checked={mailTeam.enabled}
              disabled={!personal.emailOn}
              onChange={(enabled) => saveMailTeam(mailTeam, { enabled })}
            />
            <SettingRow
              title="Какие платежи"
              description="Только те, где вы ответственный, или все платежи этого отдела"
              control={
                <SelectField
                  ariaLabel={`Какие платежи отдела «${mailTeam.name}»`}
                  align="end"
                  value={mailTeam.scope}
                  onChange={(value) => saveMailTeam(mailTeam, { scope: value as EmailTeam["scope"], enabled: true })}
                  options={[
                    { value: "mine", label: "Только мои" },
                    { value: "department", label: "Все платежи отдела" },
                  ]}
                />
              }
            />
          </fieldset>
        )}
        <SettingRow
          title="Проверка"
          description="Пробное письмо на почту аккаунта"
          control={
            <button
              type="button"
              className="ghost"
              data-hint={HINTS.mailTest}
              disabled={busy}
              onClick={() =>
                run(async () => {
                  const probe = await api<Probe>("/api/v1/notifications/personal/email/test", { method: "POST" });
                  toast?.push(probe.detail);
                })
              }
            >
              Отправить письмо
            </button>
          }
        />
      </SettingGroup>

      <SettingGroup
        id="team-chat"
        title={`Чат отдела «${data.team.team_name}»`}
        aside={
          <span className={`pill ${teamTg.status === "connected" ? "pill-paid" : "pill-neutral"}`}>
            {teamTg.status === "connected" ? "подключён" : teamTg.status === "disconnected" ? "отключён" : "не подключён"}
          </span>
        }
      >
        <SettingRow
          title={teamTg.status === "connected" ? teamTg.chat_title || "Чат подключён" : "Групповой чат"}
          description={
            manage
              ? "Раз в день в чат приходит одна сводка, а не карточки по всем платежам"
              : "Подключает владелец или админ отдела"
          }
          hint={teamTg.source === "env" ? "Сейчас сводки идут в чат из настроек сервера. Подключение отсюда его заменит." : undefined}
          control={
            manage ? (
              <button
                type="button"
                className={teamTg.status === "connected" ? "ghost" : "primary"}
                data-hint={HINTS.teamChatLink}
                disabled={busy || !teamTg.bot_ready}
                onClick={() =>
                  run(async () => {
                    setTeamLink(await api<TelegramLink>("/api/v1/telegram/team-chat/link", { method: "POST" }));
                  })
                }
              >
                {teamTg.status === "connected" ? "Другой чат" : "Подключить"}
              </button>
            ) : undefined
          }
        >
          {teamLink && (
            <div className="link-box">
              <p className="desc">
                Ссылка работает до использования или до новой. Добавьте бота в группу. В чат придёт одна сводка, не карточки по всем
                платежам.
              </p>
              <a href={teamLink.url} target="_blank" rel="noreferrer">
                Открыть в Telegram
              </a>
              <button type="button" className="ghost" data-hint={HINTS.copyLink} onClick={() => copy(teamLink.url)}>
                Скопировать
              </button>
            </div>
          )}
        </SettingRow>
        {manage && teamTg.status === "connected" && (
          <>
            <SettingRow
              title="Проверка"
              description="Пробное сообщение в чат отдела"
              error={teamTg.test_error}
              control={
                <button
                  type="button"
                  className="ghost"
                  data-hint={HINTS.teamChatTest}
                  disabled={busy || teamTg.test_pending}
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
              }
            />
            <SettingRow
              title="Отключить чат"
              description="Сводки в этот чат больше не придут"
              control={
                confirmTeam ? (
                  <div className="row-actions">
                    <button
                      type="button"
                      className="ghost danger"
                      disabled={busy}
                      data-hint={HINTS.teamChatOffConfirm}
                      onClick={() =>
                        run(async () => {
                          const next = await api<TeamTelegram>("/api/v1/telegram/team-chat", { method: "DELETE" });
                          setData({ ...data, team: { ...data.team, telegram: next } });
                          setConfirmTeam(false);
                        })
                      }
                    >
                      Да, отключить
                    </button>
                    <button type="button" className="ghost" data-hint={HINTS.cancel} onClick={() => setConfirmTeam(false)}>
                      Отмена
                    </button>
                  </div>
                ) : (
                  <button type="button" className="ghost danger" data-hint={HINTS.teamChatOff} onClick={() => setConfirmTeam(true)}>
                    Отключить
                  </button>
                )
              }
            />
          </>
        )}
      </SettingGroup>

      {manage && (
        <SettingGroup id="integrations" title="Уведомления в другие сервисы (вебхук)" status={<SaveStatus save={hookSave} />}>
          <SwitchRow
            title="Отправлять вебхук"
            description="Вставьте ссылку, которую выдал сервис (например, Zapier, Make, n8n или ваш CRM). Мы будем отправлять на неё событие, когда счёт просрочен или оплачен."
            checked={webhookOn}
            onChange={(on) => {
              setWebhookOn(on);
              if (on) return;
              urlSaver.cancel();
              webhookDirty.current = false;
              if (data.team.webhook_url) {
                const previous = webhookUrl;
                setWebhookUrl("");
                saveWebhook("", () => {
                  setWebhookOn(true);
                  setWebhookUrl(previous);
                });
              } else {
                setWebhookUrl("");
              }
            }}
          />
          {webhookOn && (
            <SettingRow
              title="Ссылка для событий"
              description={`Отдел «${data.team.team_name}»: напоминание, просрочка, оплата`}
              htmlFor="webhook-url"
              error={urlProblem}
              hint="Сохраняется сама, как только ссылка введена."
              wide
              control={
                <RowInput
                  id="webhook-url"
                  type="url"
                  inputMode="url"
                  value={webhookUrl}
                  placeholder="https://hooks.example.com/…"
                  invalid={Boolean(urlProblem)}
                  onChange={(value) => {
                    webhookDirty.current = true;
                    setWebhookUrl(value);
                    urlSaver.schedule(value);
                  }}
                  onBlur={() => urlSaver.flush()}
                />
              }
            />
          )}
          {webhookOn && data.team.webhook_url && (
            <SettingRow
              title="Последняя отправка"
              description={
                data.team.webhook_check_error
                  ? `Не прошла: ${data.team.webhook_check_error}`
                  : data.team.webhook_checked_at
                    ? `Прошла ${timeFormat.format(new Date(data.team.webhook_checked_at))}`
                    : "Событий ещё не было. Отправьте тестовое, чтобы проверить"
              }
              control={
                manage ? (
                  <button
                    type="button"
                    className="ghost"
                    data-hint={HINTS.webhookTest}
                    disabled={busy}
                    onClick={() =>
                      run(async () => {
                        const probe = await api<Probe>("/api/v1/notifications/team/webhook/test", { method: "POST" });
                        toast?.push(probe.detail);
                        await load();
                      })
                    }
                  >
                    <Send size={16} strokeWidth={1.75} aria-hidden />
                    Тестовое событие
                  </button>
                ) : undefined
              }
            />
          )}
        </SettingGroup>
      )}
    </>
  );
}
