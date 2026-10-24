import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.assistant.actions import apply_patch, load_own, perform
from app.assistant import suggestions as hints
from app.assistant.chat import chunk_text, clear_messages, list_messages, run_turn
from app.assistant.speech import SpeechError, recognize
from app.core.database import get_db
from app.core.deps import get_team_context
from app.models import AssistantMessage
from app.schemas.assistant import ActionOut, ActionPatch, ConfirmOut, MessageIn, MessageOut, SpeechOut, SuggestionsOut
from app.services.access import TeamContext

router = APIRouter(prefix="/assistant", tags=["assistant"])

MAX_UPLOAD = 8 * 1024 * 1024


def _message_out(message: AssistantMessage) -> MessageOut:
    return MessageOut.model_validate(message)


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("/messages", response_model=list[MessageOut], summary="История чата с Кипом")
def history(
    limit: int = 50,
    ctx: TeamContext = Depends(get_team_context),
    db: Session = Depends(get_db),
) -> list[MessageOut]:
    bounded = min(max(limit, 1), 200)
    return [_message_out(row) for row in list_messages(db, ctx, bounded)]


@router.get("/suggestions", response_model=SuggestionsOut, summary="Стартовые подсказки Кипа")
def start_suggestions(ctx: TeamContext = Depends(get_team_context)) -> SuggestionsOut:
    return SuggestionsOut(suggestions=hints.defaults(ctx.role))


@router.delete("/messages", status_code=204, summary="Очистить чат отдела")
def clear_history(
    ctx: TeamContext = Depends(get_team_context),
    db: Session = Depends(get_db),
) -> None:
    clear_messages(db, ctx)


@router.post("/messages", summary="Сообщение Кипу")
def post_message(
    payload: MessageIn,
    stream: bool = True,
    ctx: TeamContext = Depends(get_team_context),
    db: Session = Depends(get_db),
):
    message = run_turn(db, ctx, payload.text)
    body = _message_out(message)
    if not stream:
        return body

    def events():
        for piece in chunk_text(body.content):
            yield _sse("token", {"text": piece})
        if body.action is not None and body.action.status == "pending":
            yield _sse("confirmation", body.action.model_dump(mode="json"))
        yield _sse("done", {"message": body.model_dump(mode="json")})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/actions/{action_id}/confirm", response_model=ConfirmOut, summary="Подтвердить карточку")
def confirm_action(
    action_id: UUID,
    ctx: TeamContext = Depends(get_team_context),
    db: Session = Depends(get_db),
) -> ConfirmOut:
    action = load_own(db, ctx, action_id)
    message = perform(db, ctx, action)
    message.suggestions = hints.defaults(ctx.role)
    db.refresh(action)
    return ConfirmOut(message=_message_out(message), action=ActionOut.model_validate(action))


@router.patch("/actions/{action_id}", response_model=ActionOut, summary="Поправить карточку до подтверждения")
def patch_action(
    action_id: UUID,
    payload: ActionPatch,
    ctx: TeamContext = Depends(get_team_context),
    db: Session = Depends(get_db),
) -> ActionOut:
    action = load_own(db, ctx, action_id)
    data = payload.model_dump(exclude_unset=True)
    if "starts_on" in data and data["starts_on"] is not None:
        data["starts_on"] = str(data["starts_on"])
    if "responsible_user_id" in data and data["responsible_user_id"] is not None:
        data["responsible_user_id"] = str(data["responsible_user_id"])
    if "occurrence_id" in data and data["occurrence_id"] is not None:
        data["occurrence_id"] = str(data["occurrence_id"])
    updated = apply_patch(db, ctx, action, data)
    return ActionOut.model_validate(updated)


@router.post("/speech", response_model=SpeechOut, summary="Распознать голосовой ввод")
async def speech(
    file: UploadFile = File(...),
    _: TeamContext = Depends(get_team_context),
) -> SpeechOut:
    raw = await file.read(MAX_UPLOAD + 1)
    if len(raw) > MAX_UPLOAD:
        raise HTTPException(status_code=413, detail="Запись длиннее лимита распознавания. Скажите короче.")
    if len(raw) < 32:
        raise HTTPException(status_code=422, detail="Не распознано. Повторите или напишите текстом.")
    try:
        text = recognize(raw, file.content_type)
    except SpeechError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from None
    return SpeechOut(text=text)
