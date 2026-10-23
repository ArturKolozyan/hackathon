import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { TeamMark, ThemeToggle, Wordmark } from "./Brand";

export function Shell() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();

  async function logout() {
    try {
      await api("/api/v1/auth/logout", { method: "POST" });
    } catch {
      /* cookie всё равно сбрасываем локально */
    }
    setUser(null);
    navigate("/login");
  }

  return (
    <div className="app">
      <header className="topbar">
        <Wordmark to="/" />
        <div className="who">
          <span className="who-name">{user?.full_name}</span>
          <span className="role">{user?.role === "admin" ? "админ" : "участник"}</span>
          <ThemeToggle />
          <button type="button" className="ghost" onClick={logout}>
            Выйти
          </button>
        </div>
      </header>
      <div className="shell">
        <nav className="nav">
          <NavLink to="/" end>
            Инбокс
          </NavLink>
          <NavLink to="/history">История</NavLink>
          {user?.role === "admin" && (
            <>
              <NavLink to="/admin/templates">Шаблоны</NavLink>
              <NavLink to="/admin/users">Люди</NavLink>
            </>
          )}
          <TeamMark />
        </nav>
        <div className="workspace">
          <main>
            <Outlet />
          </main>
          <TeamMark />
        </div>
      </div>
    </div>
  );
}
