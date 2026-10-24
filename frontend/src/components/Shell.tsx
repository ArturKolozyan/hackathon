import { useEffect, useRef, useState } from "react";
import {
  BarChart3,
  Bell,
  CalendarDays,
  History,
  Inbox,
  LogOut,
  Menu,
  Repeat,
  ScrollText,
  Settings,
  Users,
  Wallet,
  X,
  type LucideIcon,
} from "lucide-react";
import { NavLink, Outlet, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { canManage, roleLabel, roleOf, useAuth } from "../auth";
import { FeaturesProvider, useFeatures } from "../features";
import { useMediaQuery } from "../useMediaQuery";
import { AssistantWidget } from "./AssistantWidget";
import { TeamMark, ThemeToggle, Wordmark } from "./Brand";

type Item = { to: string; label: string; icon: LucideIcon; end?: boolean };

const MAIN: Item[] = [
  { to: "/", label: "Инбокс", icon: Inbox, end: true },
  { to: "/calendar", label: "Календарь", icon: CalendarDays },
  { to: "/history", label: "История", icon: History },
  { to: "/budget", label: "Бюджет", icon: Wallet },
  { to: "/stats", label: "Статистика", icon: BarChart3 },
  { to: "/notifications", label: "Уведомления", icon: Bell },
  { to: "/settings", label: "Настройки", icon: Settings },
];

const ADMIN: Item[] = [
  { to: "/templates", label: "Шаблоны", icon: Repeat },
  { to: "/people", label: "Люди", icon: Users },
  { to: "/audit", label: "Журнал", icon: ScrollText },
];

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
  const [params, setParams] = useSearchParams();
  const narrow = useMediaQuery("(max-width: 860px)");
  const [menuOpen, setMenuOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const navRef = useRef<HTMLElement>(null);
  const manage = canManage(user);
  const role = roleOf(user);

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!narrow) setMenuOpen(false);
  }, [narrow]);

  useEffect(() => {
    if (!menuOpen) return;
    navRef.current?.querySelector<HTMLElement>("a, button")?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setMenuOpen(false);
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  useEffect(() => {
    document.querySelector<HTMLElement>(".nav-scroll a.active")?.scrollIntoView({ inline: "nearest", block: "nearest" });
  }, [location.pathname]);

  useEffect(() => {
    if (params.get("chat") !== "1") return;
    if (features.loaded && features.assistant) setChatOpen(true);
    if (!features.loaded) return;
    const next = new URLSearchParams(params);
    next.delete("chat");
    setParams(next, { replace: true });
  }, [params, setParams, features.loaded, features.assistant]);

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
        <div className="topbar-start">
          <button
            type="button"
            className="icon-btn menu-btn"
            aria-expanded={menuOpen}
            aria-controls="app-nav"
            onClick={() => setMenuOpen((value) => !value)}
          >
            {menuOpen ? <X size={18} strokeWidth={1.75} aria-hidden /> : <Menu size={18} strokeWidth={1.75} aria-hidden />}
            <span className="sr-only">{menuOpen ? "Закрыть меню" : "Открыть меню"}</span>
          </button>
          <Wordmark to="/" />
        </div>
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
        </div>
      </header>
      {menuOpen && <div className="nav-backdrop" onClick={() => setMenuOpen(false)} />}
      <div className="shell">
        <nav ref={navRef} id="app-nav" className={menuOpen ? "nav is-open" : "nav"} aria-label="Разделы">
          <div className="nav-scroll">
            {MAIN.map((item) => (
              <NavItem key={item.to} item={item} />
            ))}
            {manage && (
              <>
                <span className="nav-label">Админ</span>
                {ADMIN.map((item) => (
                  <NavItem key={item.to} item={item} />
                ))}
              </>
            )}
          </div>
          <div className="nav-foot">
            <TeamMark />
            <button type="button" className="nav-logout" onClick={() => void logout()}>
              <LogOut size={18} strokeWidth={1.75} aria-hidden />
              <span>Выйти</span>
            </button>
          </div>
        </nav>
        <div className="workspace">
          <main id="content">
            <Outlet key={user?.active_team_id ?? "none"} />
          </main>
        </div>
      </div>
      {features.loaded && features.assistant && <AssistantWidget open={chatOpen} onOpenChange={setChatOpen} />}
    </div>
  );
}

function NavItem({ item }: { item: Item }) {
  const Icon = item.icon;
  return (
    <NavLink to={item.to} end={item.end} className={({ isActive }) => (isActive ? "active" : undefined)}>
      <Icon size={18} strokeWidth={1.75} aria-hidden />
      <span>{item.label}</span>
    </NavLink>
  );
}
