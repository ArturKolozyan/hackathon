import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base
from app.models.user import User


class TelegramBot(Base):
    """Один бот на установку. Username кэширует worker из getMe, командам он общий."""

    __tablename__ = "telegram_bot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    bot_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bot_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # ok — long poll жив. disabled — токена нет. error — последняя ошибка сети.
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="unknown", server_default="unknown")
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TelegramIntegration(Base):
    """Чат одной команды. TELEGRAM_CHAT_ID — запасной, только если команда в базе одна.

    team_status:
    - absent — в базе чата нет, можно взять TELEGRAM_CHAT_ID;
    - connected — шлём в team_chat_id;
    - disconnected — чат сознательно выключен или бота удалили, env не подхватываем.
    """

    __tablename__ = "telegram_integration"
    __table_args__ = (
        CheckConstraint(
            "team_status in ('absent', 'connected', 'disconnected')",
            name="ck_telegram_integration_team_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    team_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), unique=True
    )
    bot_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bot_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    team_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    team_chat_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    team_chat_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    team_status: Mapped[str] = mapped_column(String(16), default="absent", server_default="absent")
    team_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    team_disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    test_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    test_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    test_error: Mapped[str | None] = mapped_column(String(200), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TelegramLinkToken(Base):
    """Одноразовая ссылка в бота. В журнал и логи сырой token не пишем."""

    __tablename__ = "telegram_link_tokens"
    __table_args__ = (
        CheckConstraint("purpose in ('team', 'user')", name="ck_telegram_link_tokens_purpose"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token: Mapped[str] = mapped_column(String(64), unique=True)
    purpose: Mapped[str] = mapped_column(String(16))
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Пусто — ссылка живёт до использования или до новой ссылки того же человека или отдела.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User | None] = relationship()
