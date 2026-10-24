"""Кип: цикл агента на записанных ответах модели (FakeGigaChat), выборки и подсказки."""

from decimal import Decimal

from sqlalchemy import select

from app.assistant import suggestions
from app.assistant.agent import compact
from app.assistant.query import query_operations
from app.core.config import get_settings
from app.models import Team, User
from app.seed import seed
from app.services.access import resolve_team
from app.services.teams import create_team
from tests.kip_fake import FakeGigaChat, GigaChatError, ToolCall, use
from tests.test_assistant_api import _headers, _say

ARTUR = (
    "Привет подскажи какие у нас операции были за прошлый месяц или сколько было просрочек и Каких операций "
    "сколько штук было и на какую сумму а еще Дай мне средний чек по всем операциям за прошлый месяц"
)


def _ctx(db, email: str):
    user = db.scalar(select(User).where(User.email == email))
    return resolve_team(db, user, None)


def _rates(monkeypatch):
    from datetime import date

    from app.services import rates

    monkeypatch.setattr(rates, "current", lambda: rates.Rates(on=date(2026, 10, 23), values={"USD": Decimal("80"), "EUR": Decimal("90")}))


# ---------- query_operations ----------


def test_query_aggregates_per_currency(db_session):
    seed(demo=True)
    ctx = _ctx(db_session, "admin@invoice.local")
    overdue = query_operations(db_session, ctx, {"status": ["overdue"], "include_rows": True})
    assert overdue["count"] == 4
    assert overdue["totals"] == [{"currency": "RUB", "count": 4, "sum": "194000.00"}]
    assert {row["title"] for row in overdue["rows"]} == {"Аренда офиса", "Электричество"}
    september = query_operations(
        db_session, ctx, {"period": "last_month", "group_by": "payment", "metrics": ["count", "sum", "avg", "min", "max"]}
    )
    assert september["applied"]["from"] == "2026-09-01" and september["applied"]["to"] == "2026-09-30"
    rub = next(row for row in september["totals"] if row["currency"] == "RUB")
    assert rub == {"currency": "RUB", "count": 2, "sum": "97000.00", "avg": "48500.00", "min": "12000.00", "max": "85000.00"}
    assert {group["key"] for group in september["groups"]} == {"Аренда офиса", "Электричество", "Подписка"}
    paid = query_operations(db_session, ctx, {"status": ["paid"], "period": "last_month"})
    assert paid["applied"]["date_field"] == "paid"


def test_query_converts_to_rub(db_session, monkeypatch):
    seed(demo=True)
    _rates(monkeypatch)
    ctx = _ctx(db_session, "admin@invoice.local")
    data = query_operations(db_session, ctx, {"period": "last_month", "convert_to_rub": True})
    # 85 000 + 12 000 ₽ и подписка 15 € по 90 ₽.
    assert data["rub"]["total_rub"] == "98350.00"
    assert data["rub"]["rates"]["EUR"] == "90.00"


def test_query_scopes_departments(db_session):
    seed(demo=True)
    owner = db_session.scalar(select(User).where(User.is_owner.is_(True)))
    create_team(db_session, owner, "Закрытый")
    db_session.commit()
    member = _ctx(db_session, "ivan@invoice.local")
    data = query_operations(db_session, member, {"department": ["Закрытый", "Инфраструктура", "Луна"]})
    assert data["denied"] == ["Закрытый"]
    assert data["unknown_departments"] == ["Луна"]
    assert data["applied"]["departments"] == ["Инфраструктура"]
    everything = query_operations(db_session, member, {"department": ["all"], "group_by": "department"})
    assert "Закрытый" not in {group["key"] for group in everything["groups"]}
    owner_ctx = _ctx(db_session, "admin@invoice.local")
    assert "denied" not in query_operations(db_session, owner_ctx, {"department": ["Закрытый"]})


def test_query_batch_answers_each_part(db_session):
    seed(demo=True)
    ctx = _ctx(db_session, "admin@invoice.local")
    data = query_operations(
        db_session,
        ctx,
        {"queries": [{"label": "a", "status": ["overdue"]}, {"label": "b", "period": "tomorrow", "status": ["unpaid"]}]},
    )
    assert [item["label"] for item in data["results"]] == ["a", "b"]
    assert data["results"][0]["count"] == 4


def test_compact_keeps_results_small():
    rows = [{"title": f"Платёж {index}", "amount": "1000.00"} for index in range(200)]
    text = compact({"count": 200, "rows": rows})
    assert len(text) <= 2000
    assert '"rows_cut"' in text


# ---------- цикл агента ----------


def test_artur_four_part_question(client, db_session, monkeypatch):
    seed(demo=True)
    headers = _headers(client, "admin@invoice.local", "change-me")
    batch = {
        "queries": [
            {"label": "операции за прошлый месяц", "period": "last_month", "include_rows": True},
            {"label": "просрочки за прошлый месяц", "period": "last_month", "status": ["overdue"]},
            {"label": "по видам", "period": "last_month", "group_by": "payment", "metrics": ["count", "sum"]},
            {"label": "средний чек", "period": "last_month", "metrics": ["count", "avg"]},
        ]
    }
    final = "### Сентябрь 2026\n\n- Операций: 3\n- Просрочено: 2 на 97 000 ₽\n- Средний чек: 48 500 ₽ и 15 €\n\n>>> А в рублях? | Сравни с августом | Кто ответственный?"
    fake = use(monkeypatch, FakeGigaChat(ToolCall("query_operations", batch), final))
    answer = _say(client, headers, ARTUR)
    results = fake.function_results()[0]["results"]
    assert [item["count"] for item in results] == [3, 2, 3, 3]
    assert results[1]["totals"] == [{"currency": "RUB", "count": 2, "sum": "97000.00"}]
    avg = {row["currency"]: row["avg"] for row in results[3]["totals"]}
    assert avg == {"RUB": "48500.00", "EUR": "15.00"}
    assert "Средний чек" in answer["content"] and ">>>" not in answer["content"]
    assert answer["suggestions"] == ["А в рублях?", "Сравни с августом", "Кто ответственный?"]
    system = fake.system()
    assert "2026-10-23" in system and "пятница" in system and "КАЖДЫЙ" in system
    get_settings.cache_clear()


def test_member_sees_denial_for_foreign_department(client, db_session, monkeypatch):
    seed(demo=True)
    owner = db_session.scalar(select(User).where(User.is_owner.is_(True)))
    hidden = create_team(db_session, owner, "Маркетинг")
    db_session.commit()
    assert hidden is not None
    headers = _headers(client, "ivan@invoice.local", "change-me-user")
    fake = use(
        monkeypatch,
        FakeGigaChat(ToolCall("query_operations", {"department": ["Маркетинг"], "status": ["overdue"]}), "К отделу «Маркетинг» у вас нет доступа."),
    )
    answer = _say(client, headers, "Сколько просрочено в Маркетинге?")
    data = fake.function_results()[0]
    assert data["denied"] == ["Маркетинг"] and data["count"] == 0
    assert "нет доступа" in answer["content"]
    names = {item["name"] for item in fake.calls[0]["functions"]}
    assert not names & {"list_people", "get_audit", "propose_create_payment"}
    assert all("менял" not in item for item in answer["suggestions"])
    get_settings.cache_clear()


def test_rub_conversion_follow_up_keeps_context(client, db_session, monkeypatch):
    seed(demo=True)
    _rates(monkeypatch)
    headers = _headers(client, "admin@invoice.local", "change-me")
    use(monkeypatch, FakeGigaChat(ToolCall("query_operations", {"period": "last_month"}), "### Сентябрь\n\n| Валюта | Сумма |\n|---|---|\n| RUB | 97 000 ₽ |"))
    _say(client, headers, "Сколько за прошлый месяц?")
    fake = use(monkeypatch, FakeGigaChat(ToolCall("query_operations", {"period": "last_month", "convert_to_rub": True}), "Всего 98 350 ₽."))
    answer = _say(client, headers, "а в рублях?")
    history = fake.calls[0]["messages"]
    assert any(item["role"] == "user" and "прошлый месяц" in item["content"] for item in history)
    assert all("| RUB |" not in item["content"] for item in history if item["role"] == "assistant")
    assert fake.function_results()[0]["rub"]["total_rub"] == "98350.00"
    assert answer["content"] == "Всего 98 350 ₽."
    assert len(answer["suggestions"]) == 3
    get_settings.cache_clear()


def test_loop_stops_after_step_limit(client, db_session, monkeypatch):
    seed(demo=True)
    headers = _headers(client, "admin@invoice.local", "change-me")
    loops = [ToolCall("query_operations", {"status": ["overdue"]}) for _ in range(9)]
    fake = use(monkeypatch, FakeGigaChat(*loops))
    answer = _say(client, headers, "считай бесконечно")
    tool_calls = [call for call in fake.calls if call["functions"]]
    assert len(tool_calls) == 5
    assert fake.calls[-1]["functions"] is None
    assert answer["content"]
    get_settings.cache_clear()


def test_model_failure_falls_back(client, db_session, monkeypatch):
    seed(demo=True)
    headers = _headers(client, "admin@invoice.local", "change-me")
    use(monkeypatch, FakeGigaChat(GigaChatError("GigaChat сейчас недоступен. Повтори через минуту.")))
    overdue = _say(client, headers, "Что просрочено?")
    assert overdue["content"].startswith("### Просрочено") and "Аренда офиса" in overdue["content"]
    assert len(overdue["suggestions"]) == 3
    use(monkeypatch, FakeGigaChat(GigaChatError("GigaChat сейчас недоступен. Повтори через минуту.")))
    other = _say(client, headers, "Напиши отчёт для директора")
    assert "недоступен" in other["content"]
    use(monkeypatch, FakeGigaChat(ToolCall("query_operations", {"status": ["overdue"], "label": "просрочено"}), GigaChatError("таймаут")))
    partial = _say(client, headers, "сколько просрочено и почему")
    assert "194" in partial["content"]
    get_settings.cache_clear()


def test_write_tool_returns_card_without_saving(client, db_session, monkeypatch):
    seed(demo=True)
    infra = db_session.scalar(select(Team).where(Team.name == "Инфраструктура"))
    headers = _headers(client, "ivan@invoice.local", "change-me-user") | {"X-Team-Id": str(infra.id)}
    use(monkeypatch, FakeGigaChat(ToolCall("propose_mark_paid", {"query": "сервер"})))
    answer = _say(client, headers, "запиши, что я заплатил за сервер")
    assert answer["action"]["kind"] == "mark_paid" and answer["action"]["status"] == "pending"
    get_settings.cache_clear()


# ---------- подсказки ----------


def test_suggestions_parse_and_fill():
    body, raw = suggestions.split("### Итог\n\n- 3 операции\n>>> А в рублях? | Сравни с прошлым месяцем | Кто ответственный за всё это в нашем отделе вообще?")
    assert body == "### Итог\n\n- 3 операции"
    picked = suggestions.finish("member", raw, ["query_operations"])
    assert picked[:2] == ["А в рублях?", "Сравни с прошлым месяцем"]
    assert len(picked) == 3 and all(len(item) <= 40 for item in picked)
    assert suggestions.split("без подсказок") == ("без подсказок", [])
    member = suggestions.finish("member", ["Кто что менял сегодня?", "Покажи логи"], ["get_audit"])
    assert len(member) == 3 and not any("менял" in item or "логи" in item.lower() for item in member)
    assert len(suggestions.defaults("owner")) == 3


def test_start_suggestions_endpoint(client, db_session):
    seed(demo=True)
    from tests.test_assistant_api import _assistant_call

    member = _assistant_call(client, "get", "/api/v1/assistant/suggestions", headers=_headers(client, "ivan@invoice.local", "change-me-user"))
    assert member.status_code == 200 and len(member.json()["suggestions"]) == 3
    assert not any("менял" in item for item in member.json()["suggestions"])


def test_prompt_uses_organization_timezone(client, db_session, monkeypatch):
    from app.models.organization import OrganizationSettings
    from app.services.org_settings import SINGLETON

    seed(demo=True)
    row = db_session.get(OrganizationSettings, SINGLETON)
    if row is None:
        row = OrganizationSettings(id=SINGLETON)
        db_session.add(row)
    row.timezone = "Asia/Vladivostok"
    db_session.commit()
    headers = _headers(client, "admin@invoice.local", "change-me")
    fake = use(monkeypatch, FakeGigaChat("Сейчас вечер."))
    _say(client, headers, "Который час?")
    system = fake.system()
    assert "Asia/Vladivostok" in system and "19:00" in system
