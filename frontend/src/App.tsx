import { Navigate, Route, Routes } from "react-router-dom";
import { AdminOnly, RequireAuth } from "./auth";
import { Shell } from "./components/Shell";
import { HistoryPage } from "./pages/HistoryPage";
import { InboxPage } from "./pages/InboxPage";
import { LoginPage } from "./pages/LoginPage";
import { TemplatesPage } from "./pages/TemplatesPage";
import { UsersPage } from "./pages/UsersPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<Shell />}>
          <Route path="/" element={<InboxPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route element={<AdminOnly />}>
            <Route path="/admin/templates" element={<TemplatesPage />} />
            <Route path="/admin/users" element={<UsersPage />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
