"""Горизонт периодов, письма и webhook. Telegram только в outbox — шлёт bot."""

import logging
import time

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.healthd import serve_health
from app.services.notify import dispatch_due_reminders
from app.services.occurrences import ensure_all

log = logging.getLogger("invoice_keeper.worker")


def tick() -> None:
    db = SessionLocal()
    try:
        created = ensure_all(db)
        db.commit()
        reminders = dispatch_due_reminders(db)
        db.commit()
        log.info("horizon ok, new_periods=%s reminders=%s", created, reminders)
    finally:
        db.close()


def run() -> None:
    serve_health(get_settings().worker_health_port, lambda: True)
    log.info("worker started")
    while True:
        settings = get_settings()
        interval = max(5, settings.worker_interval_seconds)
        try:
            tick()
        except Exception:
            log.exception("worker tick failed")
        time.sleep(interval)
