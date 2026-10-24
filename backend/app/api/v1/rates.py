from decimal import Decimal

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from app.core.deps import get_active_user
from app.models import User
from app.schemas.rates import RatesOut
from app.services import rates

router = APIRouter(prefix="/rates", tags=["rates"])


@router.get("", response_model=RatesOut, summary="Курсы ЦБ РФ для подсказки в рублях")
async def get_rates(_: User = Depends(get_active_user)) -> RatesOut:
    """Только справка «≈ … ₽» рядом с суммой в USD и EUR. Если ЦБ недоступен — пустой ответ, не ошибка."""
    current = await run_in_threadpool(rates.current)
    if current is None:
        return RatesOut()
    return RatesOut(on=current.on, rates={code: value.quantize(Decimal("0.0001")) for code, value in current.values.items()})
