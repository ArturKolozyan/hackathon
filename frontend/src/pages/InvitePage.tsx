import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError, api, type InviteInfo, type Me } from "../api";
import { useAuth } from "../auth";
import { AuthFrame } from "../components/AuthFrame";
import { HINTS } from "../hints";
import { LoadingBlock } from "../components/ui";

export function InvitePage() {
  const { token = "" } = useParams();
  const { setUser } = useAuth();
  const navigate = useNavigate();
  const [info, setInfo] = useState<InviteInfo | null>(null);
  const [gone, setGone] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const path = `/api/v1/auth/invite/${encodeURIComponent(token)}`;

  useEffect(() => {
    api<InviteInfo>(path)
      .then(setInfo)
      .catch((err: unknown) => setGone(err instanceof ApiError ? err.message : "Сервис не ответил"));
  }, [path]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (password !== repeat) {
      setError("Пароли не совпадают");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const body = await api<{ user: Me }>(path, { method: "POST", body: JSON.stringify({ password }) });
      setUser(body.user);
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Сервис не ответил");
      setBusy(false);
    }
  }

  return (
    <AuthFrame kicker="Приглашение" title="Добро пожаловать в rekeeper." text="Задайте пароль и войдите. Потом можно привязать Telegram.">
      {gone ? (
        <section className="panel login-form">
          <h2>Ссылка не работает</h2>
          <p className="desc">{gone}</p>
          <p className="caption">
            <Link to="/login">Ко входу</Link>
          </p>
        </section>
      ) : !info ? (
        <LoadingBlock label="Проверяем приглашение…" />
      ) : (
        <form className="panel login-form" onSubmit={submit}>
          <h2>{info.full_name}</h2>
          <p className="desc">Почта для входа: {info.email}</p>
          <input type="email" value={info.email} autoComplete="username" readOnly hidden />
          <label>
            Пароль
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} autoComplete="new-password" />
          </label>
          <label>
            Повторите пароль
            <input type="password" value={repeat} onChange={(event) => setRepeat(event.target.value)} required minLength={8} autoComplete="new-password" />
          </label>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="primary" disabled={busy} data-hint={HINTS.inviteAccept}>
            {busy ? "Входим…" : "Задать пароль и войти"}
          </button>
        </form>
      )}
    </AuthFrame>
  );
}
