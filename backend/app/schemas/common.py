from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, PlainSerializer


def _money(value: Decimal) -> str:
    return format(Decimal(value).quantize(Decimal("0.01")), "f")


Money = Annotated[Decimal, PlainSerializer(_money, return_type=str, when_used="json")]


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserBrief(APIModel):
    id: UUID
    full_name: str
    email: str


class UserOut(UserBrief):
    role: str
    is_active: bool
    telegram_chat_id: str | None = None
    created_at: datetime
