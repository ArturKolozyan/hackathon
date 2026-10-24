import { Navigate, Route, Routes } from "react-router-dom";
import { ManageOnly, RequireAuth, RequireTeam } from "./auth";
import { Shell } from "./components/Shell";
import { AuditPage } from "./pages/AuditPage";
import { BudgetPage } from "./pages/BudgetPage";
import { CalendarPage } from "./pages/CalendarPage";
import { ForgotPage } from "./pages/ForgotPage";
import { HistoryPage } from "./pages/HistoryPage";
import { InboxPage } from "./pages/InboxPage";
import { InvitePage } from "./pages/InvitePage";
import { FirstPasswordPage } from "./pages/FirstPasswordPage";
import { LinkTelegramPage } from "./pages/LinkTelegramPage";
import { LoginPage } from "./pages/LoginPage";
import { NotificationsPage } from "./pages/NotificationsPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { PeoplePage } from "./pages/PeoplePage";
import { ResetPage } from "./pages/ResetPage";
import { OrganizationPage } from "./pages/OrganizationPage";
import { SettingsPage } from "./pages/SettingsPage";
import { StatsPage } from "./pages/StatsPage";
import { TemplatesPage } from "./pages/TemplatesPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/forgot" element={<ForgotPage />} />
      <Route path="/reset" element={<ResetPage />} />
      <Route path="/invite/:token" element={<InvitePage />} />
      <Route element={<RequireAuth />}>
        <Route path="/first-password" element={<FirstPasswordPage />} />
        <Route path="/link-telegram" element={<LinkTelegramPage />} />
        <Route path="/start" element={<OnboardingPage />} />
        <Route element={<RequireTeam />}>
          <Route element={<Shell />}>
            <Route path="/" element={<InboxPage />} />
            <Route path="/assistant" element={<Navigate to="/?chat=1" replace />} />
            <Route path="/calendar" element={<CalendarPage />} />
            <Route path="/history" element={<HistoryPage />} />
            <Route path="/budget" element={<BudgetPage />} />
            <Route path="/stats" element={<StatsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/organization" element={<OrganizationPage />} />
            <Route path="/notifications" element={<NotificationsPage />} />
            <Route element={<ManageOnly />}>
              <Route path="/templates" element={<TemplatesPage />} />
              <Route path="/people" element={<PeoplePage />} />
              <Route path="/team" element={<Navigate to="/people" replace />} />
              <Route path="/audit" element={<AuditPage />} />
            </Route>
            <Route path="/admin/templates" element={<Navigate to="/templates" replace />} />
            <Route path="/admin/users" element={<Navigate to="/people" replace />} />
            <Route path="/admin/audit" element={<Navigate to="/audit" replace />} />
          </Route>
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
