import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Numeric, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (
        CheckConstraint("period_type in ('month', 'year')", name="ck_budgets_period_type"),
        CheckConstraint("currency in ('RUB', 'USD', 'EUR')", name="ck_budgets_currency"),
        CheckConstraint("amount > 0", name="ck_budgets_amount"),
        UniqueConstraint("period_type", "period_key", "currency", name="uq_budgets_period_currency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    period_type: Mapped[str] = mapped_column(String(8))
    period_key: Mapped[str] = mapped_column(String(7))
    currency: Mapped[str] = mapped_column(String(3))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
