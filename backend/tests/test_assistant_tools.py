"""Инструменты ассистента: роль и отдел те же, что у REST, ответы из базы, действия только после подтверждения."""

from sqlalchemy import select

from app.assistant import tools
from app.assistant.gigachat import Completion, ToolCall
from app.core.config import get_settings
from app.models import AssistantAction, Membership, PaymentOccurrence, RecurringPayment, Team, User
from app.seed import seed
from app.services.access import resolve_team
from app.services.teams import create_team
from tests.test_assistant_api import _assistant_call, _headers, _say

ADMIN_TOOLS = {"list_people", "propose_create_payment", "propose_update_payment", "propose_archive_payment"}


def _ctx(db, email: str):
    user = db.scalar(select(User).where(User.email == email))
    return resolve_team(db, user, None)


class _Model:
    """GigaChat-заглушка: запоминает выданные инструменты и просит один вызов."""

    def __init__(self, call: ToolCall | None) -> None:
        self.call = call
        self.functions: list[dict] = []

    def complete(self, messages, functions=None):
        self.functions = functions or []
        return Completion(content="", tool_call=self.call, model="test")


def _with_model(monkeypatch, call: ToolCall | None) -> _Model:
    monkeypatch.setenv("GIGACHAT_AUTH_KEY", "test-key")
    get_settings.cache_clear()
    model = _Model(call)
    monkeypatch.setattr("app.assistant.chat.GigaChatClient", lambda *args, **kwargs: model)
    return model


def test_tools_follow_the_role(db_session):
    seed(demo=True)
    member = {item["name"] for item in tools.functions_for(_ctx(db_session, "ivan@invoice.local"))}
    admin = {item["name"] for item in tools.functions_for(_ctx(db_session, "maria@invoice.local"))}
    assert not member & ADMIN_TOOLS
    assert {"list_overdue", "budget_status", "monthly_stats", "product_help", "propose_mark_paid", "propose_mark_unpaid"} <= member
    assert ADMIN_TOOLS <= admin
    text, action = tools.run(db_session, _ctx(db_session, "ivan@invoice.local"), "list_people", {})
    assert text == tools.ADMIN_ONLY and action is None


def test_member_cannot_reach_admin_tools_through_the_model(client, db_session, monkeypatch):
    seed(demo=True)
    headers = _headers(client, "ivan@invoice.local", "change-me-user")
    before = db_session.scalar(select(RecurringPayment.id).limit(1))
    model = _with_model(monkeypatch, ToolCall("propose_create_payment", {"title": "Взлом", "amount": "1", "currency": "RUB"}))
    answer = _say(client, headers, "заведи что-нибудь")
    assert not {item["name"] for item in model.functions} & ADMIN_TOOLS
    assert answer["action"] is None
    assert "админ" in answer["content"]
    assert db_session.scalar(select(AssistantAction.id).limit(1)) is None
    assert before is not None
    get_settings.cache_clear()


def test_model_reads_only_departments_of_the_user(client, db_session, monkeypatch):
    seed(demo=True)
    owner = db_session.scalar(select(User).where(User.is_owner.is_(True)))
    hidden = create_team(db_session, owner, "Закрытый")
    db_session.commit()
    owner_headers = _headers(client, "admin@invoice.local", "change-me") | {"X-Team-Id": str(hidden.id)}
    created = client.post(
        "/api/v1/recurring-payments",
        headers=owner_headers,
        json={"title": "Тайный сервер", "amount": "777.00", "currency": "USD", "next_payment_date": "2026-11-04", "periodicity": "monthly"},
    )
    assert created.status_code == 201, created.text
    headers = _headers(client, "ivan@invoice.local", "change-me-user")
    _with_model(monkeypatch, ToolCall("payment_details", {"query": "Тайный сервер"}))
    details = _say(client, headers, "что с тайным сервером")
    assert "777" not in details["content"]
    _with_model(monkeypatch, ToolCall("departments_stats", {}))
    stats = _say(client, headers, "статистика по отделам")
    assert "Закрытый" not in stats["content"] and "777" not in stats["content"]
    forced = _assistant_call(
        client,
        "post",
        "/api/v1/assistant/messages",
        params={"stream": "false"},
        headers=headers | {"X-Team-Id": str(hidden.id)},
        json={"text": "что просрочено"},
    )
    assert forced.status_code == 403
    get_settings.cache_clear()


def test_mark_unpaid_needs_confirmation(client, db_session):
    seed(demo=True)
    headers = _headers(client, "ivan@invoice.local", "change-me-user")
    staged = _say(client, headers, "верни аренду в неоплаченные")
    action = staged["action"]
    assert action["kind"] == "mark_unpaid" and action["status"] == "pending"
    occurrence_id = db_session.get(AssistantAction, action["id"]).payload["fields"]["occurrence_id"]
    assert db_session.get(PaymentOccurrence, occurrence_id).paid_at is not None
    done = _assistant_call(client, "post", f"/api/v1/assistant/actions/{action['id']}/confirm", headers=headers)
    assert done.status_code == 200, done.text
    assert done.json()["action"]["status"] == "confirmed"
    assert "снова в инбоксе" in done.json()["message"]["content"]
    db_session.expire_all()
    assert db_session.get(PaymentOccurrence, occurrence_id).paid_at is None


def test_reads_are_structured(client, db_session):
    seed(demo=True)
    admin = _headers(client, "admin@invoice.local", "change-me")
    assert _say(client, admin, "Что вы умеете?")["content"].startswith("### Чем могу помочь")
    budget = _say(client, admin, "бюджет на октябрь")["content"]
    assert budget.startswith("### Бюджет: октябрь 2026") and "| Валюта | План |" in budget
    stats = _say(client, admin, "статистика за 3 месяца")["content"]
    assert "| Месяц |" in stats and "Сентябрь 2026" in stats
    people = _say(client, admin, "кто в отделе")["content"]
    assert people.startswith("### Люди отдела") and "Иван Петров" in people
    how = _say(client, admin, "как выгрузить CSV?")["content"]
    assert how.startswith("### Выгрузка CSV") and "«Выгрузить CSV»" in how
    member = _headers(client, "ivan@invoice.local", "change-me-user")
    assert _say(client, member, "кто в отделе")["content"] == tools.ADMIN_ONLY
    own = {row.team.name for row in db_session.scalars(select(Membership).join(Team)).all() if row.user.email == "ivan@invoice.local"}
    table = _say(client, member, "статистика по отделам")["content"]
    assert all(name in table for name in own)
