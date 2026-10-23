export type Role = "admin" | "user";

export type User = {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  telegram_chat_id: string | null;
  created_at: string;
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
  currency: string;
  status: "overdue" | "due_soon" | "upcoming" | "paid";
  bucket: "overdue" | "soon" | "rest" | "history";
  paid_at: string | null;
  paid_on: string | null;
  paid_on_time: boolean | null;
  days_delta: number;
  lateness_days: number | null;
  note: string | null;
  template_archived: boolean;
  responsible: { id: string; full_name: string; email: string };
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
  soon_days: number;
  counts: { overdue: number; due_soon: number; upcoming: number; paid: number };
  by_currency: CurrencyTotals[];
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
  responsible: { id: string; full_name: string; email: string };
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

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
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
