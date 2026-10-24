"""Системный промпт и функции GigaChat. Цифры в ответ кладёт не модель, а инструменты."""

from datetime import date

FUNCTIONS: list[dict] = [
    {
        "name": "week_outlook",
        "description": "Что горит на этой неделе: просроченные и платежи со сроком до воскресенья. Europe/Moscow.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "list_overdue",
        "description": "Только просроченные неоплаченные периоды.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "month_spending",
        "description": "Сколько уже оплачено за календарный месяц по валютам и что ещё открыто. month в формате YYYY-MM.",
        "parameters": {
            "type": "object",
            "properties": {"month": {"type": "string", "description": "YYYY-MM, пусто — текущий месяц"}},
        },
    },
    {
        "name": "list_open",
        "description": "Открытые платежи инбокса и суммы по валютам.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "find_responsible",
        "description": "Кто ответственный за платёж. query — часть названия.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "propose_create_payment",
        "description": (
            "Показать карточку создания ежемесячного платежа. Ничего не записывает. "
            "periodicity только month. Валюта RUB, USD или EUR. responsible_name — имя из команды."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "amount": {"type": "string"},
                "currency": {"type": "string"},
                "day_of_month": {"type": "integer"},
                "responsible_name": {"type": "string"},
                "starts_on": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["title", "amount", "currency", "day_of_month", "responsible_name"],
        },
    },
    {
        "name": "propose_mark_paid",
        "description": "Карточка «отметить период оплаченным». Не ставит оплату. query — название. month — YYYY-MM, если назван период.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "month": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "propose_update_payment",
        "description": "Карточка изменения шаблона. Не записывает. Укажи query и хотя бы одно поле.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "amount": {"type": "string"},
                "currency": {"type": "string"},
                "day_of_month": {"type": "integer"},
                "responsible_name": {"type": "string"},
                "title": {"type": "string"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "propose_archive_payment",
        "description": "Карточка архивации шаблона. Не архивирует, пока человек не подтвердит.",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
]

_FACT = ("сколько", "сумм", "просроч", "горит", "ответствен", "платеж", "оплат", "расход", "должен")


def system_prompt(today: date, team_name: str) -> str:
    return (
        "Ты ассистент rekeeper — инбокса регулярных платежей команды. "
        f"Сейчас открыта команда «{team_name}». Другие команды не упоминай. "
        f"Сегодня {today.isoformat()}, часовой пояс Europe/Moscow. "
        "Отвечай по-русски, коротко, на ты. "
        "Суммы, даты, статусы и имена бери только из функций. Если вопрос про данные — вызови функцию. "
        "Изменения только через propose_*: они показывают карточку и ничего не записывают. "
        "Не пиши, что платёж уже создан или оплачен. "
        "Платежи только раз в месяц, по дню месяца. Неделя, квартал и год не поддерживаются — так и скажи. "
        "Валюты: RUB, USD, EUR. Не выдумывай платежи и людей."
    )


def asks_for_facts(text: str) -> bool:
    low = text.lower().replace("ё", "е")
    return any(part in low for part in _FACT)


def has_digit(text: str) -> bool:
    return any(char.isdigit() for char in text)
