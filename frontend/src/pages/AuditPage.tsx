import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, ScrollText, SearchX, X } from "lucide-react";
import { ApiError, api, type AuditItem, type AuditList, type DirectoryUser } from "../api";
import { ACTION_GROUPS, actionLabel, metaPhrase } from "../auditCopy";
import { DateField, SelectField } from "../components/fields";
import { PageControls } from "../components/PageControls";
import { EmptyState, ErrorState, LoadingBlock } from "../components/ui";
import { HINTS } from "../hints";
import { useFresh } from "../fresh";

function timeFormat(timeZone: string): Intl.DateTimeFormat {
  return new Intl.DateTimeFormat("ru-RU", { timeZone, day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

const LIMIT = 20;

/** Одна строка на запись. Обрезаются только детали; если они не влезли, «…» раскрывает строку вниз. */
function Row({ item, format }: { item: AuditItem; format: Intl.DateTimeFormat }) {
  const textRef = useRef<HTMLSpanElement>(null);
  const [open, setOpen] = useState(false);
  const [overflow, setOverflow] = useState(false);
  const details = metaPhrase(item.meta);

  useLayoutEffect(() => {
    const node = textRef.current;
    if (!node) return;
    const measure = () => setOverflow(node.scrollWidth > node.clientWidth + 1);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [details]);

  return (
    <tr className={open ? "audit-row is-open" : "audit-row"}>
      <td className="audit-when">{format.format(new Date(item.at))}</td>
      <td className="audit-who">{item.actor_name ?? "—"}</td>
      <td className="audit-action">{actionLabel(item.action)}</td>
      <td className="audit-detail">
        <span className="audit-detail-line">
          <span ref={textRef} className="audit-detail-text">
            {details}
          </span>
          {(overflow || open) && (
            <button
              type="button"
              className="audit-more"
              aria-expanded={open}
              aria-label={open ? "Свернуть детали" : "Показать детали полностью"}
              data-hint={open ? HINTS.auditLess : HINTS.auditMore}
              onClick={() => setOpen((value) => !value)}
            >
              {open ? "Свернуть" : "…"}
            </button>
          )}
        </span>
      </td>
    </tr>
  );
}

/** «Логи»: who did what and when. Filters are applied on the server (/audit-logs query params). */
export function AuditPage() {
  const [data, setData] = useState<AuditList | null>(null);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [actor, setActor] = useState("");
  const [kind, setKind] = useState("");
  const [people, setPeople] = useState<DirectoryUser[]>([]);
  const fresh = useFresh();

  useEffect(() => {
    api<DirectoryUser[]>("/api/v1/users")
      .then(setPeople)
      .catch(() => setPeople([]));
  }, []);

  const query = useMemo(() => {
    const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) });
    if (from) params.set("date_from", from);
    if (to) params.set("date_to", to);
    if (actor) params.set("actor_user_id", actor);
    const group = ACTION_GROUPS.find((item) => item.value === kind);
    group?.actions.forEach((action) => params.append("action", action));
    return params.toString();
  }, [from, to, actor, kind, offset]);

  const load = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      setData(await api<AuditList>(`/api/v1/audit-logs?${query}`));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Логи не загрузились");
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    void load();
  }, [load, fresh]);

  const format = useMemo(() => timeFormat(data?.timezone ?? "Europe/Moscow"), [data?.timezone]);

  const filtered = Boolean(from || to || actor || kind);
  const shown = data ? offset + data.items.length : 0;

  function filter<T>(set: (value: T) => void) {
    return (value: T) => {
      set(value);
      setOffset(0);
    };
  }

  function reset() {
    setFrom("");
    setTo("");
    setActor("");
    setKind("");
    setOffset(0);
  }

  const peopleOptions = [
    { value: "", label: "Все участники" },
    ...[...people]
      .sort((a, b) => a.full_name.localeCompare(b.full_name, "ru"))
      .map((person) => ({ value: person.id, label: person.is_active ? person.full_name : `${person.full_name} (отключён)` })),
  ];
  const kindOptions = [{ value: "", label: "Все действия" }, ...ACTION_GROUPS.map(({ value, label }) => ({ value, label }))];

  return (
    <div className="page page-wide">
      <PageControls
        left={
          <div className="tb-group log-filters" role="group" aria-label="Фильтры логов">
            <div className="date-range">
              <DateField value={from} onChange={filter(setFrom)} max={to || undefined} ariaLabel="С даты" placeholder="с" />
              <span className="muted" aria-hidden>
                —
              </span>
              <DateField value={to} onChange={filter(setTo)} min={from || undefined} ariaLabel="По дату" placeholder="по" />
            </div>
            <SelectField
              value={actor}
              onChange={filter(setActor)}
              options={peopleOptions}
              ariaLabel="Участник"
              searchable
            />
            <SelectField value={kind} onChange={filter(setKind)} options={kindOptions} ariaLabel="Тип действия" />
            {filtered && (
              <button type="button" className="ghost reset-btn" data-hint={HINTS.filtersReset} onClick={reset}>
                <X size={16} strokeWidth={1.75} aria-hidden />
                Сбросить
              </button>
            )}
          </div>
        }
        right={
          data &&
          data.total > 0 && (
            <div className="tb-group cal-nav">
              <span className="tb-label">
                {data.items.length === 0 ? 0 : offset + 1}–{shown} из {data.total}
              </span>
              <button
                type="button"
                className="icon-btn"
                aria-label="Новее"
                data-hint={HINTS.pageNewer}
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - LIMIT))}
              >
                <ChevronLeft size={18} strokeWidth={1.75} aria-hidden />
              </button>
              <button
                type="button"
                className="icon-btn"
                aria-label="Старее"
                data-hint={HINTS.pageOlder}
                disabled={shown >= data.total}
                onClick={() => setOffset(offset + LIMIT)}
              >
                <ChevronRight size={18} strokeWidth={1.75} aria-hidden />
              </button>
            </div>
          )
        }
      />
      {error && <ErrorState message={error} onRetry={() => void load()} />}
      {!data && !error && <LoadingBlock label="Загружаем логи…" />}
      {data && data.items.length === 0 && !error && (
        filtered ? (
          <EmptyState
            icon={SearchX}
            title="Ничего не нашлось"
            action={
              <button type="button" className="ghost" data-hint={HINTS.filtersReset} onClick={reset}>
                Сбросить фильтры
              </button>
            }
          >
            Под эти фильтры записей нет. Измените их или сбросьте.
          </EmptyState>
        ) : (
          <EmptyState icon={ScrollText} title="Записей пока нет">
            Здесь появятся входы, изменения шаблонов, людей и бюджета, а также оплаты.
          </EmptyState>
        )
      )}
      {data && data.items.length > 0 && (
        <div className={loading ? "table-wrap panel is-stale" : "table-wrap panel"} aria-busy={loading}>
          <table className="table audit-table">
            <thead>
              <tr>
                <th>Когда</th>
                <th>Кто</th>
                <th>Действие</th>
                <th>Детали</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((item) => (
                <Row key={item.id} item={item} format={format} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
