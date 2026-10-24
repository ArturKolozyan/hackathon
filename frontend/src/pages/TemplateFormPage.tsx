import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, api, type DirectoryUser, type Template } from "../api";
import { DateField, SelectField } from "../components/fields";
import { FormField, FormScreen, FormSection } from "../components/FormScreen";
import { ErrorState, LoadingBlock, useToast } from "../components/ui";
import { longDue } from "../format";
import { HINTS } from "../hints";

type Draft = {
  title: string;
  description: string;
  amount: string;
  currency: string;
  next_payment_date: string;
  periodicity: string;
  interval_months: string;
  responsible_user_id: string;
};

type Errors = Partial<Record<keyof Draft, string>>;

const emptyDraft: Draft = {
  title: "",
  description: "",
  amount: "",
  currency: "RUB",
  next_payment_date: "",
  periodicity: "monthly",
  interval_months: "2",
  responsible_user_id: "",
};

const CURRENCY_SIGN: Record<string, string> = { RUB: "₽", USD: "$", EUR: "€" };

function validate(draft: Draft): Errors {
  const errors: Errors = {};
  if (!draft.title.trim()) errors.title = "Назовите платёж, например «Аренда офиса»";
  const amount = Number(draft.amount.replace(/\s/g, "").replace(",", "."));
  if (!draft.amount.trim()) errors.amount = "Укажите сумму";
  else if (!Number.isFinite(amount) || amount <= 0) errors.amount = "Сумма — положительное число";
  if (!draft.next_payment_date) errors.next_payment_date = "Выберите дату ближайшей оплаты";
  if (draft.periodicity === "every_n") {
    const months = Number(draft.interval_months);
    if (!Number.isInteger(months) || months < 1 || months > 36) errors.interval_months = "От 1 до 36 месяцев";
  }
  return errors;
}

export function TemplateFormPage() {
  const { id } = useParams();
  const editing = Boolean(id);
  const navigate = useNavigate();
  const toast = useToast();
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [appliesFrom, setAppliesFrom] = useState<string | null>(null);
  const [people, setPeople] = useState<DirectoryUser[]>([]);
  const [errors, setErrors] = useState<Errors>({});
  const [touched, setTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [ready, setReady] = useState(!editing);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<DirectoryUser[]>("/api/v1/users")
      .then((users) => setPeople(users.filter((person) => person.is_active)))
      .catch(() => setPeople([]));
  }, []);

  useEffect(() => {
    if (!id) return;
    api<Template>(`/api/v1/recurring-payments/${id}`)
      .then((item) => {
        setDraft({
          title: item.title,
          description: item.description ?? "",
          amount: item.amount,
          currency: item.currency,
          next_payment_date: item.next_payment_date ?? item.starts_on,
          periodicity: item.periodicity,
          interval_months: String(item.interval_months ?? 2),
          responsible_user_id: item.responsible?.id ?? "",
        });
        setAppliesFrom(item.applies_from);
        setReady(true);
      })
      .catch((err: unknown) => setLoadError(err instanceof ApiError ? err.message : "Шаблон не загрузился"));
  }, [id]);

  function update<K extends keyof Draft>(key: K, value: Draft[K]) {
    const next = { ...draft, [key]: value };
    setDraft(next);
    if (touched) setErrors(validate(next));
  }

  function back() {
    navigate("/templates");
  }

  async function submit() {
    setTouched(true);
    const found = validate(draft);
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    setBusy(true);
    setError(null);
    const payload = {
      title: draft.title.trim(),
      description: draft.description.trim() || null,
      amount: draft.amount.replace(/\s/g, "").replace(",", "."),
      currency: draft.currency,
      next_payment_date: draft.next_payment_date,
      periodicity: draft.periodicity,
      interval_months: draft.periodicity === "every_n" ? Number(draft.interval_months) : undefined,
      responsible_user_id: draft.responsible_user_id || null,
    };
    try {
      if (id) {
        await api(`/api/v1/recurring-payments/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
        toast?.push("Шаблон сохранён");
      } else {
        await api("/api/v1/recurring-payments", { method: "POST", body: JSON.stringify(payload) });
        toast?.push("Шаблон создан");
      }
      back();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не сохранилось");
    } finally {
      setBusy(false);
    }
  }

  if (loadError) {
    return (
      <div className="page">
        <ErrorState message={loadError} onRetry={() => window.location.reload()} />
      </div>
    );
  }
  if (!ready) return <LoadingBlock label="Загружаем шаблон…" />;

  return (
    <FormScreen
      title={editing ? "Правка шаблона" : "Новый шаблон"}
      onBack={back}
      onSubmit={() => void submit()}
      submitLabel={editing ? "Сохранить" : "Создать"}
      submitHint={editing ? HINTS.templateSave : HINTS.templateCreate}
      busy={busy}
      error={error}
    >
      <FormSection title="Платёж">
        <FormField label="Как называется платёж?" error={errors.title}>
          {({ id: fieldId, describedBy, invalid }) => (
            <input
              id={fieldId}
              value={draft.title}
              onChange={(event) => update("title", event.target.value)}
              maxLength={200}
              placeholder="Аренда офиса"
              aria-invalid={invalid}
              aria-describedby={describedBy}
              autoFocus
            />
          )}
        </FormField>
        <div className="form-row">
          <FormField label="Сколько платим?" error={errors.amount} suffix={CURRENCY_SIGN[draft.currency] ?? draft.currency}>
            {({ id: fieldId, describedBy, invalid }) => (
              <input
                id={fieldId}
                value={draft.amount}
                onChange={(event) => update("amount", event.target.value)}
                inputMode="decimal"
                placeholder="0"
                aria-invalid={invalid}
                aria-describedby={describedBy}
              />
            )}
          </FormField>
          <FormField label="В какой валюте?">
            {() => (
              <SelectField
                ariaLabel="Валюта"
                value={draft.currency}
                onChange={(currency) => update("currency", currency)}
                options={[
                  { value: "RUB", label: "Рубли, RUB" },
                  { value: "USD", label: "Доллары, USD" },
                  { value: "EUR", label: "Евро, EUR" },
                ]}
              />
            )}
          </FormField>
        </div>
        <FormField label="Комментарий" optional hint="Например, номер договора или кому платим.">
          {({ id: fieldId, describedBy }) => (
            <input
              id={fieldId}
              value={draft.description}
              onChange={(event) => update("description", event.target.value)}
              aria-describedby={describedBy}
            />
          )}
        </FormField>
      </FormSection>

      <FormSection title="Расписание">
        <FormField
          label="Когда ближайшая оплата?"
          error={errors.next_payment_date}
          hint={
            editing && appliesFrom
              ? `Изменения применятся с периода ${longDue(appliesFrom)}.`
              : "От этой даты считаются следующие периоды."
          }
        >
          {() => (
            <DateField
              ariaLabel="Дата ближайшей оплаты"
              value={draft.next_payment_date}
              onChange={(value) => update("next_payment_date", value)}
            />
          )}
        </FormField>
        <div className="form-row">
          <FormField label="Как часто платим?">
            {() => (
              <SelectField
                ariaLabel="Периодичность"
                value={draft.periodicity}
                onChange={(value) => update("periodicity", value)}
                options={[
                  { value: "monthly", label: "Ежемесячно" },
                  { value: "quarterly", label: "Раз в квартал" },
                  { value: "semiannual", label: "Раз в полгода" },
                  { value: "yearly", label: "Ежегодно" },
                  { value: "once", label: "Разово" },
                  { value: "every_n", label: "Каждые N месяцев" },
                ]}
              />
            )}
          </FormField>
          {draft.periodicity === "every_n" && (
            <FormField label="Через сколько месяцев?" error={errors.interval_months} suffix="мес.">
              {({ id: fieldId, describedBy, invalid }) => (
                <input
                  id={fieldId}
                  type="number"
                  min={1}
                  max={36}
                  value={draft.interval_months}
                  onChange={(event) => update("interval_months", event.target.value)}
                  aria-invalid={invalid}
                  aria-describedby={describedBy}
                />
              )}
            </FormField>
          )}
        </div>
      </FormSection>

      <FormSection title="Ответственный">
        <FormField label="Кто отвечает за оплату?" hint="Ему придут напоминания в Telegram и на почту.">
          {() => (
            <SelectField
              ariaLabel="Ответственный"
              value={draft.responsible_user_id}
              onChange={(value) => update("responsible_user_id", value)}
              options={[
                { value: "", label: "Без ответственного" },
                ...people.map((person) => ({ value: person.id, label: person.full_name })),
              ]}
            />
          )}
        </FormField>
      </FormSection>
    </FormScreen>
  );
}
