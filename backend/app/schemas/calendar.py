from datetime import date

from pydantic import BaseModel

from app.schemas.occurrence import OccurrenceOut


class CalendarDay(BaseModel):
    date: date
    items: list[OccurrenceOut]


class CalendarOut(BaseModel):
    timezone: str
    year: int
    month: int
    today: date
    days: list[CalendarDay]
