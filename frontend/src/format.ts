import type { CurrencyTotals, Occurrence } from "./api";

export function formatMoney(amount: string, currency: string): string {
  const negative = amount.trim().startsWith("-");
  const [wholeRaw, fracRaw = "00"] = amount.replace("-", "").split(".");
  const grouped = wholeRaw.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  const cents = (fracRaw + "00").slice(0, 2);
  const value = `${negative ? "−" : ""}${cents === "00" ? grouped : `${grouped},${cents}`}`;
  if (currency === "USD") return `$${value}`;
  if (currency === "EUR") return `€${value}`;
  return `${value} ₽`;
}

const MONTHS = [
  "январь",
  "февраль",
  "март",
  "апрель",
  "май",
  "июнь",
  "июль",
  "август",
  "сентябрь",
  "октябрь",
  "ноябрь",
  "декабрь",
];

export function monthTitle(year: number, month: number): string {
  return `${MONTHS[month - 1]} ${year}`;
}

export function shiftMonth(year: number, month: number, delta: number): { year: number; month: number } {
  const index = year * 12 + (month - 1) + delta;
  return { year: Math.floor(index / 12), month: (index % 12) + 1 };
}

export function statusTone(status: Occurrence["status"]): "overdue" | "soon" | "paid" | "neutral" {
  if (status === "overdue") return "overdue";
  if (status === "due_soon") return "soon";
  if (status === "paid") return "paid";
  return "neutral";
}

export function shortDue(iso: string): string {
  const [, month, day] = iso.slice(0, 10).split("-");
  return `${day}.${month}`;
}

const MONTHS_GENITIVE = [
  "января",
  "февраля",
  "марта",
  "апреля",
  "мая",
  "июня",
  "июля",
  "августа",
  "сентября",
  "октября",
  "ноября",
  "декабря",
];

export function longDue(iso: string): string {
  const [year, month, day] = iso.slice(0, 10).split("-");
  const index = Number(month) - 1;
  if (!year || !MONTHS_GENITIVE[index] || !day) return iso;
  return `${Number(day)} ${MONTHS_GENITIVE[index]} ${year}`;
}

export function daysWord(count: number): string {
  const abs = Math.abs(count);
  const tail = abs % 10;
  const hundred = abs % 100;
  if (tail === 1 && hundred !== 11) return "день";
  if (tail >= 2 && tail <= 4 && (hundred < 12 || hundred > 14)) return "дня";
  return "дней";
}

export function urgency(item: Occurrence): string {
  if (item.status === "paid") {
    if (item.paid_on_time) return "оплачено вовремя";
    const late = item.lateness_days ?? 0;
    return `оплачено на ${late} ${daysWord(late)} позже`;
  }
  if (item.days_delta < 0) {
    const late = -item.days_delta;
    return `просрочено на ${late} ${daysWord(late)}`;
  }
  if (item.days_delta === 0) return "срок сегодня";
  if (item.days_delta === 1) return "завтра";
  return `через ${item.days_delta} ${daysWord(item.days_delta)}`;
}

export function statusPill(item: Occurrence): { tone: "overdue" | "soon" | "paid" | "neutral"; label: string } {
  const label = urgency(item);
  if (item.status === "paid") return { tone: "paid", label };
  if (item.status === "overdue" || item.bucket === "overdue") return { tone: "overdue", label };
  if (item.status === "due_soon" || item.bucket === "soon") return { tone: "soon", label };
  return { tone: "neutral", label };
}

export function statusShort(status: Occurrence["status"]): string {
  if (status === "overdue") return "Просрочено";
  if (status === "due_soon") return "Скоро";
  if (status === "paid") return "Оплачено";
  return "Впереди";
}

export function capitalMonth(year: number, month: number): string {
  const title = monthTitle(year, month);
  return title.charAt(0).toUpperCase() + title.slice(1);
}

export function isoParts(iso: string): { year: number; month: number; day: number } {
  const [year, month, day] = iso.slice(0, 10).split("-").map(Number);
  return { year, month, day };
}

export function addIsoDays(iso: string, delta: number): string {
  const { year, month, day } = isoParts(iso);
  const date = new Date(Date.UTC(year, month - 1, day));
  date.setUTCDate(date.getUTCDate() + delta);
  const y = date.getUTCFullYear();
  const m = String(date.getUTCMonth() + 1).padStart(2, "0");
  const d = String(date.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function weekStart(iso: string): string {
  const { year, month, day } = isoParts(iso);
  const date = new Date(Date.UTC(year, month - 1, day));
  const offset = (date.getUTCDay() + 6) % 7;
  return addIsoDays(iso, -offset);
}

export function isWeekend(iso: string): boolean {
  const { year, month, day } = isoParts(iso);
  const dow = new Date(Date.UTC(year, month - 1, day)).getUTCDay();
  return dow === 0 || dow === 6;
}

export function shiftAnchorMonth(iso: string, delta: number): string {
  const { year, month, day } = isoParts(iso);
  const next = shiftMonth(year, month, delta);
  const last = new Date(Date.UTC(next.year, next.month, 0)).getUTCDate();
  const clamped = Math.min(day, last);
  return `${next.year}-${String(next.month).padStart(2, "0")}-${String(clamped).padStart(2, "0")}`;
}

export function weekLabel(startIso: string, endIso: string): string {
  const start = isoParts(startIso);
  const end = isoParts(endIso);
  if (start.year === end.year && start.month === end.month) {
    return `${start.day}–${end.day} ${MONTHS_GENITIVE[start.month - 1]} ${start.year}`;
  }
  if (start.year === end.year) {
    return `${start.day} ${MONTHS_GENITIVE[start.month - 1]} – ${end.day} ${MONTHS_GENITIVE[end.month - 1]} ${start.year}`;
  }
  return `${start.day} ${MONTHS_GENITIVE[start.month - 1]} ${start.year} – ${end.day} ${MONTHS_GENITIVE[end.month - 1]} ${end.year}`;
}

export function chipTone(row: CurrencyTotals): { amount: string; label: string; tone: string } {
  const overdue = Number(row.overdue_amount);
  const soon = Number(row.due_soon_amount);
  const upcoming = Number(row.upcoming_amount);
  if (overdue > 0) return { amount: row.overdue_amount, label: "просрочено", tone: "overdue" };
  if (soon > 0) return { amount: row.due_soon_amount, label: "скоро", tone: "soon" };
  if (upcoming > 0) return { amount: row.upcoming_amount, label: "впереди", tone: "rest" };
  return { amount: row.paid_amount, label: "закрыто", tone: "paid" };
}

/** Two-letter avatar initials: 'Админ' -> 'АД', 'Maria Sokolova' -> 'MS'. */
export function initials(name: string | undefined | null): string {
  const words = (name ?? "").trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return Array.from(words[0]).slice(0, 2).join("").toUpperCase();
  return (Array.from(words[0])[0] + Array.from(words[1])[0]).toUpperCase();
}

/** "2026-10" ± delta months → "2026-11". */
export function shiftMonthKey(key: string, delta: number): string {
  const [year, month] = key.split("-").map(Number);
  if (!year || !month) return key;
  const next = shiftMonth(year, month, delta);
  return `${next.year}-${String(next.month).padStart(2, "0")}`;
}
