import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NotificationDelivery(Base):
    """Успешная доставка события в один канал. Дедуп отдельно по каналам.

    Письмо, которое ушло сегодня, не запрещает Telegram-агенту отправить
    то же напоминание, когда бот появится. Повтор того же канала — нет.
    """

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint("occurrence_id", "event", "channel", name="uq_notification_deliveries_once"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    occurrence_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("payment_occurrences.id", ondelete="CASCADE")
    )
    event: Mapped[str] = mapped_column(String(64))
    channel: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
