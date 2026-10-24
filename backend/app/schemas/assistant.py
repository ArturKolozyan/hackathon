from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    status: str
    summary: str
    payload: dict
    result_text: str | None = None


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: str
    content: str
    created_at: datetime
    action: ActionOut | None = None
    suggestions: list[str] = Field(
        default_factory=list,
        description="Ровно три коротких вопроса-подсказки под ответом. Только у свежего ответа; в истории пусто.",
    )


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class ActionPatch(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    amount: str | None = None
    currency: str | None = None
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    starts_on: str | None = None
    responsible_user_id: UUID | None = None
    occurrence_id: UUID | None = None


class SpeechOut(BaseModel):
    text: str


class ConfirmOut(BaseModel):
    message: MessageOut
    action: ActionOut


class SuggestionsOut(BaseModel):
    suggestions: list[str] = Field(description="Три стартовых вопроса по роли человека в открытом отделе.")
