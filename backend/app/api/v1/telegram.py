from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user, require_manager
from app.models import User
from app.schemas.telegram import NotificationsIn, TeamTelegram, TelegramLinkOut, TelegramSelf
from app.services import time as clock
from app.services.access import TeamContext
from app.services.telegram_links import (
    bot_username,
    deep_link,
    disconnect_team,
    issue_token,
    request_test,
    resolve_team_chat_id,
    team_row,
    unlink_user,
)

router = APIRouter(tags=["telegram"])


def _bot_ready(db: Session) -> bool:
    return bool(get_settings().telegram_bot_token.strip()) and bot_username(db) is not None


def _self_out(db: Session, user: User) -> TelegramSelf:
    return TelegramSelf(
        linked=user.telegram_user_id is not None,
        username=user.telegram_username,
        display_name=user.telegram_display_name,
        reminders_enabled=user.telegram_reminders,
        bot_ready=_bot_ready(db),
        bot_username=bot_username(db),
    )


def _team_out(db: Session, team_id) -> TeamTelegram:
    row = team_row(db, team_id)
    chat_id, source = resolve_team_chat_id(db, team_id)
    if source == "database":
        status = "connected"
    elif row is not None and row.team_status == "disconnected":
        status = "disconnected"
    elif source == "env":
        status = "connected"
    else:
        status = "absent"
    pending = bool(
        row is not None and row.test_requested_at is not None and row.test_sent_at is None and not row.test_error
    )
    title = None
    shown_chat = None
    if status == "connected":
        shown_chat = chat_id
        if row is not None and source == "database":
            title = row.team_chat_title
    elif status == "disconnected" and row is not None:
        shown_chat = row.team_chat_id
        title = row.team_chat_title
    return TeamTelegram(
        status=status,
        source=source if status == "connected" else "none",
        chat_title=title,
        chat_id=shown_chat,
        bot_username=bot_username(db),
        bot_ready=_bot_ready(db),
        test_pending=pending,
        test_sent_at=row.test_sent_at if row is not None else None,
        test_error=row.test_error if row is not None else None,
    )


def _require_bot(db: Session) -> str:
    if not get_settings().telegram_bot_token.strip():
        raise HTTPException(status_code=503, detail="Telegram не настроен")
    username = bot_username(db)
    if not username:
        raise HTTPException(
            status_code=503,
            detail="Бот ещё не представился. Подождите, пока контейнер bot вызовет getMe, или задайте TELEGRAM_BOT_USERNAME.",
        )
    return username


@router.get("/telegram/status", response_model=TeamTelegram, summary="Чат отдела в Telegram")
def team_status(ctx: TeamContext = Depends(require_manager), db: Session = Depends(get_db)) -> TeamTelegram:
    return _team_out(db, ctx.team.id)


@router.post("/telegram/team-chat/link", response_model=TelegramLinkOut, summary="Ссылка для чата отдела")
def team_link(ctx: TeamContext = Depends(require_manager), db: Session = Depends(get_db)) -> TelegramLinkOut:
    username = _require_bot(db)
    token = issue_token(db, purpose="team", user=ctx.user, team_id=ctx.team.id)
    return TelegramLinkOut(url=deep_link(username, token.token, group=True), expires_at=token.expires_at)


@router.delete("/telegram/team-chat", response_model=TeamTelegram, summary="Отключить чат отдела")
def team_unlink(ctx: TeamContext = Depends(require_manager), db: Session = Depends(get_db)) -> TeamTelegram:
    disconnect_team(db, actor=ctx.user, team_id=ctx.team.id)
    return _team_out(db, ctx.team.id)


@router.post("/telegram/team-chat/test", response_model=TeamTelegram, summary="Тестовое сообщение в чат отдела")
def team_test(ctx: TeamContext = Depends(require_manager), db: Session = Depends(get_db)) -> TeamTelegram:
    if not get_settings().telegram_bot_token.strip():
        raise HTTPException(status_code=409, detail="В .env нет TELEGRAM_BOT_TOKEN")
    try:
        request_test(db, ctx.team.id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return _team_out(db, ctx.team.id)


@router.get("/me/telegram", response_model=TelegramSelf, summary="Личный Telegram")
def my_telegram(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> TelegramSelf:
    return _self_out(db, user)


@router.post("/me/telegram/link", response_model=TelegramLinkOut, summary="Ссылка для привязки Telegram")
def my_link(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> TelegramLinkOut:
    username = _require_bot(db)
    token = issue_token(db, purpose="user", user=user)
    return TelegramLinkOut(url=deep_link(username, token.token, group=False), expires_at=token.expires_at)


@router.post("/me/telegram/skip", response_model=TelegramSelf, summary="Пропустить привязку Telegram")
def my_skip(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> TelegramSelf:
    user.telegram_onboarding_done = True
    user.updated_at = clock.now()
    db.commit()
    db.refresh(user)
    return _self_out(db, user)


@router.delete("/me/telegram", response_model=TelegramSelf, summary="Отвязать Telegram")
def my_unlink(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> TelegramSelf:
    unlink_user(db, user)
    db.refresh(user)
    return _self_out(db, user)


@router.patch("/me/notifications", response_model=TelegramSelf, summary="Личные напоминания")
def my_notifications(
    payload: NotificationsIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramSelf:
    user.telegram_reminders = payload.telegram_reminders
    user.updated_at = clock.now()
    db.commit()
    db.refresh(user)
    return _self_out(db, user)
