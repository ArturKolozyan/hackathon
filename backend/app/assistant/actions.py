"""Карточки изменений. Исполнение — те же функции, что REST, и только после подтверждения."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.v1.payment_occurrences import confirm
from app.api.v1.recurring_payments import archive_payment, create_payment, update_payment
from app.assistant import match as names
from app.assistant.answers import catalog
from app.assistant.dates import first_due
from app.assistant.permissions import AssistantDenied, assert_manage_templates, assert_mark_paid, can_manage_templates
from app.models import AssistantAction, AssistantMessage, Team, User
from app.schemas.occurrence import ConfirmIn
from app.schemas.recurring import RecurringCreate, RecurringUpdate
from app.services import time as clock
from app.services.access import TeamContext
from app.services.occurrences import list_views, view_one
from app.services.teams import membership, require_participant

READ_KINDS = {"week", "overdue", "spending", "paid_month", "open", "responsible", "person"}


def _validation_text(exc: ValidationError) -> str:
    messages: list[str] = []
    for error in exc.errors():
        msg = str(error.get("msg") or "Проверь поля")
        prefix = "Value error, "
        if msg.startswith(prefix):
            msg = msg[len(prefix) :]
        messages.append(msg)
    return "Не получилось: " + "; ".join(messages) if messages else "Проверь поля."


def _detail(exc: HTTPException) -> str:
    if isinstance(exc.detail, str):
        return exc.detail
    return "Не получилось выполнить. Проверь поля."


def _cancel_pending(db: Session, user_id: uuid.UUID, team_id: uuid.UUID) -> None:
    now = clock.now()
    db.execute(
        update(AssistantAction)
        .where(
            AssistantAction.user_id == user_id,
            AssistantAction.team_id == team_id,
            AssistantAction.status == "pending",
        )
        .values(status="cancelled", resolved_at=now)
    )


def _stage(
    db: Session,
    ctx: TeamContext,
    kind: str,
    fields: dict,
    summary: str,
    *,
    extra: dict | None = None,
    editable: bool = True,
) -> AssistantAction:
    _cancel_pending(db, ctx.user.id, ctx.team.id)
    payload: dict = {"fields": fields, "editable": editable}
    if extra:
        payload.update(extra)
    if kind in {"create_payment", "update_payment"}:
        payload["people"] = names.people_payload(db, ctx.team.id)
    action = AssistantAction(
        user_id=ctx.user.id,
        team_id=ctx.team.id,
        kind=kind,
        status="pending",
        payload=payload,
        summary=summary,
    )
    db.add(action)
    db.flush()
    return action


def _one_template(db: Session, team_id: uuid.UUID, query: str):
    found = names.match_templates(db, query, team_id)
    if not found:
        return None, f"Платежа «{query}» не нашёл. Сейчас есть: {catalog(db, team_id)}."
    if len(found) > 1:
        titles = ", ".join(f"«{row.title}»" for row in found)
        return None, f"Нашёл несколько платежей: {titles}. Уточни название."
    return found[0], None


def _one_person(db: Session, team_id: uuid.UUID, name: str, actor: User):
    if name == "__self__":
        return actor, None
    found = names.match_users(db, name, team_id)
    if not found:
        people = ", ".join(user.full_name for user in names.active_users(db, team_id)) or "никого"
        return None, f"Не нашёл ответственного «{name}». Сейчас в отделе: {people}."
    if len(found) > 1:
        return None, "Нашёл несколько людей: " + ", ".join(user.full_name for user in found) + ". Уточни имя."
    return found[0], None


def _create_summary(fields: dict) -> str:
    due = date.fromisoformat(fields["first_due"])
    return (
        f"Создать платёж: {fields['title']}\n"
        f"{fields['amount']} {fields['currency']}\n"
        f"каждое {fields['day_of_month']}-е, первый срок {due.strftime('%d.%m.%Y')}\n"
        f"ответственный: {fields['responsible_name']}"
    )


def plan_create(db: Session, ctx: TeamContext, slots: dict) -> tuple[str, AssistantAction | None]:
    if not can_manage_templates(ctx):
        return "Создавать и менять платежи может владелец или админ. Отметить период оплаченным можно самому.", None
    responsible, error = _one_person(db, ctx.team.id, str(slots.get("responsible_name") or ""), ctx.user)
    if error or responsible is None:
        return error or "Нужен ответственный.", None
    try:
        payload = RecurringCreate(
            title=str(slots["title"]),
            amount=Decimal(str(slots["amount"])),
            currency=str(slots["currency"]),
            day_of_month=int(slots["day_of_month"]),
            starts_on=date.fromisoformat(str(slots["starts_on"])),
            responsible_user_id=responsible.id,
        )
    except (ValidationError, ValueError, KeyError) as exc:
        if isinstance(exc, ValidationError):
            return _validation_text(exc), None
        return "Не разобрал поля платежа. Напиши название, сумму, валюту, день и ответственного.", None
    due = first_due(payload.starts_on, payload.day_of_month)
    fields = {
        "title": payload.title,
        "amount": f"{payload.amount:.2f}",
        "currency": payload.currency,
        "day_of_month": payload.day_of_month,
        "starts_on": payload.starts_on.isoformat(),
        "responsible_user_id": str(responsible.id),
        "responsible_name": responsible.full_name,
        "first_due": due.isoformat(),
    }
    summary = _create_summary(fields)
    return summary, _stage(db, ctx, "create_payment", fields, summary)


def _update_kwargs(changes: dict) -> dict:
    patch: dict = {}
    if "title" in changes:
        patch["title"] = changes["title"]
    if "amount" in changes:
        patch["amount"] = Decimal(str(changes["amount"]))
    if "currency" in changes:
        patch["currency"] = changes["currency"]
    if "day_of_month" in changes:
        patch["day_of_month"] = changes["day_of_month"]
    if "responsible_user_id" in changes:
        patch["responsible_user_id"] = uuid.UUID(str(changes["responsible_user_id"]))
    return patch


def _change_lines(before: dict, changes: dict) -> list[str]:
    lines: list[str] = []
    if "amount" in changes or "currency" in changes:
        old = f"{before['amount']} {before['currency']}"
        new_amount = changes.get("amount", before["amount"])
        new_currency = changes.get("currency", before["currency"])
        lines.append(f"сумма: {old} → {new_amount} {new_currency}")
    if "day_of_month" in changes:
        lines.append(f"день: {before['day_of_month']} → {changes['day_of_month']}")
    if "responsible_name" in changes:
        lines.append(f"ответственный: {before['responsible_name']} → {changes['responsible_name']}")
    if "title" in changes:
        lines.append(f"название: {before['title']} → {changes['title']}")
    return lines


def plan_update(db: Session, ctx: TeamContext, slots: dict) -> tuple[str, AssistantAction | None]:
    if not can_manage_templates(ctx):
        return "Менять платежи может владелец или админ.", None
    template, error = _one_template(db, ctx.team.id, str(slots.get("query") or ""))
    if error or template is None:
        return error or "Какой платёж изменить?", None
    before = {
        "title": template.title,
        "amount": f"{template.amount:.2f}",
        "currency": template.currency,
        "day_of_month": template.day_of_month,
        "responsible_user_id": str(template.responsible_user_id) if template.responsible_user_id else None,
        "responsible_name": template.responsible.full_name if template.responsible is not None else "",
    }
    changes: dict = {}
    if slots.get("amount"):
        changes["amount"] = str(slots["amount"])
        changes["currency"] = str(slots.get("currency") or template.currency)
    elif slots.get("currency"):
        changes["currency"] = str(slots["currency"])
    if slots.get("day_of_month") is not None:
        changes["day_of_month"] = int(slots["day_of_month"])
    if slots.get("title"):
        changes["title"] = str(slots["title"])
    if slots.get("responsible_name"):
        person, person_error = _one_person(db, ctx.team.id, str(slots["responsible_name"]), ctx.user)
        if person_error or person is None:
            return person_error or "Кого назначить?", None
        changes["responsible_user_id"] = str(person.id)
        changes["responsible_name"] = person.full_name
    if not changes:
        return "Что именно изменить: сумму, день или ответственного?", None
    try:
        validated = RecurringUpdate(**_update_kwargs(changes))
    except (ValidationError, ValueError) as exc:
        if isinstance(exc, ValidationError):
            return _validation_text(exc), None
        return "Не разобрал изменение.", None
    if validated.amount is not None:
        changes["amount"] = f"{validated.amount:.2f}"
    if validated.currency is not None:
        changes["currency"] = validated.currency
    lines = _change_lines(before, changes)
    summary = "Изменить платёж: " + template.title + "\n" + "\n".join(lines)
    fields = {"payment_id": str(template.id), "title": template.title, "before": before, "changes": changes}
    return summary, _stage(db, ctx, "update_payment", fields, summary)


def plan_archive(db: Session, ctx: TeamContext, slots: dict) -> tuple[str, AssistantAction | None]:
    if not can_manage_templates(ctx):
        return "Архивировать платежи может владелец или админ.", None
    template, error = _one_template(db, ctx.team.id, str(slots.get("query") or ""))
    if error or template is None:
        return error or "Какой платёж архивировать?", None
    summary = (
        f"Архивировать платёж: {template.title}\n"
        "Новые напоминания остановятся. История периодов останется."
    )
    fields = {"payment_id": str(template.id), "title": template.title}
    return summary, _stage(db, ctx, "archive_payment", fields, summary, editable=False)


def _open_occurrences(db: Session, team_id: uuid.UUID, template_id: uuid.UUID):
    _today, items = list_views(db, view="all", team_id=team_id, recurring_payment_id=template_id)
    return [item for item in items if item.status != "paid"]


def plan_mark_paid(db: Session, ctx: TeamContext, slots: dict) -> tuple[str, AssistantAction | None]:
    if not ctx.user.is_active:
        return "Недостаточно прав.", None
    template, error = _one_template(db, ctx.team.id, str(slots.get("query") or ""))
    if error or template is None:
        return error or "Какой платёж отметить оплаченным?", None
    opened = _open_occurrences(db, ctx.team.id, template.id)
    if slots.get("year") and slots.get("month"):
        key = f"{int(slots['year']):04d}-{int(slots['month']):02d}"
        _today, items = list_views(db, view="all", team_id=ctx.team.id, recurring_payment_id=template.id)
        chosen = [item for item in items if item.period == key]
        if not chosen:
            return f"У «{template.title}» нет периода {key}.", None
        target = chosen[0]
        if target.status == "paid":
            return f"«{template.title}» за {target.period_label} уже оплачен.", None
    elif not opened:
        return f"У «{template.title}» нет открытых периодов.", None
    else:
        today = clock.today()
        current = [item for item in opened if item.due_date.year == today.year and item.due_date.month == today.month]
        overdue = [item for item in opened if item.status == "overdue"]
        target = current[0] if current else (overdue[0] if overdue else opened[0])
    alternatives = [
        {
            "occurrence_id": str(item.id),
            "period_label": item.period_label,
            "due_date": item.due_date.isoformat(),
            "status": item.status,
        }
        for item in opened
        if item.id != target.id
    ]
    fields = {
        "occurrence_id": str(target.id),
        "payment_id": str(template.id),
        "title": target.title,
        "period_label": target.period_label,
        "amount": f"{Decimal(target.amount):.2f}",
        "currency": target.currency,
        "due_date": target.due_date.isoformat(),
        "status": target.status,
    }
    summary = (
        f"Отметить оплаченным: {target.title}\n"
        f"{target.period_label}: {fields['amount']} {target.currency}, "
        f"до {target.due_date.strftime('%d.%m.%Y')}, {fields['status']}"
    )
    summary = summary.replace(fields["status"], {"overdue": "просрочено", "due_soon": "скоро", "upcoming": "впереди"}.get(fields["status"], fields["status"]))
    return summary, _stage(
        db,
        ctx,
        "mark_paid",
        fields,
        summary,
        extra={"alternatives": alternatives},
        editable=bool(alternatives),
    )


def plan(db: Session, ctx: TeamContext, kind: str, slots: dict) -> tuple[str, AssistantAction | None]:
    if kind == "clarify":
        return str(slots.get("text") or "Уточни запрос."), None
    if kind == "unsupported_frequency":
        return "Регулярные платежи сейчас только раз в месяц, по дню месяца. Назови день, например «каждое 12-е».", None
    if kind == "create":
        return plan_create(db, ctx, slots)
    if kind == "update":
        return plan_update(db, ctx, slots)
    if kind == "archive":
        return plan_archive(db, ctx, slots)
    if kind == "mark_paid":
        return plan_mark_paid(db, ctx, slots)
    return "Не понял действие.", None


def _who(person) -> str:
    if person is None:
        return "не назначен"
    return person.full_name


def _fresh_context(db: Session, ctx: TeamContext) -> TeamContext:
    user = db.get(User, ctx.user.id)
    team = db.get(Team, ctx.team.id)
    if user is None or team is None or not user.is_active:
        raise AssistantDenied("Недостаточно прав")
    row = membership(db, team.id, user.id)
    if row is None and not user.is_owner:
        raise AssistantDenied("Вы не в этом отделе")
    return TeamContext(user=user, team=team, membership=row)


def _execute(db: Session, ctx: TeamContext, action: AssistantAction) -> str:
    if action.team_id != ctx.team.id:
        raise AssistantDenied("Вы не в этом отделе")
    fields = action.payload.get("fields") or {}
    if action.kind == "create_payment":
        assert_manage_templates(ctx)
        created = create_payment(
            RecurringCreate(
                title=fields["title"],
                amount=Decimal(str(fields["amount"])),
                currency=fields["currency"],
                day_of_month=int(fields["day_of_month"]),
                starts_on=date.fromisoformat(fields["starts_on"]),
                responsible_user_id=uuid.UUID(fields["responsible_user_id"]),
            ),
            ctx,
            db,
        )
        return (
            f"Создан платёж «{created.title}»: {created.amount:.2f} {created.currency}, "
            f"каждое {created.day_of_month}-е, ответственный {_who(created.responsible)}."
        )
    if action.kind == "update_payment":
        assert_manage_templates(ctx)
        changes = fields.get("changes") or {}
        updated = update_payment(uuid.UUID(fields["payment_id"]), RecurringUpdate(**_update_kwargs(changes)), ctx, db)
        return (
            f"Обновил «{updated.title}»: {updated.amount:.2f} {updated.currency}, "
            f"каждое {updated.day_of_month}-е, ответственный {_who(updated.responsible)}."
        )
    if action.kind == "archive_payment":
        assert_manage_templates(ctx)
        archived = archive_payment(uuid.UUID(fields["payment_id"]), ctx, db)
        return f"«{archived.title}» в архиве. Новые периоды не создаются, история на месте."
    if action.kind == "mark_paid":
        assert_mark_paid(ctx)
        occurrence = confirm(uuid.UUID(fields["occurrence_id"]), ConfirmIn(), ctx, db)
        paid = occurrence.paid_on.strftime("%d.%m.%Y") if occurrence.paid_on else "сегодня"
        return f"«{occurrence.title}» за {occurrence.period_label} отмечен оплаченным ({paid})."
    raise HTTPException(status_code=422, detail="Неизвестное действие")


def perform(db: Session, ctx: TeamContext, action: AssistantAction) -> AssistantMessage:
    if action.user_id != ctx.user.id or action.team_id != ctx.team.id:
        raise HTTPException(status_code=403, detail="Это подтверждение другого человека.")
    locked = db.execute(
        update(AssistantAction)
        .where(AssistantAction.id == action.id, AssistantAction.status == "pending")
        .values(status="running")
    )
    db.commit()
    if locked.rowcount != 1:
        raise HTTPException(status_code=409, detail="Уже обработано")
    db.refresh(action)
    fresh = _fresh_context(db, ctx)
    try:
        text = _execute(db, fresh, action)
        status = "confirmed"
    except AssistantDenied as exc:
        text = exc.detail
        status = "failed"
    except HTTPException as exc:
        text = _detail(exc)
        status = "failed"
    action.status = status
    action.result_text = text
    action.resolved_at = clock.now()
    message = AssistantMessage(user_id=fresh.user.id, team_id=fresh.team.id, role="assistant", content=text)
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def apply_patch(db: Session, ctx: TeamContext, action: AssistantAction, patch: dict) -> AssistantAction:
    if action.user_id != ctx.user.id or action.team_id != ctx.team.id:
        raise HTTPException(status_code=403, detail="Это подтверждение другого человека.")
    if action.status != "pending":
        raise HTTPException(status_code=409, detail="Уже обработано")
    if not action.payload.get("editable", True):
        raise HTTPException(status_code=422, detail="Эту карточку лучше поправить фразой в чате.")
    fields = dict(action.payload.get("fields") or {})
    if action.kind == "create_payment":
        _patch_create(db, ctx.team.id, fields, patch)
        action.payload = {**action.payload, "fields": fields}
        action.summary = _create_summary(fields)
    elif action.kind == "update_payment":
        _patch_update(db, ctx.team.id, fields, patch)
        action.payload = {**action.payload, "fields": fields}
        action.summary = "Изменить платёж: " + fields["title"] + "\n" + "\n".join(
            _change_lines(fields["before"], fields["changes"])
        )
    elif action.kind == "mark_paid":
        _patch_paid(db, ctx.team.id, action, fields, patch)
        action.payload = {**action.payload, "fields": fields}
        action.summary = (
            f"Отметить оплаченным: {fields['title']}\n"
            f"{fields['period_label']}: {fields['amount']} {fields['currency']}, до "
            f"{date.fromisoformat(fields['due_date']).strftime('%d.%m.%Y')}"
        )
    else:
        raise HTTPException(status_code=422, detail="Эту карточку лучше поправить фразой в чате.")
    db.commit()
    db.refresh(action)
    return action


def _participant(db: Session, team_id: uuid.UUID, user_id: uuid.UUID) -> User:
    try:
        return require_participant(db, team_id, user_id)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "Ответственный не в этом отделе"
        raise HTTPException(status_code=422, detail=detail) from None


def _patch_create(db: Session, team_id: uuid.UUID, fields: dict, patch: dict) -> None:
    if patch.get("title"):
        fields["title"] = str(patch["title"]).strip()
    if patch.get("amount"):
        fields["amount"] = str(patch["amount"])
    if patch.get("currency"):
        fields["currency"] = str(patch["currency"])
    if patch.get("day_of_month") is not None:
        fields["day_of_month"] = int(patch["day_of_month"])
    if patch.get("starts_on"):
        fields["starts_on"] = str(patch["starts_on"])
    if patch.get("responsible_user_id"):
        person = _participant(db, team_id, uuid.UUID(str(patch["responsible_user_id"])))
        fields["responsible_user_id"] = str(person.id)
        fields["responsible_name"] = person.full_name
    try:
        payload = RecurringCreate(
            title=fields["title"],
            amount=Decimal(str(fields["amount"])),
            currency=fields["currency"],
            day_of_month=int(fields["day_of_month"]),
            starts_on=date.fromisoformat(fields["starts_on"]),
            responsible_user_id=uuid.UUID(fields["responsible_user_id"]),
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_validation_text(exc)) from None
    due = first_due(payload.starts_on, payload.day_of_month)
    fields.update(
        {
            "title": payload.title,
            "amount": f"{payload.amount:.2f}",
            "currency": payload.currency,
            "day_of_month": payload.day_of_month,
            "starts_on": payload.starts_on.isoformat(),
            "first_due": due.isoformat(),
        }
    )


def _patch_update(db: Session, team_id: uuid.UUID, fields: dict, patch: dict) -> None:
    changes = dict(fields.get("changes") or {})
    if patch.get("amount"):
        changes["amount"] = str(patch["amount"])
        changes.setdefault("currency", fields["before"]["currency"])
    if patch.get("currency"):
        changes["currency"] = str(patch["currency"])
    if patch.get("day_of_month") is not None:
        changes["day_of_month"] = int(patch["day_of_month"])
    if patch.get("title"):
        changes["title"] = str(patch["title"]).strip()
    if patch.get("responsible_user_id"):
        person = _participant(db, team_id, uuid.UUID(str(patch["responsible_user_id"])))
        changes["responsible_user_id"] = str(person.id)
        changes["responsible_name"] = person.full_name
    try:
        validated = RecurringUpdate(**_update_kwargs(changes))
    except (ValidationError, ValueError) as exc:
        if isinstance(exc, ValidationError):
            raise HTTPException(status_code=422, detail=_validation_text(exc)) from None
        raise HTTPException(status_code=422, detail="Не разобрал изменение.") from None
    if validated.amount is not None:
        changes["amount"] = f"{validated.amount:.2f}"
    if validated.currency is not None:
        changes["currency"] = validated.currency
    fields["changes"] = changes


def _patch_paid(db: Session, team_id: uuid.UUID, action: AssistantAction, fields: dict, patch: dict) -> None:
    occurrence_id = str(patch.get("occurrence_id") or "")
    if not occurrence_id:
        raise HTTPException(status_code=422, detail="Выбери период")
    allowed = {str(fields.get("occurrence_id"))}
    allowed.update(str(item.get("occurrence_id")) for item in action.payload.get("alternatives") or [])
    if occurrence_id not in allowed:
        raise HTTPException(status_code=422, detail="Этот период не из карточки")
    item = view_one(db, uuid.UUID(occurrence_id), team_id)
    if item.status == "paid":
        raise HTTPException(status_code=422, detail="Этот период уже оплачен")
    if str(item.recurring_payment_id) != str(fields.get("payment_id")):
        raise HTTPException(status_code=422, detail="Этот период не из карточки")
    fields.update(
        {
            "occurrence_id": str(item.id),
            "title": item.title,
            "period_label": item.period_label,
            "amount": f"{Decimal(item.amount):.2f}",
            "currency": item.currency,
            "due_date": item.due_date.isoformat(),
            "status": item.status,
        }
    )


def load_for_user(db: Session, user: User, action_id: uuid.UUID) -> AssistantAction:
    action = db.get(AssistantAction, action_id)
    if action is None or action.user_id != user.id:
        raise HTTPException(status_code=404, detail="Карточка не найдена")
    return action


def load_own(db: Session, ctx: TeamContext, action_id: uuid.UUID) -> AssistantAction:
    action = load_for_user(db, ctx.user, action_id)
    if action.team_id != ctx.team.id:
        raise HTTPException(status_code=404, detail="Карточка не найдена")
    return action


def pending_for(db: Session, ctx: TeamContext) -> AssistantAction | None:
    stmt = (
        select(AssistantAction)
        .where(
            AssistantAction.user_id == ctx.user.id,
            AssistantAction.team_id == ctx.team.id,
            AssistantAction.status == "pending",
        )
        .order_by(AssistantAction.created_at.desc())
    )
    return db.scalars(stmt).first()

