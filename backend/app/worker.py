import logging
import time

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.integrations.telegram import describe_transport
from app.services.occurrences import ensure_all

log = logging.getLogger("invoice_keeper.worker")


def run() -> None:
    # Отправитель Telegram живёт здесь, не в API. Пока он не включён:
    # воркер только держит горизонт периодов, чтобы просрочка не стопорила следующий месяц.
    log.info("worker started %s", describe_transport())
    while True:
        try:
            db = SessionLocal()
            try:
                created = ensure_all(db)
                db.commit()
            finally:
                db.close()
            log.info("horizon ok, new_periods=%s", created)
        except Exception:
            log.exception("worker tick failed")
        time.sleep(max(5, get_settings().worker_interval_seconds))
