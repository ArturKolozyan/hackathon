from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import Field
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
    demo_user_three_email: str = "oleg@invoice.local"
    demo_user_three_name: str = "Олег Смирнов"
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
    telegram_bot_token: str = Field(default="", repr=False)
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
    # Ассистент. Пустой ключ — свободные фразы молчат, короткие команды по базе живы.
    gigachat_auth_key: str = ""
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_model: str = "GigaChat-2-Max"
    gigachat_fallback_model: str = "GigaChat-2-Pro"
    gigachat_oauth_url: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    gigachat_api_base: str = "https://gigachat.devices.sberbank.ru/api/v1"
    gigachat_ca_file: str = ""
    yandex_speechkit_api_key: str = ""
    yandex_folder_id: str = ""
    yandex_stt_url: str = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"
    assistant_http_timeout: float = 25.0
    assistant_http_retries: int = 2

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


@lru_cache
def get_settings() -> Settings:
    return Settings()
