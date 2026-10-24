import { useEffect } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api";
import { canManage, roleLabel, roleOf, useAuth } from "../auth";
import { FeaturesProvider, useFeatures } from "../features";
import { TeamMark, ThemeToggle, Wordmark } from "./Brand";

export function Shell() {
  return (
    <FeaturesProvider>
      <ShellView />
    </FeaturesProvider>
  );
}

function ShellView() {
  const { user, setUser, switchTeam } = useAuth();
  const features = useFeatures();
  const navigate = useNavigate();
  const location = useLocation();
  const manage = canManage(user);
  const role = roleOf(user);

  useEffect(() => {
    document.querySelector<HTMLElement>(".nav a.active")?.scrollIntoView({ inline: "nearest", block: "nearest" });
  }, [location.pathname]);

  async function logout() {
    try {
      await api("/api/v1/auth/logout", { method: "POST" });
    } catch {
      /* cookie всё равно сбрасываем локально */
    }
    setUser(null);
    navigate("/login");
  }

  async function onTeam(teamId: string) {
    if (!teamId || teamId === user?.active_team_id) return;
    await switchTeam(teamId);
  }

  return (
    <div className="app">
      <a className="skip" href="#content">
        К содержанию
      </a>
      <header className="topbar">
        <Wordmark to="/" />
        <div className="who">
          {user && user.memberships.length > 0 && (
            <select
              className="team-switch"
              aria-label="Отдел"
              value={user.active_team_id ?? ""}
              onChange={(event) => void onTeam(event.target.value)}
            >
              {user.memberships.map((row) => (
                <option key={row.team_id} value={row.team_id}>
                  {row.team_name}
                </option>
              ))}
            </select>
          )}
          <span className="who-name">{user?.full_name}</span>
          <span className="role">{roleLabel(role)}</span>
          <ThemeToggle />
          <button type="button" className="ghost" onClick={logout}>
            Выйти
          </button>
        </div>
      </header>
      <div className="shell">
        <nav className="nav" aria-label="Разделы">
          <NavLink to="/" end>
            Инбокс
          </NavLink>
          {features.assistant && <NavLink to="/assistant">Ассистент</NavLink>}
          <NavLink to="/calendar">Календарь</NavLink>
          <NavLink to="/history">История</NavLink>
          <NavLink to="/budget">Бюджет</NavLink>
          <NavLink to="/stats">Статистика</NavLink>
          <NavLink to="/notifications">Уведомления</NavLink>
          <NavLink to="/settings">Настройки</NavLink>
          {user?.is_owner && <NavLink to="/organization">Организация</NavLink>}
          {manage && (
            <>
              <span className="nav-label">Админ</span>
              <NavLink to="/templates">Шаблоны</NavLink>
              <NavLink to="/people">Люди</NavLink>
              <NavLink to="/audit">Журнал</NavLink>
            </>
          )}
          <TeamMark />
        </nav>
        <div className="workspace">
          <main id="content">
            <Outlet key={user?.active_team_id ?? "none"} />
          </main>
          <TeamMark />
        </div>
      </div>
    </div>
  );
}
