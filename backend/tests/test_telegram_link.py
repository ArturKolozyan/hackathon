from datetime import timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.models import PaymentOccurrence, TelegramBot, TelegramIntegration, TelegramLinkToken, User
from app.seed import seed
from app.services import time as clock
from app.services.telegram_cards import handle_callback
from app.services.telegram_links import issue_token, request_test, resolve_team_chat_id
from app.services.telegram_updates import handle_update
from tests.test_telegram import CHAT, FakeBot, _admin, _october, _reload, _template


def _message(text: str, *, chat_id: int, chat_type: str, title: str | None = None, sender: int = 42) -> dict:
    chat: dict = {"id": chat_id, "type": chat_type}
    if title:
        chat["title"] = title
    return {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "text": text,
            "chat": chat,
            "from": {"id": sender, "first_name": "Арт", "username": "art"},
        },
    }


def _ready(db, username: str = "rekeeper_bot") -> None:
    db.add(TelegramBot(id=1, bot_username=username))
    db.commit()


def test_group_link_replaces_previous_chat(db_session):
    admin = _admin(db_session)
    bot = FakeBot()
    token = issue_token(db_session, purpose="team", user=admin)
    handle_update(
        db_session,
        bot,
        _message(f"/start@rekeeper_bot {token.token}", chat_id=-100500, chat_type="group", title="404 mercy"),
    )
    # command with bot mention and payload
    assert bot.sent[-1]["text"] == "Подключено. Сейчас открытых платежей нет."
    row = db_session.get(TelegramIntegration, 1)
    assert row is not None
    assert row.team_status == "connected"
    assert row.team_chat_id == "-100500"
    assert row.team_chat_title == "404 mercy"
    assert resolve_team_chat_id(db_session) == ("-100500", "database")

    again = issue_token(db_session, purpose="team", user=admin)
    handle_update(
        db_session,
        bot,
        _message(f"/start {again.token}", chat_id=-100777, chat_type="supergroup", title="Новый"),
    )
    db_session.refresh(row)
    assert row.team_chat_id == "-100777"
    assert row.team_chat_title == "Новый"
    assert bot.sent[-1]["text"] == "Подключено. Сейчас открытых платежей нет."


def test_personal_link_greeting_and_one_account(db_session):
    ivan = User(email="ivan@invoice.local", full_name="Иван", password_hash="x", is_active=True)
    maria = User(email="maria@invoice.local", full_name="Мария", password_hash="x", is_active=True)
    db_session.add_all([ivan, maria])
    db_session.commit()
    bot = FakeBot()
    token = issue_token(db_session, purpose="user", user=ivan)
    handle_update(db_session, bot, _message(f"/start {token.token}", chat_id=42, chat_type="private", sender=42))
    assert bot.sent[-1]["text"].startswith("Привет, Иван! Telegram привязан")
    db_session.refresh(ivan)
    assert ivan.telegram_user_id == 42
    assert ivan.telegram_username == "art"

    other = issue_token(db_session, purpose="user", user=maria)
    handle_update(db_session, bot, _message(f"/start {other.token}", chat_id=42, chat_type="private", sender=42))
    assert "уже привязан" in bot.sent[-1]["text"]
    db_session.refresh(maria)
    db_session.refresh(other)
    assert maria.telegram_user_id is None
    assert other.used_at is None

    handle_update(db_session, bot, _message("/start", chat_id=42, chat_type="private"))
    assert "Привязать Telegram" in bot.sent[-1]["text"]


def test_expired_and_replayed_token_are_rejected(db_session):
    admin = _admin(db_session)
    bot = FakeBot()
    expired = issue_token(db_session, purpose="team", user=admin)
    expired.expires_at = clock.now() - timedelta(seconds=1)
    db_session.commit()
    handle_update(
        db_session,
        bot,
        _message(f"/start {expired.token}", chat_id=-100, chat_type="group", title="Чат"),
    )
    assert "истекла" in bot.sent[-1]["text"]
    assert resolve_team_chat_id(db_session)[0] in (None, "")

    fresh = issue_token(db_session, purpose="user", user=admin)
    handle_update(db_session, bot, _message(f"/start {fresh.token}", chat_id=7, chat_type="private", sender=7))
    handle_update(db_session, bot, _message(f"/start {fresh.token}", chat_id=8, chat_type="private", sender=8))
    assert "истекла" in bot.sent[-1]["text"] or "недействительна" in bot.sent[-1]["text"]
    db_session.refresh(admin)
    assert admin.telegram_user_id == 7


def test_token_in_the_wrong_chat_is_not_spent(db_session):
    admin = _admin(db_session)
    bot = FakeBot()
    team = issue_token(db_session, purpose="team", user=admin)
    handle_update(db_session, bot, _message(f"/start {team.token}", chat_id=7, chat_type="private", sender=7))
    assert "группу" in bot.sent[-1]["text"]
    db_session.refresh(team)
    assert team.used_at is None

    personal = issue_token(db_session, purpose="user", user=admin)
    handle_update(
        db_session,
        bot,
        _message(f"/start {personal.token}", chat_id=-5, chat_type="group", title="Чат"),
    )
    assert "личном чате" in bot.sent[-1]["text"]
    db_session.refresh(personal)
    assert personal.used_at is None


def test_bot_removed_and_supergroup_migration(db_session):
    admin = _admin(db_session)
    template = _template(db_session, title="Сервер", day=26)
    row = _october(db_session, template)
    row.telegram_chat_id = "-100"
    row.telegram_message_id = 3
    db_session.commit()
    token = issue_token(db_session, purpose="team", user=admin)
    bot = FakeBot()
    handle_update(db_session, bot, _message(f"/start {token.token}", chat_id=-100, chat_type="group", title="Команда"))

    handle_update(
        db_session,
        bot,
        {
            "update_id": 2,
            "my_chat_member": {
                "chat": {"id": -100, "type": "group", "title": "Команда"},
                "new_chat_member": {"status": "kicked"},
            },
        },
    )
    state = db_session.get(TelegramIntegration, 1)
    assert state is not None
    assert state.team_status == "disconnected"
    assert state.team_chat_id == "-100"
    assert resolve_team_chat_id(db_session) == (None, "none")

    handle_update(
        db_session,
        bot,
        {"update_id": 3, "message": {"chat": {"id": -100, "type": "group"}, "migrate_to_chat_id": -100999}},
    )
    db_session.refresh(state)
    assert state.team_status == "connected"
    assert state.team_chat_id == "-100999"
    moved = _reload(db_session, row)
    assert moved.telegram_chat_id == "-100999"


def test_private_button_uses_linked_user(db_session):
    template = _template(db_session, title="Сервер", day=20)
    ivan = User(
        email="ivan@invoice.local",
        full_name="Иван",
        password_hash="x",
        is_active=True,
        telegram_user_id=42,
    )
    db_session.add(ivan)
    db_session.flush()
    from app.models import Team
    from app.services.teams import add_member

    team = db_session.get(Team, template.team_id)
    assert team is not None
    add_member(db_session, team, ivan, "member", actor=_admin(db_session))
    db_session.commit()
    row = _october(db_session, template)
    bot = FakeBot()
    handle_callback(
        db_session,
        bot,
        {
            "id": "cb-dm",
            "from": {"id": 42, "first_name": "Иван"},
            "data": f"paid:{row.id}",
            "message": {"message_id": 4, "chat": {"id": 42, "type": "private"}},
        },
    )
    fresh = _reload(db_session, row)
    assert fresh.paid_at is not None
    assert fresh.paid_by_id == ivan.id
    assert fresh.dm_chat_id == "42"
    assert bot.answers[-1][1] == "Оплачено"


def test_api_permissions_and_env_fallback(client, db_session, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "12345:TEST")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", CHAT)
    get_settings.cache_clear()
    try:
        from tests.support import add_person, bootstrap_owner

        bootstrap_owner()
        add_person(db_session, email="ivan@invoice.local", password="change-me-user", name="Иван")
        db_session.commit()
        db_session.expire_all()
        admin_login = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@invoice.local", "password": "change-me"},
        )
        assert admin_login.status_code == 200, admin_login.text
        admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
        ivan_login = client.post(
            "/api/v1/auth/login",
            json={"email": "ivan@invoice.local", "password": "change-me-user"},
        )
        ivan_headers = {"Authorization": f"Bearer {ivan_login.json()['access_token']}"}

        assert client.post("/api/v1/telegram/team-chat/link", headers=ivan_headers).status_code == 403
        assert client.delete("/api/v1/telegram/team-chat", headers=ivan_headers).status_code == 403
        assert client.post("/api/v1/telegram/team-chat/test", headers=ivan_headers).status_code == 403
        assert client.get("/api/v1/telegram/status", headers=ivan_headers).status_code == 403

        not_ready = client.post("/api/v1/telegram/team-chat/link", headers=admin_headers)
        assert not_ready.status_code == 503, not_ready.text

        _ready(db_session)
        status = client.get("/api/v1/telegram/status", headers=admin_headers)
        assert status.status_code == 200, status.text
        assert status.json()["source"] == "env"
        assert status.json()["status"] == "connected"
        assert status.json()["chat_id"] == CHAT

        link = client.post("/api/v1/me/telegram/link", headers=ivan_headers)
        assert link.status_code == 200, link.text
        assert link.json()["url"].startswith("https://t.me/rekeeper_bot?start=")
        assert "startgroup" not in link.json()["url"]

        team = client.post("/api/v1/telegram/team-chat/link", headers=admin_headers)
        assert team.status_code == 200, team.text
        assert "startgroup=" in team.json()["url"]
        stored = db_session.scalar(select(TelegramLinkToken).where(TelegramLinkToken.purpose == "team"))
        assert stored is not None
        assert stored.token not in str(db_session.scalar(select(User.email)))

        toggled = client.patch(
            "/api/v1/me/notifications",
            headers=ivan_headers,
            json={"telegram_reminders": False},
        )
        assert toggled.status_code == 200, toggled.text
        assert toggled.json()["reminders_enabled"] is False
        me = client.get("/api/v1/me/telegram", headers=ivan_headers)
        assert me.json()["linked"] is False
        assert me.json()["reminders_enabled"] is False

        test = client.post("/api/v1/telegram/team-chat/test", headers=admin_headers)
        assert test.status_code == 200, test.text
        assert test.json()["test_pending"] is True
        bot = FakeBot()
        from app.services.telegram_links import flush_test_message

        flush_test_message(bot)
        assert bot.sent[-1]["chat_id"] == CHAT
        assert "на связи" in bot.sent[-1]["text"]
        after = client.get("/api/v1/telegram/status", headers=admin_headers).json()
        assert after["test_pending"] is False
        assert after["test_sent_at"]

        gone = client.delete("/api/v1/telegram/team-chat", headers=admin_headers)
        assert gone.status_code == 200, gone.text
        assert gone.json()["status"] == "disconnected"
        assert gone.json()["source"] == "none"
        db_session.expire_all()
        assert resolve_team_chat_id(db_session) == (None, "none")
        blocked = client.post("/api/v1/telegram/team-chat/test", headers=admin_headers)
        assert blocked.status_code == 409

        unlinked = client.delete("/api/v1/me/telegram", headers=ivan_headers)
        assert unlinked.status_code == 200
        assert unlinked.json()["linked"] is False
    finally:
        get_settings.cache_clear()


def test_link_rows_do_not_require_telegram_for_seed(db_session):
    seed(demo=True)
    db_session.expire_all()
    users = list(db_session.scalars(select(User)).all())
    assert users
    assert all(user.telegram_user_id is None for user in users)
    assert db_session.get(TelegramIntegration, 1) is None
    assert db_session.scalar(select(PaymentOccurrence).limit(1)) is not None
    assert resolve_team_chat_id(db_session) == (None, "none")
