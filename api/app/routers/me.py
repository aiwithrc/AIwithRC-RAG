from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select, update

from app.deps import CurrentAuth, Db
from app.db import utcnow
from app.models import KnowledgeBase, Session, User
from app.schemas.auth import MeOut, MePatch, PasswordChangeIn, SessionOut
from app.security.passwords import hash_password, verify_password
from app.security.sessions import clear_cookie, client_ip
from app.security.useragent import describe
from app.services import events

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=MeOut)
def get_me(auth: CurrentAuth) -> User:
    return auth.user


@router.patch("", response_model=MeOut)
def patch_me(body: MePatch, auth: CurrentAuth, request: Request, db: Db) -> User:
    user = auth.user
    changes = body.model_dump(exclude_unset=True)
    profile_changed = False

    if "email" in changes and changes["email"] != user.email:
        if db.scalar(select(User).where(User.email == changes["email"], User.id != user.id)):
            raise HTTPException(status.HTTP_409_CONFLICT, "Another account already uses this email.")
        user.email = changes["email"]
        profile_changed = True
    if "name" in changes and changes["name"] != user.name:
        user.name = changes["name"]
        profile_changed = True
    if "theme" in changes:
        user.theme = changes["theme"]
    if "default_kb_id" in changes:
        kb_id = changes["default_kb_id"]
        if kb_id is not None and not db.scalar(
            select(KnowledgeBase.id).where(KnowledgeBase.id == kb_id, KnowledgeBase.workspace_id == user.workspace_id)
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Knowledge base not found.")
        user.default_kb_id = kb_id

    if profile_changed:
        events.record(
            db, workspace_id=user.workspace_id, user_id=user.id, category="settings", title="Profile updated",
            detail=f"{user.name} · {user.email}", ip=client_ip(request),
        )
    db.add(user)
    db.commit()
    return user


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: PasswordChangeIn, auth: CurrentAuth, request: Request, db: Db) -> Response:
    user = auth.user
    if not verify_password(user.password_hash, body.current):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect.")
    user.password_hash = hash_password(body.new)
    db.add(user)
    ip = client_ip(request)
    events.record(
        db, workspace_id=user.workspace_id, user_id=user.id, category="login", title="Password changed",
        detail=f"{describe(auth.session.user_agent)} · {ip}", ip=ip,
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _active_sessions(db: Db, user_id: str) -> list[Session]:
    return list(
        db.scalars(
            select(Session)
            .where(Session.user_id == user_id, Session.revoked_at.is_(None))
            .order_by(Session.last_seen_at.desc())
        )
    )


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(auth: CurrentAuth, db: Db) -> list[SessionOut]:
    return [
        SessionOut(
            id=s.id, device=describe(s.user_agent), ip=s.ip, created_at=s.created_at,
            last_seen_at=s.last_seen_at, current=s.id == auth.session.id,
        )
        for s in _active_sessions(db, auth.user.id)
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(session_id: str, auth: CurrentAuth, request: Request, db: Db) -> Response:
    sess = db.scalar(
        select(Session).where(Session.id == session_id, Session.user_id == auth.user.id, Session.revoked_at.is_(None))
    )
    if sess is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found.")
    if sess.id == auth.session.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Use Sign out to end this session.")
    sess.revoked_at = utcnow()
    events.record(
        db, workspace_id=auth.workspace_id, user_id=auth.user.id, category="login", title="Session signed out",
        detail=f"{describe(sess.user_agent)} · {sess.ip}", ip=client_ip(request),
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/sessions", status_code=status.HTTP_204_NO_CONTENT)
def revoke_other_sessions(
    auth: CurrentAuth, request: Request, db: Db, others: bool = Query(False)
) -> Response:
    if not others:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Pass ?others=true to sign out all other sessions.")
    result = db.execute(
        update(Session)
        .where(Session.user_id == auth.user.id, Session.id != auth.session.id, Session.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    n = result.rowcount or 0
    if n:
        events.record(
            db, workspace_id=auth.workspace_id, user_id=auth.user.id, category="login",
            title="Signed out all other sessions", detail=f"{n} session{'s' if n != 1 else ''} ended",
            ip=client_ip(request),
        )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(auth: CurrentAuth, request: Request, response: Response, db: Db) -> Response:
    user = auth.user
    if user.role == "owner":
        owners = db.scalar(
            select(func.count()).select_from(User).where(User.workspace_id == user.workspace_id, User.role == "owner")
        )
        if (owners or 0) <= 1:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "You're the only owner of this workspace. Make someone else an owner first, "
                "or reset the server with the CLI.",
            )
    events.record(
        db, workspace_id=user.workspace_id, user_id=None, category="login", title="Account deleted",
        detail=user.email, tone="err", ip=client_ip(request),
    )
    db.delete(user)
    db.commit()
    clear_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
