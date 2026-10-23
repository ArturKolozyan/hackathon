"""SMTP-канал напоминания. Выключенный или неполный SMTP — no-op, процесс не падает.

Срок «пора ли писать» здесь не считается: это уже решил should_remind.
"""

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

log = logging.getLogger("invoice_keeper.email")

_STATUS_RU = {
    "overdue": "просрочено",
    "due_soon": "скоро",
    "upcoming": "впереди",
    "paid": "оплачено",
}


def configured() -> bool:
    settings = get_settings()
    return bool(
        settings.email_enabled
        and settings.smtp_host.strip()
        and settings.smtp_from.strip()
        and settings.smtp_to.strip()
    )


def _header(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ").strip()


def send_reminder_email(payload: dict) -> str:
    if not configured():
        return "skipped"
    settings = get_settings()
    body = payload["occurrence"]
    status = _STATUS_RU.get(body["status"], body["status"])
    message = EmailMessage()
    message["Subject"] = _header(f"rekeeper: {body['title']} до {body['due_date']}")
    message["From"] = _header(settings.smtp_from)
    recipients = [item.strip() for item in settings.smtp_to.split(",") if item.strip()]
    message["To"] = ", ".join(_header(item) for item in recipients)
    message.set_content(
        "\n".join(
            [
                "rekeeper",
                "",
                body["title"],
                f"Сумма: {body['amount']} {body['currency']}",
                f"Срок: {body['due_date']}",
                f"Статус: {status}",
                "",
                "Напоминание об обязательстве команды. Оплату отмечайте в панели.",
            ]
        ),
        charset="utf-8",
    )
    try:
        if settings.smtp_port == 465:
            client_factory = smtplib.SMTP_SSL
            start_tls = False
        else:
            client_factory = smtplib.SMTP
            start_tls = settings.smtp_tls
        with client_factory(settings.smtp_host.strip(), settings.smtp_port, timeout=10) as client:
            if start_tls:
                client.starttls()
            if settings.smtp_user.strip():
                client.login(settings.smtp_user.strip(), settings.smtp_password)
            client.send_message(message)
    except Exception as exc:
        log.warning("email send failed: %s", type(exc).__name__)
        return "failed"
    return "sent"
