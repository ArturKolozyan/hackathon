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
  "user.invite": "Новая ссылка-приглашение",
  "user.invite_accept": "Приглашение принято",
  "occurrence.paid": "Оплата",
  "occurrence.unpaid": "Оплата снята",
  "occurrence.paid_at": "Дата оплаты",
  "occurrence.receipt": "Комментарий к чеку",
  "occurrence.receipt_attach": "Чек прикреплён",
  "occurrence.receipt_remove": "Чек убран",
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
  "team.create": "Отдел создан",
  "team.rename": "Отдел переименован",
  "team.delete": "Отдел удалён",
  "member.join": "Добавлен в отдел",
  "member.role": "Роль в отделе",
  "member.remove": "Убран из отдела",
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
  timezone: "часовой пояс",
  remind_7_days: "напоминание за 7 дней",
  remind_3_days: "напоминание за 3 дня",
  remind_1_day: "напоминание за 1 день",
  remind_overdue: "напоминание о просрочке",
  owner_overdue_copy: "копия просрочки владельцу",
};

/** Action kinds for the Логи filter, grouped by category. */
export const ACTION_GROUPS: { value: string; label: string; actions: string[] }[] = [
  { value: "payments", label: "Оплаты", actions: ["occurrence.paid", "occurrence.unpaid", "occurrence.paid_at", "occurrence.receipt_attach", "occurrence.receipt_remove", "occurrence.receipt", "occurrence.update"] },
  { value: "templates", label: "Шаблоны", actions: ["template.create", "template.update", "template.delete"] },
  { value: "people", label: "Люди и приглашения", actions: ["user.create", "user.update", "user.delete", "user.invite", "user.invite_accept"] },
  { value: "teams", label: "Отделы", actions: ["team.create", "team.rename", "team.delete", "member.join", "member.role", "member.remove"] },
  { value: "budget", label: "Бюджет", actions: ["budget.create", "budget.update", "budget.delete"] },
  {
    value: "channels",
    label: "Telegram и вебхук",
    actions: ["telegram.team_connect", "telegram.team_disconnect", "telegram.user_link", "telegram.user_unlink", "team.webhook"],
  },
  { value: "auth", label: "Входы и выходы", actions: ["auth.login.success", "auth.login.failure", "auth.logout"] },
  { value: "organization", label: "Настройки организации", actions: ["organization.update"] },
];

export function actionLabel(action: string): string {
  return ACTIONS[action] ?? action.replaceAll(".", " ").replaceAll("_", " ");
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
    const role = value === "admin" ? "админ" : value === "user" || value === "member" ? "участник" : value === "owner" ? "владелец" : String(value);
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
  if (key === "file") return value ? `файл: ${String(value)}` : null;
  if (key === "title" || key === "name") return `название: ${String(value)}`;
  if (key === "team") return `отдел: ${String(value)}`;
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
  return parts.join("; ") || "—";
}
