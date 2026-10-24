import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ChannelSubscription(Base):
    """Какие команды пользователь слушает личным каналом.

    Пустой набор при scope_set имеет смысл «ни одной».
    Пока scope_set ложь, строки не читаются: канал слушает все текущие команды.
    """

    __tablename__ = "channel_subscriptions"
    __table_args__ = (
        CheckConstraint("channel in ('email', 'telegram')", name="ck_channel_subscriptions_channel"),
        CheckConstraint("scope in ('mine', 'department')", name="ck_channel_subscriptions_scope"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    channel: Mapped[str] = mapped_column(String(16), primary_key=True)
    team_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
    )
    # Письма по этому отделу: только платежи, где человек ответственный, или весь отдел.
    scope: Mapped[str] = mapped_column(String(16), default="mine", server_default="mine")
