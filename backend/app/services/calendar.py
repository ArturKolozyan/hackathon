import calendar as calendar_mod
from datetime import date

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import PaymentOccurrence
from app.schemas.calendar import CalendarDay, CalendarOut
from app.services import time as clock
from app.services.occurrences import _load_stmt, ensure_all
from app.services.present import occurrence_out


def month_calendar(db: Session, year: int | None, month: int | None, team_id=None) -> CalendarOut:
    today = clock.today()
    year = year or today.year
    month = month or today.month
    anchor = date(year, month, 1)
    ensure_all(db, anchor if anchor > today else today)
    db.commit()
    db.expire_all()
    last = calendar_mod.monthrange(year, month)[1]
    start = date(year, month, 1)
    end = date(year, month, last)
    stmt = _load_stmt().where(PaymentOccurrence.due_date >= start, PaymentOccurrence.due_date <= end)
    if team_id is not None:
        stmt = stmt.where(PaymentOccurrence.team_id == team_id)
    rows = db.scalars(stmt.order_by(PaymentOccurrence.due_date, PaymentOccurrence.title)).unique().all()
    grouped: dict[date, list] = {}
    for row in rows:
        if row.template is not None and row.template.is_archived and row.paid_at is None:
            continue
        grouped.setdefault(row.due_date, []).append(occurrence_out(row, row.template, today))
    days = [CalendarDay(date=day, items=items) for day, items in sorted(grouped.items())]
    settings = get_settings()
    return CalendarOut(timezone=settings.timezone, year=year, month=month, today=today, days=days)
