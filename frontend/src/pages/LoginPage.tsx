import { FormEvent, useEffect, useState } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { ApiError, api, type DemoAccount, type Me } from "../api";
import { useAuth } from "../auth";
import { TeamMark, ThemeSwitch, Wordmark } from "../components/Brand";
import { HINTS } from "../hints";
import { LoadingBlock } from "../components/ui";

export function LoginPage() {
  const { user, ready, setUser } = useAuth();
  const location = useLocation();
  const notice = (location.state as { notice?: string } | null)?.notice;
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [demos, setDemos] = useState<DemoAccount[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api<{ show_demo_credentials: boolean; accounts: DemoAccount[] }>("/api/v1/public-config")
      .then((body) => {
        if (!cancelled && body.show_demo_credentials) setDemos(body.accounts);
      })
      .catch(() => {
        if (!cancelled) setDemos([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
      const body = await api<{ user: Me }>("/api/v1/auth/login", {
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
        <ThemeSwitch />
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
          {notice && <p className="caption">{notice}</p>}
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" className="primary" disabled={busy} data-hint={HINTS.login}>
            {busy ? "Вхожу…" : "Войти"}
          </button>
          <p className="auth-links">
            <Link to="/forgot">Забыли пароль</Link>
          </p>
          {demos.length > 0 && (
            <div className="demo">
              {demos.map((account) => (
                <button
                  data-hint={HINTS.demoAccount}
                  key={account.label}
                  type="button"
                  onClick={() => {
                    setEmail(account.email);
                    setPassword(account.password);
                  }}
                >
                  <span className="demo-label">{account.label}</span>
                  <span>
                    {account.email}
                    <span>{account.password}</span>
                  </span>
                </button>
              ))}
            </div>
          )}
        </form>
      </div>
      <footer className="login-foot">
        <TeamMark />
      </footer>
    </div>
  );
}
