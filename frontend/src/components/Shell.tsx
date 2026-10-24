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
import { BottomNav } from "./BottomNav";
import { TeamMark, ThemeSwitch, Wordmark } from "./Brand";
import { SelectField } from "./fields";
import { PageControlsSlot } from "./PageControls";

type Item = { to: string; label: string; icon: LucideIcon; end?: boolean; manage?: boolean };

/** Разделы по смыслу, а не по роли. Недоступное роли скрыто, порядок тот же. */
const WORK: Item[] = [
  { to: "/", label: "Инбокс", icon: Inbox, end: true },
  { to: "/calendar", label: "Календарь", icon: CalendarDays },
  { to: "/templates", label: "Шаблоны", icon: Repeat, manage: true },
  { to: "/history", label: "История", icon: History },
  { to: "/budget", label: "Бюджет", icon: Wallet },
  { to: "/stats", label: "Статистика", icon: BarChart3 },
  { to: "/people", label: "Люди", icon: Users, manage: true },
];

const SERVICE: Item[] = [
  { to: "/settings", label: "Настройки", icon: Settings },
  { to: "/logs", label: "Логи", icon: ScrollText, manage: true },
];

/** Sidebar collapses into a drawer when it would not fit: narrow or short viewports. */
const COLLAPSED = "(max-width: 1023px), (max-height: 639px)";

function roleName(role: TeamRole | null, owner: boolean): string {
  if (owner || role === "owner") return "Владелец";
  if (role === "admin") return "Администратор";
  return "Участник";
}

function sectionOf(pathname: string): string | null {
  const all = [...WORK, ...SERVICE];
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
  const workspaceRef = useRef<HTMLDivElement>(null);
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
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    /* inert снимается эффектом ниже, но фокус нужен сразу. */
    navRef.current?.removeAttribute("inert");
    (navRef.current?.querySelector<HTMLElement>(".nav a.active") ?? navRef.current?.querySelector<HTMLElement>("a, button"))?.focus();
    function onKey(event: KeyboardEvent) {
      if (event.key === "Tab") {
        /* Фокус не уходит из открытого меню. */
        const nodes = [...(navRef.current?.querySelectorAll<HTMLElement>("a[href], button:not(:disabled)") ?? [])];
        if (nodes.length === 0) return;
        const first = nodes[0];
        const last = nodes[nodes.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
        return;
      }
      if (event.key !== "Escape") return;
      setMenuOpen(false);
      (opener && opener.isConnected ? opener : burgerRef.current)?.focus();
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
    workspaceRef.current?.toggleAttribute("inert", menuOpen);
  }, [drawerHidden, menuOpen]);

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
        role={collapsed ? "dialog" : undefined}
        aria-modal={menuOpen || undefined}
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
        <div className="profile">
          <span className="avatar" aria-hidden="true">
            {initials(user?.full_name)}
          </span>
          <div className="profile-text">
            <span className="profile-name">{user?.full_name}</span>
            <span className="profile-role">{roleName(role, Boolean(user?.is_owner))}</span>
          </div>
        </div>
        {user && user.memberships.length > 0 && (
          <div className="team-block">
            <span className="team-label" id="team-label">
              Отдел:
            </span>
            {user.memberships.length > 1 ? (
              <SelectField
                className="team-switch"
                ariaLabel="Отдел"
                hint={HINTS.teamSwitch}
                value={user.active_team_id ?? ""}
                onChange={(teamId) => void onTeam(teamId)}
                options={user.memberships.map((row) => ({ value: row.team_id, label: row.team_name }))}
              />
            ) : (
              <p className="team-single" aria-labelledby="team-label">
                {user.memberships[0].team_name}
              </p>
            )}
          </div>
        )}
        <nav className="nav" aria-label="Разделы">
          {WORK.filter((item) => manage || !item.manage).map((item) => (
            <NavItem key={item.to} item={item} />
          ))}
          <hr className="nav-divider" />
          {SERVICE.filter((item) => manage || !item.manage).map((item) => (
            <NavItem key={item.to} item={item} />
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="sidebar-actions">
            <ThemeSwitch />
            <button type="button" className="nav-logout" data-hint={HINTS.logout} onClick={() => void logout()}>
              <LogOut size={18} strokeWidth={1.75} aria-hidden />
              <span>Выйти</span>
            </button>
          </div>
          <TeamMark />
        </div>
      </aside>
      <div className="workspace" ref={workspaceRef}>
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
        {collapsed && <BottomNav menuOpen={menuOpen} onMore={() => setMenuOpen(true)} />}
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
