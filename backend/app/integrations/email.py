"""SMTP. Напоминания и письма аккаунта ходят в один сервер, но это разные письма.

Напоминание молчит без EMAIL_ENABLED и SMTP_TO.
Код и приглашение SMTP_TO не используют и от EMAIL_ENABLED не зависят:
хватает SMTP_HOST. Пустой хост — dev, код остаётся в логе API.

Прод: smtp.beget.com:2525 и SMTP_TLS (STARTTLS). Порт 465 с VPS закрыт,
поэтому 465 — только явный SMTP_SSL, обычный порт всегда STARTTLS по флагу.
Сокет ждёт не дольше 15 секунд. Письмо аккаунта уходит в фоне и не держит запрос.
"""

import logging
import smtplib
import threading
from email.message import EmailMessage

from app.core.config import get_settings

log = logging.getLogger("invoice_keeper.email")

SMTP_TIMEOUT = 15

_STATUS_RU = {
    "overdue": "просрочено",
    "due_soon": "скоро",
    "upcoming": "впереди",
    "paid": "оплачено",
}

_threads: list[threading.Thread] = []
_lock = threading.Lock()


def configured() -> bool:
    settings = get_settings()
    return bool(
        settings.email_enabled
        and settings.smtp_host.strip()
        and settings.smtp_from.strip()
        and settings.smtp_to.strip()
    )


def personal_mail_ready() -> bool:
    """Личное письмо не смотрит на SMTP_TO. Порт 465 здесь не выбирается: его берёт connect_smtp."""
    settings = get_settings()
    return bool(settings.email_enabled and settings.smtp_host.strip() and settings.smtp_from.strip())


def smtp_host_configured() -> bool:
    return bool(get_settings().smtp_host.strip())


def _header(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ").strip()


def from_header() -> str:
    raw = get_settings().smtp_from.strip()
    return raw or "rekeeper <noreply@rekeeper.ru>"


def public_url() -> str:
    """Канонический адрес панели. В карточку Telegram не подставляется."""
    raw = get_settings().app_public_url.strip()
    raw = raw.replace("\r", "").replace("\n", "").replace(" ", "").rstrip("/")
    if raw.startswith("https://") or raw.startswith("http://"):
        return raw
    return ""


def connect_smtp():
    """465 — неявный SSL. Любой другой порт, включая 2525, — SMTP и STARTTLS, если SMTP_TLS."""
    settings = get_settings()
    host = settings.smtp_host.strip()
    if settings.smtp_port == 465:
        client = smtplib.SMTP_SSL(host, settings.smtp_port, timeout=SMTP_TIMEOUT)
        start_tls = False
    else:
        client = smtplib.SMTP(host, settings.smtp_port, timeout=SMTP_TIMEOUT)
        start_tls = bool(settings.smtp_tls)
    if start_tls:
        client.starttls()
    if settings.smtp_user.strip():
        client.login(settings.smtp_user.strip(), settings.smtp_password)
    return client


def _compose_reminder(payload: dict, recipients: list[str]) -> EmailMessage:
    settings = get_settings()
    body = payload["occurrence"]
    status = _STATUS_RU.get(body["status"], body["status"])
    overdue = payload.get("event") == "occurrence.overdue" or body.get("status") == "overdue"
    message = EmailMessage()
    if overdue:
        message["Subject"] = _header(f"rekeeper: просрочено — {body['title']}")
    else:
        message["Subject"] = _header(f"rekeeper: {body['title']} до {body['due_date']}")
    message["From"] = _header(settings.smtp_from)
    message["To"] = ", ".join(_header(item) for item in recipients)
    lines = [
        "rekeeper",
        "",
        body["title"],
        f"Сумма: {body['amount']} {body['currency']}",
        f"Срок: {body['due_date']}",
        f"Статус: {status}",
        "",
    ]
    if overdue:
        lines.append("Срок прошёл.")
    lines.append("Напоминание об обязательстве команды. Оплату отмечайте в панели.")
    panel = public_url()
    if panel:
        lines.append(panel)
    message.set_content("\n".join(lines), charset="utf-8")
    return message


def _deliver(message: EmailMessage) -> str:
    try:
        with connect_smtp() as client:
            client.send_message(message)
    except Exception as exc:
        log.warning("email send failed: %s", type(exc).__name__)
        return "failed"
    return "sent"


def send_reminder_email(payload: dict, *, to: str | None = None) -> str:
    """to=None — общий ящик SMTP_TO. Иначе письмо на почту человека, SMTP_TO не нужен."""
    if to is None:
        if not configured():
            return "skipped"
        recipients = [item.strip() for item in get_settings().smtp_to.split(",") if item.strip()]
    else:
        if not personal_mail_ready():
            return "skipped"
        address = to.strip()
        if not address:
            return "skipped"
        recipients = [address]
    return _deliver(_compose_reminder(payload, recipients))


def send_test_email(to: str) -> str:
    if not personal_mail_ready():
        return "skipped"
    message = EmailMessage()
    message["Subject"] = _header("rekeeper: тестовое уведомление")
    message["From"] = _header(get_settings().smtp_from)
    message["To"] = _header(to)
    lines = [
        "rekeeper",
        "",
        "Это тестовое уведомление.",
        "Письма о платежах выбранных команд будут приходить на этот адрес.",
    ]
    panel = public_url()
    if panel:
        lines.append(panel)
    message.set_content("\n".join(lines), charset="utf-8")
    return _deliver(message)


def deliver_auth_now(*, to: str, subject: str, text: str, html: str) -> None:
    """Синхронно. Для фона и тестов. Исключение наружу, код в лог не пишем."""
    message = EmailMessage()
    message["Subject"] = _header(subject)
    message["From"] = _header(from_header())
    message["To"] = _header(to)
    message.set_content(text, charset="utf-8")
    message.add_alternative(html, subtype="html")
    with connect_smtp() as client:
        client.send_message(message)


def _send_auth(payload: dict) -> None:
    try:
        deliver_auth_now(
            to=payload["to"],
            subject=payload["subject"],
            text=payload["text"],
            html=payload["html"],
        )
    except Exception as exc:
        log.warning("письмо не ушло на %s: %s", payload["to"], type(exc).__name__)


def send_auth_email(*, to: str, subject: str, text: str, html: str) -> str:
    """log — хост пустой. smtp — поток уже ушёл, запрос регистрации его не ждёт."""
    if not smtp_host_configured():
        return "log"
    thread = threading.Thread(
        target=_send_auth,
        args=({"to": to, "subject": subject, "text": text, "html": html},),
        daemon=True,
        name="rekeeper-mail",
    )
    with _lock:
        _threads.append(thread)
    thread.start()
    return "smtp"


def flush_auth_mail(timeout: float = 5) -> None:
    """Тесты дожидаются фона. Запрос API этот метод не вызывает."""
    with _lock:
        pending = list(_threads)
        _threads.clear()
    for thread in pending:
        thread.join(timeout)
