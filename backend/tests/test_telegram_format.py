"""Оформление Telegram: деньги и даты по-русски, HTML экранирован."""

from datetime import date
from decimal import Decimal

from app.services import telegram_html as tg
from app.services.humanize import due_phrase, money, plural, ru_date

TODAY = date(2026, 10, 23)


def test_humanize():
    assert money(Decimal("12500"), "RUB") == "12\u202f500\u00a0₽"
    assert money(Decimal("40.5"), "USD") == "40,50\u00a0$"
    assert money(Decimal("1000000"), "EUR") == "1\u202f000\u202f000\u00a0€"
    assert ru_date(date(2026, 10, 26)) == "26 октября 2026"
    assert ru_date(date(2026, 3, 1), year=False) == "1 марта"
    assert plural(1, "день", "дня", "дней") == "день"
    assert plural(3, "день", "дня", "дней") == "дня"
    assert plural(11, "день", "дня", "дней") == "дней"
    assert plural(21, "день", "дня", "дней") == "день"
    assert due_phrase(TODAY, TODAY) == "сегодня"
    assert due_phrase(date(2026, 10, 24), TODAY) == "завтра"
    assert due_phrase(date(2026, 10, 28), TODAY) == "через 5 дней"
    assert due_phrase(date(2026, 10, 21), TODAY) == "просрочено на 2 дня"


def test_user_text_is_escaped():
    card = tg.compose("🔴", "Просрочено", [tg.bold("<script>&"), tg.field("Отдел", "R&D <b>")])
    assert "<script>" not in card and "&lt;script&gt;&amp;" in card
    assert "R&amp;D &lt;b&gt;" in card
    assert card.startswith("🔴 <b>Просрочено</b>")
    assert "·" not in card
