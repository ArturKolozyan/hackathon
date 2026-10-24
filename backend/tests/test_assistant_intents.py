from datetime import date

from app.assistant.dates import extract_month, first_due, resolve_period, week_bounds
from app.assistant.intents import parse_intent

TODAY = date(2026, 10, 23)


def _kind(text: str) -> str | None:
    intent = parse_intent(text, TODAY)
    return None if intent is None else intent.kind


def test_week_bounds_are_monday_to_sunday():
    start, end = week_bounds(TODAY)
    assert start == date(2026, 10, 19)
    assert end == date(2026, 10, 25)
    assert start.weekday() == 0
    assert end.weekday() == 6


def test_named_and_relative_months():
    assert extract_month("сколько потратили за октябрь", TODAY) == (2026, 10)
    assert extract_month("за сентябрь", TODAY) == (2026, 9)
    assert extract_month("за прошлый месяц", TODAY) == (2026, 9)
    assert extract_month("за месяц", TODAY) == (2026, 10)


def test_first_due_skips_a_day_already_passed():
    assert first_due(TODAY, 20) == date(2026, 11, 20)
    assert first_due(TODAY, 26) == date(2026, 10, 26)


def test_questions_go_to_the_model():
    """Вопросы больше не перехватываются регулярками: их разбирает модель с инструментами."""
    for text in (
        "Что горит на этой неделе?",
        "Что просрочено?",
        "Сколько потратили за сентябрь?",
        "Покажи открытые платежи",
        "Кто ответственный за сервер?",
        "Что у Марии?",
        "Как работают напоминания?",
        "Привет подскажи какие у нас операции были за прошлый месяц или сколько было просрочек",
        "Что я могу делать как участник?",
        "Что оплачено за сентябрь?",
    ):
        assert parse_intent(text, TODAY) is None, text


def test_explicit_commands_stay_commands():
    assert _kind("Что вы умеете?") == "capabilities"
    assert _kind("очисти чат") == "clear"
    assert _kind("Отметь сервер оплаченным") == "mark_paid"
    assert _kind("верни аренду в неоплаченные") == "mark_unpaid"


def test_resolve_period():
    assert resolve_period("tomorrow", TODAY) == (date(2026, 10, 24), date(2026, 10, 24))
    assert resolve_period("last_month", TODAY) == (date(2026, 9, 1), date(2026, 9, 30))
    assert resolve_period("this_week", TODAY) == (date(2026, 10, 19), date(2026, 10, 25))
    assert resolve_period("next_month", date(2026, 12, 5)) == (date(2027, 1, 1), date(2027, 1, 31))
    assert resolve_period("last_year", TODAY) == (date(2025, 1, 1), date(2025, 12, 31))
    assert resolve_period("2025-12", TODAY) == (date(2025, 12, 1), date(2025, 12, 31))
    assert resolve_period("last_quarter", TODAY) == (date(2026, 7, 1), date(2026, 9, 30))
    assert resolve_period("2026-10-27", TODAY) == (date(2026, 10, 27), date(2026, 10, 27))
    assert resolve_period("", TODAY) == (None, None)


def test_mutation_phrases_extract_slots_and_do_not_execute():
    created = parse_intent("Создай платёж «Домен» 1200 рублей каждое 20 число, ответственный Иван", TODAY)
    assert created is not None and created.kind == "create"
    assert created.slots["title"] == "Домен"
    assert created.slots["amount"] == "1200"
    assert created.slots["currency"] == "RUB"
    assert created.slots["day_of_month"] == 20
    assert created.slots["responsible_name"] == "Иван"
    assert created.slots["starts_on"] == "2026-10-23"

    figma = parse_intent("Добавь платёж Figma на 15 евро 3-го, отвечает Мария", TODAY)
    assert figma is not None and figma.kind == "create"
    assert figma.slots["title"] == "Figma"
    assert figma.slots["amount"] == "15"
    assert figma.slots["currency"] == "EUR"
    assert figma.slots["day_of_month"] == 3
    assert figma.slots["responsible_name"] == "Мария"

    cloud = parse_intent("Новый платёж Облако 25 долларов каждое 8-е, ответственный Админ", TODAY)
    assert cloud is not None and cloud.slots["currency"] == "USD"
    assert cloud.slots["day_of_month"] == 8
    assert cloud.slots["title"] == "Облако"

    paid = parse_intent("Отметь сервер оплаченным", TODAY)
    assert paid is not None and paid.kind == "mark_paid"
    assert paid.slots["query"] == "сервер"

    october = parse_intent("Закрой аренду за октябрь", TODAY)
    assert october is not None and october.kind == "mark_paid"
    assert october.slots["query"] == "аренду"
    assert october.slots["month"] == 10

    assert _kind("Подписка оплачена") == "mark_paid"

    amount = parse_intent("Измени сумму сервера на 45 долларов", TODAY)
    assert amount is not None and amount.kind == "update"
    assert amount.slots["amount"] == "45"
    assert amount.slots["currency"] == "USD"
    assert amount.slots["query"] == "сервера"

    day = parse_intent("Поменяй день аренды на 7", TODAY)
    assert day is not None and day.slots["day_of_month"] == 7

    person = parse_intent("Смени ответственного за подписку на Марию", TODAY)
    assert person is not None and person.kind == "update"
    assert person.slots["responsible_name"] == "Марию"

    assert _kind("Архивируй платёж подписка") == "archive"
    assert _kind("Удали шаблон домен") == "archive"


def test_incomplete_and_unsupported_do_not_look_like_chat():
    weekly = parse_intent("Создай еженедельный платёж хостинг 10 долларов", TODAY)
    assert weekly is not None and weekly.kind == "unsupported_frequency"
    missing = parse_intent("Создай платёж хостинг", TODAY)
    assert missing is not None and missing.kind == "clarify"
    assert "сумм" in missing.slots["text"]
    vague = parse_intent("Отметь оплаченным", TODAY)
    assert vague is not None and vague.kind == "clarify"
    assert parse_intent("Привет", TODAY) is None
