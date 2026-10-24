"""Регрессии аудита: будущее не пишется в базу, архив, конец месяца, перенос срока, факт оплаты,
пустые поля, часовой пояс организации, вебхук с паузами, факт только у оплаченного, чеки на диске."""

import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.models import NotificationDelivery, PaymentOccurrence, RecurringPayment, Team
from app.services.occurrences import ensure_template, prune_future
from app.services.receipts import storage_dir, sweep
from tests.support import add_person, bootstrap_owner
from tests.test_stars import HEIC, PDF

TODAY = date(2026, 10, 23)


def _headers(client, email="admin@invoice.local", password="change-me") -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _owner(client) -> dict[str, str]:
    bootstrap_owner()
    return _headers(client)


def _create(client, headers, title="Хостинг", next_date="2026-11-10", amount="100.00", **extra) -> dict:
    body = {"title": title, "amount": amount, "currency": "RUB", "next_payment_date": next_date, "periodicity": "monthly"}
    body.update(extra)
    response = client.post("/api/v1/recurring-payments", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _periods(client, headers, payment_id) -> list[dict]:
    response = client.get(f"/api/v1/payment-occurrences?recurring_payment_id={payment_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["items"]


def _count(db) -> int:
    db.expire_all()
    return int(db.scalar(select(func.count()).select_from(PaymentOccurrence)) or 0)


def test_future_views_do_not_store_periods(client, db_session):
    headers = _owner(client)
    _create(client, headers, starts_on=None)
    stored = _count(db_session)
    calendar = client.get("/api/v1/payments/calendar?year=2027&month=6", headers=headers)
    assert calendar.status_code == 200, calendar.text
    items = [item for day in calendar.json()["days"] for item in day["items"]]
    assert [item["due_date"] for item in items] == ["2027-06-10"]
    assert items[0]["planned"] is True
    assert client.get("/api/v1/payments/summary?as_of=2027-06-15", headers=headers).status_code == 200
    budget = client.get("/api/v1/budgets/report?period_type=month&period_key=2027-06", headers=headers)
    assert budget.status_code == 200, budget.text
    assert any(line["expected_amount"] == "100.00" for line in budget.json()["rows"] if line["currency"] == "RUB")
    stats = client.get("/api/v1/stats?month=2027-03", headers=headers)
    assert stats.status_code == 200, stats.text
    assert [row["planned"] for row in stats.json()["operations"]["items"]] == [True]
    assert _count(db_session) == stored


def test_prune_removes_only_untouched_far_periods(client, db_session):
    headers = _owner(client)
    created = _create(client, headers)
    template = db_session.get(RecurringPayment, created["id"])
    ensure_template(db_session, template, date(2027, 8, 1))
    db_session.commit()
    far = db_session.scalars(
        select(PaymentOccurrence).where(PaymentOccurrence.due_date > date(2027, 1, 1)).order_by(PaymentOccurrence.due_date)
    ).all()
    assert len(far) >= 5
    far[0].note = "договорились заранее"
    far[1].amount = 150
    far[2].receipt_file = "kept.pdf"
    db_session.commit()
    removed = prune_future(db_session, TODAY)
    db_session.commit()
    assert removed == len(far) - 3
    assert prune_future(db_session, TODAY) == 0
    left = {row.id for row in db_session.scalars(select(PaymentOccurrence)).all()}
    assert {far[0].id, far[1].id, far[2].id} <= left


def test_archive_hides_future_everywhere_and_unarchive_resumes_today(client, db_session, monkeypatch):
    headers = _owner(client)
    created = _create(client, headers, title="Сервер", next_date="2026-09-10")
    before = _periods(client, headers, created["id"])
    assert any(item["due_date"] >= "2026-10-23" for item in before)
    assert client.delete(f"/api/v1/recurring-payments/{created['id']}", headers=headers).status_code == 200
    left = _periods(client, headers, created["id"])
    assert left and all(item["due_date"] < "2026-10-23" for item in left)
    csv = client.get("/api/v1/payment-occurrences/export.csv?view=all", headers=headers).content.decode("utf-8-sig")
    assert "2026-11-10" not in csv
    stats = client.get("/api/v1/stats?month=2026-11", headers=headers).json()
    assert stats["to_pay"] == []
    monkeypatch.setattr("app.services.time.today", lambda: date(2027, 2, 1))
    reopened = client.patch(f"/api/v1/recurring-payments/{created['id']}", headers=headers, json={"is_archived": False})
    assert reopened.status_code == 200, reopened.text
    after = _periods(client, headers, created["id"])
    new = [item["due_date"] for item in after if item["due_date"] > "2026-10-23"]
    # Месяцы в архиве не стали просрочкой: расписание продолжилось с ближайшего срока.
    assert min(new) == "2027-02-10"


def test_month_end_anchor_survives_edits(client, db_session):
    headers = _owner(client)
    created = _create(client, headers, title="Аренда", next_date="2026-10-31")
    assert created["day_of_month"] == 31
    same = client.patch(
        f"/api/v1/recurring-payments/{created['id']}",
        headers=headers,
        json={"title": "Аренда офиса", "next_payment_date": created["next_payment_date"]},
    )
    assert same.json()["day_of_month"] == 31
    moved = client.patch(f"/api/v1/recurring-payments/{created['id']}", headers=headers, json={"next_payment_date": "2026-11-30"})
    assert moved.status_code == 200, moved.text
    assert moved.json()["day_of_month"] == 31
    dues = {item["period"]: item["due_date"] for item in _periods(client, headers, created["id"])}
    assert dues["2026-11"] == "2026-11-30" and dues["2026-12"] == "2026-12-31"


def test_moving_due_date_to_previous_month_does_not_duplicate(client, db_session):
    headers = _owner(client)
    created = _create(client, headers, next_date="2026-11-03")
    november = next(item for item in _periods(client, headers, created["id"]) if item["period"] == "2026-11")
    moved = client.patch(f"/api/v1/payment-occurrences/{november['id']}", headers=headers, json={"due_date": "2026-10-30"})
    assert moved.status_code == 200, moved.text
    assert moved.json()["period"] == "2026-11"
    periods = [item["period"] for item in _periods(client, headers, created["id"])]
    assert periods.count("2026-11") == 1
    far = client.patch(f"/api/v1/payment-occurrences/{november['id']}", headers=headers, json={"due_date": "2027-03-01"})
    assert far.status_code == 422


def test_paid_totals_use_actual_amount_and_only_paid_has_it(client, db_session):
    headers = _owner(client)
    created = _create(client, headers, next_date="2026-10-05")
    october = next(item for item in _periods(client, headers, created["id"]) if item["period"] == "2026-10")
    november = next(item for item in _periods(client, headers, created["id"]) if item["period"] == "2026-11")
    refused = client.patch(f"/api/v1/payment-occurrences/{november['id']}", headers=headers, json={"paid_amount": "90.00"})
    assert refused.status_code == 422
    paid = client.post(
        f"/api/v1/payment-occurrences/{october['id']}/confirm", headers=headers, json={"paid_at": "2026-10-05", "paid_amount": "120.00"}
    )
    assert paid.status_code == 200, paid.text
    summary = client.get("/api/v1/payments/summary", headers=headers).json()
    rub = next(row for row in summary["by_currency"] if row["currency"] == "RUB")
    assert rub["paid_amount"] == "120.00"
    unpaid = client.patch(f"/api/v1/payment-occurrences/{october['id']}", headers=headers, json={"paid_at": None})
    assert unpaid.json()["paid_amount"] is None


def test_patch_with_nulls_is_422(client, db_session):
    headers = _owner(client)
    created = _create(client, headers)
    for field in ("title", "amount", "currency", "next_payment_date", "is_archived", "periodicity", "day_of_month"):
        response = client.patch(f"/api/v1/recurring-payments/{created['id']}", headers=headers, json={field: None})
        assert response.status_code == 422, (field, response.status_code, response.text)


def test_organization_timezone_drives_paid_dates(client, db_session):
    headers = _owner(client)
    assert client.patch("/api/v1/organization", headers=headers, json={"timezone": "Asia/Tokyo"}).status_code == 200
    created = _create(client, headers, next_date="2026-10-20")
    october = next(item for item in _periods(client, headers, created["id"]) if item["period"] == "2026-10")
    paid = client.post(
        f"/api/v1/payment-occurrences/{october['id']}/confirm", headers=headers, json={"paid_at": "2026-10-20T20:30:00+00:00"}
    )
    assert paid.status_code == 200, paid.text
    # 20:30 UTC — в Москве ещё 20-е, в Токио уже 21 октября: оплата с опозданием на день.
    assert paid.json()["paid_on"] == "2026-10-21"
    assert paid.json()["lateness_days"] == 1
    listed = client.get("/api/v1/payment-occurrences?view=history", headers=headers).json()
    assert listed["timezone"] == "Asia/Tokyo"


def test_broken_team_webhook_backs_off_and_gives_up(client, db_session, monkeypatch):
    from app.services import notify

    headers = _owner(client)
    monkeypatch.setattr("app.integrations.webhook._addresses", lambda host, port: ["93.184.216.34"])
    saved = client.put("/api/v1/notifications/team/webhook", headers=headers, json={"url": "https://hooks.example/in"})
    assert saved.status_code == 200, saved.text
    calls: list[str] = []

    def broken(url, body, headers):
        calls.append(url)
        raise TimeoutError("timeout")

    monkeypatch.setattr("app.integrations.webhook._post", broken)
    _create(client, headers, title="Долг", next_date="2026-10-20")
    moment = {"now": datetime(2026, 10, 23, 12, 0, tzinfo=ZoneInfo("Europe/Moscow"))}
    monkeypatch.setattr("app.services.time.now", lambda: moment["now"])
    notify.dispatch_due_reminders(db_session)
    db_session.commit()
    assert len(calls) == 1
    notify.dispatch_due_reminders(db_session)
    assert len(calls) == 1, "в паузе адрес отдела не дёргаем"
    for _ in range(10):
        moment["now"] += timedelta(hours=7)
        notify.dispatch_due_reminders(db_session)
        db_session.commit()
    team = db_session.scalar(select(Team))
    assert team.webhook_failures >= 5 and team.webhook_retry_at is not None
    rows = db_session.scalars(select(NotificationDelivery).where(NotificationDelivery.channel == "webhook")).all()
    assert rows and all(row.status == "skipped" and row.attempts == notify.WEBHOOK_TRIES for row in rows)


def test_receipt_files_follow_their_periods(client, db_session, monkeypatch):
    headers = _owner(client)
    created = _create(client, headers, next_date="2026-10-05")
    october = next(item for item in _periods(client, headers, created["id"]) if item["period"] == "2026-10")
    url = f"/api/v1/payment-occurrences/{october['id']}/receipt"
    saved = client.post(url, headers=headers, files={"file": ("чек.heic", HEIC, "image/heic")})
    assert saved.status_code == 200, saved.text
    fetched = client.get(url, headers=headers)
    assert fetched.status_code == 200
    assert fetched.headers["cache-control"] == "private, no-cache"
    assert fetched.headers["content-disposition"].startswith("attachment")
    pdf = client.post(url, headers=headers, files={"file": ("чек.pdf", PDF, "application/pdf")})
    assert pdf.status_code == 200
    assert client.get(url, headers=headers).headers["content-disposition"].startswith("inline")
    key = db_session.scalar(select(PaymentOccurrence.receipt_file).where(PaymentOccurrence.id == october["id"]))
    assert (storage_dir() / key).is_file()

    temp = add_person(db_session, email="temp@invoice.local", name="Временный")
    temp.must_change_password = True
    db_session.commit()
    assert client.get(url, headers=_headers(client, "temp@invoice.local", "change-me-user")).status_code == 403

    orphan = storage_dir() / "orphan.pdf"
    orphan.write_bytes(PDF)
    fresh = storage_dir() / "fresh.pdf.part"
    fresh.write_bytes(PDF)
    old = time.time() - 7200
    os.utime(orphan, (old, old))
    assert sweep(db_session) == 1
    assert not orphan.exists() and fresh.exists() and (storage_dir() / key).is_file()
    fresh.unlink()

    team = db_session.scalar(select(Team))
    removed = client.request("DELETE", f"/api/v1/teams/{team.id}", headers=headers, json={"name": team.name})
    assert removed.status_code == 204, removed.text
    assert not Path(storage_dir() / key).exists()


def test_audit_log_keeps_last_thousand(client, db_session):
    from app.models import AuditLog
    from app.services import audit

    bootstrap_owner()
    others = len(db_session.scalars(select(AuditLog)).all())
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db_session.add_all(AuditLog(at=start + timedelta(minutes=index), action="test.old", meta={}) for index in range(audit.AUDIT_KEEP + 5))
    db_session.commit()
    audit.record(db_session, action="test.new")
    db_session.commit()
    rows = db_session.scalars(select(AuditLog).order_by(AuditLog.at)).all()
    assert len(rows) == audit.AUDIT_KEEP
    assert "test.new" in {row.action for row in rows}
    dropped = audit.AUDIT_KEEP + 5 + others + 1 - audit.AUDIT_KEEP
    assert rows[0].at == start + timedelta(minutes=dropped)


CBR_SAMPLE = (
    '<?xml version="1.0" encoding="windows-1251"?><ValCurs Date="24.10.2026" name="Foreign Currency Market">'
    '<Valute ID="R01235"><CharCode>USD</CharCode><Nominal>1</Nominal><Value>80,5381</Value></Valute>'
    '<Valute ID="R01239"><CharCode>EUR</CharCode><Nominal>1</Nominal><Value>90,2429</Value></Valute>'
    '<Valute ID="R01030"><CharCode>DZD</CharCode><Nominal>100</Nominal><Value>59,7463</Value></Valute>'
    "</ValCurs>"
).encode("windows-1251")


def test_rates_are_cached_and_quiet_when_unavailable(client, db_session, monkeypatch):
    from decimal import Decimal

    from app.services import rates

    parsed = rates._from_xml(CBR_SAMPLE)
    assert parsed.on == date(2026, 10, 24) and parsed.values == {"USD": Decimal("80.5381"), "EUR": Decimal("90.2429")}
    assert client.get("/api/v1/rates").status_code == 401
    headers = _owner(client)
    assert client.get("/api/v1/rates", headers=headers).json() == {"on": None, "rates": {}}

    rates.forget()
    calls = []
    monkeypatch.setattr(rates, "fetch", lambda: calls.append(1) or parsed)
    first = client.get("/api/v1/rates", headers=headers).json()
    assert first == {"on": "2026-10-24", "rates": {"USD": "80.5381", "EUR": "90.2429"}}
    client.get("/api/v1/rates", headers=headers)
    assert len(calls) == 1
    # ЦБ пропал: остаётся последний курс со своей датой.
    monkeypatch.setattr(rates, "_checked", 1.0)
    monkeypatch.setattr(rates, "fetch", lambda: None)
    assert client.get("/api/v1/rates", headers=headers).json()["on"] == "2026-10-24"


def test_api_responses_are_never_cached(client, db_session):
    headers = _owner(client)
    assert client.get("/api/v1/health").headers["cache-control"] == "no-store"
    assert client.get("/api/v1/me", headers=headers).headers["cache-control"] == "no-store"
