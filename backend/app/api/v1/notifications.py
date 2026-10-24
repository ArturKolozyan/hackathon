from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.telegram import _bot_ready, _team_out
from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_team_context, require_manager
from app.integrations.email import send_test_email
from app.schemas.notifications import (
    EmailTeamIn,
    EmailTeamOut,
    NotificationsOut,
    PersonalChannelOut,
    PersonalNotificationsIn,
    ProbeOut,
    TeamChannelsOut,
    TeamRef,
    WebhookIn,
)
from app.services.access import TeamContext, department_access
from app.services.channels import effective_team_ids, email_teams, save_personal, set_email_team
from app.services.team_webhook import check_team_webhook, clean_webhook_url, set_team_webhook
from app.services.telegram_links import bot_row, bot_username, request_personal_test
from datetime import timedelta
from app.services import time as clock

router = APIRouter(tags=["notifications"])


def _bot_alive(db: Session) -> bool:
    row = bot_row(db)
    if row is None or row.heartbeat_at is None or row.status != "ok":
        return False
    return clock.now() - row.heartbeat_at <= timedelta(seconds=90)


def _view(db: Session, ctx: TeamContext) -> NotificationsOut:
    user = ctx.user
    db.refresh(user)
    db.refresh(ctx.team)
    pending = bool(
        user.telegram_test_requested_at is not None
        and user.telegram_test_sent_at is None
        and not user.telegram_test_error
    )
    manager = ctx.role in {"owner", "admin"}
    return NotificationsOut(
        email=PersonalChannelOut(
            enabled=user.email_reminders,
            team_ids=effective_team_ids(db, user, "email"),
            teams=[
                EmailTeamOut(id=team_id, name=name, enabled=enabled, scope=scope)
                for team_id, name, enabled, scope in email_teams(db, user)
            ],
            address=user.email,
            notify_scope=user.notify_scope,
            notify_overdue=user.notify_overdue,
        ),
        telegram=PersonalChannelOut(
            enabled=user.telegram_reminders,
            team_ids=effective_team_ids(db, user, "telegram"),
            notify_scope=user.notify_scope,
            notify_overdue=user.notify_overdue,
            bot_alive=_bot_alive(db),
            linked=user.telegram_user_id is not None,
            username=user.telegram_username,
            display_name=user.telegram_display_name,
            bot_ready=_bot_ready(db),
            bot_username=bot_username(db),
            test_pending=pending,
            test_sent_at=user.telegram_test_sent_at,
            test_error=user.telegram_test_error,
        ),
        teams=[TeamRef(id=row.team_id, name=row.team.name) for row in department_access(db, user)],
        team=TeamChannelsOut(
            team_id=ctx.team.id,
            team_name=ctx.team.name,
            can_manage=manager,
            telegram=_team_out(db, ctx.team.id),
            # В URL webhook часто зашит секрет (Slack, n8n): участнику его не отдаём.
            webhook_url=ctx.team.webhook_url if manager else None,
            webhook_checked_at=ctx.team.webhook_checked_at if manager else None,
            webhook_check_error=ctx.team.webhook_check_error if manager else None,
        ),
    )


@router.get("/notifications", response_model=NotificationsOut, summary="Каналы уведомлений")
def show(ctx: TeamContext = Depends(get_team_context), db: Session = Depends(get_db)) -> NotificationsOut:
    return _view(db, ctx)


@router.patch("/notifications/personal", response_model=NotificationsOut, summary="Личные каналы")
def update_personal(
    payload: PersonalNotificationsIn,
    ctx: TeamContext = Depends(get_team_context),
    db: Session = Depends(get_db),
) -> NotificationsOut:
    save_personal(
        db,
        ctx.user,
        email_enabled=payload.email_enabled,
        email_team_ids=payload.email_team_ids,
        telegram_enabled=payload.telegram_enabled,
        telegram_team_ids=payload.telegram_team_ids,
        notify_scope=payload.notify_scope,
        notify_overdue=payload.notify_overdue,
    )
    return _view(db, ctx)


@router.put(
    "/notifications/personal/email/teams/{team_id}",
    response_model=NotificationsOut,
    summary="Письма по одному отделу",
    description="Включить или выключить письма по отделу и выбрать охват: только мои платежи или весь отдел.",
)
def update_email_team(
    team_id: UUID,
    payload: EmailTeamIn,
    ctx: TeamContext = Depends(get_team_context),
    db: Session = Depends(get_db),
) -> NotificationsOut:
    set_email_team(db, ctx.user, team_id, enabled=payload.enabled, scope=payload.scope)
    return _view(db, ctx)


@router.post("/notifications/personal/email/test", response_model=ProbeOut, summary="Тестовое письмо")
def test_email(ctx: TeamContext = Depends(get_team_context), db: Session = Depends(get_db)) -> ProbeOut:
    result = send_test_email(ctx.user.email)
    if result == "skipped":
        raise HTTPException(
            status_code=409,
            detail="Почта не настроена: нужны EMAIL_ENABLED, SMTP_HOST и SMTP_FROM. Порт 2525 и SMTP_TLS.",
        )
    if result != "sent":
        raise HTTPException(status_code=502, detail="Письмо не ушло. Проверьте SMTP, порт 2525 и SMTP_TLS.")
    return ProbeOut(ok=True, detail="Тестовое письмо отправлено")


@router.post("/notifications/personal/telegram/test", response_model=ProbeOut, summary="Тестовое в личку")
def test_telegram(ctx: TeamContext = Depends(get_team_context), db: Session = Depends(get_db)) -> ProbeOut:
    if not get_settings().telegram_bot_token.strip():
        raise HTTPException(status_code=409, detail="В .env нет TELEGRAM_BOT_TOKEN")
    try:
        request_personal_test(db, ctx.user)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return ProbeOut(ok=True, pending=True, detail="Сообщение уйдёт в личку в ближайшие секунды")


@router.put("/notifications/team/webhook", response_model=NotificationsOut, summary="Webhook отдела")
def save_webhook(
    payload: WebhookIn,
    ctx: TeamContext = Depends(require_manager),
    db: Session = Depends(get_db),
) -> NotificationsOut:
    set_team_webhook(db, ctx.team, clean_webhook_url(payload.url), ctx.user)
    return _view(db, ctx)


@router.post("/notifications/team/webhook/test", response_model=ProbeOut, summary="Проверить webhook отдела")
def test_webhook(
    ctx: TeamContext = Depends(require_manager),
    db: Session = Depends(get_db),
) -> ProbeOut:
    ok, detail = check_team_webhook(db, ctx.team)
    if not ok:
        raise HTTPException(status_code=502, detail=detail)
    return ProbeOut(ok=True, detail=detail)
