import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NotificationDelivery(Base):
    """Успешная доставка события в один канал. Дедуп отдельно по каналам.

    Письмо, которое ушло сегодня, не запрещает Telegram отправить то же
    напоминание. Общий чат и личка — разные получатели одного канала.
    """

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "occurrence_id", "event", "channel", "recipient", name="uq_notification_deliveries_once"
        ),
        CheckConstraint(
            "status in ('pending', 'sent', 'skipped')",
            name="ck_notification_deliveries_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    occurrence_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("payment_occurrences.id", ondelete="CASCADE")
    )
    event: Mapped[str] = mapped_column(String(64))
    channel: Mapped[str] = mapped_column(String(32))
    recipient: Mapped[str] = mapped_column(String(80), default="", server_default="")
    # pending — ждёт бота (telegram). sent — ушло. skipped — просроченный T-3 или некому слать.
    status: Mapped[str] = mapped_column(String(16), default="sent", server_default="sent")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
