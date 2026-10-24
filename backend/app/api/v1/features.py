"""Что включено в этой установке. Секретов в ответе нет."""

import logging
from datetime import timedelta

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.services import time as clock
from app.services.telegram_links import bot_row

log = logging.getLogger("invoice_keeper.features")

router = APIRouter(tags=["meta"])


def assistant_reachable(url: str) -> bool:
    target = url.strip().rstrip("/")
    if not target:
        return False
    try:
        response = httpx.get(f"{target}/health", timeout=1.5)
    except httpx.HTTPError:
        log.debug("assistant health unreachable")
        return False
    return response.status_code == 200


@router.get("/features", summary="Включённые возможности установки")
def features(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict[str, bool]:
    del user
    settings = get_settings()
    assistant = settings.assistant_configured
    voice = assistant and settings.voice_configured
    available = assistant_reachable(settings.assistant_url) if assistant else False
    email = bool(settings.email_enabled and settings.smtp_host.strip() and settings.smtp_from.strip())
    telegram = bool(settings.telegram_bot_token.strip())
    alive = False
    row = bot_row(db)
    if row is not None and row.heartbeat_at is not None and row.status == "ok":
        alive = clock.now() - row.heartbeat_at <= timedelta(seconds=90)
    return {
        "assistant": assistant,
        "assistant_available": available,
        "voice": voice,
        "email": email,
        "telegram": telegram,
        "bot_alive": alive,
    }
