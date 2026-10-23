"""Второй экран инбокса. В этом куске отправитель намеренно не реализован.

На VPS в Москве IPv4 до api.telegram.org таймаутится, IPv6 отвечает.
Когда появится бот, HTTP-клиент воркера должен ходить на API по IPv6
(или через прокси вне РФ). Напоминание: за SOON_DAYS и сразу, если уже
просрочено; без дублей; архив шаблона останавливает новые напоминания,
история периодов остаётся.
"""

from app.core.config import get_settings


def describe_transport() -> dict[str, object]:
    token = get_settings().telegram_bot_token.strip()
    return {
        "sender": "not_implemented",
        "host": "api.telegram.org",
        "force_ipv6": get_settings().telegram_force_ipv6,
        "token_configured": bool(token),
        "vps_note": "Moscow VPS: IPv4 to api.telegram.org times out; use IPv6",
    }


def send_message(*_args: object, **_kwargs: object) -> None:
    raise NotImplementedError("Telegram sender is intentionally not implemented yet")
