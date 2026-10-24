"""Telegram: long polling, кнопка «Оплачено», привязки, outbox, ассистент в боте.

API и worker сюда не ходят и от этого процесса не зависят.
Без токена процесс живёт и отвечает на health: статус disabled.
"""

from __future__ import annotations

import logging
import threading
import time

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.healthd import serve_health
from app.integrations.telegram import TelegramClient, TelegramError, describe_transport, make_bot
from app.services.outbox import drain_telegram
from app.services.telegram_cards import sync_telegram_cards
from app.services.telegram_links import bot_row, flush_test_message, remember_bot
from app.services.telegram_updates import handle_update
from app.services import time as clock

log = logging.getLogger("invoice_keeper.bot")


def _beat(status: str, error: str | None = None) -> None:
    db = SessionLocal()
    try:
        row = bot_row(db, create=True)
        assert row is not None
        row.heartbeat_at = clock.now()
        row.status = status
        row.last_error = (error or "")[:500] or None
        row.updated_at = clock.now()
        db.commit()
    except Exception:
        db.rollback()
        log.exception("bot heartbeat failed")
    finally:
        db.close()


def _drain_and_cards(bot: TelegramClient) -> None:
    db = SessionLocal()
    try:
        drain_telegram(db, bot)
        sync_telegram_cards(db, bot)
        db.commit()
    except Exception:
        db.rollback()
        log.exception("bot drain failed")
    finally:
        db.close()


def _pending_loop(stop: threading.Event, bot: TelegramClient) -> None:
    try:
        while not stop.is_set():
            flush_test_message(bot)
            stop.wait(2)
    except Exception:
        log.exception("telegram test loop failed")


def _warm(bot: TelegramClient) -> bool:
    try:
        bot.delete_webhook()
        me = bot.get_me()
        remember_bot(me)
        log.info("telegram long poll as @%s network=%s", me.get("username"), bot.network)
        return True
    except TelegramError as exc:
        log.warning("telegram warmup failed (%s) network=%s", exc.description, bot.network)
        _beat("error", exc.description)
        return False


def _poll(bot: TelegramClient, offset: int | None) -> tuple[int | None, bool]:
    try:
        updates = bot.get_updates(offset, 25)
    except TelegramError as exc:
        log.warning("telegram poll failed (%s)", exc.description)
        _beat("error", exc.description)
        time.sleep(2)
        return offset, exc.status == 409
    for update in updates:
        try:
            update_id = int(update["update_id"])
        except (KeyError, TypeError, ValueError):
            continue
        try:
            db = SessionLocal()
            try:
                handle_update(db, bot, update)
                db.commit()
            finally:
                db.close()
        except Exception:
            log.exception("telegram update %s failed", update_id)
            break
        offset = update_id + 1
    return offset, False


def run() -> None:
    serve_health(get_settings().bot_health_port, lambda: True)
    log.info("bot started %s", describe_transport())
    bot = make_bot()
    if bot is None:
        log.info("telegram skipped: TELEGRAM_BOT_TOKEN empty")
        while True:
            _beat("disabled")
            time.sleep(max(5, get_settings().worker_interval_seconds))
    offset: int | None = None
    warm = False
    stop = threading.Event()
    side = threading.Thread(target=_pending_loop, args=(stop, bot), name="telegram-test", daemon=True)
    side.start()
    try:
        while True:
            try:
                _drain_and_cards(bot)
            except Exception:
                log.exception("bot tick failed")
            if not warm:
                warm = _warm(bot)
                if not warm:
                    time.sleep(5)
                    continue
            offset, conflict = _poll(bot, offset)
            if conflict:
                warm = False
                continue
            _beat("ok")
    finally:
        stop.set()
        side.join(timeout=3)
        bot.close()
