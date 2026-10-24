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
    from app.services.org_settings import load_org
    from app.services.time import bind_zone, reset_zone

    db = SessionLocal()
    token = bind_zone(load_org(db).timezone)
    try:
        created = ensure_all(db)
        db.commit()
        reminders = dispatch_due_reminders(db)
        db.commit()
        log.info("horizon ok, new_periods=%s reminders=%s", created, reminders)
    finally:
        reset_zone(token)
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
