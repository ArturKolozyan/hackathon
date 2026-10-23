from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def zone() -> ZoneInfo:
    return get_settings().zone


def now() -> datetime:
    return datetime.now(zone())


def today() -> date:
    return now().date()
