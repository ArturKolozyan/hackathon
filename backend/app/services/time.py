from contextvars import ContextVar
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings

_zone_override: ContextVar[ZoneInfo | None] = ContextVar("invoice_zone", default=None)


def bind_zone(name: str):
    return _zone_override.set(ZoneInfo(name))


def reset_zone(token) -> None:
    try:
        _zone_override.reset(token)
    except ValueError:
        # Токен из другого контекста: просто снимаем привязку.
        _zone_override.set(None)


def zone() -> ZoneInfo:
    current = _zone_override.get()
    if current is not None:
        return current
    return get_settings().zone


def now() -> datetime:
    return datetime.now(zone())


def today() -> date:
    return now().date()
