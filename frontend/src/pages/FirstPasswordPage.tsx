import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../api";
import { HINTS } from "../hints";
import { useAuth } from "../auth";

export function FirstPasswordPage() {
  const { user, refresh } = useAuth();
  const navigate = useNavigate();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/api/v1/me/password", {
        method: "POST",
        body: JSON.stringify({ current_password: current, new_password: next }),
      });
      await refresh();
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не получилось сменить пароль");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <form className="panel login-form" onSubmit={submit}>
        <h1>Смените временный пароль</h1>
        <p className="desc">{user?.email}. Дальше панель откроется с новым паролем.</p>
        <label>
          Временный пароль
          <input type="password" value={current} onChange={(event) => setCurrent(event.target.value)} required />
        </label>
        <label>
          Новый пароль
          <input type="password" minLength={8} value={next} onChange={(event) => setNext(event.target.value)} required />
        </label>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" className="primary" disabled={busy} data-hint={HINTS.firstPassword}>
          {busy ? "Сохраняю…" : "Продолжить"}
        </button>
      </form>
    </div>
  );
}
