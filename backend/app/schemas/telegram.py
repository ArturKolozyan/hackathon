from datetime import datetime

from pydantic import BaseModel, Field


class TelegramSelf(BaseModel):
    linked: bool
    username: str | None = None
    display_name: str | None = None
    reminders_enabled: bool
    bot_ready: bool
    bot_username: str | None = None


class TelegramLinkOut(BaseModel):
    url: str
    expires_at: datetime | None = Field(default=None, description="Пусто — до использования или новой ссылки")


class TeamTelegram(BaseModel):
    status: str = Field(description="connected, disconnected или absent")
    source: str = Field(description="database, env или none")
    chat_title: str | None = None
    chat_id: str | None = None
    bot_username: str | None = None
    bot_ready: bool
    test_pending: bool
    test_sent_at: datetime | None = None
    test_error: str | None = None


class NotificationsIn(BaseModel):
    telegram_reminders: bool
