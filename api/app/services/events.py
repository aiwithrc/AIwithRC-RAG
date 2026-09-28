"""Write rows for the History screen. Call `record()` for every user-visible action."""

from sqlalchemy.orm import Session as DbSession

from app.models import Event

CATEGORIES = {"chat", "doc", "login", "key", "settings"}


def record(
    db: DbSession,
    *,
    workspace_id: str,
    category: str,
    title: str,
    detail: str = "",
    user_id: str | None = None,
    tone: str | None = None,
    tag: str | None = None,
    ref_type: str | None = None,
    ref_id: str | None = None,
    ip: str | None = None,
) -> Event:
    assert category in CATEGORIES, category
    ev = Event(
        workspace_id=workspace_id,
        user_id=user_id,
        category=category,
        title=title,
        detail=detail,
        tone=tone,
        tag=tag,
        ref_type=ref_type,
        ref_id=ref_id,
        ip=ip,
    )
    db.add(ev)
    return ev
