from datetime import date

from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.occurrence import OccurrenceOut


class CalendarDay(BaseModel):
    date: date
    items: list[OccurrenceOut]


class CalendarTeam(BaseModel):
    id: UUID
    name: str


class CalendarOut(BaseModel):
    timezone: str
    year: int
    month: int
    today: date
    days: list[CalendarDay]
    teams: list[CalendarTeam] = Field(
        default_factory=list,
        description="Отделы в выдаче. scope=all — все доступные человеку, иначе текущий.",
    )
