"""Единственное место, где решается, пора ли напомнить о периоде.

Каналы (email, webhook, Telegram) этот порог не повторяют.
Окно то же, что у инбокса: за SOON_DAYS дней, включая день срока,
и сразу, если период уже в окне или просрочен. Оплаченный и архивный — нет.
Дедуп отправки живёт в notify, не здесь.
"""

from datetime import date, datetime


def should_remind(
    *,
    due: date,
    paid_at: datetime | None,
    archived: bool,
    today: date,
    soon_days: int,
) -> bool:
    if archived or paid_at is not None:
        return False
    return (due - today).days <= soon_days
