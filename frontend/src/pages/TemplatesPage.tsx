import { useCallback, useEffect, useMemo, useState } from "react";
import { Plus, Repeat, Search, SearchX } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { ApiError, api, type Template } from "../api";
import { PageControls } from "../components/PageControls";
import { EmptyState, ErrorState, InlineConfirm, LoadingBlock, SwitchCard } from "../components/ui";
import { formatMoney, shortDue } from "../format";
import { HINTS } from "../hints";

export function periodPhrase(item: Pick<Template, "periodicity" | "interval_months">): string {
  if (item.periodicity === "once") return "разово";
  if (item.periodicity === "yearly") return "ежегодно";
  if (item.periodicity === "quarterly") return "раз в квартал";
  if (item.periodicity === "semiannual") return "раз в полгода";
  if (item.periodicity === "every_n" && item.interval_months) return `каждые ${item.interval_months} мес.`;
  return "ежемесячно";
}

export function TemplatesPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<Template[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState<string | null>(null);
  const [remindOverdue, setRemindOverdue] = useState(true);

  const load = useCallback(async () => {
    setItems(await api<Template[]>("/api/v1/recurring-payments?include_archived=true"));
  }, []);

  useEffect(() => {
    load()
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : "Не загрузилось"))
      .finally(() => setReady(true));
  }, [load]);

  async function archive(item: Template, archived: boolean, remind = true) {
    setError(null);
    try {
      await api(`/api/v1/recurring-payments/${item.id}`, {
        method: "PATCH",
        body: JSON.stringify(archived ? { is_archived: true, remind_archived_overdue: remind } : { is_archived: false }),
      });
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Не получилось");
    }
  }

  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return items;
    return items.filter(
      (item) =>
        item.title.toLowerCase().includes(needle) ||
        (item.responsible?.full_name ?? "").toLowerCase().includes(needle) ||
        (item.description ?? "").toLowerCase().includes(needle),
    );
  }, [items, query]);
  const active = shown.filter((item) => !item.is_archived);
  const archived = shown.filter((item) => item.is_archived);
  const hasActive = items.some((item) => !item.is_archived);

  function renderRow(item: Template) {
    return (
      <article key={item.id} className={item.is_archived ? "row-card is-muted" : "row-card"}>
        <div className="row-main">
          <div className="row-title">
            <h3>{item.title}</h3>
            {item.debt_count > 0 && <span className="pill pill-overdue">долг {item.debt_count}</span>}
          </div>
          <p className="row-meta">
            {[
              item.next_payment_date ? `ближайшая ${shortDue(item.next_payment_date)}` : `${item.day_of_month}-е число`,
              periodPhrase(item),
              item.responsible?.full_name ?? "без ответственного",
              `открыто ${item.open_count}, закрыто ${item.paid_count}`,
            ].join(", ")}
          </p>
          {item.description && <p className="row-meta">{item.description}</p>}
        </div>
        <strong className="money row-value">{formatMoney(item.amount, item.currency)}</strong>
        <div className="row-actions">
          {confirmArchive === item.id ? (
            <div className="stack row-confirm">
              {item.debt_count > 0 && (
                <p className="error" role="alert">
                  Неоплаченных прошлых периодов: {item.debt_count}. Они останутся в инбоксе и итогах. Новые периоды не
                  создаются.
                </p>
              )}
              <SwitchCard
                title="Напоминать о просрочке"
                description="Старые долги этого шаблона продолжат приходить в напоминаниях"
                checked={remindOverdue}
                onChange={setRemindOverdue}
              />
              <InlineConfirm
                title="Новые периоды не появятся. История и долг останутся."
                confirmLabel="В архив"
                onConfirm={() => {
                  setConfirmArchive(null);
                  void archive(item, true, remindOverdue);
                }}
                onCancel={() => setConfirmArchive(null)}
              />
            </div>
          ) : (
            <>
              <button type="button" className="ghost" data-hint={HINTS.templateEdit} onClick={() => navigate(`/templates/${item.id}/edit`)}>
                Изменить
              </button>
              <button
                type="button"
                className="ghost"
                data-hint={item.is_archived ? HINTS.templateRestore : HINTS.templateArchive}
                onClick={() => {
                  if (item.is_archived) {
                    void archive(item, false);
                    return;
                  }
                  setRemindOverdue(item.remind_archived_overdue);
                  setConfirmArchive(item.id);
                }}
              >
                {item.is_archived ? "Вернуть" : "В архив"}
              </button>
            </>
          )}
        </div>
      </article>
    );
  }

  return (
    <div className="page">
      <PageControls
        left={
          <label className="tb-search">
            <Search size={16} strokeWidth={1.75} aria-hidden />
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Название или ответственный"
              aria-label="Поиск по шаблонам"
            />
          </label>
        }
        right={
          <button type="button" className="primary" data-hint={HINTS.templateNew} onClick={() => navigate("/templates/new")}>
            <Plus size={16} strokeWidth={2} aria-hidden />
            Новый шаблон
          </button>
        }
      />
      {error && <ErrorState message={error} onRetry={() => void load().catch(() => undefined)} />}
      {!ready && !error && <LoadingBlock label="Загружаем шаблоны…" />}
      {ready && !error && !hasActive && !query && (
        <EmptyState
          icon={Repeat}
          title={items.length > 0 ? "Активных шаблонов нет" : "Шаблонов пока нет"}
          action={
            <button type="button" className="primary" data-hint={HINTS.templateNew} onClick={() => navigate("/templates/new")}>
              Создать шаблон
            </button>
          }
        >
          Шаблон описывает регулярный платёж: сумму, день и ответственного. По нему каждый период появится в инбоксе.
        </EmptyState>
      )}
      {ready && query && shown.length === 0 && (
        <EmptyState
          icon={SearchX}
          title="Ничего не нашлось"
          action={
            <button type="button" className="ghost" onClick={() => setQuery("")}>
              Очистить поиск
            </button>
          }
        >
          Проверьте название или имя ответственного.
        </EmptyState>
      )}
      {active.length > 0 && (
        <section className="group">
          <header>
            <h2>Активные</h2>
            <span className="muted">{active.length}</span>
          </header>
          <div className="row-list">{active.map(renderRow)}</div>
        </section>
      )}
      {archived.length > 0 && (
        <section className="group">
          <header>
            <h2>Архив</h2>
            <span className="muted">{archived.length}</span>
          </header>
          <div className="row-list">{archived.map(renderRow)}</div>
        </section>
      )}
    </div>
  );
}
