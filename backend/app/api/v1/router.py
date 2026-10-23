from fastapi import APIRouter

from app.api.v1 import auth, payment_occurrences, payments, recurring_payments, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(recurring_payments.router)
api_router.include_router(payment_occurrences.router)
api_router.include_router(payments.router)


@api_router.get("/health", tags=["meta"], summary="Проверка живости")
def health() -> dict[str, str]:
    return {"status": "ok"}
