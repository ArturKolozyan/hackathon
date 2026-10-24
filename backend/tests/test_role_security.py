"""Ролевая модель на всех маршрутах: аноним, участник, админ чужого отдела, админ без прав владельца."""

import uuid

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.assistant_main import app as assistant_app
from app.core.database import SessionLocal
from app.main import app
from app.models import PaymentOccurrence, Team, User
from app.services.teams import create_team
from tests.support import add_person, bootstrap_owner

PASSWORD = "change-me-user"
# Маршруты без входа: вход, восстановление пароля, приглашение, публичный конфиг и проверки живости.
PUBLIC = {
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/password/forgot"),
    ("POST", "/api/v1/auth/password/reset"),
    ("GET", "/api/v1/auth/invite/{token}"),
    ("POST", "/api/v1/auth/invite/{token}"),
    ("GET", "/api/v1/public-config"),
    ("GET", "/api/v1/health"),
    ("GET", "/"),
    ("GET", "/health"),
}
AUTH_DEPS = {"get_current_user", "get_active_user", "get_team_context", "read_token"}


def _routes() -> list[tuple[str, str, object]]:
    rows = []
    for application in (app, assistant_app):
        for route in application.routes:
            if not isinstance(route, APIRoute):
                continue
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                rows.append((method, route.path, application))
    return rows


def _deps(dependant, found: set[str]) -> set[str]:
    for child in dependant.dependencies:
        found.add(getattr(child.call, "__name__", ""))
        _deps(child, found)
    return found


def _fill(path: str, ids: dict[str, str]) -> str:
    for key, value in ids.items():
        path = path.replace("{" + key + "}", value)
    return path


def _call(application, method: str, path: str, headers: dict | None = None, body: dict | None = None):
    with TestClient(application) as client:
        return client.request(method, path, headers=headers or {}, json=body if method in {"POST", "PATCH", "PUT"} else None)


def test_every_private_route_needs_login(migrated):
    seen = set()
    for method, path, application in _routes():
        route = next(r for r in application.routes if isinstance(r, APIRoute) and r.path == path and method in r.methods)
        guarded = bool(_deps(route.dependant, set()) & AUTH_DEPS)
        seen.add((method, path))
        if (method, path) in PUBLIC:
            continue
        assert guarded, f"{method} {path}: маршрут без проверки входа"
        response = _call(application, method, _fill(path, {"id": str(uuid.uuid4()), "team_id": str(uuid.uuid4()), "user_id": str(uuid.uuid4()), "occurrence_id": str(uuid.uuid4()), "budget_id": str(uuid.uuid4()), "action_id": str(uuid.uuid4())}), body={})
        assert response.status_code == 401, f"{method} {path}: {response.status_code}"
    assert PUBLIC <= seen


def _login(client, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def world(client, db_session):
    """Два отдела: в «Бухгалтерии» участник и админ, в «Складе» свой админ. Данные есть только в «Бухгалтерии»."""
    owner_id = bootstrap_owner(team="Бухгалтерия").id
    db = db_session
    home = db.scalar(select(Team).where(Team.name == "Бухгалтерия"))
    other = create_team(db, db.get(User, owner_id), "Склад")
    db.commit()
    member = add_person(db, email="member@invoice.local", name="Участник", team=home)
    admin = add_person(db, email="admin-a@invoice.local", name="Админ А", role="admin", team=home)
    add_person(db, email="admin-b@invoice.local", name="Админ Б", role="admin", team=other)
    db.commit()
    owner = _login(client, "admin@invoice.local", "change-me") | {"X-Team-Id": str(home.id)}
    template = client.post(
        "/api/v1/recurring-payments",
        headers=owner,
        json={"title": "Секретная аренда", "amount": "10.00", "currency": "RUB", "next_payment_date": "2026-11-04", "periodicity": "monthly"},
    )
    assert template.status_code == 201, template.text
    budget = client.post(
        "/api/v1/budgets",
        headers=owner,
        json={"period_type": "month", "period_key": "2026-11", "currency": "RUB", "amount": "100"},
    )
    assert budget.status_code in {200, 201}, budget.text
    occurrence = db.scalar(select(PaymentOccurrence).where(PaymentOccurrence.team_id == home.id))
    ids = {
        "home": str(home.id),
        "other": str(other.id),
        "template": template.json()["id"],
        "budget": budget.json()["id"],
        "occurrence": str(occurrence.id),
        "member": str(member.id),
        "admin": str(admin.id),
    }
    sessions = {
        "member": _login(client, "member@invoice.local", PASSWORD) | {"X-Team-Id": ids["home"]},
        "admin": _login(client, "admin-a@invoice.local", PASSWORD) | {"X-Team-Id": ids["home"]},
        "stranger": _login(client, "admin-b@invoice.local", PASSWORD) | {"X-Team-Id": ids["other"]},
    }
    return ids, sessions


def _request(client, method: str, path: str, headers: dict, body: dict | None = None):
    target = assistant_app if path.startswith("/api/v1/assistant") else None
    if target is not None:
        return _call(target, method, path, headers, body or {})
    if body == "FILE":
        return client.request(method, path, headers=headers, files={"file": ("check.pdf", b"%PDF-1.4 test", "application/pdf")})
    return client.request(method, path, headers=headers, json=body)


# Только админ отдела или владелец. Тело валидное, чтобы ответ решала проверка роли, а не схема.
MANAGER_ONLY = [
    ("POST", "/api/v1/recurring-payments", {"title": "Х", "amount": "1.00", "currency": "RUB", "next_payment_date": "2026-11-04", "periodicity": "monthly"}),
    ("PATCH", "/api/v1/recurring-payments/{template}", {"amount": "1.00"}),
    ("DELETE", "/api/v1/recurring-payments/{template}", None),
    ("POST", "/api/v1/budgets", {"period_type": "month", "period_key": "2026-12", "currency": "RUB", "amount": "1"}),
    ("PATCH", "/api/v1/budgets/{budget}", {"amount": "1"}),
    ("DELETE", "/api/v1/budgets/{budget}", None),
    ("GET", "/api/v1/audit-logs", None),
    ("GET", "/api/v1/telegram/status", None),
    ("POST", "/api/v1/telegram/team-chat/link", None),
    ("DELETE", "/api/v1/telegram/team-chat", None),
    ("POST", "/api/v1/telegram/team-chat/test", None),
    ("PUT", "/api/v1/notifications/team/webhook", {"url": "https://example.com/hook"}),
    ("POST", "/api/v1/notifications/team/webhook/test", None),
    ("GET", "/api/v1/users", None),
    ("POST", "/api/v1/users", {"email": "new@invoice.local", "full_name": "Новый"}),
    ("GET", "/api/v1/users/{admin}", None),
    ("PATCH", "/api/v1/users/{admin}", {"full_name": "Взлом"}),
    ("DELETE", "/api/v1/users/{admin}", None),
    ("GET", "/api/v1/users/{admin}/invite", None),
    ("POST", "/api/v1/users/{admin}/invite", None),
    ("GET", "/api/v1/users/{admin}/telegram-link", None),
    ("POST", "/api/v1/users/{admin}/telegram-link", None),
    ("DELETE", "/api/v1/users/{admin}/telegram", None),
    ("PATCH", "/api/v1/teams/{home}/members/{admin}", {"role": "member"}),
    ("DELETE", "/api/v1/teams/{home}/members/{admin}", None),
]
# Только владелец организации: админ отдела сюда тоже не проходит.
OWNER_ONLY = [
    ("GET", "/api/v1/organization", None),
    ("PATCH", "/api/v1/organization", {"remind_7_days": False}),
    ("POST", "/api/v1/teams", {"name": "Новый отдел"}),
    ("PATCH", "/api/v1/teams/{home}", {"name": "Переименован"}),
    ("DELETE", "/api/v1/teams/{home}", {"name": "Бухгалтерия"}),
    ("PATCH", "/api/v1/teams/{home}/members/{member}", {"role": "admin"}),
]
# Чужие объекты при своём отделе в заголовке: не найдено или запрещено, но не данные.
FOREIGN_IDS = [
    ("GET", "/api/v1/recurring-payments/{template}", None),
    ("PATCH", "/api/v1/recurring-payments/{template}", {"amount": "1.00"}),
    ("DELETE", "/api/v1/recurring-payments/{template}", None),
    ("GET", "/api/v1/payment-occurrences/{occurrence}", None),
    ("PATCH", "/api/v1/payment-occurrences/{occurrence}", {"amount": "1.00"}),
    ("POST", "/api/v1/payment-occurrences/{occurrence}/confirm", {}),
    ("POST", "/api/v1/payment-occurrences/{occurrence}/revoke", None),
    ("GET", "/api/v1/payment-occurrences/{occurrence}/receipt", None),
    ("POST", "/api/v1/payment-occurrences/{occurrence}/receipt", "FILE"),
    ("DELETE", "/api/v1/payment-occurrences/{occurrence}/receipt", None),
    ("PATCH", "/api/v1/budgets/{budget}", {"amount": "1"}),
    ("DELETE", "/api/v1/budgets/{budget}", None),
    ("GET", "/api/v1/teams/{home}/members", None),
    ("PATCH", "/api/v1/teams/{home}/members/{member}", {"role": "admin"}),
    ("DELETE", "/api/v1/teams/{home}/members/{member}", None),
    ("POST", "/api/v1/teams/{home}/leave", None),
    ("GET", "/api/v1/users/{member}", None),
    ("PATCH", "/api/v1/users/{member}", {"full_name": "Взлом"}),
    ("DELETE", "/api/v1/users/{member}", None),
    ("GET", "/api/v1/users/{member}/invite", None),
    ("POST", "/api/v1/users/{member}/telegram-link", None),
    ("DELETE", "/api/v1/users/{member}/telegram", None),
]


def _case_id(case: tuple) -> str:
    return f"{case[0]} {case[1]}"


@pytest.mark.parametrize("case", MANAGER_ONLY + OWNER_ONLY, ids=_case_id)
def test_member_is_refused(client, world, case):
    ids, sessions = world
    method, path, body = case
    response = _request(client, method, _fill(path, ids), sessions["member"], body)
    assert response.status_code == 403, f"{method} {path}: {response.status_code} {response.text[:200]}"


@pytest.mark.parametrize("case", OWNER_ONLY, ids=_case_id)
def test_department_admin_is_not_owner(client, world, case):
    ids, sessions = world
    method, path, body = case
    response = _request(client, method, _fill(path, ids), sessions["admin"], body)
    assert response.status_code == 403, f"{method} {path}: {response.status_code} {response.text[:200]}"


@pytest.mark.parametrize("case", FOREIGN_IDS, ids=_case_id)
def test_other_department_admin_gets_nothing_by_id(client, world, case):
    ids, sessions = world
    method, path, body = case
    response = _request(client, method, _fill(path, ids), sessions["stranger"], body)
    assert response.status_code in {403, 404}, f"{method} {path}: {response.status_code} {response.text[:200]}"


def _team_routes() -> list[tuple[str, str]]:
    rows = []
    for method, path, application in _routes():
        route = next(r for r in application.routes if isinstance(r, APIRoute) and r.path == path and method in r.methods)
        if "get_team_context" in _deps(route.dependant, set()):
            rows.append((method, path))
    return rows


@pytest.mark.parametrize("case", _team_routes(), ids=lambda case: f"{case[0]} {case[1]}")
def test_other_department_header_is_refused(client, world, case):
    """Любой маршрут отдела с чужим X-Team-Id: 403 до всякой логики."""
    ids, sessions = world
    method, path = case
    headers = sessions["stranger"] | {"X-Team-Id": ids["home"]}
    filled = _fill(path, {"id": ids["template"], "occurrence_id": ids["occurrence"], "budget_id": ids["budget"], "action_id": str(uuid.uuid4())})
    response = _request(client, method, filled, headers, {})
    assert response.status_code == 403, f"{method} {path}: {response.status_code} {response.text[:200]}"


def test_other_department_lists_stay_empty(client, world):
    ids, sessions = world
    for path in (
        "/api/v1/recurring-payments",
        "/api/v1/payment-occurrences/inbox",
        "/api/v1/payment-occurrences?view=all",
        "/api/v1/payment-occurrences/export.csv?view=all",
        "/api/v1/payments/summary",
        "/api/v1/payments/calendar?month=2026-11",
        "/api/v1/budgets",
        "/api/v1/audit-logs",
        "/api/v1/users",
        "/api/v1/stats",
    ):
        response = client.get(path, headers=sessions["stranger"])
        assert response.status_code in {200, 422}, f"{path}: {response.status_code}"
        assert "Секретная аренда" not in response.text, path
        assert "member@invoice.local" not in response.text, path
    forced = client.get(f"/api/v1/stats?team_id={ids['home']}", headers=sessions["stranger"])
    assert forced.status_code in {403, 404}
