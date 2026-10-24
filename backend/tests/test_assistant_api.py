from sqlalchemy import func, select

from app.core.config import get_settings
from app.models import RecurringPayment, Team
from app.seed import seed


def _login(client, email: str, password: str) -> dict:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _headers(client, email: str, password: str) -> dict[str, str]:
    return _auth(_login(client, email, password)["access_token"])


def _count(db) -> int:
    db.expire_all()
    return int(db.scalar(select(func.count()).select_from(RecurringPayment)) or 0)


def _assistant_call(client, method: str, url: str, **kwargs):
    if url.startswith("/api/v1/assistant"):
        from fastapi.testclient import TestClient

        from app.assistant_main import app as assistant_app

        with TestClient(assistant_app) as assistant:
            return getattr(assistant, method)(url, **kwargs)
    return getattr(client, method)(url, **kwargs)


def _say(client, headers, text: str) -> dict:
    response = _assistant_call(
        client,
        "post",
        "/api/v1/assistant/messages",
        params={"stream": "false"},
        headers=headers,
        json={"text": text},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_reads_come_from_the_database(client, db_session, monkeypatch):
    from tests.kip_fake import FakeGigaChat, ToolCall, use

    seed(demo=True)
    headers = _headers(client, "admin@invoice.local", "change-me")
    fake = use(monkeypatch, FakeGigaChat(ToolCall("query_operations", {"period": "this_week", "status": ["unpaid"], "include_rows": True}), "### На этой неделе\n\n- Подписка"))
    week = _say(client, headers, "Что горит на этой неделе?")
    rows = fake.function_results()[0]["rows"]
    assert {row["title"] for row in rows} == {"Электричество"}
    assert week["content"].startswith("### На этой неделе")
    assert week["action"] is None

    infra = db_session.scalar(select(Team).where(Team.name == "Инфраструктура"))
    assert infra is not None
    fake = use(monkeypatch, FakeGigaChat(ToolCall("get_payment", {"query": "сервер"}), "Мария Соколова"))
    _say(client, {**headers, "X-Team-Id": str(infra.id)}, "Кто ответственный за сервер?")
    card = fake.function_results()[0]
    assert card["responsible"] == "Мария Соколова" and card["department"] == "Инфраструктура"

    use(monkeypatch, FakeGigaChat("### Просрочено"))
    streamed = _assistant_call(
        client,
        "post",
        "/api/v1/assistant/messages",
        params={"stream": "true"},
        headers=headers,
        json={"text": "Что просрочено?"},
    )
    assert streamed.status_code == 200, streamed.text
    assert "event: token" in streamed.text
    assert "event: done" in streamed.text
    history = _assistant_call(client, "get", "/api/v1/assistant/messages", headers=headers)
    assert history.status_code == 200
    assert len(history.json()) >= 4
    get_settings.cache_clear()


def test_create_waits_for_confirm_and_checks_role(client, db_session):
    seed(demo=True)
    admin = _headers(client, "admin@invoice.local", "change-me")
    ivan = _headers(client, "ivan@invoice.local", "change-me-user")
    before = _count(db_session)

    denied = _say(client, ivan, "Создай платёж «Чужой» 10 рублей каждое 4 число, ответственный Иван")
    assert denied["action"] is None
    assert "админ" in denied["content"].lower()
    assert _count(db_session) == before

    proposed = _say(client, admin, "Создай платёж «Почта» 1200 рублей каждое 20 число, ответственный Иван")
    action = proposed["action"]
    assert action["status"] == "pending"
    assert action["kind"] == "create_payment"
    assert "Почта" in action["summary"]
    assert "Первый срок: 20 ноября" in action["summary"]
    assert "Иван Петров" in action["summary"]
    assert _count(db_session) == before

    revised = _say(client, admin, "сумму на 1300 рублей")
    assert revised["action"]["id"] == action["id"]
    assert "Сумма: 1\u202f300\u00a0₽" in revised["action"]["summary"]
    assert _count(db_session) == before

    stolen = _assistant_call(client, "post", f"/api/v1/assistant/actions/{action['id']}/confirm", headers=ivan)
    assert stolen.status_code == 404
    assert _count(db_session) == before

    confirmed = _assistant_call(client, "post", f"/api/v1/assistant/actions/{action['id']}/confirm", headers=admin)
    assert confirmed.status_code == 200, confirmed.text
    body = confirmed.json()
    assert body["action"]["status"] == "confirmed"
    assert "Почта" in body["message"]["content"]
    assert _count(db_session) == before + 1

    again = _assistant_call(client, "post", f"/api/v1/assistant/actions/{action['id']}/confirm", headers=admin)
    assert again.status_code == 409
    assert _count(db_session) == before + 1

    row = db_session.scalar(select(RecurringPayment).where(RecurringPayment.title == "Почта"))
    assert row is not None
    assert f"{row.amount:.2f}" == "1300.00"
    assert row.currency == "RUB"


def test_mark_paid_update_and_archive_need_confirmation(client, db_session):
    seed(demo=True)
    admin = _headers(client, "admin@invoice.local", "change-me")
    ivan = _headers(client, "ivan@invoice.local", "change-me-user")

    infra = db_session.scalar(select(Team).where(Team.name == "Инфраструктура"))
    studio = db_session.scalar(select(Team).where(Team.name == "Бухгалтерия"))
    assert infra is not None and studio is not None
    paid = _say(client, {**ivan, "X-Team-Id": str(infra.id)}, "Отметь сервер оплаченным")
    assert paid["action"]["kind"] == "mark_paid"
    assert "Сервер" in paid["action"]["summary"]
    server = db_session.scalar(select(RecurringPayment).where(RecurringPayment.title == "Сервер"))
    assert server is not None
    done = _assistant_call(client, "post", f"/api/v1/assistant/actions/{paid['action']['id']}/confirm", headers=ivan)
    assert done.status_code == 200, done.text
    assert done.json()["action"]["status"] == "confirmed"
    assert "оплачен" in done.json()["message"]["content"]

    update = _say(client, {**admin, "X-Team-Id": str(infra.id)}, "Измени сумму сервера на 45 долларов")
    assert "Сумма: 40\u00a0$ → **45\u00a0$**" in update["action"]["summary"]
    db_session.expire_all()
    assert f"{server.amount:.2f}" == "40.00"
    changed = _assistant_call(client, "post", f"/api/v1/assistant/actions/{update['action']['id']}/confirm", headers=admin)
    assert changed.status_code == 200, changed.text
    db_session.expire_all()
    assert f"{server.amount:.2f}" == "45.00"

    person = _say(client, {**admin, "X-Team-Id": str(studio.id)}, "Смени ответственного за подписку на Марию")
    assert "Мария Соколова" in person["action"]["summary"]
    sub = db_session.scalar(select(RecurringPayment).where(RecurringPayment.title == "Подписка"))
    assert sub is not None and sub.responsible.full_name == "Иван Петров"
    _assistant_call(client, "post", f"/api/v1/assistant/actions/{person['action']['id']}/confirm", headers=admin)
    db_session.expire_all()
    assert sub.responsible.full_name == "Мария Соколова"

    archived = _say(client, {**admin, "X-Team-Id": str(studio.id)}, "Архивируй платёж подписка")
    assert archived["action"]["kind"] == "archive_payment"
    assert sub.is_archived is False
    _assistant_call(client, "post", f"/api/v1/assistant/actions/{archived['action']['id']}/confirm", headers=admin)
    db_session.expire_all()
    assert sub.is_archived is True


def test_member_cannot_confirm_a_forged_template_change(client, db_session):
    seed(demo=True)
    from app.models import AssistantAction, User

    ivan = db_session.scalar(select(User).where(User.email == "ivan@invoice.local"))
    assert ivan is not None
    action = AssistantAction(
        user_id=ivan.id,
        team_id=ivan.active_team_id,
        kind="create_payment",
        status="pending",
        payload={
            "fields": {
                "title": "Хак",
                "amount": "10.00",
                "currency": "RUB",
                "day_of_month": 4,
                "starts_on": "2026-10-23",
                "responsible_user_id": str(ivan.id),
                "responsible_name": "Иван Петров",
                "first_due": "2026-11-04",
            }
        },
        summary="Создать платёж: Хак",
    )
    db_session.add(action)
    db_session.commit()
    headers = _headers(client, "ivan@invoice.local", "change-me-user")
    before = _count(db_session)
    response = _assistant_call(client, "post", f"/api/v1/assistant/actions/{action.id}/confirm", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["action"]["status"] == "failed"
    assert "Недостаточно прав" in response.json()["message"]["content"]
    assert _count(db_session) == before


def test_answers_and_history_follow_the_active_team(client, db_session, monkeypatch):
    from tests.kip_fake import FakeGigaChat, ToolCall, use

    seed(demo=True)
    token = _headers(client, "ivan@invoice.local", "change-me-user")
    studio_team = db_session.scalar(select(Team).where(Team.name == "Бухгалтерия"))
    aeza = db_session.scalar(select(Team).where(Team.name == "Инфраструктура"))
    assert studio_team is not None and aeza is not None
    studio_headers = {**token, "X-Team-Id": str(studio_team.id)}
    aeza_headers = {**token, "X-Team-Id": str(aeza.id)}

    open_call = ToolCall("query_operations", {"status": ["unpaid"], "include_rows": True, "limit": 30})
    fake = use(monkeypatch, FakeGigaChat(open_call, "Аренда офиса, Электричество"))
    studio = _say(client, studio_headers, "Покажи открытые платежи")
    titles = {row["title"] for row in fake.function_results()[0]["rows"]}
    assert "Аренда офиса" in titles and "Домен" not in titles
    assert "Аренда офиса" in studio["content"]

    fake = use(monkeypatch, FakeGigaChat(ToolCall("get_payment", {"query": "домен", "department": "Бухгалтерия"}), "Не нашёл."))
    _say(client, studio_headers, "Кто ответственный за домен?")
    assert "error" in fake.function_results()[0]

    fake = use(monkeypatch, FakeGigaChat(open_call, "Домен, Сервер"))
    _say(client, aeza_headers, "Покажи открытые платежи")
    titles = {row["title"] for row in fake.function_results()[0]["rows"]}
    assert "Домен" in titles and "Аренда офиса" not in titles
    get_settings.cache_clear()

    maria = _headers(client, "maria@invoice.local", "change-me-user")
    owned = _say(
        client,
        {**maria, "X-Team-Id": str(aeza.id)},
        "Создай платёж «Хостинг» 10 рублей каждое 4 число, ответственный Иван",
    )
    assert owned["action"]["kind"] == "create_payment"
    assert "Иван Петров" in owned["action"]["summary"]

    studio_history = _assistant_call(client, "get", "/api/v1/assistant/messages", headers=studio_headers)
    aeza_history = _assistant_call(client, "get", "/api/v1/assistant/messages", headers=aeza_headers)
    assert studio_history.status_code == 200
    assert any("Аренда офиса" in item["content"] for item in studio_history.json())
    assert all("Аренда офиса" not in item["content"] for item in aeza_history.json())


def test_confirm_does_not_touch_another_teams_payment(client, db_session):
    seed(demo=True)
    from app.models import AssistantAction, User

    admin = db_session.scalar(select(User).where(User.email == "admin@invoice.local"))
    domain = db_session.scalar(select(RecurringPayment).where(RecurringPayment.title == "Домен"))
    assert admin is not None and admin.active_team_id is not None
    assert domain is not None and domain.team_id != admin.active_team_id
    action = AssistantAction(
        user_id=admin.id,
        team_id=admin.active_team_id,
        kind="update_payment",
        status="pending",
        payload={
            "fields": {
                "payment_id": str(domain.id),
                "title": domain.title,
                "before": {"amount": "990.00", "currency": "RUB", "day_of_month": 1, "title": "Домен", "responsible_name": ""},
                "changes": {"amount": "1.00", "currency": "RUB"},
            }
        },
        summary="Изменить платёж: Домен",
    )
    db_session.add(action)
    db_session.commit()
    headers = _headers(client, "admin@invoice.local", "change-me")
    response = _assistant_call(client, "post", f"/api/v1/assistant/actions/{action.id}/confirm", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["action"]["status"] == "failed"
    db_session.expire_all()
    fresh = db_session.get(RecurringPayment, domain.id)
    assert fresh is not None
    assert f"{fresh.amount:.2f}" == "990.00"


def test_tool_data_reaches_the_model_and_chat_can_be_cleared(client, db_session, monkeypatch):
    from tests.kip_fake import FakeGigaChat, ToolCall, use

    seed(demo=True)
    headers = _headers(client, "admin@invoice.local", "change-me")
    fake = use(monkeypatch, FakeGigaChat(ToolCall("query_operations", {"status": ["overdue"]}), "### Просрочено\n\n- 4 счёта на 194 000 ₽"))
    answer = _say(client, headers, "какая сумма висит")
    assert fake.function_results()[0]["totals"][0]["sum"] == "194000.00"
    assert "194 000" in answer["content"]
    assert "markdown" in fake.system().lower()
    wiped = _assistant_call(client, "delete", "/api/v1/assistant/messages", headers=headers)
    assert wiped.status_code == 204, wiped.text
    history = _assistant_call(client, "get", "/api/v1/assistant/messages", headers=headers)
    assert history.status_code == 200
    assert history.json() == []
    cleared = _say(client, headers, "очисти чат")
    assert "очищен" in cleared["content"] and len(cleared["suggestions"]) == 3
    get_settings.cache_clear()
