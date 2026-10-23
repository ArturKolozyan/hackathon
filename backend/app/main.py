from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title="Invoice Keeper API",
    version="1.0.0",
    summary="Инбокс обязательств команды",
    description=(
        "Шаблон регулярного платежа и период — разные сущности. "
        "Инбокс сортируется: просрочено, скоро, остальное. "
        "«Оплачено» — подтверждение человека, не банка. "
        "Суммы в итогах не конвертируются между валютами. "
        "Telegram-бот живёт в worker (long polling): напоминание в общий чат и кнопка «Оплачено» "
        "ставят paid_at = сейчас в TIMEZONE. paid_by этой кнопки — активный администратор с почтой "
        "ADMIN_EMAIL, не тот, кто нажал. Если администратора нет, paid_by = null. Заметка не меняется."
    ),
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"service": "invoice-keeper", "docs": "/api/v1/docs", "health": "/api/v1/health"}
