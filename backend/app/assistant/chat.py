"""Один ход диалога: фраза → ответ или карточка. Запись платежа здесь не происходит."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.assistant.actions import READ_KINDS, pending_for, plan
from app.assistant.actions import apply_patch as patch_action
from app.assistant.answers import answer_read
from app.assistant.gigachat import GigaChatClient, GigaChatError
from app.assistant.intents import parse_intent
from app.assistant.prompts import FUNCTIONS, asks_for_facts, has_digit, system_prompt
from app.assistant.revise import try_revise
from app.assistant import match as names
from app.models import AssistantAction, AssistantMessage
from app.services import time as clock
from app.services.access import TeamContext

log = logging.getLogger("invoice_keeper.assistant")

FALLBACK = "Сейчас отвечаю на команды по платежам. Например: что горит на этой неделе?"
UNBACKED = "Не буду называть цифры без данных. Спроси, что горит, что просрочено или сколько потратили за месяц."


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
        raise HTTPException(status_code=422, detail="Напиши сообщение")
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
    if intent.kind in READ_KINDS:
        return answer_read(db, ctx.team.id, intent.kind, intent.slots), None
    return plan(db, ctx, intent.kind, intent.slots)


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
            return "Не понял, кого назначить ответственным."
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
    messages: list[dict] = [{"role": "system", "content": system_prompt(today, ctx.team.name)}]
    for row in rows:
        role = "assistant" if row.role == "assistant" else "user"
        messages.append({"role": role, "content": row.content[:2000]})
    return messages


def _month_slots(raw: object, today: date) -> dict:
    if isinstance(raw, str) and re.fullmatch(r"\d{4}-\d{2}", raw.strip()):
        year, month = raw.strip().split("-")
        return {"year": int(year), "month": int(month)}
    return {"year": today.year, "month": today.month}


def _dispatch(db: Session, ctx: TeamContext, name: str, arguments: dict) -> tuple[str | None, AssistantAction | None]:
    today = clock.today()
    team_id = ctx.team.id
    if name == "week_outlook":
        return answer_read(db, team_id, "week", {}), None
    if name == "list_overdue":
        return answer_read(db, team_id, "overdue", {}), None
    if name == "list_open":
        return answer_read(db, team_id, "open", {}), None
    if name == "month_spending":
        return answer_read(db, team_id, "spending", _month_slots(arguments.get("month"), today)), None
    if name == "find_responsible":
        return answer_read(db, team_id, "responsible", {"query": str(arguments.get("query") or "")}), None
    if name == "propose_create_payment":
        slots = {
            "title": arguments.get("title"),
            "amount": arguments.get("amount"),
            "currency": arguments.get("currency"),
            "day_of_month": arguments.get("day_of_month"),
            "responsible_name": arguments.get("responsible_name"),
            "starts_on": arguments.get("starts_on") or today.isoformat(),
        }
        return plan(db, ctx, "create", slots)
    if name == "propose_mark_paid":
        slots = {"query": arguments.get("query")}
        month = arguments.get("month")
        if isinstance(month, str) and re.fullmatch(r"\d{4}-\d{2}", month.strip()):
            year, mon = month.strip().split("-")
            slots["year"] = int(year)
            slots["month"] = int(mon)
        return plan(db, ctx, "mark_paid", slots)
    if name == "propose_update_payment":
        return plan(db, ctx, "update", dict(arguments))
    if name == "propose_archive_payment":
        return plan(db, ctx, "archive", {"query": arguments.get("query")})
    return "Не понял действие. Повтори проще.", None


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
        for _round in range(3):
            completion = gc.complete(messages, functions=FUNCTIONS)
            call = completion.tool_call
            if call is None:
                content = completion.content.strip()
                if asks_for_facts(text) and has_digit(content):
                    return UNBACKED, None
                return content or FALLBACK, None
            prose, action = _dispatch(db, ctx, call.name, call.arguments)
            if action is not None or prose is not None:
                return prose or FALLBACK, action
            messages.append(
                {
                    "role": "assistant",
                    "content": completion.content or "",
                    "function_call": {"name": call.name, "arguments": call.arguments},
                }
            )
            messages.append({"role": "function", "name": call.name, "content": "{}"})
    except GigaChatError as exc:
        log.warning("assistant model failed")
        return exc.detail, None
    except Exception:
        log.exception("assistant model crashed")
        return "Ассистент сейчас недоступен. Повтори фразу короче.", None
    return "Не собрал ответ. Сформулируй короче.", None


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
