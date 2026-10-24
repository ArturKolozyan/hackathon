import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    invite_token: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    webhook_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    webhook_check_error: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Сломанный вебхук: подряд неудачные отправки и когда пробовать снова (экспоненциальная пауза).
    webhook_failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    webhook_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    memberships: Mapped[list["Membership"]] = relationship(back_populates="team", cascade="all, delete-orphan", passive_deletes=True)


class Membership(Base):
    """Роль в отделе: admin или member. Владелец организации — users.is_owner, не здесь."""

    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_memberships_team_user"),
        CheckConstraint("role in ('admin', 'member')", name="ck_memberships_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    team: Mapped[Team] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(back_populates="memberships")
