from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import func, select

from app.config import get_settings
from app.deps import CurrentAuth, Db
from app.db import utcnow
from app.models import KnowledgeBase, User, Workspace, WorkspaceSettings
from app.schemas.auth import AuthConfigOut, LoginIn, MeOut, SignupIn
from app.security.passwords import hash_password, needs_rehash, verify_password
from app.security.ratelimit import login_limiter
from app.security.sessions import clear_cookie, client_ip, create_session
from app.security.useragent import describe
from app.services import events

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_count(db: Db) -> int:
    return db.scalar(select(func.count()).select_from(User)) or 0


def signup_open(db: Db) -> bool:
    return _user_count(db) == 0 or get_settings().allow_signup


@router.get("/config", response_model=AuthConfigOut)
def auth_config(db: Db) -> AuthConfigOut:
    return AuthConfigOut(
        signup_open=signup_open(db), has_users=_user_count(db) > 0, public_host=get_settings().public_host
    )


def bootstrap_workspace(db: Db, owner_name: str) -> tuple[Workspace, KnowledgeBase]:
    """First signup: create the workspace, its settings and a starter Local knowledge base."""
    settings = get_settings()
    ws = Workspace(name=f"{owner_name}'s workspace")
    db.add(ws)
    db.flush()
    db.add(WorkspaceSettings(workspace_id=ws.id, embedding_model=settings.embedding_model))
    kb = KnowledgeBase(
        workspace_id=ws.id, name="My documents", description="Files you drop on the chat screen", runtime="local"
    )
    db.add(kb)
    db.flush()
    return ws, kb


@router.post("/signup", response_model=MeOut, status_code=status.HTTP_201_CREATED)
def signup(body: SignupIn, request: Request, response: Response, db: Db) -> User:
    first = _user_count(db) == 0
    if not first and not get_settings().allow_signup:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sign-up is closed on this server. Ask the owner for an account.")
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")

    if first:
        ws, kb = bootstrap_workspace(db, body.name)
        user = User(
            workspace_id=ws.id, email=body.email, name=body.name, password_hash=hash_password(body.password),
            role="owner", default_kb_id=kb.id,
        )
    else:
        ws = db.scalars(select(Workspace).order_by(Workspace.created_at)).first()
        assert ws is not None
        user = User(
            workspace_id=ws.id, email=body.email, name=body.name, password_hash=hash_password(body.password),
            role="member",
        )
    db.add(user)
    db.flush()
    sess = create_session(db, user, request, response)
    ip = client_ip(request)
    events.record(
        db, workspace_id=ws.id, user_id=user.id, category="login", title="Account created",
        detail=f"{describe(sess.user_agent)} · {ip}", tone="ok", ref_type="session", ref_id=sess.id, ip=ip,
    )
    db.commit()
    return user


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, request: Request, response: Response, db: Db) -> User:
    ip = client_ip(request)
    ua = request.headers.get("user-agent")
    ip_key, email_key = f"ip:{ip}", f"email:{body.email}"
    user = db.scalar(select(User).where(User.email == body.email))
    ws_id = user.workspace_id if user else db.scalar(select(Workspace.id).order_by(Workspace.created_at).limit(1))

    def fail(reason: str, code: int, message: str) -> HTTPException:
        if ws_id:
            events.record(
                db, workspace_id=ws_id, user_id=user.id if user else None, category="login",
                title="Failed sign-in attempt", detail=f"{describe(ua)} · {ip} · {reason}",
                tone="err", tag="Blocked", ip=ip,
            )
            db.commit()
        return HTTPException(code, message)

    if login_limiter.is_blocked(ip_key) or login_limiter.is_blocked(email_key):
        raise fail("too many attempts", status.HTTP_429_TOO_MANY_REQUESTS,
                   "Too many sign-in attempts. Try again in 15 minutes.")

    if not verify_password(user.password_hash if user else None, body.password) or user is None:
        login_limiter.hit(ip_key)
        login_limiter.hit(email_key)
        raise fail("wrong password" if user else "unknown email", status.HTTP_401_UNAUTHORIZED,
                   "Email or password is incorrect.")

    login_limiter.reset(email_key)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    sess = create_session(db, user, request, response)
    events.record(
        db, workspace_id=user.workspace_id, user_id=user.id, category="login", title="Signed in",
        detail=f"{describe(ua)} · {ip}", tone="ok", ref_type="session", ref_id=sess.id, ip=ip,
    )
    db.commit()
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(auth: CurrentAuth, response: Response, db: Db) -> Response:
    auth.session.revoked_at = utcnow()
    db.add(auth.session)
    db.commit()
    clear_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
