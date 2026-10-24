import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AssistantAction(Base):
    """Черновик изменения. В базу платежей попадает только после подтверждения."""

    __tablename__ = "assistant_actions"
    __table_args__ = (
        CheckConstraint(
            "kind in ('create_payment', 'update_payment', 'archive_payment', 'mark_paid', 'mark_unpaid')",
            name="kind",
        ),
        CheckConstraint(
            "status in ('pending', 'running', 'confirmed', 'cancelled', 'failed')",
            name="status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    team_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    payload: Mapped[dict] = mapped_column(JSONB)
    summary: Mapped[str] = mapped_column(Text)
    result_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"
    __table_args__ = (CheckConstraint("role in ('user', 'assistant')", name="role"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    team_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    action_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("assistant_actions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    action: Mapped[AssistantAction | None] = relationship()
