"""Права ассистента — те же функции, что у REST.

Шаблоны: `require_role(ctx, "admin")` (владелец и админ).
Период: любой участник команды, как `confirm` в payment-occurrences.
Своей таблицы ролей нет. Команда — `TeamContext` активной команды.
"""

from fastapi import HTTPException

from app.services.access import TeamContext, require_role


class AssistantDenied(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def can_manage_templates(ctx: TeamContext) -> bool:
    try:
        require_role(ctx, "admin")
    except HTTPException:
        return False
    return bool(ctx.user.is_active)


def assert_manage_templates(ctx: TeamContext) -> None:
    try:
        require_role(ctx, "admin")
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "Недостаточно прав"
        raise AssistantDenied(detail) from None
    if not ctx.user.is_active:
        raise AssistantDenied("Недостаточно прав")


def assert_mark_paid(ctx: TeamContext) -> None:
    if not ctx.user.is_active:
        raise AssistantDenied("Недостаточно прав")
