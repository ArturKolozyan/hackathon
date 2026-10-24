import { useEffect, useState } from "react";
import { api } from "./api";

type Rates = { on: string | null; rates: Record<string, string> };

const TTL = 60 * 60 * 1000;
let cached: { at: number; value: Rates } | null = null;
let pending: Promise<Rates> | null = null;

function load(): Promise<Rates> {
  if (cached && Date.now() - cached.at < TTL) return Promise.resolve(cached.value);
  if (!pending) {
    pending = api<Rates>("/api/v1/rates")
      .then((value) => {
        cached = { at: Date.now(), value };
        return value;
      })
      .catch(() => ({ on: null, rates: {} }))
      .finally(() => {
        pending = null;
      });
  }
  return pending;
}

/** Курсы ЦБ для подсказки. Пока не пришли или недоступны — null, подсказки нет. */
export function useRates(): Rates | null {
  const [rates, setRates] = useState<Rates | null>(cached?.value ?? null);
  useEffect(() => {
    let alive = true;
    void load().then((value) => alive && setRates(value));
    return () => {
      alive = false;
    };
  }, []);
  return rates;
}

const DAY = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", timeZone: "UTC" });

export function rubText(amount: string, currency: string, rates: Rates | null): string | null {
  if (currency === "RUB" || !rates?.on) return null;
  const rate = Number(rates.rates[currency]);
  const value = Number(String(amount).replace(/\s/g, "").replace(",", "."));
  if (!(rate > 0) || !Number.isFinite(value) || value <= 0) return null;
  const rub = Math.round(value * rate)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, "\u00a0");
  const [year, month, day] = rates.on.split("-").map(Number);
  return `≈\u00a0${rub}\u00a0₽ по курсу ЦБ на ${DAY.format(Date.UTC(year, month - 1, day))}`;
}

/** Строка «≈ 92 340 ₽ по курсу ЦБ на 24 октября» под суммой в USD или EUR. Для рублей и без курса — ничего. */
export function RubHint({ amount, currency, className = "rub-hint" }: { amount: string; currency: string; className?: string }) {
  const rates = useRates();
  const text = rubText(amount, currency, rates);
  if (!text) return null;
  return <span className={className}>{text}</span>;
}
