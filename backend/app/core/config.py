from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    database_url: str = "postgresql+psycopg://invoice:change-me@localhost:5432/invoice_keeper"
    secret_key: str = "change-me-not-a-secret"
    # Владелец установки. OWNER_* — канон кейса «администратор из .env».
    # ADMIN_* оставлены алиасами: старый .env и демо жюри продолжают работать.
    owner_email: str = ""
    owner_password: str = ""
    owner_name: str = ""
    # true на один запуск: записать OWNER_PASSWORD владельцу и залогировать. Потом вернуть false.
    owner_reset_password: bool = False
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
    # Пароли на странице входа. По умолчанию выключено: ответ публичный.
    show_demo_credentials: bool = False
    timezone: str = "Europe/Moscow"
    soon_days: int = 3
    # Каденция по умолчанию, пока организация не переопределила её в базе.
    reminder_days: str = "7,3"
    overdue_repeat_days: int = 1
    owner_overdue_copy: bool = False
    horizon_months: int = 2
    session_days: int = 14
    cookie_secure: bool = False
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    # Канонический адрес. Письмо-напоминание дописывает его в конец. Пустая строка — без ссылки.
    app_public_url: str = "https://rekeeper.ru"
    worker_interval_seconds: int = 60
    telegram_bot_token: str = Field(default="", repr=False)
    telegram_chat_id: str = ""
    # auto пробует IPv6, затем IPv4. ipv6 — только v6 (Aeza). ipv4 — только v4.
    # Пустое значение: если TELEGRAM_FORCE_IPV6=true (устаревший алиас) — ipv6, иначе auto.
    telegram_network: str = ""
    telegram_proxy: str = ""
    telegram_bot_username: str = ""
    telegram_force_ipv6: bool = False
    assistant_url: str = ""
    bot_health_port: int = 8001
    assistant_port: int = 8002
    worker_health_port: int = 8003
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
    # Пустой ключ — ассистент выключен в /features и в боте. Контейнер — профиль compose.
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
    def resolved_owner_email(self) -> str:
        return (self.owner_email or self.admin_email).strip().lower()

    @property
    def resolved_owner_password(self) -> str:
        return self.owner_password or self.admin_password

    @property
    def resolved_owner_name(self) -> str:
        return (self.owner_name or self.admin_name or "Владелец").strip() or "Владелец"

    @property
    def resolved_telegram_network(self) -> str:
        raw = (self.telegram_network or "").strip().lower()
        if raw in {"auto", "ipv4", "ipv6"}:
            return raw
        if self.telegram_force_ipv6:
            return "ipv6"
        return "auto"

    @property
    def assistant_configured(self) -> bool:
        return bool(self.gigachat_auth_key.strip())

    @property
    def voice_configured(self) -> bool:
        return bool(self.yandex_speechkit_api_key.strip() and self.yandex_folder_id.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


@lru_cache
def get_settings() -> Settings:
    return Settings()
