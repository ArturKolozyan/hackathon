import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, api, type DirectoryUser } from "../api";
import { absoluteUrl } from "./PeoplePage";
import { useAuth } from "../auth";
import { SelectField } from "../components/fields";
import { FormField, FormScreen, FormSection } from "../components/FormScreen";
import { useToast } from "../components/ui";
import { HINTS } from "../hints";

type Draft = { full_name: string; email: string; role: string };
type Errors = Partial<Record<keyof Draft, string>>;

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function validate(draft: Draft): Errors {
  const errors: Errors = {};
  if (!draft.full_name.trim()) errors.full_name = "Укажите имя и фамилию";
  if (!draft.email.trim()) errors.email = "Укажите почту";
  else if (!EMAIL.test(draft.email.trim())) errors.email = "Похоже, в почте ошибка";
  return errors;
}

export function PersonFormPage() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const toast = useToast();
  const [draft, setDraft] = useState<Draft>({ full_name: "", email: "", role: "user" });
  const [errors, setErrors] = useState<Errors>({});
  const [touched, setTouched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function update<K extends keyof Draft>(key: K, value: Draft[K]) {
    const next = { ...draft, [key]: value };
    setDraft(next);
    if (touched) setErrors(validate(next));
  }

  async function submit() {
    setTouched(true);
    const found = validate(draft);
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api<DirectoryUser>("/api/v1/users", {
        method: "POST",
        body: JSON.stringify({
          email: draft.email.trim(),
          full_name: draft.full_name.trim(),
          role: draft.role,
          department_id: user?.active_team_id,
        }),
      });
      if (created.invite_url) {
        toast?.push("Человек добавлен. Отправьте ему ссылку-приглашение из карточки.");
        navigate("/people", {
          state: { shown: { personId: created.id, kind: "invite", url: absoluteUrl(created.invite_url) } },
        });
      } else {
        toast?.push("Человек добавлен в отдел.");
        navigate("/people");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не получилось добавить");
    } finally {
      setBusy(false);
    }
  }

  const team = user?.memberships.find((row) => row.team_id === user.active_team_id)?.team_name;

  return (
    <FormScreen
      title="Новый человек"
      onBack={() => navigate("/people")}
      onSubmit={() => void submit()}
      submitLabel="Добавить"
      submitHint={HINTS.personCreate}
      busyLabel="Добавляю…"
      busy={busy}
      error={error}
    >
      <FormSection title="Кто это">
        <FormField label="Как зовут?" error={errors.full_name}>
          {({ id, describedBy, invalid }) => (
            <input
              id={id}
              value={draft.full_name}
              onChange={(event) => update("full_name", event.target.value)}
              placeholder="Мария Соколова"
              autoComplete="off"
              aria-invalid={invalid}
              aria-describedby={describedBy}
              autoFocus
            />
          )}
        </FormField>
        <FormField label="Какая у него почта?" error={errors.email} hint="Это его логин. Письмо не уходит: после добавления появится личная ссылка-приглашение, по ней человек сам задаст пароль.">
          {({ id, describedBy, invalid }) => (
            <input
              id={id}
              type="email"
              value={draft.email}
              onChange={(event) => update("email", event.target.value)}
              placeholder="name@company.ru"
              autoComplete="off"
              aria-invalid={invalid}
              aria-describedby={describedBy}
            />
          )}
        </FormField>
      </FormSection>

      <FormSection title="Доступ">
        <FormField label="Какая роль?" hint={team ? `Человек появится в отделе «${team}».` : undefined}>
          {() => (
            <SelectField
              ariaLabel="Роль"
              value={draft.role}
              onChange={(role) => update("role", role)}
              options={[
                { value: "user", label: "Участник — видит и закрывает платежи" },
                ...(user?.is_owner ? [{ value: "admin", label: "Админ отдела — ещё шаблоны и люди" }] : []),
              ]}
            />
          )}
        </FormField>
      </FormSection>
    </FormScreen>
  );
}
