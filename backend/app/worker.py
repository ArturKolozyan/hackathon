import logging
import threading
import time

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.integrations.telegram import TelegramClient, TelegramError, describe_transport, make_bot
from app.services.notify import dispatch_due_reminders
from app.services.occurrences import ensure_all
from app.services.telegram_cards import sync_telegram_cards
from app.services.telegram_links import flush_test_message, remember_bot
from app.services.telegram_updates import handle_update

log = logging.getLogger("invoice_keeper.worker")


def tick() -> None:
    """Один тик: горизонт, общий fan-out напоминаний, правка уже отправленных карточек.

    Коммит горизонта до dispatch: deliver() пишет message id своей сессией
    и должен увидеть период. Второго отбора сроков здесь нет.
    """
    db = SessionLocal()
    bot = None
    try:
        created = ensure_all(db)
        db.commit()
        reminders = dispatch_due_reminders(db)
        edited = 0
        bot = make_bot()
        if bot is not None:
            edited = sync_telegram_cards(db, bot)
        db.commit()
        log.info("horizon ok, new_periods=%s reminders=%s synced=%s", created, reminders, edited)
    finally:
        if bot is not None:
            bot.close()
        db.close()


def run() -> None:
    # Горизонт, почта, webhook и Telegram — один процесс. Long polling, не webhook.
    log.info("worker started %s", describe_transport())
    bot: TelegramClient | None = make_bot()
    offset: int | None = None
    warm = bot is None
    announced_skip = False
    stop = threading.Event()
    side: threading.Thread | None = None
    if bot is not None:
        side = threading.Thread(target=_pending_loop, args=(stop,), name="telegram-test", daemon=True)
        side.start()
    try:
        while True:
            settings = get_settings()
            interval = max(5, settings.worker_interval_seconds)
            try:
                if bot is None and not announced_skip:
                    log.info("telegram skipped: TELEGRAM_BOT_TOKEN empty")
                    announced_skip = True
                tick()
            except Exception:
                log.exception("worker tick failed")

            if bot is None:
                time.sleep(interval)
                continue
            if not warm:
                warm = _warm(bot, interval)
                if not warm:
                    continue
            offset, conflict = _poll(bot, offset, interval)
            if conflict:
                warm = False
    finally:
        stop.set()
        if side is not None:
            side.join(timeout=3)


def _pending_loop(stop: threading.Event) -> None:
    """Тестовое сообщение. API в bridge без IPv6 до Bot API не дотягивается."""
    client = make_bot()
    if client is None:
        return
    try:
        while not stop.is_set():
            flush_test_message(client)
            stop.wait(2)
    finally:
        client.close()


def _warm(bot: TelegramClient, interval: int) -> bool:
    try:
        bot.delete_webhook()
        me = bot.get_me()
        remember_bot(me)
        log.info("telegram long poll as @%s force_ipv6=%s", me.get("username"), bot.force_ipv6)
        return True
    except TelegramError as exc:
        log.warning(
            "telegram warmup failed (%s) force_ipv6=%s. "
            "From a Docker bridge there is often no IPv6 route to api.telegram.org; "
            "on the Aeza VPS start worker with compose.telegram-host.yml",
            exc.description,
            bot.force_ipv6,
        )
        time.sleep(min(interval, 10))
        return False


def _poll(bot: TelegramClient, offset: int | None, interval: int) -> tuple[int | None, bool]:
    timeout = min(50, interval)
    try:
        updates = bot.get_updates(offset, timeout)
    except TelegramError as exc:
        log.warning("telegram poll failed (%s)", exc.description)
        time.sleep(2)
        # 409: webhook или второй getUpdates. Снимем webhook на следующем круге.
        return offset, exc.status == 409
    for update in updates:
        try:
            update_id = int(update["update_id"])
        except (KeyError, TypeError, ValueError):
            log.warning("telegram update without id")
            continue
        try:
            db = SessionLocal()
            try:
                handle_update(db, bot, update)
            finally:
                db.close()
        except Exception:
            log.exception("telegram update %s failed", update_id)
            break
        offset = update_id + 1
    return offset, False
