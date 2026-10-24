import { FormEvent, useCallback, useEffect, useState } from "react";
import { ApiError, api, type OrganizationSettings } from "../api";
import { useAuth } from "../auth";
import { ErrorState, LoadingBlock } from "../components/ui";

export function OrganizationPage() {
  const { user } = useAuth();
  const [form, setForm] = useState<OrganizationSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setForm(await api<OrganizationSettings>("/api/v1/organization"));
  }, []);

  useEffect(() => {
    if (!user?.is_owner) return;
    load().catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Не загрузилось"));
  }, [load, user?.is_owner]);

  if (!user?.is_owner) {
    return (
      <div className="page">
        <ErrorState message="Настройки организации доступны только владельцу" />
      </div>
    );
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!form) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      setForm(
        await api<OrganizationSettings>("/api/v1/organization", {
          method: "PATCH",
          body: JSON.stringify({
            timezone: form.timezone.trim(),
            reminder_days: form.reminder_days.trim(),
            overdue_repeat_days: Number(form.overdue_repeat_days),
            owner_overdue_copy: form.owner_overdue_copy,
          }),
        }),
      );
      setNotice("Сохранено. Каденция действует со следующего прохода напоминаний.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не сохранилось");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <p className="kicker">Организация</p>
          <h1>Общие настройки</h1>
        </div>
      </div>
      <p className="caption">
        Часовой пояс, дни напоминаний и повтор просрочки. По умолчанию значения из .env, здесь они переопределяются для всех отделов.
        В каденции остаётся срок не меньше чем за 3 дня.
      </p>
      {!form && !error && <LoadingBlock label="Загружаем настройки…" />}
      {error && !form && <ErrorState message={error} onRetry={() => void load().catch(() => undefined)} />}
      {form && (
        <form className="panel form-grid" onSubmit={(event) => void submit(event)}>
          <label>
            Часовой пояс
            <input value={form.timezone} onChange={(event) => setForm({ ...form, timezone: event.target.value })} required />
          </label>
          <label>
            Дни напоминаний
            <input
              value={form.reminder_days}
              onChange={(event) => setForm({ ...form, reminder_days: event.target.value })}
              required
              placeholder="7,3,0"
            />
          </label>
          <label>
            Повтор просрочки, дни
            <input
              type="number"
              min={1}
              max={90}
              value={form.overdue_repeat_days}
              onChange={(event) => setForm({ ...form, overdue_repeat_days: Number(event.target.value) })}
              required
            />
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={form.owner_overdue_copy}
              onChange={(event) => setForm({ ...form, owner_overdue_copy: event.target.checked })}
            />
            Копия просрочки владельцу
          </label>
          {error && (
            <div className="span-2">
              <p className="error" role="alert">
                {error}
              </p>
            </div>
          )}
          {notice && <p className="caption span-2">{notice}</p>}
          <div className="row-actions span-2">
            <button type="submit" className="primary" disabled={busy}>
              {busy ? "Сохраняю…" : "Сохранить"}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
