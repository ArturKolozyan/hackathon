import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type OrganizationSettings } from "../../api";
import { RowInput, SettingGroup, SettingRow, SwitchRow } from "../../components/SettingRow";
import { ErrorState, LoadingBlock, SaveStatus, useDebounced, useSaveState } from "../../components/ui";

type TextKey = "timezone" | "reminder_days" | "overdue_repeat_days";

/** Mirrors backend parse_reminder_days: integers 0–90, at least one ≥ 3. */
export function reminderError(raw: string): string | null {
  const parts = raw
    .replace(/;/g, ",")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  if (parts.length === 0) return "Укажите дни через запятую, например 7, 3";
  for (const part of parts) {
    if (!/^\d+$/.test(part)) return "Только целые числа через запятую";
    const value = Number(part);
    if (value > 90) return "День напоминания — от 0 до 90";
  }
  if (!parts.some((part) => Number(part) >= 3)) return "Нужно хотя бы одно напоминание не позже чем за 3 дня до срока";
  return null;
}

function timezoneError(raw: string): string | null {
  const value = raw.trim();
  if (!value) return "Укажите часовой пояс, например Europe/Moscow";
  try {
    new Intl.DateTimeFormat("ru-RU", { timeZone: value });
    return null;
  } catch {
    return "Такого часового пояса нет. Пример: Europe/Moscow";
  }
}

function repeatError(raw: string): string | null {
  const value = Number(raw);
  if (!raw.trim() || !Number.isInteger(value) || value < 1 || value > 90) return "От 1 до 90 дней";
  return null;
}

const CHECKS: Record<TextKey, (raw: string) => string | null> = {
  timezone: timezoneError,
  reminder_days: reminderError,
  overdue_repeat_days: repeatError,
};

/** Owner-only organization settings, saved field by field (no «Сохранить»). */
export function OrganizationSection() {
  const [saved, setSaved] = useState<OrganizationSettings | null>(null);
  const [draft, setDraft] = useState<Record<TextKey, string>>({ timezone: "", reminder_days: "", overdue_repeat_days: "" });
  const [copy, setCopy] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<TextKey, string | null>>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const save = useSaveState();
  const schedSave = useSaveState();

  const apply = useCallback((next: OrganizationSettings) => {
    setSaved(next);
    setDraft({
      timezone: next.timezone,
      reminder_days: next.reminder_days.split(",").join(", "),
      overdue_repeat_days: String(next.overdue_repeat_days),
    });
    setCopy(next.owner_overdue_copy);
  }, []);

  const load = useCallback(async () => {
    apply(await api<OrganizationSettings>("/api/v1/organization"));
  }, [apply]);

  useEffect(() => {
    load().catch((err: unknown) => setLoadError(err instanceof ApiError ? err.message : "Не загрузилось"));
  }, [load]);

  async function patch(body: Partial<OrganizationSettings>) {
    const next = await api<OrganizationSettings>("/api/v1/organization", { method: "PATCH", body: JSON.stringify(body) });
    setSaved(next);
  }

  function commit(key: TextKey, raw: string) {
    const problem = CHECKS[key](raw);
    setErrors((current) => ({ ...current, [key]: problem }));
    if (problem || !saved) return;
    const value = key === "overdue_repeat_days" ? Number(raw) : key === "reminder_days" ? raw.replace(/\s/g, "") : raw.trim();
    const current = key === "overdue_repeat_days" ? saved.overdue_repeat_days : saved[key];
    if (String(value) === String(current)) return;
    void (key === "timezone" ? save : schedSave).run(async () => {
      try {
        await patch({ [key]: value } as Partial<OrganizationSettings>);
      } catch (err) {
        if (err instanceof ApiError && err.status === 422) setErrors((now) => ({ ...now, [key]: err.message }));
        throw err;
      }
    });
  }

  const saver = useDebounced<{ key: TextKey; raw: string }>(({ key, raw }) => commit(key, raw), 600);

  function onText(key: TextKey, raw: string) {
    setDraft((current) => ({ ...current, [key]: raw }));
    if (errors[key]) setErrors((current) => ({ ...current, [key]: CHECKS[key](raw) }));
    saver.schedule({ key, raw });
  }

  if (loadError && !saved) return <ErrorState message={loadError} onRetry={() => void load().catch(() => undefined)} />;
  if (!saved) return <LoadingBlock label="Загружаем настройки организации…" />;

  return (
    <>
      <SettingGroup id="organization" title="Организация" status={<SaveStatus save={save} />} aside="для всех отделов">
        <SettingRow
          title="Часовой пояс"
          description="По нему считаются сроки и время напоминаний"
          htmlFor="org-tz"
          error={errors.timezone}
          control={
            <RowInput
              id="org-tz"
              value={draft.timezone}
              placeholder="Europe/Moscow"
              invalid={Boolean(errors.timezone)}
              onChange={(raw) => onText("timezone", raw)}
              onBlur={() => saver.flush()}
            />
          }
        />
        <SwitchRow
          title="Копия просрочки владельцу"
          description="Вы тоже получите сообщение, когда платёж в любом отделе просрочен"
          checked={copy}
          onChange={(next) => {
            const before = copy;
            setCopy(next);
            void save.run(() => patch({ owner_overdue_copy: next }), () => setCopy(before));
          }}
        />
      </SettingGroup>
      <SettingGroup id="schedule" title="Расписание напоминаний" status={<SaveStatus save={schedSave} />}>
        <SettingRow
          title="За сколько дней напоминать"
          description="Дни до срока через запятую. По умолчанию — за 7 и за 3 дня"
          htmlFor="org-days"
          error={errors.reminder_days}
          hint="Хотя бы одно напоминание — не позже чем за 3 дня до срока, чтобы успеть оплатить."
          control={
            <RowInput
              id="org-days"
              value={draft.reminder_days}
              placeholder="7, 3"
              invalid={Boolean(errors.reminder_days)}
              onChange={(raw) => onText("reminder_days", raw)}
              onBlur={() => saver.flush()}
            />
          }
        />
        <SettingRow
          title="Повторять о просрочке"
          description="Со следующего дня после срока и затем каждые N дней, пока долг не закрыт"
          htmlFor="org-repeat"
          error={errors.overdue_repeat_days}
          control={
            <RowInput
              id="org-repeat"
              value={draft.overdue_repeat_days}
              suffix="дн."
              inputMode="numeric"
              invalid={Boolean(errors.overdue_repeat_days)}
              onChange={(raw) => onText("overdue_repeat_days", raw.replace(/\D/g, "").slice(0, 2))}
              onBlur={() => saver.flush()}
            />
          }
        />
      </SettingGroup>
    </>
  );
}
