import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api } from "../api";
import { useAuth } from "../auth";
import { ThemeToggle, Wordmark } from "../components/Brand";

export function OnboardingPage() {
  const { refresh, user } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/api/v1/teams", { method: "POST", body: JSON.stringify({ name }) });
      await refresh();
      navigate("/", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не получилось");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <header className="topbar">
        <Wordmark />
        <ThemeToggle />
      </header>
      <div className="login-grid">
        <section className="login-copy">
          <p className="kicker">Первый вход</p>
          <h1>{user?.full_name.split(" ")[0]}, соберите команду.</h1>
          <p>Вы станете владельцем. Людей можно позвать ссылкой или письмом. Если вас уже пригласили — откройте ссылку из письма.</p>
        </section>
        <form className="panel login-form" onSubmit={submit}>
          <h2>Новая команда</h2>
          <label>
            Название
            <input value={name} onChange={(event) => setName(event.target.value)} required placeholder="Студия" />
          </label>
          {error && <p className="error" role="alert">{error}</p>}
          <button type="submit" className="primary" disabled={busy}>{busy ? "Создаю…" : "Создать команду"}</button>
          <p className="caption">Приглашение придёт ссылкой. Откройте её, будучи залогиненным, или зарегистрируйтесь по ней.</p>
        </form>
      </div>
    </div>
  );
}
