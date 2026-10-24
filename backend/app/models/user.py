import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class User(Base):
    """Аккаунт. Владелец установки — is_owner. Роль в отделе — на membership."""

    __tablename__ = "users"
    __table_args__ = (
        Index("uq_users_one_owner", "is_owner", unique=True, postgresql_where=text("is_owner")),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active_team_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    telegram_username: Mapped[str | None] = mapped_column(String(32), nullable=True)
    telegram_display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    telegram_reminders: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    telegram_scope_set: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    telegram_test_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_test_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_test_error: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email_reminders: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    email_scope_set: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Владелец установки. Ровно один. Задаётся OWNER_EMAIL / ADMIN_EMAIL, не членством.
    is_owner: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    telegram_onboarding_done: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Ссылка-приглашение: пока не пусто, человек ещё не задал пароль. Новая ссылка заменяет старую.
    invite_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    # mine — только платежи, где человек ответственный; department — все платежи его отделов.
    notify_scope: Mapped[str] = mapped_column(String(16), default="mine", server_default="mine")
    notify_overdue: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user")
