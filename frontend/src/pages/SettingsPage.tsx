import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, api, type Me, type Sent } from "../api";
import { useAuth } from "../auth";

export function SettingsPage() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();

  return (
    <div className="page">
      <div className="stack">
        {user?.is_owner ? (
          <OwnerLocked />
        ) : (
          <ProfileCard
            onPasswordChanged={() => {
              setUser(null);
              navigate("/login", { replace: true, state: { notice: "Пароль сменён. Войдите снова." } });
            }}
          />
        )}
        <section className="panel settings-card">
          <h2>Уведомления</h2>
          <p className="desc">Личный Telegram, почта и каналы отдела настраиваются в отдельном разделе.</p>
          <Link className="outline" to="/notifications">
            Открыть уведомления
          </Link>
        </section>
      </div>
    </div>
  );
}

function OwnerLocked() {
  const { user } = useAuth();
  return (
    <section className="panel settings-card">
      <div className="row-between">
        <h2>Аккаунт владельца</h2>
        <span className="muted">{user?.email}</span>
      </div>
      <p className="desc">
        Имя, почта и пароль владельца из панели не меняются. Восстановление пароля — через .env: выставьте
        OWNER_RESET_PASSWORD=true, задайте OWNER_PASSWORD и перезапустите API. После входа верните флаг в false.
      </p>
      <p className="caption">{user?.full_name}</p>
    </section>
  );
}

function ProfileCard({ onPasswordChanged }: { onPasswordChanged: () => void }) {
  const { user, setUser } = useAuth();
  const [name, setName] = useState(user?.full_name ?? "");
  const [currentPassword, setCurrentPassword] = useState("");
  const [nextPassword, setNextPassword] = useState("");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [mailSent, setMailSent] = useState<Sent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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

  async function saveName(event: FormEvent) {
    event.preventDefault();
    await run(async () => {
      setUser(await api<Me>("/api/v1/me", { method: "PATCH", body: JSON.stringify({ full_name: name }) }));
      setNotice("Имя сохранено");
    });
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
      const sent = await api<Sent>("/api/v1/me/email", { method: "POST", body: JSON.stringify({ email }) });
      setMailSent(sent);
      setNotice(sent.message);
    });
  }

  async function confirmEmail(event: FormEvent) {
    event.preventDefault();
    await run(async () => {
      setUser(await api<Me>("/api/v1/me/email/confirm", { method: "POST", body: JSON.stringify({ code }) }));
      setMailSent(null);
      setCode("");
      setEmail("");
      setNotice("Почта обновлена");
    });
  }

  return (
    <section className="panel settings-card">
      <div className="row-between">
        <h2>Аккаунт</h2>
        <span className="muted">{user?.email}</span>
      </div>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {notice && <p className="caption">{notice}</p>}
      {mailSent?.delivery === "log" && <p className="dev-banner">Почта не подключена: код записан в лог API.</p>}
      <form className="pay-form" onSubmit={(event) => void saveName(event)}>
        <label>
          Имя
          <input value={name} onChange={(event) => setName(event.target.value)} required maxLength={200} />
        </label>
        <button type="submit" className="primary" disabled={busy}>
          Сохранить имя
        </button>
      </form>
      <form className="pay-form" onSubmit={(event) => void savePassword(event)}>
        <label>
          Текущий пароль
          <input
            type="password"
            autoComplete="current-password"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
            required
          />
        </label>
        <label>
          Новый пароль
          <input
            type="password"
            autoComplete="new-password"
            value={nextPassword}
            onChange={(event) => setNextPassword(event.target.value)}
            required
            minLength={8}
          />
        </label>
        <button type="submit" className="ghost" disabled={busy}>
          Сменить пароль
        </button>
      </form>
      <form className="pay-form" onSubmit={(event) => void (mailSent ? confirmEmail(event) : sendEmail(event))}>
        <label>
          Новая почта
          <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required disabled={Boolean(mailSent)} />
        </label>
        {mailSent && (
          <label>
            Код из письма
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
        <div className="row-actions">
          <button type="submit" className="ghost" disabled={busy || (Boolean(mailSent) && code.length !== 6)}>
            {mailSent ? "Подтвердить почту" : "Отправить код"}
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
    </section>
  );
}
