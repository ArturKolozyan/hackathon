import { BarChart3, CalendarDays, History, Inbox, Menu, type LucideIcon } from "lucide-react";
import { NavLink, useLocation } from "react-router-dom";
import { HINTS, NAV_HINTS } from "../hints";

type Tab = { to: string; label: string; icon: LucideIcon; end?: boolean };

/**
 * Нижняя навигация на телефоне: четыре раздела, куда заходят каждый день, и «Ещё»,
 * которое открывает боковое меню со всеми остальными разделами, отделом и темой.
 * Разделы доступны всем ролям, поэтому набор один.
 */
const TABS: Tab[] = [
  { to: "/", label: "Инбокс", icon: Inbox, end: true },
  { to: "/calendar", label: "Календарь", icon: CalendarDays },
  { to: "/history", label: "История", icon: History },
  { to: "/stats", label: "Статистика", icon: BarChart3 },
];

export function BottomNav({ menuOpen, onMore }: { menuOpen: boolean; onMore: () => void }) {
  const { pathname } = useLocation();
  const inTabs = TABS.some((tab) => (tab.end ? pathname === tab.to : pathname.startsWith(tab.to)));
  return (
    <nav className="bottom-nav" aria-label="Главные разделы">
      {TABS.map((tab) => {
        const Icon = tab.icon;
        return (
          <NavLink key={tab.to} to={tab.to} end={tab.end} data-hint={NAV_HINTS[tab.to]} className={({ isActive }) => (isActive ? "active" : undefined)}>
            <span className="bn-icon" aria-hidden="true">
              <Icon size={20} strokeWidth={1.75} />
            </span>
            <span className="bn-label">{tab.label}</span>
          </NavLink>
        );
      })}
      <button
        type="button"
        className={inTabs ? undefined : "is-current"}
        aria-expanded={menuOpen}
        aria-controls="app-nav"
        data-hint={HINTS.menuOpen}
        onClick={onMore}
      >
        <span className="bn-icon" aria-hidden="true">
          <Menu size={20} strokeWidth={1.75} />
        </span>
        <span className="bn-label">Ещё</span>
      </button>
    </nav>
  );
}
