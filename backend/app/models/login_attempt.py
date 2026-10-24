from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LoginAttempt(Base):
    """Перебор пароля. Блокируется существующая почта, не произвольный адрес."""

    __tablename__ = "login_attempts"

    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
