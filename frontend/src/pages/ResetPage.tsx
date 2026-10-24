import { FormEvent, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api";
import { HINTS } from "../hints";
import { AuthFrame } from "../components/AuthFrame";

export function ResetPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [email, setEmail] = useState(params.get("email") || "");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/api/v1/auth/password/reset", {
        method: "POST",
        body: JSON.stringify({ email, code, password }),
      });
      navigate("/login", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Сервис не ответил");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame kicker="Пароль" title="Новый пароль." text="Старые сессии закроются. После сброса войдите заново.">
      <form className="panel login-form" onSubmit={submit}>
        <h2>Новый пароль</h2>
        <label>
          Почта
          <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
        </label>
        <label>
          Код
          <input className="code-input" inputMode="numeric" maxLength={6} value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))} required />
        </label>
        <label>
          Новый пароль
          <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required minLength={8} autoComplete="new-password" />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button type="submit" className="primary" disabled={busy} data-hint={HINTS.resetSave}>Сохранить</button>
        <p className="caption"><Link to="/login">Ко входу</Link></p>
      </form>
    </AuthFrame>
  );
}
