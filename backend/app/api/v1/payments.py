from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.summary import SummaryOut
from app.services.summary import build_summary

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("/summary", response_model=SummaryOut, summary="Итоги по валютам")
def summary(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SummaryOut:
    return build_summary(db)
