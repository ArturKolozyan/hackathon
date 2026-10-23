import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { api, type User } from "./api";

type AuthState = {
  user: User | null;
  ready: boolean;
  setUser: (user: User | null) => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    api<User>("/api/v1/auth/me")
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setReady(true));
  }, []);

  const value = useMemo(() => ({ user, ready, setUser }), [user, ready]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (!value) throw new Error("AuthProvider отсутствует");
  return value;
}

export function RequireAuth() {
  const { user, ready } = useAuth();
  if (!ready) return <p className="boot">Загрузка…</p>;
  if (!user) return <Navigate to="/login" replace />;
  return <Outlet />;
}

export function AdminOnly() {
  const { user } = useAuth();
  if (user?.role !== "admin") {
    return (
      <section className="panel">
        <h1>Только для админа</h1>
        <p>Шаблоны и состав команды меняет администратор. Очередь платежей видна всем.</p>
      </section>
    );
  }
  return <Outlet />;
}
