"""Server-side sessions: an opaque random token in an httpOnly cookie, only its hash in the DB."""

import secrets
from datetime import timedelta

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.db import utcnow
from app.models import Session, User
from app.security.crypto import sha256_hex

COOKIE_NAME = "rag_session"
# Only write last_seen_at when it is older than this, to avoid a DB write per request.
_TOUCH_INTERVAL = timedelta(minutes=1)


def client_ip(request: Request) -> str:
    # X-Forwarded-For is applied by Uvicorn's --proxy-headers, and only for proxies listed in
    # FORWARDED_ALLOW_IPS. Reading the header here directly would let anyone spoof their IP.
    return request.client.host if request.client else ""


def create_session(db: DbSession, user: User, request: Request, response: Response) -> Session:
    token = secrets.token_urlsafe(32)
    sess = Session(
        user_id=user.id,
        token_hash=sha256_hex(token),
        user_agent=(request.headers.get("user-agent") or "")[:512],
        ip=client_ip(request),
    )
    db.add(sess)
    db.flush()
    settings = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.session_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    return sess


def clear_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def load_session(db: DbSession, request: Request) -> tuple[Session, User] | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    row = db.execute(
        select(Session, User)
        .join(User, User.id == Session.user_id)
        .where(Session.token_hash == sha256_hex(token), Session.revoked_at.is_(None))
    ).first()
    if row is None:
        return None
    sess, user = row
    now = utcnow()
    if now - sess.created_at > timedelta(days=get_settings().session_days):
        return None
    if now - sess.last_seen_at > _TOUCH_INTERVAL:
        sess.last_seen_at = now
        db.commit()
    return sess, user
