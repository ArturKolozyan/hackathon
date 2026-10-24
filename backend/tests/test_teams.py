from app.seed import seed
from tests.support import add_person, bootstrap_owner


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login(client, email: str, password: str) -> dict:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def _headers(client, email: str, password: str, team_id: str | None = None) -> dict[str, str]:
    body = _login(client, email, password)
    headers = _auth(body["access_token"])
    headers["X-Team-Id"] = team_id or body["user"]["active_team_id"]
    return headers


def test_roles_and_isolation(client, db_session):
    from app.services.accounts import create_verified_user
    from app.services.teams import create_team

    owner = bootstrap_owner(email="owner@invoice.local", password="change-me-user", name="Владелец", team="Альфа")
    member = add_person(db_session, email="member@invoice.local", password="change-me-user", name="Участник")
    stranger = create_verified_user(db_session, email="beta@invoice.local", full_name="Бета", password="change-me-user")
    beta_team = create_team(db_session, owner, "Бета")
    from app.services.teams import add_member

    add_member(db_session, beta_team, stranger, "member", actor=owner)
    db_session.commit()
    owner_headers = _headers(client, "owner@invoice.local", "change-me-user")
    member_headers = _headers(client, "member@invoice.local", "change-me-user")
    beta = str(beta_team.id)
    alpha = owner_headers["X-Team-Id"]
    blocked = client.post(
        "/api/v1/recurring-payments",
        headers=member_headers,
        json={
            "title": "Чужой",
            "amount": "10.00",
            "currency": "RUB",
            "day_of_month": 5,
            "starts_on": "2026-10-01",
            "responsible_user_id": str(member.id),
        },
    )
    assert blocked.status_code == 403
    created = client.post(
        "/api/v1/recurring-payments",
        headers=owner_headers,
        json={
            "title": "Аренда",
            "amount": "10.00",
            "currency": "RUB",
            "day_of_month": 5,
            "starts_on": "2026-10-01",
            "responsible_user_id": str(owner.id),
        },
    )
    assert created.status_code == 201, created.text
    stranger_headers = _headers(client, "beta@invoice.local", "change-me-user")
    foreign = dict(stranger_headers)
    foreign["X-Team-Id"] = alpha
    assert client.get("/api/v1/payment-occurrences/inbox", headers=foreign).status_code == 403
    beta_headers = stranger_headers
    periods = client.get(
        f"/api/v1/payment-occurrences?recurring_payment_id={created.json()['id']}",
        headers=owner_headers,
    ).json()["items"]
    leaked = client.get(f"/api/v1/payment-occurrences/{periods[0]['id']}", headers=beta_headers)
    assert leaked.status_code == 404
    assert client.get("/api/v1/recurring-payments", headers=beta_headers).json() == []
    future = client.post(
        f"/api/v1/payment-occurrences/{periods[0]['id']}/confirm",
        headers=owner_headers,
        json={"paid_at": "2026-10-24"},
    )
    assert future.status_code == 422
    assert "будущ" in future.json()["detail"]


def test_invites_rotate_and_register(client, db_session, caplog):
    bootstrap_owner(email="owner@invoice.local", password="change-me-user", name="Владелец", team="Альфа")
    headers = _headers(client, "owner@invoice.local", "change-me-user")
    team_id = headers["X-Team-Id"]
    assert client.get(f"/api/v1/teams/{team_id}/invite-link", headers=headers).status_code == 404
    assert client.post("/api/v1/auth/register", json={"email": "a@b.c", "full_name": "А", "password": "change-me-user"}).status_code == 404
    assert client.get("/api/v1/join/nope").status_code == 404
    created = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": "guest@invoice.local",
            "full_name": "Гость",
            "password": "change-me-user",
            "role": "user",
            "department_id": team_id,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["role"] == "user"
    assert client.post("/api/v1/auth/login", json={"email": "guest@invoice.local", "password": "change-me-user"}).status_code == 200


def _mail_code(caplog, email: str) -> str:
    for record in reversed(caplog.records):
        if (
            record.name == "invoice_keeper.mail"
            and record.args
            and len(record.args) >= 2
            and record.args[1] == email
            and "код" in record.getMessage()
        ):
            return str(record.args[0])
    raise AssertionError(caplog.text or "код не попал в лог")


def _login_fresh(client, caplog) -> str:
    email = "walker@invoice.local"
    client.post("/api/v1/auth/register", json={"email": email, "full_name": "Гость", "password": "change-me-user"})
    code = _mail_code(caplog, email)
    body = client.post("/api/v1/auth/register/confirm", json={"email": email, "code": code})
    assert body.status_code == 200, body.text
    return body.json()["access_token"]


def test_remove_clears_responsible_and_archive_hides_open(client, db_session):
    owner = bootstrap_owner()
    person = add_person(db_session, email="ivan@invoice.local", password="change-me-user", name="Иван")
    db_session.commit()
    headers = _headers(client, "admin@invoice.local", "change-me")
    team_id = headers["X-Team-Id"]
    created = client.post(
        "/api/v1/recurring-payments",
        headers=headers,
        json={
            "title": "Аренда",
            "amount": "10.00",
            "currency": "RUB",
            "day_of_month": 5,
            "starts_on": "2026-08-01",
            "responsible_user_id": str(person.id),
        },
    )
    assert created.status_code == 201, created.text
    assert client.delete(f"/api/v1/teams/{team_id}/members/{person.id}", headers=headers).status_code == 204
    card = client.get(f"/api/v1/recurring-payments/{created.json()['id']}", headers=headers)
    assert card.json()["responsible"] is None
    still = _login(client, "ivan@invoice.local", "change-me-user")
    assert client.get("/api/v1/payment-occurrences/inbox", headers=_auth(still["access_token"])).status_code == 409
    periods = client.get(
        f"/api/v1/payment-occurrences?recurring_payment_id={created.json()['id']}",
        headers=headers,
    ).json()["items"]
    august = next(item for item in periods if item["period"] == "2026-08")
    client.post(
        f"/api/v1/payment-occurrences/{august['id']}/confirm",
        headers=headers,
        json={"paid_at": "2026-08-05"},
    )
    assert client.delete(f"/api/v1/recurring-payments/{created.json()['id']}", headers=headers).status_code == 200
    inbox = client.get("/api/v1/payment-occurrences/inbox", headers=headers).json()
    open_ids = {item["id"] for name in ("overdue", "soon", "rest") for item in inbox[name]}
    unpaid = [item for item in periods if item["id"] != august["id"]]
    assert unpaid
    missing = [item["period"] for item in unpaid if item["id"] not in open_ids]
    assert not missing, missing
    assert august["id"] not in open_ids
    history = client.get("/api/v1/payment-occurrences?view=history", headers=headers).json()["items"]
    assert any(item["id"] == august["id"] for item in history)
    summary = client.get("/api/v1/payments/summary", headers=headers).json()
    assert summary["counts"]["overdue"] >= 1
    assert summary["counts"]["paid"] >= 1


def test_stats_and_demo_isolation(client):
    seed(demo=True)
    admin = _login(client, "admin@invoice.local", "change-me")
    headers = _auth(admin["access_token"])
    inbox = client.get("/api/v1/payment-occurrences/inbox", headers=headers).json()
    titles = {item["title"] for name in ("overdue", "soon", "rest") for item in inbox[name]}
    assert "Домен" not in titles
    ivan = _login(client, "ivan@invoice.local", "change-me-user")
    stats = client.get("/api/v1/stats", headers=_auth(ivan["access_token"]))
    assert stats.status_code == 200, stats.text
    body = stats.json()
    names = {row["team_name"] for row in body["by_team"]}
    assert names == {"Бухгалтерия", "Инфраструктура"}
    assert any(row["currency"] == "RUB" and row["count"] > 0 for row in body["to_pay"])
    studio = next(row["team_id"] for row in body["by_team"] if row["team_name"] == "Бухгалтерия")
    switched = client.post("/api/v1/me/active-team", headers=headers, json={"team_id": studio})
    assert switched.status_code == 200
    assert switched.json()["active_team_id"] == studio


def test_owner_stats_cover_every_department(client):
    seed(demo=True)
    admin = _login(client, "admin@invoice.local", "change-me")
    body = client.get("/api/v1/stats", headers=_auth(admin["access_token"])).json()
    teams = client.get("/api/v1/teams", headers=_auth(admin["access_token"]))
    names = {row["team_name"] for row in body["by_team"]}
    assert {"Бухгалтерия", "Инфраструктура"} <= names
    assert {row["role"] for row in body["by_team"]} == {"owner"}
    assert any(row["count"] > 0 for row in body["to_pay"]), teams.text
