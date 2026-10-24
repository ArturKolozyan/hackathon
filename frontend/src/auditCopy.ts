import { formatMoney } from "./format";

const ACTIONS: Record<string, string> = {
  "auth.login.success": "Вход",
  "auth.login.failure": "Неудачный вход",
  "auth.logout": "Выход",
  "template.create": "Шаблон создан",
  "template.update": "Шаблон изменён",
  "template.delete": "Шаблон в архиве",
  "user.create": "Человек создан",
  "user.update": "Человек изменён",
  "user.delete": "Человек отключён",
  "occurrence.paid": "Оплата",
  "occurrence.unpaid": "Оплата снята",
  "occurrence.paid_at": "Дата оплаты",
  "occurrence.receipt": "Чек",
  "budget.create": "Бюджет задан",
  "budget.update": "Бюджет изменён",
  "budget.delete": "Бюджет удалён",
  "telegram.team_connect": "Чат отдела подключён",
  "telegram.team_disconnect": "Чат отдела отключён",
  "telegram.user_link": "Telegram привязан",
  "telegram.user_unlink": "Telegram отвязан",
  "team.webhook": "Webhook отдела",
  "organization.update": "Настройки организации",
  "occurrence.update": "Период изменён",
};

const FIELDS: Record<string, string> = {
  title: "название",
  description: "комментарий",
  amount: "сумма",
  currency: "валюта",
  day_of_month: "день месяца",
  starts_on: "дата старта",
  responsible_user_id: "ответственный",
  is_archived: "архив",
  receipt_url: "ссылка на чек",
  receipt_note: "комментарий к чеку",
  full_name: "имя",
  email: "почта",
  role: "роль",
  is_active: "доступ",
  note: "заметка",
  paid_at: "дата оплаты",
  paid_amount: "фактическая сумма",
  due_date: "срок",
  periodicity: "периодичность",
  interval_months: "интервал",
  remind_archived_overdue: "напоминание просрочки архива",
};

export function actionLabel(action: string): string {
  return ACTIONS[action] ?? action.replaceAll(".", " · ").replaceAll("_", " ");
}

function fieldList(value: unknown): string {
  const items = Array.isArray(value) ? value : [value];
  return items.map((item) => FIELDS[String(item)] ?? String(item).replaceAll("_", " ")).join(", ");
}

function datePhrase(iso: string): string {
  const [year, month, day] = iso.slice(0, 10).split("-");
  if (!year || !month || !day) return iso;
  return `${day}.${month}.${year}`;
}

function phrase(key: string, value: unknown, meta: Record<string, unknown>): string | null {
  if (key === "amount" && typeof meta.currency === "string") return null;
  if (key === "currency" && "amount" in meta) return null;
  if (key === "password_changed") return value ? "пароль изменён" : null;
  if (key === "is_active") return value ? "доступ включён" : "доступ отключён";
  if (key === "source" && value === "telegram") return "откуда: Telegram";
  if (key === "state" && (value === "задан" || value === "снят")) return `адрес ${value}`;
  if (key === "reason" && value === "bot_removed") return "причина: бота удалили из чата";
  if (key === "role") {
    const role = value === "admin" ? "админ" : value === "user" ? "участник" : String(value);
    return `роль: ${role}`;
  }
  if (key === "period_type") {
    const kind = value === "month" ? "месяц" : value === "year" ? "год" : String(value);
    return `тип периода: ${kind}`;
  }
  if (key === "changes" && value && typeof value === "object" && !Array.isArray(value)) {
    const bits = Object.entries(value as Record<string, { was?: string; became?: string }>).map(([field, pair]) => {
      const label = FIELDS[field] ?? field.replaceAll("_", " ");
      return `${label}: ${pair?.was ?? "—"} → ${pair?.became ?? "—"}`;
    });
    return bits.join("; ");
  }
  if (key === "fields") return `что изменилось: ${fieldList(value)}`;
  if (key === "paid_on" && typeof value === "string") return `дата оплаты: ${datePhrase(value)}`;
  if (key === "email") return `почта: ${String(value)}`;
  if (key === "title") return `название: ${String(value)}`;
  if (key === "status") return `ответ сервера: ${String(value)}`;
  if (key === "period_key") return `период: ${String(value)}`;
  if (key === "amount" && typeof value === "string") return `сумма: ${value}`;
  if (key === "currency") return `валюта: ${String(value)}`;
  if (value == null || value === "") return null;
  const label = key.replaceAll("_", " ");
  const shown = Array.isArray(value) ? value.join(", ") : String(value);
  return `${label}: ${shown}`;
}

export function metaPhrase(meta: Record<string, unknown>): string {
  const parts: string[] = [];
  if (typeof meta.amount === "string" && typeof meta.currency === "string") {
    parts.push(`сумма: ${formatMoney(meta.amount, meta.currency)}`);
  }
  for (const [key, value] of Object.entries(meta)) {
    const line = phrase(key, value, meta);
    if (line) parts.push(line);
  }
  return parts.join(" · ") || "—";
}
