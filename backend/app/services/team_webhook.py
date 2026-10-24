"""Webhook одной команды. URL задаёт владелец или админ, проверка — один POST.

Только https на публичный адрес. Тело ответа не сохраняем и не показываем, только код.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.integrations.webhook import probe_webhook, public_url_error
from app.models import Team, User
from app.services import time as clock
from app.services.audit import record


def clean_webhook_url(raw: str) -> str:
    cleaned = raw.strip()
    if not cleaned:
        return ""
    if any(char in cleaned for char in "\r\n\t "):
        raise HTTPException(status_code=422, detail="Некорректный URL")
    if len(cleaned) > 500:
        raise HTTPException(status_code=422, detail="Слишком длинный URL")
    error = public_url_error(cleaned)
    if error is not None:
        raise HTTPException(status_code=422, detail=error)
    return cleaned


def set_team_webhook(db: Session, team: Team, url: str, actor: User) -> None:
    team.webhook_url = url or None
    team.webhook_checked_at = None
    team.webhook_check_error = None
    team.updated_at = clock.now()
    record(
        db,
        action="team.webhook",
        actor=actor,
        entity_type="team",
        entity_id=team.id,
        meta={"state": "задан" if url else "снят"},
        team_id=team.id,
    )
    db.commit()
    db.refresh(team)


def check_team_webhook(db: Session, team: Team) -> tuple[bool, str]:
    url = (team.webhook_url or "").strip()
    if not url:
        raise HTTPException(status_code=409, detail="Сначала укажите URL")
    payload = {
        "event": "channel.test",
        "sent_at": clock.now().isoformat(),
        "team_id": str(team.id),
    }
    outcome, detail = probe_webhook(url, payload)
    team.webhook_checked_at = clock.now()
    team.webhook_check_error = None if outcome == "sent" else detail[:200]
    team.updated_at = clock.now()
    db.commit()
    return outcome == "sent", detail
