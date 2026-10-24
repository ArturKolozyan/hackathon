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
          <h1>{user?.is_owner ? "Создайте первый отдел" : "Вас ещё не добавили в отдел"}</h1>
          <p>
            {user?.is_owner
              ? "Отдел создаёт владелец. Людей добавляют в разделе «Люди»."
              : "Попросите владельца добавить вас. Самостоятельная регистрация закрыта."}
          </p>
        </section>
        {user?.is_owner ? (
          <form className="panel login-form" onSubmit={submit}>
            <h2>Новый отдел</h2>
            <label>
              Название
              <input value={name} onChange={(event) => setName(event.target.value)} required placeholder="Бухгалтерия" />
            </label>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <button type="submit" className="primary" disabled={busy}>
              {busy ? "Создаю…" : "Создать отдел"}
            </button>
          </form>
        ) : (
          <section className="panel note">
            <p>Когда вас добавят, обновите страницу.</p>
          </section>
        )}
      </div>
    </div>
  );
}
