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
  is_owner: boolean;
  email_verified: boolean;
  created_at: string;
  active_team_id: string | null;
  memberships: Membership[];
  telegram_chat_id: string | null;
  telegram_linked: boolean;
  must_change_password: boolean;
  telegram_onboarding_done: boolean;
};

export type DemoAccount = {
  label: string;
  email: string;
  password: string;
};

export type PublicConfig = {
  show_demo_credentials: boolean;
  accounts: DemoAccount[];
};

export type Features = {
  assistant: boolean;
  assistant_available: boolean;
  voice: boolean;
  email: boolean;
  telegram: boolean;
  bot_alive: boolean;
};

export type DirectoryUser = {
  id: string;
  email: string;
  full_name: string;
  role: "owner" | "admin" | "user";
  is_active: boolean;
  is_owner: boolean;
  telegram_linked: boolean;
  must_change_password: boolean;
  invite_pending: boolean;
  invite_url?: string | null;
  departments: { id: string; name: string; role: string }[];
};

export type InviteLink = {
  url: string;
};

export type InviteInfo = {
  email: string;
  full_name: string;
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

export type Receipt = {
  name: string;
  content_type: string;
  size: number;
  uploaded_at: string | null;
  url: string;
};

export type Occurrence = {
  id: string;
  recurring_payment_id: string;
  title: string;
  description: string | null;
  period: string;
  period_label: string;
  due_date: string;
  amount: string;
  paid_amount: string | null;
  currency: string;
  status: "overdue" | "due_soon" | "upcoming" | "paid";
  bucket: "overdue" | "soon" | "rest" | "history";
  paid_at: string | null;
  paid_on: string | null;
  paid_on_time: boolean | null;
  days_delta: number;
  lateness_days: number | null;
  note: string | null;
  team_id: string;
  receipt: Receipt | null;
  receipt_note: string | null;
  telegram_reminded_at: string | null;
  template_archived: boolean;
  /** Будущий период, которого ещё нет в базе: только показать. */
  planned?: boolean;
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
  teams: { id: string; name: string }[];
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
  timezone: string;
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
  expires_at: string | null;
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

export type NotifyTeam = {
  id: string;
  name: string;
};

export type EmailTeam = {
  id: string;
  name: string;
  enabled: boolean;
  scope: "mine" | "department";
};

export type PersonalChannel = {
  enabled: boolean;
  team_ids: string[];
  teams: EmailTeam[];
  notify_scope: "mine" | "department";
  notify_overdue: boolean;
  bot_alive: boolean;
  address: string | null;
  linked: boolean;
  username: string | null;
  display_name: string | null;
  bot_ready: boolean;
  bot_username: string | null;
  test_pending: boolean;
  test_sent_at: string | null;
  test_error: string | null;
};

export type NotificationsView = {
  email: PersonalChannel;
  telegram: PersonalChannel;
  teams: NotifyTeam[];
  team: {
    team_id: string;
    team_name: string;
    can_manage: boolean;
    telegram: TeamTelegram;
    webhook_url: string | null;
    webhook_checked_at: string | null;
    webhook_check_error: string | null;
  };
};

export type Probe = {
  ok: boolean;
  pending: boolean;
  detail: string;
};

export type Template = {
  id: string;
  title: string;
  description: string | null;
  amount: string;
  currency: string;
  day_of_month: number;
  starts_on: string;
  next_payment_date: string | null;
  periodicity: string;
  interval_months: number | null;
  applies_from: string | null;
  debt_count: number;
  is_archived: boolean;
  responsible: { id: string; full_name: string; email: string } | null;
  open_count: number;
  paid_count: number;
  created_at: string;
};

export type OrganizationSettings = {
  timezone: string;
  remind_7_days: boolean;
  remind_3_days: boolean;
  remind_1_day: boolean;
  remind_overdue: boolean;
  owner_overdue_copy: boolean;
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

export type AssistantPerson = { id: string; full_name: string };

export type AssistantAlternative = {
  occurrence_id: string;
  period_label: string;
  due_date: string;
  status: string;
};

export type AssistantAction = {
  id: string;
  kind: "create_payment" | "update_payment" | "archive_payment" | "mark_paid" | "mark_unpaid";
  status: "pending" | "running" | "confirmed" | "cancelled" | "failed";
  summary: string;
  payload: {
    fields?: Record<string, unknown>;
    people?: AssistantPerson[];
    alternatives?: AssistantAlternative[];
    editable?: boolean;
  };
  result_text: string | null;
};

export type AssistantConfirm = {
  message: AssistantMessage;
  action: AssistantAction;
};

export type AssistantMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  action: AssistantAction | null;
  /** Три вопроса-подсказки под свежим ответом Кипа; в истории пусто. */
  suggestions?: string[];
};

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
  departments: { id: string; name: string }[];
  paid_count: number;
  paid_on_time: number;
  monthly: StatsMonth[];
  operations: { items: StatsOperation[]; total: number; page: number; page_size: number } | null;
};

export type StatsMonth = { month: string; currency: string; paid: string; overdue: string; planned: string };

export type StatsOperation = {
  occurrence_id: string;
  team_id: string;
  team_name: string;
  title: string;
  period_label: string;
  due_date: string;
  amount: string;
  paid_amount: string | null;
  currency: string;
  status: "overdue" | "due_soon" | "upcoming" | "paid";
  paid_on: string | null;
  lateness_days: number | null;
  has_receipt: boolean;
  planned?: boolean;
  responsible: { id: string; full_name: string; email: string } | null;
};

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const team = storedTeamId();
  if (team && !headers.has("X-Team-Id")) headers.set("X-Team-Id", team);
  const response = await fetch(path, { cache: "no-store", ...options, headers, credentials: "include" });
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

export async function downloadCsv(path: string, filename = "occurrences.csv"): Promise<void> {
  const headers = new Headers();
  const team = storedTeamId();
  if (team) headers.set("X-Team-Id", team);
  const response = await fetch(path, { cache: "no-store", credentials: "include", headers });
  if (!response.ok) {
    const raw = await response.text();
    let data: unknown = null;
    try {
      data = raw ? JSON.parse(raw) : null;
    } catch {
      data = null;
    }
    throw new ApiError(response.status, messageFrom(data, response.status));
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function parseSseBlock(block: string): { event: string; data: unknown } | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return null;
  return { event, data: JSON.parse(dataLines.join("\n")) };
}

function withTeam(init: HeadersInit): Headers {
  const headers = new Headers(init);
  const team = storedTeamId();
  if (team) headers.set("X-Team-Id", team);
  return headers;
}

export async function streamAssistant(text: string, onToken: (chunk: string) => void): Promise<AssistantMessage> {
  const response = await fetch("/api/v1/assistant/messages?stream=true", {
    method: "POST",
    credentials: "include",
    headers: withTeam({ "Content-Type": "application/json", Accept: "text/event-stream" }),
    body: JSON.stringify({ text }),
  });
  if (!response.ok || !response.body) {
    const raw = await response.text();
    let data: unknown = null;
    try {
      data = raw ? JSON.parse(raw) : null;
    } catch {
      data = null;
    }
    throw new ApiError(response.status, messageFrom(data, response.status));
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let doneMessage: AssistantMessage | null = null;
  while (true) {
    const step = await reader.read();
    if (step.done) break;
    buffer += decoder.decode(step.value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      const parsed = parseSseBlock(block);
      if (!parsed || !parsed.data || typeof parsed.data !== "object") continue;
      const payload = parsed.data as { text?: string; detail?: string; message?: AssistantMessage };
      if (parsed.event === "token" && payload.text) onToken(payload.text);
      if (parsed.event === "error") throw new ApiError(503, payload.detail || "Кип не ответил");
      if (parsed.event === "done" && payload.message) doneMessage = payload.message;
    }
  }
  if (!doneMessage) throw new ApiError(503, "Кип не ответил. Повторите фразу.");
  return doneMessage;
}

export async function clearAssistant(): Promise<void> {
  await api<void>("/api/v1/assistant/messages", { method: "DELETE" });
}

export async function transcribe(blob: Blob): Promise<string> {
  const form = new FormData();
  const name = blob.type.includes("ogg") ? "speech.ogg" : "speech.webm";
  form.append("file", blob, name);
  const response = await fetch("/api/v1/assistant/speech", {
    method: "POST",
    body: form,
    credentials: "include",
    headers: withTeam({}),
  });
  const raw = await response.text();
  let data: unknown = null;
  try {
    data = raw ? JSON.parse(raw) : null;
  } catch {
    data = null;
  }
  if (!response.ok) throw new ApiError(response.status, messageFrom(data, response.status));
  const text = data && typeof data === "object" && "text" in data ? (data as { text: unknown }).text : "";
  return typeof text === "string" ? text : "";
}
