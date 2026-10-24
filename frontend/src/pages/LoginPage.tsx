import { FormEvent, useState } from "react";
import { Navigate } from "react-router-dom";
import { ApiError, api, type User } from "../api";
import { useAuth } from "../auth";
import { TeamMark, ThemeToggle, Wordmark } from "../components/Brand";
import { LoadingBlock } from "../components/ui";

const adminEmail = import.meta.env.VITE_DEMO_ADMIN_EMAIL || "admin@invoice.local";
const adminPassword = import.meta.env.VITE_DEMO_ADMIN_PASSWORD || "change-me";
const userEmail = import.meta.env.VITE_DEMO_USER_EMAIL || "ivan@invoice.local";
const userPassword = import.meta.env.VITE_DEMO_USER_PASSWORD || "change-me-user";
const secondEmail = import.meta.env.VITE_DEMO_USER_TWO_EMAIL || "maria@invoice.local";

export function LoginPage() {
  const { user, ready, setUser } = useAuth();
  const [email, setEmail] = useState(adminEmail);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!ready) {
    return (
      <div className="boot">
        <LoadingBlock label="Открываем вход…" />
      </div>
    );
  }
  if (user) return <Navigate to="/" replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = await api<{ user: User }>("/api/v1/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setUser(body.user);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Сервис не ответил");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <a className="skip" href="#login-form">
        К форме входа
      </a>
      <header className="topbar">
        <Wordmark />
        <ThemeToggle />
      </header>
      <div className="login-grid">
        <section className="login-copy">
          <p className="kicker">Очередь, не журнал</p>
          <h1>Сверху то, что горит.</h1>
          <p>Просрочено, потом ближайшие сроки, потом остальное. Закрыл период — карточка уходит в историю, следующий месяц не ждёт.</p>
        </section>
        <form id="login-form" className="panel login-form" onSubmit={submit} aria-busy={busy}>
          <h2>Вход</h2>
          <label>
            Почта
            <input
              type="email"
              name="email"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <label>
            Пароль
            <input
              type="password"
              name="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="primary" disabled={busy}>
            {busy ? "Вхожу…" : "Войти"}
          </button>
          <dl className="demo">
            <div>
              <dt>Админ</dt>
              <dd>
                {adminEmail}
                <span>{adminPassword}</span>
              </dd>
            </div>
            <div>
              <dt>Иван</dt>
              <dd>
                {userEmail}
                <span>{userPassword}</span>
              </dd>
            </div>
            <div>
              <dt>Мария</dt>
              <dd>
                {secondEmail}
                <span>тот же пароль</span>
              </dd>
            </div>
          </dl>
        </form>
      </div>
      <footer className="login-foot">
        <TeamMark />
      </footer>
    </div>
  );
}
