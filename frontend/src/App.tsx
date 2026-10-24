import { Navigate, Route, Routes } from "react-router-dom";
import { ManageOnly, RequireAuth, RequireTeam } from "./auth";
import { Shell } from "./components/Shell";
import { AuditPage } from "./pages/AuditPage";
import { BudgetPage } from "./pages/BudgetPage";
import { CalendarPage } from "./pages/CalendarPage";
import { ConfirmPage } from "./pages/ConfirmPage";
import { ForgotPage } from "./pages/ForgotPage";
import { HistoryPage } from "./pages/HistoryPage";
import { InboxPage } from "./pages/InboxPage";
import { JoinPage } from "./pages/JoinPage";
import { LoginPage } from "./pages/LoginPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { RegisterPage } from "./pages/RegisterPage";
import { ResetPage } from "./pages/ResetPage";
import { SettingsPage } from "./pages/SettingsPage";
import { StatsPage } from "./pages/StatsPage";
import { TeamPage } from "./pages/TeamPage";
import { TemplatesPage } from "./pages/TemplatesPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/confirm" element={<ConfirmPage />} />
      <Route path="/forgot" element={<ForgotPage />} />
      <Route path="/reset" element={<ResetPage />} />
      <Route path="/join/:token" element={<JoinPage />} />
      <Route element={<RequireAuth />}>
        <Route path="/start" element={<OnboardingPage />} />
        <Route element={<RequireTeam />}>
          <Route element={<Shell />}>
            <Route path="/" element={<InboxPage />} />
            <Route path="/calendar" element={<CalendarPage />} />
            <Route path="/history" element={<HistoryPage />} />
            <Route path="/budget" element={<BudgetPage />} />
            <Route path="/stats" element={<StatsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route element={<ManageOnly />}>
              <Route path="/templates" element={<TemplatesPage />} />
              <Route path="/team" element={<TeamPage />} />
              <Route path="/audit" element={<AuditPage />} />
            </Route>
            <Route path="/admin/templates" element={<Navigate to="/templates" replace />} />
            <Route path="/admin/users" element={<Navigate to="/team" replace />} />
            <Route path="/admin/audit" element={<Navigate to="/audit" replace />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
