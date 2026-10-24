import { useEffect, useRef, useState } from "react";
import {
  BarChart3,
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
import { api, type TeamRole } from "../api";
import { canManage, roleOf, useAuth } from "../auth";
import { FeaturesProvider, useFeatures } from "../features";
import { initials } from "../format";
import { HINTS, NAV_HINTS } from "../hints";
import { useMediaQuery } from "../useMediaQuery";
import { AssistantWidget } from "./AssistantWidget";
import { TeamMark, ThemeToggle, Wordmark } from "./Brand";
import { SelectField } from "./fields";
import { PageControlsSlot } from "./PageControls";

type Item = { to: string; label: string; icon: LucideIcon; end?: boolean };

const MAIN: Item[] = [
  { to: "/", label: "Инбокс", icon: Inbox, end: true },
  { to: "/calendar", label: "Календарь", icon: CalendarDays },
  { to: "/history", label: "История", icon: History },
  { to: "/budget", label: "Бюджет", icon: Wallet },
  { to: "/stats", label: "Статистика", icon: BarChart3 },
  { to: "/settings", label: "Настройки", icon: Settings },
];

const ADMIN: Item[] = [
  { to: "/templates", label: "Шаблоны", icon: Repeat },
  { to: "/people", label: "Люди", icon: Users },
  { to: "/logs", label: "Логи", icon: ScrollText },
];

/** Sidebar collapses into a drawer when it would not fit: narrow or short viewports. */
const COLLAPSED = "(max-width: 1023px), (max-height: 639px)";

function roleName(role: TeamRole | null, owner: boolean): string {
  if (owner || role === "owner") return "Владелец";
  if (role === "admin") return "Админ";
  return "Участник";
}

function sectionOf(pathname: string): string | null {
  const all = [...MAIN, ...ADMIN];
  const hit = all.find((item) => (item.end ? pathname === item.to : pathname.startsWith(item.to)));
  return hit?.label ?? null;
}

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
  const collapsed = useMediaQuery(COLLAPSED);
  const [menuOpen, setMenuOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [slot, setSlot] = useState<HTMLDivElement | null>(null);
  const navRef = useRef<HTMLElement>(null);
  const burgerRef = useRef<HTMLButtonElement>(null);
  const manage = canManage(user);
  const role = roleOf(user);

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!collapsed) setMenuOpen(false);
  }, [collapsed]);

  useEffect(() => {
    if (!menuOpen) return;
    navRef.current?.querySelector<HTMLElement>("a.active, a, button")?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setMenuOpen(false);
      burgerRef.current?.focus();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [menuOpen]);

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

  const drawerHidden = collapsed && !menuOpen;

  useEffect(() => {
    navRef.current?.toggleAttribute("inert", drawerHidden);
  }, [drawerHidden]);

  const section = sectionOf(location.pathname);

  return (
    <div className={menuOpen ? "app menu-open" : "app"}>
      <a className="skip" href="#content">
        К содержанию
      </a>
      {menuOpen && <div className="nav-backdrop" aria-hidden="true" onClick={() => setMenuOpen(false)} />}
      <aside
        ref={navRef}
        id="app-nav"
        className={menuOpen ? "sidebar is-open" : "sidebar"}
        aria-label="Боковое меню"
        aria-hidden={drawerHidden || undefined}
      >
        <div className="sidebar-head">
          <Wordmark to="/" />
          {collapsed && (
            <button type="button" className="icon-btn sidebar-close" aria-label="Закрыть меню" data-hint={HINTS.menuClose} onClick={() => setMenuOpen(false)}>
              <X size={18} strokeWidth={1.75} aria-hidden />
            </button>
          )}
        </div>
        {user && user.memberships.length > 1 && (
          <SelectField
            className="team-switch"
            ariaLabel="Отдел"
            hint={HINTS.teamSwitch}
            value={user.active_team_id ?? ""}
            onChange={(teamId) => void onTeam(teamId)}
            options={user.memberships.map((row) => ({ value: row.team_id, label: row.team_name }))}
          />
        )}
        {user && user.memberships.length === 1 && <p className="team-single">{user.memberships[0].team_name}</p>}
        <nav className="nav" aria-label="Разделы">
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
        </nav>
        <div className="sidebar-foot">
          <div className="profile" data-hint={HINTS.profile}>
            <span className="avatar" aria-hidden="true">
              {initials(user?.full_name)}
            </span>
            <div className="profile-text">
              <span className="profile-name">
                {user?.full_name}
              </span>
              <span className="pill pill-neutral profile-role">{roleName(role, Boolean(user?.is_owner))}</span>
            </div>
            <ThemeToggle />
          </div>
          <button type="button" className="nav-logout" data-hint={HINTS.logout} onClick={() => void logout()}>
            <LogOut size={18} strokeWidth={1.75} aria-hidden />
            <span>Выйти</span>
          </button>
          <TeamMark />
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          {collapsed && (
            <>
              <button
                ref={burgerRef}
                type="button"
                className="icon-btn menu-btn"
                aria-expanded={menuOpen}
                aria-controls="app-nav"
                aria-label="Открыть меню"
                data-hint={HINTS.menuOpen}
                onClick={() => setMenuOpen(true)}
              >
                <Menu size={18} strokeWidth={1.75} aria-hidden />
              </button>
              {section && <span className="topbar-section">{section}</span>}
            </>
          )}
          <div className="topbar-controls" ref={setSlot} />
        </header>
        <main id="content">
          <PageControlsSlot value={slot}>
            <Outlet key={user?.active_team_id ?? "none"} />
          </PageControlsSlot>
        </main>
      </div>
      {features.loaded && features.assistant && <AssistantWidget open={chatOpen} onOpenChange={setChatOpen} />}
    </div>
  );
}

function NavItem({ item }: { item: Item }) {
  const Icon = item.icon;
  return (
    <NavLink to={item.to} end={item.end} data-hint={NAV_HINTS[item.to]} className={({ isActive }) => (isActive ? "active" : undefined)}>
      <Icon size={18} strokeWidth={1.75} aria-hidden />
      <span>{item.label}</span>
    </NavLink>
  );
}
