from datetime import date

from app.seed import seed
from tests.support import add_person, bootstrap_owner


def _login(client, email: str, password: str) -> dict:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_health_and_docs(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}
    assert client.get("/api/v1/docs").status_code == 200
    spec = client.get("/api/v1/openapi.json")
    assert spec.status_code == 200
    assert "/api/v1/payments/summary" in spec.json()["paths"]


def test_login_me_logout_revokes_session(client):
    bootstrap_owner()
    response = client.post("/api/v1/auth/login", json={"email": "admin@invoice.local", "password": "change-me"})
    assert response.status_code == 200, response.text
    assert "httponly" in response.headers["set-cookie"].lower()
    token = response.json()["access_token"]
    assert client.get("/api/v1/auth/me", headers=_auth(token)).status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": "admin@invoice.local", "password": "nope-nope"}).status_code == 401
    assert client.post("/api/v1/auth/logout", headers=_auth(token)).status_code == 204
    assert client.get("/api/v1/auth/me", headers=_auth(token)).status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 401


def test_demo_inbox_buckets_and_summary(client):
    seed(demo=True)
    admin = _login(client, "admin@invoice.local", "change-me")
    headers = _auth(admin["access_token"])
    inbox = client.get("/api/v1/payment-occurrences/inbox", headers=headers)
    assert inbox.status_code == 200, inbox.text
    body = inbox.json()
    assert [item["status"] for item in body["overdue"]] == ["overdue", "overdue", "overdue", "overdue"]
    assert len(body["soon"]) == 1
    assert body["soon"][0]["currency"] == "EUR"
    assert body["soon"][0]["amount"] == "15.00"
    assert body["soon"][0]["title"] == "Подписка"
    assert len(body["rest"]) == 6
    assert {item["currency"] for item in body["overdue"]} == {"RUB"}
    assert any(item["period_label"] == "сентябрь 2026" and item["title"] == "Аренда офиса" for item in body["overdue"])
    assert any(item["title"] == "Электричество" for item in body["overdue"])
    summary = client.get("/api/v1/payments/summary", headers=headers).json()
    assert summary["counts"] == {"overdue": 4, "due_soon": 1, "upcoming": 6, "paid": 7}
    by_currency = {row["currency"]: row for row in summary["by_currency"]}
    assert by_currency["RUB"]["overdue_amount"] == "194000.00"
    assert "USD" not in by_currency
    assert by_currency["EUR"]["due_soon_amount"] == "15.00"
    assert by_currency["EUR"]["overdue_amount"] == "0.00"
    power = client.get("/api/v1/payment-occurrences?view=history", headers=headers).json()["items"]
    july_power = next(item for item in power if item["title"] == "Электричество" and item["period"] == "2026-07")
    assert july_power["paid_amount"] == "14150.00"
    assert july_power["amount"] == "12000.00"
    teams = client.get("/api/v1/teams", headers=headers).json()
    infra = next(row["id"] for row in teams if row["name"] == "Инфраструктура")
    history = client.get("/api/v1/payment-occurrences?view=history", headers={**headers, "X-Team-Id": infra}).json()["items"]
    late = [item for item in history if item["paid_on_time"] is False]
    assert len(late) == 1
    assert late[0]["title"] == "Сервер"
    assert late[0]["lateness_days"] == 3
    rent_overdue = [item for item in body["overdue"] if item["title"] == "Аренда офиса"]
    rent_later = [item for item in body["rest"] if item["title"] == "Аренда офиса"]
    assert rent_overdue and rent_later
    assert max(item["due_date"] for item in rent_later) > min(item["due_date"] for item in rent_overdue)


def test_seed_twice_does_not_duplicate(client):
    seed(demo=True)
    seed(demo=True)
    admin = _login(client, "admin@invoice.local", "change-me")
    summary = client.get("/api/v1/payments/summary", headers=_auth(admin["access_token"])).json()
    assert summary["counts"]["paid"] == 7
    assert summary["counts"]["overdue"] == 4


def test_user_cannot_admin_but_can_close_period(client):
    seed(demo=True)
    admin = _login(client, "admin@invoice.local", "change-me")
    ivan = _login(client, "ivan@invoice.local", "change-me-user")
    user_headers = _auth(ivan["access_token"])
    admin_headers = _auth(admin["access_token"])
    team_id = ivan["user"]["active_team_id"]
    assert client.get("/api/v1/users", headers=user_headers).status_code == 403
    denied = client.post(
        "/api/v1/users",
        headers=user_headers,
        json={
            "email": "blocked@invoice.local",
            "full_name": "Чужой",
            "password": "change-me-user",
            "role": "user",
            "department_id": team_id,
        },
    )
    assert denied.status_code == 403
    assert client.post("/api/v1/teams", headers=user_headers, json={"name": "Свой"}).status_code == 403
    blocked_template = {
        "title": "Чужой",
        "amount": "10.00",
        "currency": "RUB",
        "day_of_month": 5,
        "starts_on": "2026-10-01",
        "responsible_user_id": ivan["user"]["id"],
    }
    assert client.post("/api/v1/recurring-payments", headers=user_headers, json=blocked_template).status_code == 403
    templates = client.get("/api/v1/recurring-payments", headers=admin_headers)
    assert templates.status_code == 200
    payment_id = templates.json()[0]["id"]
    assert client.patch(f"/api/v1/recurring-payments/{payment_id}", headers=user_headers, json={"title": "Хак"}).status_code == 403
    assert client.delete(f"/api/v1/recurring-payments/{payment_id}", headers=user_headers).status_code == 403
    inbox = client.get("/api/v1/payment-occurrences/inbox?mine=true", headers=user_headers)
    assert inbox.status_code == 200
    titles = {item["title"] for name in ("overdue", "soon", "rest") for item in inbox.json()[name]}
    assert "Сервер" not in titles
    assert "Аренда офиса" in titles
    target = inbox.json()["overdue"][0]
    paid = client.post(
        f"/api/v1/payment-occurrences/{target['id']}/confirm",
        headers=user_headers,
        json={"paid_at": "2026-10-23", "note": "Закрыл из инбокса"},
    )
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "paid"
    assert paid.json()["paid_by"]["email"] == "ivan@invoice.local"
    again = client.get("/api/v1/payment-occurrences/inbox?mine=true", headers=user_headers).json()
    left = {item["id"] for name in ("overdue", "soon", "rest") for item in again[name]}
    assert target["id"] not in left
    summary = client.get("/api/v1/payments/summary", headers=user_headers)
    assert summary.status_code == 200


def test_fact_date_recalculates_and_short_month(client):
    bootstrap_owner()
    admin = _login(client, "admin@invoice.local", "change-me")
    headers = _auth(admin["access_token"])
    created = client.post(
        "/api/v1/recurring-payments",
        headers=headers,
        json={
            "title": "Домен",
            "amount": "10.00",
            "currency": "USD",
            "day_of_month": 12,
            "starts_on": "2026-10-01",
            "responsible_user_id": admin["user"]["id"],
        },
    )
    assert created.status_code == 201, created.text
    payment_id = created.json()["id"]
    items = client.get(f"/api/v1/payment-occurrences?recurring_payment_id={payment_id}", headers=headers).json()["items"]
    october = next(item for item in items if item["period"] == "2026-10")
    late = client.post(
        f"/api/v1/payment-occurrences/{october['id']}/confirm",
        headers=headers,
        json={"paid_at": "2026-10-12T22:30:00Z"},
    )
    assert late.json()["paid_on_time"] is False
    assert late.json()["paid_on"] == "2026-10-13"
    fixed = client.patch(
        f"/api/v1/payment-occurrences/{october['id']}",
        headers=headers,
        json={"paid_at": "2026-10-12"},
    )
    assert fixed.status_code == 200, fixed.text
    assert fixed.json()["paid_on_time"] is True
    assert fixed.json()["paid_on"] == "2026-10-12"
    same_evening = client.post(
        f"/api/v1/payment-occurrences/{october['id']}/confirm",
        headers=headers,
        json={"paid_at": "2026-10-12T20:30:00Z"},
    )
    assert same_evening.json()["paid_on_time"] is True
    short = client.post(
        "/api/v1/recurring-payments",
        headers=headers,
        json={
            "title": "Короткий месяц",
            "amount": "3.00",
            "currency": "EUR",
            "day_of_month": 31,
            "starts_on": "2026-02-01",
            "responsible_user_id": admin["user"]["id"],
        },
    )
    assert short.status_code == 201, short.text
    periods = client.get(
        f"/api/v1/payment-occurrences?recurring_payment_id={short.json()['id']}",
        headers=headers,
    ).json()["items"]
    assert next(item for item in periods if item["period"] == "2026-02")["due_date"] == "2026-02-28"
    assert next(item for item in periods if item["period"] == "2026-04")["due_date"] == "2026-04-30"


def test_paid_snapshot_and_archive(client, monkeypatch):
    bootstrap_owner()
    admin = _login(client, "admin@invoice.local", "change-me")
    headers = _auth(admin["access_token"])

    def create(title: str, day: int, amount: str = "100.00") -> dict:
        response = client.post(
            "/api/v1/recurring-payments",
            headers=headers,
            json={
                "title": title,
                "amount": amount,
                "currency": "RUB",
                "day_of_month": day,
                "starts_on": "2026-08-01",
                "responsible_user_id": admin["user"]["id"],
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    def items_of(payment_id: str) -> list[dict]:
        response = client.get(f"/api/v1/payment-occurrences?recurring_payment_id={payment_id}", headers=headers)
        assert response.status_code == 200, response.text
        return response.json()["items"]

    tracked = create("Снимок", 12)
    august = next(item for item in items_of(tracked["id"]) if item["period"] == "2026-08")
    assert client.post(
        f"/api/v1/payment-occurrences/{august['id']}/confirm",
        headers=headers,
        json={"paid_at": "2026-08-12"},
    ).status_code == 200
    renamed = client.patch(f"/api/v1/recurring-payments/{tracked['id']}", headers=headers, json={"amount": "180.00", "title": "Снимок новый"})
    assert renamed.status_code == 200, renamed.text
    refreshed = {item["period"]: item for item in items_of(tracked["id"])}
    assert refreshed["2026-08"]["amount"] == "100.00"
    assert refreshed["2026-08"]["title"] == "Снимок"
    assert refreshed["2026-08"]["due_date"] == "2026-08-12"
    assert refreshed["2026-10"]["amount"] == "100.00"
    assert refreshed["2026-10"]["title"] == "Снимок"
    assert refreshed["2026-10"]["due_date"] == "2026-10-12"
    assert refreshed["2026-11"]["amount"] == "180.00"
    assert refreshed["2026-11"]["title"] == "Снимок новый"
    assert renamed.json()["applies_from"] == "2026-11-12"
    moved = client.patch(
        f"/api/v1/recurring-payments/{tracked['id']}",
        headers=headers,
        json={"day_of_month": 3},
    )
    assert moved.status_code == 200, moved.text
    after_day = {item["period"]: item for item in items_of(tracked["id"])}
    assert after_day["2026-08"]["due_date"] == "2026-08-12"
    assert after_day["2026-10"]["due_date"] == "2026-10-12"
    assert after_day["2026-11"]["due_date"] == "2026-11-03"

    archived = create("Архив", 10, "50.00")
    alive = create("Живой", 11, "50.00")
    before_archived = len(items_of(archived["id"]))
    before_alive = len(items_of(alive["id"]))
    assert before_archived > 0
    removed = client.delete(f"/api/v1/recurring-payments/{archived['id']}", headers=headers)
    assert removed.status_code == 200
    assert removed.json()["is_archived"] is True
    monkeypatch.setattr("app.services.time.today", lambda: date(2027, 6, 1))
    assert len(items_of(archived["id"])) == before_archived
    assert len(items_of(alive["id"])) > before_alive


def test_owner_leaves_only_after_transfer(client, db_session):
    bootstrap_owner()
    temp = add_person(db_session, email="temp@invoice.local", password="change-me-user", name="Временный")
    db_session.commit()
    admin = _login(client, "admin@invoice.local", "change-me")
    headers = _auth(admin["access_token"])
    team_id = admin["user"]["active_team_id"]
    locked = client.patch(
        f"/api/v1/users/{admin['user']['id']}",
        headers=headers,
        json={"full_name": "Другой"},
    )
    assert locked.status_code == 403
    assert "нельзя" in locked.json()["detail"]
    assert client.delete(f"/api/v1/users/{admin['user']['id']}", headers=headers).status_code == 403
    assert client.post(
        f"/api/v1/teams/{team_id}/transfer",
        headers=headers,
        json={"user_id": str(temp.id)},
    ).status_code == 404
    inbox = client.get("/api/v1/payment-occurrences/inbox", headers=headers)
    assert inbox.status_code == 200
