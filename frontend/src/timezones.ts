/**
 * Часовые пояса СНГ для настроек организации. Тот же список проверяет бэкенд (app/core/timezones.py).
 * Смещение и местное время считаются через Intl в момент показа, поэтому переходы на летнее время учтены.
 */
export type CisZone = { id: string; city: string };

export const DEFAULT_TIMEZONE = "Europe/Moscow";

export const CIS_TIMEZONES: CisZone[] = [
  { id: "Europe/Kaliningrad", city: "Калининград" },
  { id: "Europe/Chisinau", city: "Кишинёв" },
  { id: "Europe/Moscow", city: "Москва, Санкт-Петербург" },
  { id: "Europe/Minsk", city: "Минск" },
  { id: "Europe/Samara", city: "Самара, Ижевск" },
  { id: "Asia/Yerevan", city: "Ереван" },
  { id: "Asia/Baku", city: "Баку" },
  { id: "Asia/Yekaterinburg", city: "Екатеринбург" },
  { id: "Asia/Tashkent", city: "Ташкент, Самарканд" },
  { id: "Asia/Ashgabat", city: "Ашхабад" },
  { id: "Asia/Dushanbe", city: "Душанбе" },
  { id: "Asia/Almaty", city: "Астана, Алматы" },
  { id: "Asia/Bishkek", city: "Бишкек" },
  { id: "Asia/Omsk", city: "Омск" },
  { id: "Asia/Novosibirsk", city: "Новосибирск" },
  { id: "Asia/Krasnoyarsk", city: "Красноярск" },
  { id: "Asia/Irkutsk", city: "Иркутск" },
  { id: "Asia/Yakutsk", city: "Якутск" },
  { id: "Asia/Vladivostok", city: "Владивосток" },
  { id: "Asia/Magadan", city: "Магадан" },
  { id: "Asia/Kamchatka", city: "Камчатка" },
];

const partsCache = new Map<string, Intl.DateTimeFormat>();

function partsFormat(zone: string): Intl.DateTimeFormat {
  let format = partsCache.get(zone);
  if (!format) {
    format = new Intl.DateTimeFormat("en-US", {
      timeZone: zone,
      hourCycle: "h23",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
    partsCache.set(zone, format);
  }
  return format;
}

/** Смещение пояса от UTC в минутах на момент `at`. */
export function offsetMinutes(zone: string, at: Date = new Date()): number {
  try {
    const parts = Object.fromEntries(partsFormat(zone).formatToParts(at).map((part) => [part.type, part.value]));
    const local = Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day), Number(parts.hour) % 24, Number(parts.minute));
    const utc = Math.floor(at.getTime() / 60000) * 60000;
    return Math.round((local - utc) / 60000);
  } catch {
    return 0;
  }
}

/** «МСК», «МСК+2», «МСК−1». */
export function mskLabel(zone: string, at: Date = new Date()): string {
  const diff = offsetMinutes(zone, at) - offsetMinutes(DEFAULT_TIMEZONE, at);
  if (diff === 0) return "МСК";
  const sign = diff > 0 ? "+" : "−";
  const abs = Math.abs(diff);
  const hours = Math.floor(abs / 60);
  const minutes = abs % 60;
  return `МСК${sign}${hours}${minutes ? `:${String(minutes).padStart(2, "0")}` : ""}`;
}

/** Местное время в поясе: «14:05». */
export function localTime(zone: string, at: Date = new Date()): string {
  try {
    return new Intl.DateTimeFormat("ru-RU", { timeZone: zone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(at);
  } catch {
    return "";
  }
}

/** Список, отсортированный по текущему смещению; при равенстве порядок из CIS_TIMEZONES. */
export function sortedZones(at: Date = new Date()): CisZone[] {
  return CIS_TIMEZONES.map((zone, index) => ({ zone, index, offset: offsetMinutes(zone.id, at) }))
    .sort((a, b) => a.offset - b.offset || a.index - b.index)
    .map((row) => row.zone);
}

export function zoneCity(id: string): string {
  return CIS_TIMEZONES.find((zone) => zone.id === id)?.city ?? id;
}
