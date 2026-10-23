import logging
import time

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.integrations.telegram import describe_transport
from app.services.notify import dispatch_due_reminders
from app.services.occurrences import ensure_all

log = logging.getLogger("invoice_keeper.worker")


def tick() -> None:
    db = SessionLocal()
    try:
        created = ensure_all(db)
        reminders = dispatch_due_reminders(db)
        db.commit()
        log.info("horizon ok, new_periods=%s reminders=%s", created, reminders)
    finally:
        db.close()


def run() -> None:
    # Горизонт периодов и напоминания. Telegram подключается через integrations.telegram.deliver.
    log.info("worker started %s", describe_transport())
    while True:
        try:
            tick()
        except Exception:
            log.exception("worker tick failed")
        time.sleep(max(5, get_settings().worker_interval_seconds))
