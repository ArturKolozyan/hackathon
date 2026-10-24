"""Часовые пояса СНГ, которые можно выбрать в настройках организации.

Пояс хранится в базе (organization_settings.timezone), переменной окружения для него нет.
Тот же список показывает фронтенд (frontend/src/timezones.ts).
"""

DEFAULT_TIMEZONE = "Europe/Moscow"

CIS_TIMEZONES: tuple[str, ...] = (
    "Europe/Kaliningrad",
    "Europe/Chisinau",
    "Europe/Moscow",
    "Europe/Minsk",
    "Europe/Samara",
    "Asia/Yerevan",
    "Asia/Baku",
    "Asia/Yekaterinburg",
    "Asia/Tashkent",
    "Asia/Ashgabat",
    "Asia/Dushanbe",
    "Asia/Almaty",
    "Asia/Bishkek",
    "Asia/Omsk",
    "Asia/Novosibirsk",
    "Asia/Krasnoyarsk",
    "Asia/Irkutsk",
    "Asia/Yakutsk",
    "Asia/Vladivostok",
    "Asia/Magadan",
    "Asia/Kamchatka",
)
