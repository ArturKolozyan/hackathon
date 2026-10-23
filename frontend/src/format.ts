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

export function shortDue(iso: string): string {
  const [, month, day] = iso.slice(0, 10).split("-");
  return `${day}.${month}`;
}

function daysWord(count: number): string {
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

export function chipTone(row: CurrencyTotals): { amount: string; label: string; tone: string } {
  const overdue = Number(row.overdue_amount);
  const soon = Number(row.due_soon_amount);
  const upcoming = Number(row.upcoming_amount);
  if (overdue > 0) return { amount: row.overdue_amount, label: "просрочено", tone: "overdue" };
  if (soon > 0) return { amount: row.due_soon_amount, label: "скоро", tone: "soon" };
  if (upcoming > 0) return { amount: row.upcoming_amount, label: "впереди", tone: "rest" };
  return { amount: row.paid_amount, label: "закрыто", tone: "paid" };
}
