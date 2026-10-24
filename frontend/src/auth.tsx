import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { api, setStoredTeamId, type Me, type TeamRole } from "./api";
import { LoadingBlock } from "./components/ui";

type AuthState = {
  user: Me | null;
  ready: boolean;
  setUser: (user: Me | null) => void;
  refresh: () => Promise<void>;
  switchTeam: (teamId: string) => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

function remember(user: Me | null) {
  setStoredTeamId(user?.active_team_id ?? null);
}

export function roleOf(user: Me | null): TeamRole | null {
  if (!user?.active_team_id) return null;
  return user.memberships.find((row) => row.team_id === user.active_team_id)?.role ?? null;
}

export function roleLabel(role: TeamRole | null): string {
  if (role === "owner") return "владелец";
  if (role === "admin") return "админ отдела";
  return "пользователь";
}

export function canManage(user: Me | null): boolean {
  const role = roleOf(user);
  return role === "owner" || role === "admin";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUserState] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);

  function setUser(next: Me | null) {
    remember(next);
    setUserState(next);
  }

  async function refresh() {
    const me = await api<Me>("/api/v1/auth/me");
    setUser(me);
  }

  async function switchTeam(teamId: string) {
    const me = await api<Me>("/api/v1/me/active-team", {
      method: "POST",
      body: JSON.stringify({ team_id: teamId }),
    });
    setUser(me);
  }

  useEffect(() => {
    api<Me>("/api/v1/auth/me")
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setReady(true));
  }, []);

  const value = useMemo(() => ({ user, ready, setUser, refresh, switchTeam }), [user, ready]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (!value) throw new Error("AuthProvider отсутствует");
  return value;
}

export function RequireAuth() {
  const { user, ready } = useAuth();
  const location = useLocation();
  if (!ready) {
    return (
      <div className="boot">
        <LoadingBlock label="Проверяем сессию…" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  if (user.must_change_password && location.pathname !== "/first-password") {
    return <Navigate to="/first-password" replace />;
  }
  if (
    !user.must_change_password &&
    !user.telegram_onboarding_done &&
    !user.telegram_linked &&
    location.pathname !== "/link-telegram"
  ) {
    return <Navigate to="/link-telegram" replace />;
  }
  return <Outlet />;
}

export function RequireTeam() {
  const { user } = useAuth();
  if (!user?.active_team_id || user.memberships.length === 0) return <Navigate to="/start" replace />;
  return <Outlet />;
}

export function ManageOnly() {
  const { user } = useAuth();
  if (!canManage(user)) {
    return (
      <section className="panel note">
        <h1>Только для владельца или админа отдела</h1>
        <p>Платежи, люди и журнал — у владельца и админа отдела. Очередь, календарь, бюджет и статистика видны всем в отделе.</p>
      </section>
    );
  }
  return <Outlet />;
}
