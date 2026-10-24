from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class OrganizationSettings(Base):
    """Одна строка на установку. Пустая таблица — значения из .env."""

    __tablename__ = "organization_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_organization_settings_singleton"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    # Включённые напоминания до срока: подмножество 7, 3, 1 через запятую, может быть пустым.
    reminder_days: Mapped[str] = mapped_column(String(64), default="7,3,1")
    # О просрочке: каждый день со следующего после срока, пока не оплачено.
    overdue_reminders: Mapped[bool] = mapped_column(Boolean, default=True)
    owner_overdue_copy: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
