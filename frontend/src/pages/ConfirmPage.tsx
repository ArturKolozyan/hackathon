import { FormEvent, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError, api, type Me, type Sent } from "../api";
import { useAuth } from "../auth";
import { AuthFrame } from "../components/AuthFrame";

export function ConfirmPage() {
  const [params] = useSearchParams();
  const email = params.get("email") || "";
  const location = useLocation();
  const state = (location.state || {}) as { delivery?: string; message?: string };
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const [code, setCode] = useState("");
  const [notice, setNotice] = useState(state.message || "Введите код из письма.");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = await api<{ user: Me }>("/api/v1/auth/register/confirm", {
        method: "POST",
        body: JSON.stringify({ email, code }),
      });
      setUser(body.user);
      navigate(body.user.memberships.length ? "/" : "/start", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Сервис не ответил");
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    setBusy(true);
    setError(null);
    try {
      const body = await api<Sent>("/api/v1/auth/register/resend", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      setNotice(body.message);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не отправилось");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame kicker="Подтверждение" title="Шесть цифр." text="Код действует 15 минут. Новый можно запросить через минуту.">
      <form className="panel login-form" onSubmit={submit}>
        <h2>{email || "Почта"}</h2>
        {state.delivery === "log" && <p className="dev-banner">Почта не подключена: код записан в лог API.</p>}
        <p className="caption">{notice}</p>
        <label>
          Код
          <input className="code-input" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} required />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button type="submit" className="primary" disabled={busy || code.length !== 6}>Подтвердить</button>
        <button type="button" className="ghost" disabled={busy || !email} onClick={() => void resend()}>Отправить ещё раз</button>
        <p className="caption"><Link to="/login">Ко входу</Link></p>
      </form>
    </AuthFrame>
  );
}
