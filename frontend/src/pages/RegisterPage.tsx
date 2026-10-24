import { FormEvent, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError, api, type Sent } from "../api";
import { AuthFrame } from "../components/AuthFrame";

export function RegisterPage() {
  const [params] = useSearchParams();
  const invite = params.get("invite") || "";
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = await api<Sent>("/api/v1/auth/register", {
        method: "POST",
        body: JSON.stringify({
          email,
          full_name: fullName,
          password,
          invite_token: invite || null,
        }),
      });
      navigate(`/confirm?email=${encodeURIComponent(email)}`, { state: { delivery: body.delivery, message: body.message } });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Сервис не ответил");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame kicker="Аккаунт" title="Почта, потом команда." text="Код придёт на почту и живёт 15 минут. Пока почта не подтверждена, войти нельзя.">
      <form className="panel login-form" onSubmit={submit}>
        <h2>Регистрация</h2>
        {invite && <p className="caption">После кода вы сразу окажетесь в команде по приглашению.</p>}
        <label>
          Имя
          <input value={fullName} onChange={(event) => setFullName(event.target.value)} required autoComplete="name" />
        </label>
        <label>
          Почта
          <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="username" />
        </label>
        <label>
          Пароль
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} autoComplete="new-password" />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button type="submit" className="primary" disabled={busy}>{busy ? "Отправляю…" : "Получить код"}</button>
        <p className="caption">
          Уже есть аккаунт? <Link to="/login">Войти</Link>
        </p>
      </form>
    </AuthFrame>
  );
}
