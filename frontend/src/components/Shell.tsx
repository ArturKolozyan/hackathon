import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

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
        <div className="brand">
          <span className="mark" aria-hidden="true">
            ИК
          </span>
          <span>
            <strong>Invoice Keeper</strong>
            <small>очередь платежей</small>
          </span>
        </div>
        <div className="who">
          <span className="who-name">{user?.full_name}</span>
          <span className="role">{user?.role === "admin" ? "админ" : "участник"}</span>
          <button type="button" className="ghost light" onClick={logout}>
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
        </nav>
        <main>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
