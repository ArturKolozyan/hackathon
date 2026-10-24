import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type OrganizationSettings } from "../../api";
import { SettingGroup, SettingRow, SwitchRow } from "../../components/SettingRow";
import { TimezoneField } from "../../components/TimezoneField";
import { ErrorState, LoadingBlock, SaveStatus, useSaveState } from "../../components/ui";
import { useFresh } from "../../fresh";

type ToggleKey = "remind_7_days" | "remind_3_days" | "remind_1_day" | "remind_overdue";

const SCHEDULE: { key: ToggleKey; title: string; description: string }[] = [
  { key: "remind_7_days", title: "За 7 дней", description: "Заранее, чтобы успеть согласовать оплату" },
  { key: "remind_3_days", title: "За 3 дня", description: "Платёж попадает в «Скоро»" },
  { key: "remind_1_day", title: "За 1 день", description: "Последнее напоминание накануне срока" },
  { key: "remind_overdue", title: "О просрочке", description: "Каждый день, начиная со следующего после срока, пока платёж не оплачен" },
];

/** Owner-only organization settings, saved instantly (no «Сохранить»). */
export function OrganizationSection() {
  const [saved, setSaved] = useState<OrganizationSettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const save = useSaveState();
  const schedSave = useSaveState();

  const apply = useCallback((next: OrganizationSettings) => {
    setSaved(next);
  }, []);

  const fresh = useFresh();
  const load = useCallback(async () => {
    apply(await api<OrganizationSettings>("/api/v1/organization"));
  }, [apply]);

  useEffect(() => {
    load().catch((err: unknown) => setLoadError(err instanceof ApiError ? err.message : "Не загрузилось"));
  }, [load, fresh]);

  async function patch(body: Partial<OrganizationSettings>) {
    setSaved(await api<OrganizationSettings>("/api/v1/organization", { method: "PATCH", body: JSON.stringify(body) }));
  }

  /** Пояс сохраняется сразу после выбора; если сервер откажет, вернётся прежний. */
  function chooseTimezone(zone: string) {
    if (!saved || zone === saved.timezone) return;
    const before = saved;
    setSaved({ ...saved, timezone: zone });
    void save.run(() => patch({ timezone: zone }), () => setSaved(before));
  }

  /** Optimistic toggle: flip now, roll back if the server refuses. */
  function toggle(key: ToggleKey | "owner_overdue_copy", next: boolean, state: typeof save) {
    if (!saved) return;
    const before = saved;
    setSaved({ ...saved, [key]: next });
    void state.run(() => patch({ [key]: next }), () => setSaved(before));
  }

  if (loadError && !saved) return <ErrorState message={loadError} onRetry={() => void load().catch(() => undefined)} />;
  if (!saved) return <LoadingBlock label="Загружаем настройки организации…" />;

  const silent = SCHEDULE.every((item) => !saved[item.key]);

  return (
    <>
      <SettingGroup id="organization" title="Организация" status={<SaveStatus save={save} />} aside="для всех отделов">
        <SettingRow
          title="Часовой пояс"
          description="По нему считаются сроки и время напоминаний"
          htmlFor="org-tz"
          wide
          control={<TimezoneField id="org-tz" value={saved.timezone} onChange={chooseTimezone} />}
        />
        <SwitchRow
          title="Копия просрочки владельцу"
          description="Вы тоже получите сообщение, когда платёж в любом отделе просрочен"
          checked={saved.owner_overdue_copy}
          onChange={(next) => toggle("owner_overdue_copy", next, save)}
        />
      </SettingGroup>
      <SettingGroup id="schedule" title="Расписание напоминаний" status={<SaveStatus save={schedSave} />} aside="почта, Telegram, вебхук">
        {SCHEDULE.map((item) => (
          <SwitchRow
            key={item.key}
            title={item.title}
            description={item.description}
            checked={saved[item.key]}
            onChange={(next) => toggle(item.key, next, schedSave)}
          />
        ))}
        {silent && (
          <SettingRow
            title="Напоминания выключены"
            description="Платежи видны в инбоксе, но сообщений о сроках не будет. Включите хотя бы одно напоминание."
          />
        )}
      </SettingGroup>
    </>
  );
}
