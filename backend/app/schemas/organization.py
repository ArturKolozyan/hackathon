from pydantic import BaseModel, Field


class OrganizationOut(BaseModel):
    timezone: str
    reminder_days: str
    overdue_repeat_days: int
    owner_overdue_copy: bool


class OrganizationPatch(BaseModel):
    timezone: str | None = Field(default=None, max_length=64)
    reminder_days: str | None = Field(default=None, max_length=64)
    overdue_repeat_days: int | None = Field(default=None, ge=1, le=90)
    owner_overdue_copy: bool | None = None
