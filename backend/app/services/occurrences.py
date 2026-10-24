import uuid
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.models import PaymentOccurrence, RecurringPayment
from app.schemas.occurrence import OccurrenceOut
from app.services import time as clock
from app.services.present import occurrence_out
from app.services.receipts import discard_after_commit
from app.services.schedule import add_months, due_date, iter_schedule, periods_between


def step_months(template: RecurringPayment) -> int | None:
    kind = template.periodicity or "monthly"
    if kind == "once":
        return None
    if kind == "quarterly":
        return 3
    if kind == "semiannual":
        return 6
    if kind == "yearly":
        return 12
    if kind == "every_n":
        return template.interval_months or 1
    return 1


def scheduled_periods(template: RecurringPayment, today: date) -> list[tuple[int, int, date]]:
    return iter_schedule(
        template.starts_on,
        template.day_of_month,
        step_months(template),
        today,
        get_settings().horizon_months,
    )


def _write_snapshot(row: PaymentOccurrence, template: RecurringPayment, due: date) -> None:
    row.team_id = template.team_id
    row.due_date = due
    row.amount = template.amount
    row.currency = template.currency
    row.title = template.title
    row.description = template.description

BUCKET_RANK = {"overdue": 0, "soon": 1, "rest": 2, "history": 3}


def ensure_template(db: Session, template: RecurringPayment, today: date, *, sync_future: bool = False) -> int:
    """Архив не рожает периоды. Снимок прошлого и оплаченного не переписывается.

    sync_future — только сохранение шаблона: будущие неоплаченные со сроком
    от сегодня получают новые поля. Чужой период эта функция не трогает.
    """
    if template.is_archived:
        return 0
    rows = db.scalars(
        select(PaymentOccurrence).where(PaymentOccurrence.recurring_payment_id == template.id)
    ).all()
    existing = {(row.period_year, row.period_month): row for row in rows}
    wanted = {(year, month): due for year, month, due in scheduled_periods(template, today)}
    if sync_future:
        for key, row in list(existing.items()):
            if row.paid_at is not None or row.due_date < today:
                continue
            if key not in wanted:
                discard_after_commit(db, row.receipt_file)
                db.delete(row)
                del existing[key]
    created = 0
    for (year, month), period_due in wanted.items():
        current = existing.get((year, month))
        if current is None:
            current = PaymentOccurrence(
                team_id=template.team_id,
                recurring_payment_id=template.id,
                period_year=year,
                period_month=month,
                due_date=period_due,
                title=template.title,
                description=template.description,
                amount=template.amount,
                currency=template.currency,
            )
            try:
                with db.begin_nested():
                    db.add(current)
                    db.flush()
            except IntegrityError:
                db.expunge(current)
                continue
            existing[(year, month)] = current
            created += 1
            continue
        if sync_future and current.paid_at is None and current.due_date >= today:
            _write_snapshot(current, template, period_due)
    return created


def ensure_all(db: Session, today: date | None = None) -> int:
    """Периоды в базе только до сегодня + горизонт. Дальше — planned_rows, без записи."""
    current = today or clock.today()
    templates = db.scalars(select(RecurringPayment).where(RecurringPayment.is_archived.is_(False))).all()
    created = 0
    for template in templates:
        created += ensure_template(db, template, current)
    return created


def _load_stmt():
    return select(PaymentOccurrence).options(
        joinedload(PaymentOccurrence.template).joinedload(RecurringPayment.responsible),
        joinedload(PaymentOccurrence.payer),
    )


def load_occurrence(db: Session, occurrence_id: uuid.UUID) -> PaymentOccurrence | None:
    return db.scalars(_load_stmt().where(PaymentOccurrence.id == occurrence_id)).unique().one_or_none()


def list_views(
    db: Session,
    *,
    view: str = "all",
    team_id: uuid.UUID | None = None,
    responsible_id: uuid.UUID | None = None,
    recurring_payment_id: uuid.UUID | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    currency: str | None = None,
) -> tuple[date, list[OccurrenceOut]]:
    current = clock.today()
    ensure_all(db, current)
    db.commit()
    # expire_on_commit выключен: без expire связь paid_by остаётся пустой в identity map.
    db.expire_all()
    stmt = _load_stmt()
    if team_id is not None:
        stmt = stmt.where(PaymentOccurrence.team_id == team_id)
    if recurring_payment_id is not None:
        stmt = stmt.where(PaymentOccurrence.recurring_payment_id == recurring_payment_id)
    rows = db.scalars(stmt).unique().all()
    items = [occurrence_out(row, row.template, current) for row in rows if not hidden(row, current)]
    if responsible_id is not None:
        items = [item for item in items if item.responsible is not None and item.responsible.id == responsible_id]
    if view == "inbox":
        items = [item for item in items if item.status != "paid"]
    elif view == "history":
        items = [item for item in items if item.status == "paid"]
    if status is not None:
        items = [item for item in items if item.status == status]
    if date_from is not None:
        items = [item for item in items if item.due_date >= date_from]
    if date_to is not None:
        items = [item for item in items if item.due_date <= date_to]
    if currency is not None:
        items = [item for item in items if item.currency == currency]
    if view == "history":
        items.sort(key=lambda item: (item.paid_at is None, -(item.paid_at.timestamp() if item.paid_at else 0), item.title))
    else:
        items.sort(key=lambda item: (BUCKET_RANK[item.bucket], item.due_date.toordinal(), item.title))
    return current, items


def require_occurrence(db: Session, occurrence_id: uuid.UUID, team_id: uuid.UUID | None = None) -> PaymentOccurrence:
    row = load_occurrence(db, occurrence_id)
    if row is None or (team_id is not None and row.team_id != team_id):
        raise HTTPException(status_code=404, detail="Период не найден")
    return row


def view_one(db: Session, occurrence_id: uuid.UUID, team_id: uuid.UUID | None = None) -> OccurrenceOut:
    db.expire_all()
    row = require_occurrence(db, occurrence_id, team_id)
    return occurrence_out(row, row.template, clock.today())


def materialized_until(today: date) -> date:
    return add_months(today, get_settings().horizon_months)


def hidden(row: PaymentOccurrence, today: date) -> bool:
    """Архивный платёж не висит будущими сроками: такие периоды не видны в инбоксе, итогах, статистике и CSV."""
    template = row.template
    return template is not None and template.is_archived and row.paid_at is None and row.due_date >= today


def untouched(row: PaymentOccurrence, template: RecurringPayment) -> bool:
    """Период ровно такой, каким его создало расписание: без оплаты, заметок, чека и ручных правок."""
    return (
        row.paid_at is None
        and row.paid_amount is None
        and row.paid_by_id is None
        and not row.note
        and not row.receipt_note
        and not row.receipt_file
        and row.due_date == due_date(row.period_year, row.period_month, template.day_of_month)
        and row.amount == template.amount
        and row.currency == template.currency
        and row.title == template.title
    )


def planned_rows(
    db: Session,
    *,
    team_ids: list[uuid.UUID] | None,
    start: date,
    end: date,
    today: date,
) -> list[PaymentOccurrence]:
    """Будущие сроки, которых ещё нет в базе: считаются по шаблону и не сохраняются.

    Объекты не добавляются в сессию. id детерминированный, чтобы ключи в интерфейсе не прыгали.
    """
    start = max(start, today + timedelta(days=1))
    if start > end:
        return []
    stmt = select(RecurringPayment).where(RecurringPayment.is_archived.is_(False))
    if team_ids is not None:
        if not team_ids:
            return []
        stmt = stmt.where(RecurringPayment.team_id.in_(team_ids))
    templates = db.scalars(stmt.options(joinedload(RecurringPayment.responsible))).unique().all()
    if not templates:
        return []
    taken = {
        (row.recurring_payment_id, row.period_year, row.period_month)
        for row in db.execute(
            select(
                PaymentOccurrence.recurring_payment_id, PaymentOccurrence.period_year, PaymentOccurrence.period_month
            ).where(PaymentOccurrence.recurring_payment_id.in_([item.id for item in templates]))
        )
    }
    out: list[PaymentOccurrence] = []
    for template in templates:
        for year, month, due in periods_between(
            template.starts_on, template.day_of_month, step_months(template), start, end
        ):
            if (template.id, year, month) in taken:
                continue
            row = PaymentOccurrence(
                id=uuid.uuid5(template.id, f"{year:04d}-{month:02d}"),
                team_id=template.team_id,
                recurring_payment_id=template.id,
                period_year=year,
                period_month=month,
                due_date=due,
                title=template.title,
                description=template.description,
                amount=template.amount,
                currency=template.currency,
            )
            # Связь без back_populates: иначе каскад положит черновик в сессию.
            row.__dict__["template"] = template
            row.__dict__["payer"] = None
            out.append(row)
    return out


def prune_future(db: Session, today: date) -> int:
    """Чистка лишних будущих периодов. Идемпотентна, можно запускать сколько угодно раз.

    Удаляет неоплаченные нетронутые периоды, которые нынешнее расписание не держит в базе:
    дальше горизонта (их когда-то создал просмотр будущих месяцев) и будущие сроки архивных платежей.
    Оплаченное, с заметкой, чеком или ручной суммой и датой не трогает.
    """
    removed = 0
    templates = db.scalars(select(RecurringPayment)).all()
    for template in templates:
        keep: set[tuple[int, int]] = set()
        if not template.is_archived:
            keep = {(year, month) for year, month, _due in scheduled_periods(template, today)}
        rows = db.scalars(
            select(PaymentOccurrence).where(
                PaymentOccurrence.recurring_payment_id == template.id,
                PaymentOccurrence.paid_at.is_(None),
                PaymentOccurrence.due_date >= today,
            )
        ).all()
        for row in rows:
            if (row.period_year, row.period_month) in keep or not untouched(row, template):
                continue
            db.delete(row)
            removed += 1
    db.flush()
    return removed


def drop_archived_future(db: Session, template: RecurringPayment, today: date) -> int:
    """Архивация: будущие нетронутые сроки удаляются, тронутые скрывает hidden()."""
    removed = 0
    rows = db.scalars(
        select(PaymentOccurrence).where(
            PaymentOccurrence.recurring_payment_id == template.id,
            PaymentOccurrence.paid_at.is_(None),
            PaymentOccurrence.due_date >= today,
        )
    ).all()
    for row in rows:
        if untouched(row, template):
            db.delete(row)
            removed += 1
    db.flush()
    return removed


def resume_from_today(template: RecurringPayment, today: date) -> None:
    """Возврат из архива: расписание продолжается с ближайшего срока от сегодня в прежнем ритме.

    Месяцы, пока платёж был в архиве, не превращаются в просрочки.
    """
    step = step_months(template)
    if step is None:
        return
    ahead = periods_between(template.starts_on, template.day_of_month, step, today, add_months(today, step + 1))
    if ahead:
        template.starts_on = ahead[0][2]
