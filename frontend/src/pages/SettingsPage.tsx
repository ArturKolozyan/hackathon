import { FormEvent, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ApiError, api, type Me, type Sent } from "../api";
import { useAuth } from "../auth";
import { PageControls } from "../components/PageControls";
import { RowInput, SettingGroup, SettingRow, SwitchRow } from "../components/SettingRow";
import { SaveStatus, useDebounced, useSaveState } from "../components/ui";
import { HINTS } from "../hints";
import { useTheme } from "../theme";
import { NotificationsSection } from "./settings/NotificationsSection";
import { OrganizationSection } from "./settings/OrganizationSection";

type Anchor = { id: string; label: string };

export function SettingsPage() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const anchors: Anchor[] = [
    { id: "profile", label: "Профиль" },
    ...(user?.is_owner ? [{ id: "organization", label: "Организация" }] : []),
    { id: "notifications", label: "Уведомления" },
    { id: "integrations", label: "Вебхук" },
    { id: "appearance", label: "Внешний вид" },
  ];

  useEffect(() => {
    const id = location.hash.replace("#", "");
    if (!id) return;
    const timer = window.setTimeout(() => document.getElementById(id)?.scrollIntoView({ block: "start" }), 120);
    return () => window.clearTimeout(timer);
  }, [location.hash]);

  return (
    <div className="page settings-page">
      <PageControls
        left={
          <nav className="tb-group chip-row" aria-label="Разделы настроек">
            {anchors.map((anchor) => (
              <button
                key={anchor.id}
                type="button"
                className="chip"
                data-hint={`${HINTS.settingsJump} «${anchor.label}»`}
                onClick={() => document.getElementById(anchor.id)?.scrollIntoView({ block: "start", behavior: "smooth" })}
              >
                {anchor.label}
              </button>
            ))}
          </nav>
        }
      />
      <div className="settings-stack">
        {user?.is_owner ? (
          <OwnerProfile />
        ) : (
          <Profile
            onPasswordChanged={() => {
              setUser(null);
              navigate("/login", { replace: true, state: { notice: "Пароль сменён. Войдите снова." } });
            }}
          />
        )}
        {user?.is_owner && <OrganizationSection />}
        <NotificationsSection />
        <Appearance />
      </div>
    </div>
  );
}

function Appearance() {
  const { theme, toggle } = useTheme();
  return (
    <SettingGroup id="appearance" title="Внешний вид">
      <SwitchRow
        title="Светлая тема"
        description="Тёмная — по умолчанию. Выбор запоминается на этом устройстве"
        checked={theme === "light"}
        onChange={toggle}
      />
    </SettingGroup>
  );
}

function OwnerProfile() {
  const { user } = useAuth();
  return (
    <SettingGroup id="profile" title="Профиль владельца">
      <SettingRow title="Имя" description="Владелец задаётся в настройках сервера" control={<span className="set-value">{user?.full_name}</span>} />
      <SettingRow title="Почта" description="Логин владельца" control={<span className="set-value">{user?.email}</span>} />
      <SettingRow
        title="Пароль"
        description="Меняется через .env: OWNER_RESET_PASSWORD=true и новый OWNER_PASSWORD, затем перезапуск API. После входа верните флаг в false"
      />
    </SettingGroup>
  );
}

function Profile({ onPasswordChanged }: { onPasswordChanged: () => void }) {
  const { user, setUser } = useAuth();
  const [name, setName] = useState(user?.full_name ?? "");
  const [nameError, setNameError] = useState<string | null>(null);
  const [currentPassword, setCurrentPassword] = useState("");
  const [nextPassword, setNextPassword] = useState("");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [mailSent, setMailSent] = useState<Sent | null>(null);
  const [open, setOpen] = useState<"email" | "password" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const nameSave = useSaveState();

  const nameSaver = useDebounced<string>((value) => {
    const next = value.trim();
    if (!next) {
      setNameError("Имя не может быть пустым");
      return;
    }
    setNameError(null);
    if (next === user?.full_name) return;
    void nameSave.run(async () => {
      setUser(await api<Me>("/api/v1/me", { method: "PATCH", body: JSON.stringify({ full_name: next }) }));
    });
  }, 600);

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

  async function savePassword(event: FormEvent) {
    event.preventDefault();
    if (nextPassword.length < 8) {
      setError("Новый пароль — минимум 8 символов");
      return;
    }
    await run(async () => {
      await api("/api/v1/me/password", {
        method: "POST",
        body: JSON.stringify({ current_password: currentPassword, new_password: nextPassword }),
      });
      onPasswordChanged();
    });
  }

  async function sendEmail(event: FormEvent) {
    event.preventDefault();
    await run(async () => {
      setMailSent(await api<Sent>("/api/v1/me/email", { method: "POST", body: JSON.stringify({ email }) }));
    });
  }

  async function confirmEmail(event: FormEvent) {
    event.preventDefault();
    await run(async () => {
      setUser(await api<Me>("/api/v1/me/email/confirm", { method: "POST", body: JSON.stringify({ code }) }));
      setMailSent(null);
      setCode("");
      setEmail("");
      setOpen(null);
    });
  }

  function toggle(next: "email" | "password") {
    setError(null);
    setOpen((current) => (current === next ? null : next));
  }

  return (
    <SettingGroup id="profile" title="Профиль" status={<SaveStatus save={nameSave} />}>
      <SettingRow
        title="Имя"
        description="Так вас видят коллеги и бот в Telegram"
        htmlFor="profile-name"
        error={nameError}
        control={
          <RowInput
            id="profile-name"
            value={name}
            invalid={Boolean(nameError)}
            onChange={(value) => {
              setName(value);
              nameSaver.schedule(value);
            }}
            onBlur={() => nameSaver.flush()}
          />
        }
      />
      <SettingRow
        title="Почта"
        description={user?.email}
        control={
          <button type="button" className="ghost" data-hint={HINTS.emailChange} aria-expanded={open === "email"} onClick={() => toggle("email")}>
            {open === "email" ? "Отмена" : "Сменить"}
          </button>
        }
      >
        {open === "email" && (
          <form className="set-form" onSubmit={(event) => void (mailSent ? confirmEmail(event) : sendEmail(event))}>
            {mailSent?.delivery === "log" && <p className="dev-banner">Почта не подключена: код записан в лог API.</p>}
            {mailSent && <p className="field-hint">{mailSent.message}</p>}
            <label className="form-field">
              <span className="form-label">Новая почта</span>
              <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required disabled={Boolean(mailSent)} />
            </label>
            {mailSent && (
              <label className="form-field">
                <span className="form-label">Код из письма</span>
                <input
                  className="code-input"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  value={code}
                  onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                  required
                />
              </label>
            )}
            {error && (
              <p className="field-error" role="alert">
                {error}
              </p>
            )}
            <div className="row-actions">
              <button
                type="submit"
                className="primary"
                data-hint={mailSent ? HINTS.emailCode : HINTS.emailChange}
                disabled={busy || (Boolean(mailSent) && code.length !== 6)}
              >
                {mailSent ? "Подтвердить" : "Отправить код"}
              </button>
              {mailSent && (
                <button
                  type="button"
                  className="ghost"
                  onClick={() => {
                    setMailSent(null);
                    setCode("");
                  }}
                >
                  Другой адрес
                </button>
              )}
            </div>
          </form>
        )}
      </SettingRow>
      <SettingRow
        title="Пароль"
        description="После смены нужно войти заново"
        control={
          <button type="button" className="ghost" data-hint={HINTS.passwordChange} aria-expanded={open === "password"} onClick={() => toggle("password")}>
            {open === "password" ? "Отмена" : "Сменить"}
          </button>
        }
      >
        {open === "password" && (
          <form className="set-form" onSubmit={(event) => void savePassword(event)}>
            <label className="form-field">
              <span className="form-label">Текущий пароль</span>
              <input
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
                required
              />
            </label>
            <label className="form-field">
              <span className="form-label">Новый пароль</span>
              <input
                type="password"
                autoComplete="new-password"
                value={nextPassword}
                onChange={(event) => setNextPassword(event.target.value)}
                required
                minLength={8}
              />
              <span className="field-hint">Минимум 8 символов</span>
            </label>
            {error && (
              <p className="field-error" role="alert">
                {error}
              </p>
            )}
            <div className="row-actions">
              <button type="submit" className="primary" data-hint={HINTS.passwordChange} disabled={busy}>
                Сменить пароль
              </button>
            </div>
          </form>
        )}
      </SettingRow>
    </SettingGroup>
  );
}
