from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Optional

from sqlalchemy.orm import Session

from backend.models import User, UserSession


def generate_salt() -> str:
    return secrets.token_hex(16)


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    ).hex()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    actual_hash = hash_password(password, salt)
    return hmac.compare_digest(actual_hash, expected_hash)


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email.strip().lower()).first()


def register_user(db: Session, email: str, password: str) -> User:
    cleaned_email = email.strip().lower()
    existing = get_user_by_email(db, cleaned_email)
    if existing:
        raise ValueError("Este email ja esta cadastrado.")

    salt = generate_salt()
    pwd_hash = hash_password(password, salt)

    user = User(
        email=cleaned_email,
        password_hash=pwd_hash,
        salt=salt,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> Optional[User]:
    cleaned_email = email.strip().lower()
    user = get_user_by_email(db, cleaned_email)
    if not user:
        return None
    if not verify_password(password, user.salt, user.password_hash):
        return None
    return user


def create_session(db: Session, user_id: int) -> UserSession:
    token = generate_session_token()
    session = UserSession(token=token, user_id=user_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_user_by_token(db: Session, token: str) -> Optional[User]:
    if not token:
        return None
    session = db.query(UserSession).filter(UserSession.token == token).first()
    if not session:
        return None
    return db.query(User).filter(User.id == session.user_id).first()


def delete_session(db: Session, token: str) -> bool:
    if not token:
        return False
    session = db.query(UserSession).filter(UserSession.token == token).first()
    if not session:
        return False
    db.delete(session)
    db.commit()
    return True
