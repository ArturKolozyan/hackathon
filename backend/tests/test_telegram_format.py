"""Оформление Telegram: деньги и даты по-русски, HTML экранирован, markdown ассистента читается в чате."""

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


def test_markdown_becomes_telegram_html():
    html = tg.markdown_to_html(
        "### Открытые платежи\n\n"
        "| Валюта | Просрочено | Всего |\n|---|---|---|\n| RUB | — | **5\u00a0₽** |\n\n"
        "Просрочено\n\n"
        "**Аренда <офис>** — 85\u00a0000\u00a0₽\nдо 5 сентября, просрочено, ответственный: Иван\n\n"
        "- [Справка](https://rekeeper.ru/help) и `код`"
    )
    assert html.startswith("<b>Открытые платежи</b>")
    assert "• <b>RUB</b> — Всего: <b>5\u00a0₽</b>" in html
    assert "Просрочено: —" not in html
    assert "<b>Просрочено</b>" in html
    assert "• <b>Аренда &lt;офис&gt;</b> — 85\u00a0000\u00a0₽" in html
    assert "<i>до 5 сентября, просрочено, ответственный: Иван</i>" in html
    assert '<a href="https://rekeeper.ru/help">Справка</a>' in html
    assert "<code>код</code>" in html
    assert "###" not in html and "|" not in html


def test_markdown_link_cannot_break_out_of_href():
    html = tg.markdown_to_html('[x](https://a.ru/"><b>y)')
    assert '"><b>' not in html
