from __future__ import annotations

import re
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from backend.models import ChatMessage, ChatSession


DEFAULT_SESSION_TITLE = "Nova conversa"


def clean_title_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^[`\"'#*>-]+", "", cleaned)
    cleaned = re.sub(r"[`\"']+$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def generate_title(user_message: str, assistant_reply: str = "") -> str:
    text = clean_title_text(user_message)
    if not text and assistant_reply:
        text = clean_title_text(assistant_reply)

    if not text:
        return DEFAULT_SESSION_TITLE

    # Remove common conversational prefixes in Portuguese / English
    prefix_patterns = [
        r"^(ola|olá|oi|ei|hello|hi|hey|bom dia|boa tarde|boa noite)[,\.\!\? ]*",
        r"^(por favor|voce pode|você pode|poderia|me ajude a|me explica|explique|o que e|o que é|como|how to|what is|tell me)[,\.\!\? ]*",
    ]
    candidate = text
    for pat in prefix_patterns:
        candidate = re.sub(pat, "", candidate, flags=re.IGNORECASE).strip()

    if not candidate:
        candidate = text

    # Capitalize first letter
    words = candidate.split()
    if len(words) > 6:
        candidate = " ".join(words[:6])

    candidate = candidate[:50].strip(" ,.-:;!?")
    if candidate:
        candidate = candidate[0].upper() + candidate[1:]
        return candidate

    return DEFAULT_SESSION_TITLE


def create_session(
    db: Session,
    title: Optional[str] = None,
    user_id: Optional[int] = None,
    session_id: Optional[str] = None,
) -> ChatSession:
    sid = session_id or uuid.uuid4().hex[:12]
    session_title = title.strip() if title and title.strip() else DEFAULT_SESSION_TITLE
    chat_session = ChatSession(id=sid, title=session_title, user_id=user_id)
    db.add(chat_session)
    db.commit()
    db.refresh(chat_session)
    return chat_session


def get_or_create_session(
    db: Session,
    session_id: Optional[str] = None,
    user_id: Optional[int] = None,
) -> ChatSession:
    if session_id:
        existing = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if existing:
            return existing
        return create_session(db, session_id=session_id, user_id=user_id)
    return create_session(db, user_id=user_id)


def list_sessions(db: Session, user_id: Optional[int] = None) -> list[ChatSession]:
    query = db.query(ChatSession)
    if user_id is not None:
        query = query.filter((ChatSession.user_id == user_id) | (ChatSession.user_id.is_(None)))
    return query.order_by(ChatSession.updated_at.desc(), ChatSession.created_at.desc()).all()


def get_session(db: Session, session_id: str) -> Optional[ChatSession]:
    return db.query(ChatSession).filter(ChatSession.id == session_id).first()


def get_session_messages(db: Session, session_id: str) -> list[ChatMessage]:
    return (
        db.query(ChatMessage)
        .filter(ChatMessage.session_key == session_id)
        .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
        .all()
    )


def delete_session(db: Session, session_id: str) -> bool:
    session = get_session(db, session_id)
    if not session:
        return False

    db.query(ChatMessage).filter(ChatMessage.session_key == session_id).delete()
    db.delete(session)
    db.commit()
    return True


def update_session_title_if_default(
    db: Session,
    session: ChatSession,
    user_message: str,
    assistant_reply: str = "",
) -> str:
    if session.title in (DEFAULT_SESSION_TITLE, "default", "", None):
        new_title = generate_title(user_message, assistant_reply)
        session.title = new_title
        db.commit()
        db.refresh(session)
        return new_title
    return session.title
