from sqlalchemy import select

from app.assistant.telegram_bridge import handle_assistant_callback, handle_private_message
from app.models import RecurringPayment, User
from app.seed import seed
from app.services.telegram_updates import handle_update


class Bot:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.edits: list[dict] = []
        self.answers: list[tuple[str, str, bool]] = []
        self.voice = b"OggSvoice"
        self._seq = 10

    def send_message(self, chat_id: str, text: str, reply_markup: dict) -> int:
        self._seq += 1
        self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
        return self._seq

    def edit_message(self, chat_id: str, message_id: int, text: str, reply_markup: dict) -> None:
        self.edits.append({"chat_id": chat_id, "message_id": message_id, "text": text, "reply_markup": reply_markup})

    def answer_callback(self, callback_query_id: str, text: str, show_alert: bool = False) -> None:
        self.answers.append((callback_query_id, text, show_alert))

    def download_voice(self, file_id: str) -> bytes:
        assert file_id == "voice-file"
        return self.voice


def _private(text: str, sender: int, chat_id: int | None = None) -> dict:
    return {
        "message": {
            "text": text,
            "chat": {"id": chat_id if chat_id is not None else sender, "type": "private"},
            "from": {"id": sender},
        }
    }


def test_unlinked_user_is_asked_to_link_and_group_is_ignored(db_session):
    bot = Bot()
    handle_update(db_session, bot, _private("что горит", 5))
    assert bot.sent
    assert "Привязать Telegram" in bot.sent[0]["text"]
    handle_update(
        db_session,
        bot,
        {"message": {"text": "что горит", "chat": {"id": -100, "type": "group"}, "from": {"id": 5}}},
    )
    assert len(bot.sent) == 1


def test_linked_text_and_voice_use_the_same_assistant(db_session, monkeypatch):
    seed(demo=True)
    ivan = db_session.scalar(select(User).where(User.email == "ivan@invoice.local"))
    assert ivan is not None
    ivan.telegram_user_id = 42
    db_session.commit()
    bot = Bot()
    handle_private_message(db_session, bot, _private("Что просрочено?", 42)["message"])
    assert "Просрочено" in bot.sent[-1]["text"]
    assert "Аренда офиса" in bot.sent[-1]["text"]

    monkeypatch.setattr(
        "app.assistant.telegram_bridge.recognize",
        lambda audio, content_type=None, **kwargs: "кто ответственный за сервер",
    )
    handle_update(
        db_session,
        bot,
        {
            "message": {
                "voice": {"file_id": "voice-file", "duration": 3, "file_size": 2000},
                "chat": {"id": 42, "type": "private"},
                "from": {"id": 42},
            }
        },
    )
    assert "Мария Соколова" in bot.sent[-1]["text"]

    long = Bot()
    handle_update(
        db_session,
        long,
        {
            "message": {
                "voice": {"file_id": "voice-file", "duration": 45, "file_size": 100},
                "chat": {"id": 42, "type": "private"},
                "from": {"id": 42},
            }
        },
    )
    assert "30 секунд" in long.sent[-1]["text"]


def test_inline_confirm_creates_payment_for_linked_admin(db_session):
    seed(demo=True)
    admin = db_session.scalar(select(User).where(User.email == "admin@invoice.local"))
    assert admin is not None
    admin.telegram_user_id = 7
    db_session.commit()
    bot = Bot()
    handle_private_message(
        db_session,
        bot,
        _private("Создай платёж «Почта» 1200 рублей каждое 20 число, ответственный Иван", 7)["message"],
    )
    markup = bot.sent[-1]["reply_markup"]["inline_keyboard"][0]
    assert markup[0]["text"] == "Подтвердить"
    assert markup[1]["text"] == "Изменить"
    data = markup[0]["callback_data"]
    assert db_session.scalar(select(RecurringPayment).where(RecurringPayment.title == "Почта")) is None
    handle_assistant_callback(
        db_session,
        bot,
        {
            "id": "cb-1",
            "data": data,
            "from": {"id": 7},
            "message": {"message_id": bot.sent[-1] and 11, "chat": {"id": 7, "type": "private"}},
        },
    )
    assert bot.answers
    row = db_session.scalar(select(RecurringPayment).where(RecurringPayment.title == "Почта"))
    assert row is not None
    assert f"{row.amount:.2f}" == "1200.00"
    assert bot.edits
    assert "Создан платёж" in bot.edits[-1]["text"]


def test_unlinked_callback_does_not_write(db_session):
    bot = Bot()
    handle_assistant_callback(
        db_session,
        bot,
        {
            "id": "cb-2",
            "data": "asst:ok:00000000-0000-0000-0000-000000000000",
            "from": {"id": 99},
            "message": {"message_id": 1, "chat": {"id": 99, "type": "private"}},
        },
    )
    assert bot.answers
    assert bot.answers[0][2] is True
    assert "привяжи" in bot.answers[0][1].lower()
