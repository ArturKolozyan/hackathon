from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str = "postgresql+psycopg://invoice:change-me@localhost:5432/invoice_keeper"
    secret_key: str = "change-me-not-a-secret"
    admin_email: str = "admin@invoice.local"
    admin_password: str = "change-me"
    admin_name: str = "Админ"
    demo_user_email: str = "ivan@invoice.local"
    demo_user_name: str = "Иван Петров"
    demo_user_two_email: str = "maria@invoice.local"
    demo_user_two_name: str = "Мария Соколова"
    demo_user_password: str = "change-me-user"
    seed_demo: bool = True
    timezone: str = "Europe/Moscow"
    soon_days: int = 3
    horizon_months: int = 2
    session_days: int = 14
    cookie_secure: bool = False
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    # Канонический адрес. Письмо-напоминание дописывает его в конец. Пустая строка — без ссылки.
    app_public_url: str = "https://rekeeper.ru"
    worker_interval_seconds: int = 60
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_force_ipv6: bool = True
    email_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_to: str = ""
    smtp_tls: bool = True
    webhook_enabled: bool = False
    webhook_url: str = ""
    webhook_secret: str = ""
    webhook_attempts: int = 3
    webhook_backoff_seconds: float = 0.4

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


@lru_cache
def get_settings() -> Settings:
    return Settings()
