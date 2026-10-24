from fastapi import APIRouter

from app.api.v1 import (
    assistant,
    audit,
    auth,
    budgets,
    join,
    me,
    notifications,
    payment_occurrences,
    payments,
    recurring_payments,
    stats,
    teams,
    telegram,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(teams.router)
api_router.include_router(join.router)
api_router.include_router(users.router)
api_router.include_router(recurring_payments.router)
api_router.include_router(payment_occurrences.router)
api_router.include_router(payments.router)
api_router.include_router(budgets.router)
api_router.include_router(audit.router)
api_router.include_router(stats.router)
api_router.include_router(telegram.router)
api_router.include_router(assistant.router)
api_router.include_router(notifications.router)


@api_router.get("/health", tags=["meta"], summary="Проверка живости")
def health() -> dict[str, str]:
    return {"status": "ok"}
