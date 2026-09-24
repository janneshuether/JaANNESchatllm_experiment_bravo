from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.config import OPENROUTER_MODEL_DEFAULT
from backend.database import get_db
from backend.models import ChatMessage, ChatSession, User
from backend.schemas.chat import (
    ChatMessageOut,
    ChatRequest,
    ChatResponse,
    ChatSessionCreate,
    ChatSessionResponse,
)
from backend.services.auth import get_user_by_token
from backend.services.openrouter import OpenRouterConfigError, generate_reply, stream_reply
from backend.services.sessions import (
    create_session,
    delete_session,
    get_or_create_session,
    get_session,
    get_session_messages,
    list_sessions,
    update_session_title_if_default,
)

router = APIRouter()


def get_optional_user(
    authorization: Optional[str] = Header(None),
    x_session_token: Optional[str] = Header(None, alias="X-Session-Token"),
    db: Session = Depends(get_db),
) -> Optional[User]:
    token = None
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]
        else:
            token = authorization.strip()
    elif x_session_token:
        token = x_session_token.strip()

    if token:
        return get_user_by_token(db, token)
    return None


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/sessions", response_model=list[ChatSessionResponse])
def get_sessions(
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> list[ChatSessionResponse]:
    user_id = current_user.id if current_user else None
    sessions = list_sessions(db, user_id=user_id)
    return [ChatSessionResponse.model_validate(s) for s in sessions]


@router.post("/api/sessions", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
def new_session(
    payload: Optional[ChatSessionCreate] = None,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> ChatSessionResponse:
    title = payload.title if payload else None
    user_id = current_user.id if current_user else None
    session = create_session(db, title=title, user_id=user_id)
    return ChatSessionResponse.model_validate(session)


@router.get("/api/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
def get_messages_for_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> list[ChatMessageOut]:
    session = get_session(db, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Sessao nao encontrada.")
    messages = get_session_messages(db, session_id)
    return [ChatMessageOut.model_validate(m) for m in messages]


@router.delete("/api/sessions/{session_id}")
def remove_session(
    session_id: str,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    success = delete_session(db, session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Sessao nao encontrada.")
    return {"message": "Sessao removida com sucesso."}


@router.post("/api/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    user_id = current_user.id if current_user else None
    session = get_or_create_session(db, session_id=payload.session_id, user_id=user_id)

    try:
        reply, model_name = await generate_reply(
            user_message=payload.message,
            history=[item.model_dump() for item in payload.history],
            model=payload.model,
        )
    except OpenRouterConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    resolved_model = payload.model or model_name or OPENROUTER_MODEL_DEFAULT

    # Persist message in active session
    db.add(ChatMessage(session_key=session.id, role="user", content=payload.message, model=resolved_model))
    db.add(ChatMessage(session_key=session.id, role="assistant", content=reply, model=resolved_model))
    db.commit()

    # Automatically set title based on first context if not yet set
    updated_title = update_session_title_if_default(db, session, payload.message, reply)

    return ChatResponse(
        reply=reply,
        model=resolved_model,
        session_id=session.id,
        session_title=updated_title,
    )


@router.post("/api/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    current_user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    user_id = current_user.id if current_user else None
    session = get_or_create_session(db, session_id=payload.session_id, user_id=user_id)
    resolved_model = payload.model or OPENROUTER_MODEL_DEFAULT

    async def event_generator():
        full_reply = ""
        try:
            async for delta in stream_reply(
                user_message=payload.message,
                history=[item.model_dump() for item in payload.history],
                model=payload.model,
            ):
                full_reply += delta
                yield f"data: {json.dumps({'delta': delta}, ensure_ascii=True)}\n\n"
        except OpenRouterConfigError as exc:
            yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=True)}\n\n"
            return
        except RuntimeError as exc:
            yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=True)}\n\n"
            return

        final_title = session.title
        if full_reply.strip():
            db.add(
                ChatMessage(
                    session_key=session.id,
                    role="user",
                    content=payload.message,
                    model=resolved_model,
                )
            )
            db.add(
                ChatMessage(
                    session_key=session.id,
                    role="assistant",
                    content=full_reply,
                    model=resolved_model,
                )
            )
            db.commit()

            # Automatic title generation from context
            final_title = update_session_title_if_default(db, session, payload.message, full_reply)

        yield f"data: {json.dumps({'done': True, 'session_id': session.id, 'session_title': final_title}, ensure_ascii=True)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )

