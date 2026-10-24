"""Отдельный процесс ассистента. GigaChat и SpeechKit живут только здесь."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import assistant as assistant_routes
from app.core.config import get_settings

app = FastAPI(title="Invoice Keeper Assistant", docs_url=None, redoc_url=None, openapi_url=None)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(assistant_routes.router, prefix="/api/v1")


@app.get("/health")
def health():
    """200 — процесс жив. Модель может быть недоступна: это уже ответ чата, не health."""
    configured = get_settings().assistant_configured
    body = {"status": "ok", "configured": configured}
    if not configured:
        return JSONResponse(status_code=200, content=body)
    return body
