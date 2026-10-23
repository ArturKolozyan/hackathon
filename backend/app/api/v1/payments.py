from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.calendar import CalendarOut
from app.schemas.summary import SummaryOut
from app.services.calendar import month_calendar
from app.services.summary import build_summary

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("/summary", response_model=SummaryOut, summary="Итоги по валютам")
def summary(
    as_of: date | None = Query(
        default=None,
        description="Итоги на конец этого дня в TIMEZONE. Без параметра — текущий момент.",
    ),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SummaryOut:
    return build_summary(db, as_of=as_of)


@router.get("/calendar", response_model=CalendarOut, summary="Календарь оплат за месяц")
def calendar(
    year: int | None = Query(default=None, ge=2000, le=2100),
    month: int | None = Query(default=None, ge=1, le=12),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CalendarOut:
    if (year is None) != (month is None):
        raise HTTPException(status_code=422, detail="Укажите year и month вместе")
    return month_calendar(db, year, month)
