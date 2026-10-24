"""Один ход диалога: фраза → ответ или карточка. Запись платежа здесь не происходит."""

from __future__ import annotations

import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, joinedload

import re

from app.assistant import agent, suggestions, tools
from app.assistant.actions import pending_for
from app.assistant.actions import apply_patch as patch_action
from app.assistant.gigachat import GigaChatClient
from app.assistant.intents import parse_intent
from app.assistant.prompts import system_prompt
from app.assistant.revise import try_revise
from app.assistant import match as names
from app.models import AssistantAction, AssistantMessage
from app.services import time as clock
from app.services.access import TeamContext, department_access
from app.services.org_settings import load_org

log = logging.getLogger("invoice_keeper.assistant")

FALLBACK = agent.FALLBACK
NO_MODEL = "Свободные вопросы я разбираю с помощью GigaChat, а он сейчас не подключён. Команды вроде «отметь аренду оплаченной» работают и так."
DEFAULT_ZONE = "Europe/Moscow"
HISTORY = 8
CLEARED = "Чат очищен. Спрашивайте что угодно о платежах и продукте."


def clear_messages(db: Session, ctx: TeamContext) -> None:
    """Стирает историю этого человека в отделе и гасит висящие карточки, чтобы следующий ход не правил скрытый черновик."""
    if not ctx.user.is_active:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    db.execute(
        update(AssistantAction)
        .where(
            AssistantAction.user_id == ctx.user.id,
            AssistantAction.team_id == ctx.team.id,
            AssistantAction.status == "pending",
        )
        .values(status="cancelled", resolved_at=clock.now())
    )
    db.execute(
        delete(AssistantMessage).where(
            AssistantMessage.user_id == ctx.user.id,
            AssistantMessage.team_id == ctx.team.id,
        )
    )
    db.commit()


def list_messages(db: Session, ctx: TeamContext, limit: int = 50) -> list[AssistantMessage]:
    stmt = (
        select(AssistantMessage)
        .options(joinedload(AssistantMessage.action))
        .where(AssistantMessage.user_id == ctx.user.id, AssistantMessage.team_id == ctx.team.id)
        .order_by(AssistantMessage.created_at.desc())
        .limit(limit)
    )
    rows = list(db.scalars(stmt).unique().all())
    rows.reverse()
    return rows


def run_turn(db: Session, ctx: TeamContext, text: str, *, client: GigaChatClient | None = None) -> AssistantMessage:
    if not ctx.user.is_active:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    cleaned = text.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="Напишите сообщение")
    if len(cleaned) > 4000:
        raise HTTPException(status_code=422, detail="Слишком длинное сообщение")
    intent = parse_intent(cleaned, clock.today())
    if intent is not None and intent.kind == "clear":
        clear_messages(db, ctx)
        message = _save(db, ctx, CLEARED, None)
        message.suggestions = suggestions.defaults(ctx.role)
        return message
    db.add(AssistantMessage(user_id=ctx.user.id, team_id=ctx.team.id, role="user", content=cleaned))
    db.flush()
    pending = pending_for(db, ctx)
    if pending is not None and intent is None:
        revised = _revise(db, ctx, pending, cleaned)
        if revised is not None:
            message = _save(db, ctx, revised, pending)
            message.suggestions = suggestions.defaults(ctx.role)
            return message
    used: list[str] = []
    proposed: list[str] = []
    if intent is not None:
        prose, action = _from_intent(db, ctx, intent)
    else:
        prose, action = _from_model(db, ctx, cleaned, client, used)
        prose, proposed = suggestions.split(prose)
    message = _save(db, ctx, prose or FALLBACK, action)
    message.suggestions = suggestions.finish(ctx.role, proposed, used)
    return message


def _save(db: Session, ctx: TeamContext, prose: str, action: AssistantAction | None) -> AssistantMessage:
    message = AssistantMessage(
        user_id=ctx.user.id,
        team_id=ctx.team.id,
        role="assistant",
        content=prose,
        action_id=action.id if action is not None else None,
    )
    if action is not None:
        message.action = action
    db.add(message)
    db.commit()
    db.refresh(message)
    if action is not None:
        message.action = action
    return message


def _from_intent(db: Session, ctx: TeamContext, intent) -> tuple[str, AssistantAction | None]:
    return tools.run_intent(db, ctx, intent.kind, intent.slots)


def _revise(db: Session, ctx: TeamContext, action: AssistantAction, text: str) -> str | None:
    if action.kind == "mark_paid" or not action.payload.get("editable", True):
        return None
    updates = try_revise(text)
    if not updates:
        return None
    patch: dict = {}
    if "title" in updates:
        patch["title"] = updates["title"]
    if "amount" in updates:
        patch["amount"] = updates["amount"]
    if "currency" in updates:
        patch["currency"] = updates["currency"]
    if "day_of_month" in updates:
        patch["day_of_month"] = updates["day_of_month"]
    if "responsible_name" in updates:
        found = names.match_users(db, updates["responsible_name"], ctx.team.id)
        if updates["responsible_name"] == "__self__":
            found = [ctx.user]
        if len(found) != 1:
            return "Не понял, кого назначить ответственным. Назовите имя как в разделе «Люди»."
        patch["responsible_user_id"] = str(found[0].id)
    if not patch:
        return None
    try:
        updated = patch_action(db, ctx, action, patch)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "Не разобрал правку."
        return detail
    return updated.summary


_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")


def _compact(text: str, limit: int = 700) -> str:
    """Прошлый ответ для контекста: без таблиц и длинных списков, только суть."""
    lines = [line for line in text.splitlines() if line.strip() and not _TABLE_ROW.match(line)]
    short = "\n".join(lines[:12])
    return short[:limit] + ("…" if len(short) > limit else "")


def _org_zone(db: Session) -> ZoneInfo:
    """Часовой пояс — настройка организации в продукте, по умолчанию Europe/Moscow."""
    try:
        return ZoneInfo(load_org(db).timezone or DEFAULT_ZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_ZONE)


def _history(db: Session, ctx: TeamContext) -> list[dict]:
    stmt = (
        select(AssistantMessage)
        .where(AssistantMessage.user_id == ctx.user.id, AssistantMessage.team_id == ctx.team.id)
        .order_by(AssistantMessage.created_at.desc(), AssistantMessage.id.desc())
        .limit(HISTORY)
    )
    rows = list(reversed(list(db.scalars(stmt).all())))
    departments = [(seat.team.name, seat.role) for seat in department_access(db, ctx.user)]
    zone = _org_zone(db)
    prompt = system_prompt(
        clock.now().astimezone(zone),
        user_name=ctx.user.full_name,
        role=ctx.role,
        team_name=ctx.team.name,
        departments=departments,
        timezone=zone.key,
    )
    messages: list[dict] = [{"role": "system", "content": prompt}]
    for row in rows:
        if row.role == "assistant":
            messages.append({"role": "assistant", "content": _compact(row.content)})
        else:
            messages.append({"role": "user", "content": row.content[:1500]})
    return messages


def _from_model(
    db: Session,
    ctx: TeamContext,
    text: str,
    client: GigaChatClient | None,
    used: list[str] | None = None,
) -> tuple[str, AssistantAction | None]:
    settings_key = ""
    try:
        from app.core.config import get_settings

        settings_key = get_settings().gigachat_auth_key.strip()
    except Exception:
        settings_key = ""
    turn = tools.Turn(db, ctx)
    messages = _history(db, ctx)
    if client is None and not settings_key:
        return agent.fallback(turn, messages, NO_MODEL), None
    gc = client or GigaChatClient()
    try:
        return agent.run(turn, gc, messages, used=used)
    except HTTPException as exc:
        return exc.detail if isinstance(exc.detail, str) else "Не получилось. Сформулируйте иначе.", None


def chunk_text(text: str, size: int = 48) -> list[str]:
    if not text:
        return []
    return [text[index : index + size] for index in range(0, len(text), size)]

