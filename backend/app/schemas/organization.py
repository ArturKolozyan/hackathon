from pydantic import BaseModel, Field


class OrganizationOut(BaseModel):
    timezone: str
    remind_7_days: bool = Field(description="Напоминание за 7 дней до срока")
    remind_3_days: bool = Field(description="Напоминание за 3 дня до срока")
    remind_1_day: bool = Field(description="Напоминание за 1 день до срока")
    remind_overdue: bool = Field(description="О просрочке каждый день, начиная со следующего после срока")
    owner_overdue_copy: bool


class OrganizationPatch(BaseModel):
    timezone: str | None = Field(default=None, max_length=64)
    remind_7_days: bool | None = None
    remind_3_days: bool | None = None
    remind_1_day: bool | None = None
    remind_overdue: bool | None = None
    owner_overdue_copy: bool | None = None
