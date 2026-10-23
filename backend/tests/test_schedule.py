from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.services.schedule import add_months, classify, due_date, paid_on_time

MOSCOW = ZoneInfo("Europe/Moscow")


def test_missing_day_falls_on_month_end():
    assert due_date(2026, 2, 31) == date(2026, 2, 28)
    assert due_date(2024, 2, 31) == date(2024, 2, 29)
    assert due_date(2026, 4, 31) == date(2026, 4, 30)
    assert due_date(2026, 12, 5) == date(2026, 12, 5)


def test_add_months_clamps_day():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 10, 1), -3) == date(2026, 7, 1)


def test_due_today_is_soon_not_overdue():
    assert classify(date(2026, 10, 23), None, date(2026, 10, 23), 3) == "due_soon"
    assert classify(date(2026, 10, 22), None, date(2026, 10, 23), 3) == "overdue"
    assert classify(date(2026, 10, 26), None, date(2026, 10, 23), 3) == "due_soon"
    assert classify(date(2026, 10, 27), None, date(2026, 10, 23), 3) == "upcoming"
    assert classify(date(2026, 10, 1), datetime(2026, 10, 1, 12, tzinfo=MOSCOW), date(2026, 10, 23), 3) == "paid"


def test_payment_uses_team_timezone():
    due = date(2026, 10, 12)
    # 22:30 UTC — уже 13 октября в Москве, это опоздание.
    late = datetime.fromisoformat("2026-10-12T22:30:00+00:00")
    # 20:30 UTC — ещё 12 октября в Москве, вовремя.
    on_time = datetime.fromisoformat("2026-10-12T20:30:00+00:00")
    assert paid_on_time(late, due, MOSCOW) is False
    assert paid_on_time(on_time, due, MOSCOW) is True
    assert paid_on_time(datetime(2026, 10, 12, 12, tzinfo=MOSCOW), due, MOSCOW) is True
