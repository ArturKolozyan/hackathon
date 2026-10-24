export type TeamRole = "owner" | "admin" | "member";

export type Membership = {
  team_id: string;
  team_name: string;
  role: TeamRole;
};

export type Me = {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  email_verified: boolean;
  created_at: string;
  active_team_id: string | null;
  memberships: Membership[];
  telegram_chat_id: string | null;
};

export type Member = {
  id: string;
  email: string;
  full_name: string;
  role: TeamRole;
  is_active: boolean;
};

export type Sent = {
  delivery: "log" | "smtp" | string;
  message: string;
};

const TEAM_KEY = "rekeeper-team";

export function storedTeamId(): string | null {
  return localStorage.getItem(TEAM_KEY);
}

export function setStoredTeamId(id: string | null) {
  if (id) localStorage.setItem(TEAM_KEY, id);
  else localStorage.removeItem(TEAM_KEY);
}

export type Occurrence = {
  id: string;
  recurring_payment_id: string;
  title: string;
  description: string | null;
  period: string;
  period_label: string;
  due_date: string;
  amount: string;
  currency: string;
  status: "overdue" | "due_soon" | "upcoming" | "paid";
  bucket: "overdue" | "soon" | "rest" | "history";
  paid_at: string | null;
  paid_on: string | null;
  paid_on_time: boolean | null;
  days_delta: number;
  lateness_days: number | null;
  note: string | null;
  receipt_url: string | null;
  receipt_note: string | null;
  telegram_reminded_at: string | null;
  template_archived: boolean;
  responsible: { id: string; full_name: string; email: string } | null;
  paid_by: { id: string; full_name: string; email: string } | null;
};

export type Inbox = {
  timezone: string;
  today: string;
  soon_days: number;
  overdue: Occurrence[];
  soon: Occurrence[];
  rest: Occurrence[];
};

export type OccurrenceList = {
  timezone: string;
  today: string;
  soon_days: number;
  items: Occurrence[];
};

export type CurrencyTotals = {
  currency: string;
  overdue_amount: string;
  due_soon_amount: string;
  upcoming_amount: string;
  paid_amount: string;
  open_amount: string;
};

export type Summary = {
  timezone: string;
  today: string;
  as_of: string | null;
  soon_days: number;
  counts: { overdue: number; due_soon: number; upcoming: number; paid: number };
  by_currency: CurrencyTotals[];
};

export type CalendarMonth = {
  timezone: string;
  year: number;
  month: number;
  today: string;
  days: { date: string; items: Occurrence[] }[];
};

export type BudgetLine = {
  id: string | null;
  currency: string;
  plan_amount: string | null;
  fact_amount: string;
  expected_amount: string;
};

export type BudgetReport = {
  period_type: "month" | "year";
  period_key: string;
  timezone: string;
  rows: BudgetLine[];
};

export type AuditItem = {
  id: string;
  at: string;
  actor_user_id: string | null;
  actor_name: string | null;
  actor_email: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  meta: Record<string, unknown>;
};

export type AuditList = {
  items: AuditItem[];
  total: number;
};

export type TelegramSelf = {
  linked: boolean;
  username: string | null;
  display_name: string | null;
  reminders_enabled: boolean;
  bot_ready: boolean;
  bot_username: string | null;
};

export type TelegramLink = {
  url: string;
  expires_at: string;
};

export type TeamTelegram = {
  status: "connected" | "disconnected" | "absent";
  source: "database" | "env" | "none";
  chat_title: string | null;
  chat_id: string | null;
  bot_username: string | null;
  bot_ready: boolean;
  test_pending: boolean;
  test_sent_at: string | null;
  test_error: string | null;
};

export type Template = {
  id: string;
  title: string;
  description: string | null;
  amount: string;
  currency: string;
  day_of_month: number;
  starts_on: string;
  is_archived: boolean;
  responsible: { id: string; full_name: string; email: string } | null;
  open_count: number;
  paid_count: number;
  created_at: string;
};

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function messageFrom(data: unknown, status: number): string {
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0] as { msg?: string; loc?: unknown[] };
      const loc = Array.isArray(first.loc) ? first.loc.filter((part) => part !== "body").join(".") : "";
      return loc && first.msg ? `${loc}: ${first.msg}` : first.msg || "Проверьте поля";
    }
  }
  return `Ошибка ${status}`;
}

export type Stats = {
  timezone: string;
  today: string;
  paid_from: string;
  paid_to: string;
  due_from: string | null;
  due_to: string | null;
  to_pay: { currency: string; amount: string; count: number }[];
  overdue: { currency: string; amount: string; count: number }[];
  paid: { currency: string; amount: string; count: number }[];
  nearest: {
    occurrence_id: string;
    team_id: string;
    team_name: string;
    title: string;
    due_date: string;
    amount: string;
    currency: string;
    status: string;
    responsible: { id: string; full_name: string; email: string } | null;
  }[];
  by_team: {
    team_id: string;
    team_name: string;
    role: TeamRole;
    to_pay: { currency: string; amount: string; count: number }[];
    overdue: { currency: string; amount: string; count: number }[];
    paid: { currency: string; amount: string; count: number }[];
  }[];
  people: { id: string; full_name: string; email: string }[];
};

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const team = storedTeamId();
  if (team && !headers.has("X-Team-Id")) headers.set("X-Team-Id", team);
  const response = await fetch(path, { ...options, headers, credentials: "include" });
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!response.ok) throw new ApiError(response.status, messageFrom(data, response.status));
  return data as T;
}
