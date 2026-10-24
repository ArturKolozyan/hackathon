import calendar as calendar_mod
from datetime import date

from sqlalchemy.orm import Session

from app.models import PaymentOccurrence
from app.schemas.calendar import CalendarDay, CalendarOut, CalendarTeam
from app.services import time as clock
from app.services.occurrences import _load_stmt, ensure_all, planned_rows
from app.services.present import occurrence_out


def month_calendar(
    db: Session,
    year: int | None,
    month: int | None,
    team_id=None,
    *,
    team_ids: list | None = None,
    teams: list[tuple] | None = None,
) -> CalendarOut:
    """team_ids — несколько отделов сразу (календарь «все отделы»). Иначе один team_id."""
    today = clock.today()
    year = year or today.year
    month = month or today.month
    # Будущий месяц не пишет периоды в базу: что дальше горизонта, считается на лету.
    ensure_all(db, today)
    db.commit()
    db.expire_all()
    last = calendar_mod.monthrange(year, month)[1]
    start = date(year, month, 1)
    end = date(year, month, last)
    stmt = _load_stmt().where(PaymentOccurrence.due_date >= start, PaymentOccurrence.due_date <= end)
    if team_ids is not None:
        stmt = stmt.where(PaymentOccurrence.team_id.in_(team_ids))
    elif team_id is not None:
        stmt = stmt.where(PaymentOccurrence.team_id == team_id)
    rows = db.scalars(stmt.order_by(PaymentOccurrence.due_date, PaymentOccurrence.title)).unique().all()
    grouped: dict[date, list] = {}
    for row in rows:
        if row.template is not None and row.template.is_archived and row.paid_at is None:
            continue
        grouped.setdefault(row.due_date, []).append(occurrence_out(row, row.template, today))
    scope = team_ids if team_ids is not None else ([team_id] if team_id is not None else None)
    for row in planned_rows(db, team_ids=scope, start=start, end=end, today=today):
        grouped.setdefault(row.due_date, []).append(occurrence_out(row, row.template, today, planned=True))
    for items in grouped.values():
        items.sort(key=lambda item: item.title)
    days = [CalendarDay(date=day, items=items) for day, items in sorted(grouped.items())]
    return CalendarOut(
        timezone=clock.zone().key,
        year=year,
        month=month,
        today=today,
        days=days,
        teams=[CalendarTeam(id=item_id, name=name) for item_id, name in (teams or [])],
    )
