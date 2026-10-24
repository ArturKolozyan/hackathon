import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError, api } from "../api";
import { HINTS } from "../hints";
import { AuthFrame } from "../components/AuthFrame";

export function ForgotPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/api/v1/auth/password/forgot", { method: "POST", body: JSON.stringify({ email }) });
      navigate(`/reset?email=${encodeURIComponent(email)}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Сервис не ответил");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame kicker="Пароль" title="Код на почту." text="Если аккаунт есть, письмо уйдёт. Чужой адрес мы не подтверждаем.">
      <form className="panel login-form" onSubmit={submit}>
        <h2>Сброс пароля</h2>
        <label>
          Почта
          <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required autoComplete="username" />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button type="submit" className="primary" disabled={busy} data-hint={HINTS.resetCode}>{busy ? "Отправляю…" : "Прислать код"}</button>
        <p className="caption"><Link to="/login">Ко входу</Link></p>
      </form>
    </AuthFrame>
  );
}
