"""Один ход диалога: фраза → ответ или карточка. Запись платежа здесь не происходит."""

from __future__ import annotations

import logging
import uuid
from datetime import date

from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, joinedload

from app.assistant import tools
from app.assistant.actions import pending_for
from app.assistant.actions import apply_patch as patch_action
from app.assistant.gigachat import GigaChatClient, GigaChatError
from app.assistant.intents import parse_intent
from app.assistant.prompts import asks_for_facts, has_digit, system_prompt
from app.assistant.revise import try_revise
from app.assistant import match as names
from app.models import AssistantAction, AssistantMessage
from app.services import time as clock
from app.services.access import TeamContext

log = logging.getLogger("invoice_keeper.assistant")

FALLBACK = "Не понял запрос. Спросите, например: «что горит на этой неделе?» или «что вы умеете?»"
UNBACKED = "Не буду называть цифры без данных. Спросите, что горит, что просрочено или сколько потратили за месяц."


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
    db.add(AssistantMessage(user_id=ctx.user.id, team_id=ctx.team.id, role="user", content=cleaned))
    db.flush()
    pending = pending_for(db, ctx)
    intent = parse_intent(cleaned, clock.today())
    if pending is not None and intent is None:
        revised = _revise(db, ctx, pending, cleaned)
        if revised is not None:
            return _save(db, ctx, revised, pending)
    if intent is not None:
        prose, action = _from_intent(db, ctx, intent)
    else:
        prose, action = _from_model(db, ctx, cleaned, client)
    return _save(db, ctx, prose, action)


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


def _history(db: Session, ctx: TeamContext, today: date) -> list[dict]:
    stmt = (
        select(AssistantMessage)
        .where(AssistantMessage.user_id == ctx.user.id, AssistantMessage.team_id == ctx.team.id)
        .order_by(AssistantMessage.created_at.desc())
        .limit(10)
    )
    rows = list(reversed(list(db.scalars(stmt).all())))
    messages: list[dict] = [{"role": "system", "content": system_prompt(today, ctx.team.name, ctx.role)}]
    for row in rows:
        role = "assistant" if row.role == "assistant" else "user"
        messages.append({"role": role, "content": row.content[:2000]})
    return messages


def _from_model(
    db: Session,
    ctx: TeamContext,
    text: str,
    client: GigaChatClient | None,
) -> tuple[str, AssistantAction | None]:
    settings_key = ""
    try:
        from app.core.config import get_settings

        settings_key = get_settings().gigachat_auth_key.strip()
    except Exception:
        settings_key = ""
    if client is None and not settings_key:
        return FALLBACK, None
    gc = client or GigaChatClient()
    messages = _history(db, ctx, clock.today())
    try:
        completion = gc.complete(messages, functions=tools.functions_for(ctx))
    except GigaChatError as exc:
        log.warning("assistant model failed")
        return exc.detail, None
    except Exception:
        log.exception("assistant model crashed")
        return "Кип временно недоступен. Попробуйте чуть позже.", None
    call = completion.tool_call
    if call is None:
        content = completion.content.strip()
        if asks_for_facts(text) and has_digit(content):
            return UNBACKED, None
        return content or FALLBACK, None
    # Ответ с данными собирает инструмент, а не модель: цифры не выдумываются.
    try:
        prose, action = tools.run(db, ctx, call.name, call.arguments)
    except HTTPException as exc:
        return exc.detail if isinstance(exc.detail, str) else "Не получилось. Сформулируйте иначе.", None
    return prose or FALLBACK, action


def chunk_text(text: str, size: int = 48) -> list[str]:
    if not text:
        return []
    return [text[index : index + size] for index in range(0, len(text), size)]


def remember_telegram(db: Session, action_id: uuid.UUID, chat_id: str, message_id: int) -> None:
    action = db.get(AssistantAction, action_id)
    if action is None:
        return
    action.telegram_chat_id = str(chat_id)[:64]
    action.telegram_message_id = message_id
    db.commit()
