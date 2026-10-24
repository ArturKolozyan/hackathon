"""Инструменты ассистента: роль и отдел те же, что у REST, ответы из базы, действия только после подтверждения."""

import json

from sqlalchemy import select

from app.assistant import tools
from app.assistant.gigachat import Completion, ToolCall
from app.core.config import get_settings
from app.models import AssistantAction, PaymentOccurrence, RecurringPayment, User
from app.seed import seed
from app.services.access import resolve_team
from app.services.teams import create_team
from tests.test_assistant_api import _assistant_call, _headers, _say

ADMIN_TOOLS = {"list_people", "get_audit", "propose_create_payment", "propose_update_payment", "propose_archive_payment"}


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
    assert {"query_operations", "get_payment", "get_budget", "product_help", "propose_mark_paid", "propose_mark_unpaid"} <= member
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
    from tests.kip_fake import FakeGigaChat, use

    fake = use(monkeypatch, FakeGigaChat(ToolCall("get_payment", {"query": "Тайный сервер"}), "нет"))
    _say(client, headers, "что с тайным сервером")
    assert "777" not in json.dumps(fake.function_results(), ensure_ascii=False)
    fake = use(monkeypatch, FakeGigaChat(ToolCall("query_operations", {"department": ["all"], "group_by": "department", "include_rows": True}), "ок"))
    _say(client, headers, "статистика по отделам")
    seen = json.dumps(fake.function_results(), ensure_ascii=False)
    assert "Закрытый" not in seen and "777" not in seen
    fake = use(monkeypatch, FakeGigaChat(ToolCall("get_budget", {"department": "Закрытый"}), "нет доступа"))
    _say(client, headers, "бюджет Закрытого")
    assert fake.function_results()[0]["denied"] == ["Закрытый"]
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
    admin_ctx = _ctx(db_session, "admin@invoice.local")
    member_ctx = _ctx(db_session, "ivan@invoice.local")
    admin = _headers(client, "admin@invoice.local", "change-me")
    assert _say(client, admin, "Что вы умеете?")["content"].startswith("### Чем могу помочь")
    budget, _ = tools.call(tools.Turn(db_session, admin_ctx), "get_budget", {"period": "2026-10"})
    line = budget["departments"][0]["lines"][0]
    assert line["currency"] == "RUB" and line["plan"] == "200000.00" and "left" in line
    people, _ = tools.call(tools.Turn(db_session, admin_ctx), "list_people", {})
    assert "Иван Петров" in {row["name"] for row in people["departments"][0]["people"]}
    how, _ = tools.call(tools.Turn(db_session, member_ctx), "product_help", {"topic": "как выгрузить CSV?"})
    assert how["markdown"].startswith("### История и выгрузка CSV") and "«Выгрузить CSV»" in how["markdown"]
    denied, card = tools.call(tools.Turn(db_session, member_ctx), "list_people", {})
    assert denied == {"denied_role": tools.ADMIN_ONLY} and card is None
    audit, _ = tools.call(tools.Turn(db_session, admin_ctx), "get_audit", {"period": "today"})
    assert "rows" in audit
    payment, _ = tools.call(tools.Turn(db_session, member_ctx), "get_payment", {"query": "аренда"})
    assert payment["title"] == "Аренда офиса" and payment["periods"]
