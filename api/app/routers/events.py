"""History: the workspace activity log, with tabs, search and CSV export."""

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from app.deps import CurrentAuth, Db
from app.models import Chat, Document, Event, User

router = APIRouter(tags=["events"])

CATEGORIES = ("chat", "doc", "login", "key", "settings")


class EventOut(BaseModel):
    id: str
    category: str
    title: str
    detail: str
    tone: str | None
    tag: str | None
    link: str | None
    user_name: str | None
    ip: str | None
    created_at: datetime


class EventPage(BaseModel):
    items: list[EventOut]
    counts: dict[str, int]
    next_cursor: str | None


def _query(auth: CurrentAuth, category: str | None, q: str | None):
    stmt = select(Event).where(Event.workspace_id == auth.workspace_id)
    if category and category in CATEGORIES:
        stmt = stmt.where(Event.category == category)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Event.title.ilike(like), Event.detail.ilike(like)))
    return stmt


def _link(db: Db, ev: Event, auth: CurrentAuth) -> str | None:
    if ev.ref_type == "chat" and ev.ref_id:
        chat = db.get(Chat, ev.ref_id)
        return f"/c/{ev.ref_id}" if chat is not None and chat.user_id == auth.user.id else None
    if ev.ref_type == "document" and ev.ref_id:
        doc = db.get(Document, ev.ref_id)
        return f"/kbs/{doc.kb_id}" if doc else None
    if ev.ref_type == "kb" and ev.ref_id:
        return f"/kbs/{ev.ref_id}"
    if ev.category == "key":
        return "/keys"
    if ev.category == "settings":
        return "/prompt" if "Prompt" in ev.title else "/settings" if "Profile" not in ev.title else "/profile"
    if ev.category == "login":
        return "/profile"
    return None


def _out(db: Db, ev: Event, auth: CurrentAuth, names: dict[str, str]) -> EventOut:
    tag = ev.tag
    if ev.ref_type == "session" and ev.ref_id == auth.session.id:
        tag = "This device"
    return EventOut(
        id=ev.id, category=ev.category, title=ev.title, detail=ev.detail, tone=ev.tone if tag else None, tag=tag,
        link=_link(db, ev, auth), user_name=names.get(ev.user_id or ""), ip=ev.ip, created_at=ev.created_at,
    )


@router.get("/events", response_model=EventPage)
def list_events(
    auth: CurrentAuth, db: Db, category: str | None = None, q: str | None = None,
    cursor: str | None = Query(None, description="created_at of the last item seen (ISO)"), limit: int = 100,
) -> EventPage:
    stmt = _query(auth, category, q)
    if cursor:
        stmt = stmt.where(Event.created_at < datetime.fromisoformat(cursor))
    limit = max(1, min(limit, 300))
    rows = list(db.scalars(stmt.order_by(Event.created_at.desc()).limit(limit + 1)))
    names = {u.id: u.name for u in db.scalars(select(User).where(User.workspace_id == auth.workspace_id))}

    counts_stmt = select(Event.category, func.count()).where(Event.workspace_id == auth.workspace_id)
    if q and q.strip():
        like = f"%{q.strip()}%"
        counts_stmt = counts_stmt.where(or_(Event.title.ilike(like), Event.detail.ilike(like)))
    by_cat = dict(db.execute(counts_stmt.group_by(Event.category)).all())
    counts = {"all": sum(by_cat.values()), **{c: by_cat.get(c, 0) for c in CATEGORIES}}
    more = len(rows) > limit
    rows = rows[:limit]
    return EventPage(
        items=[_out(db, e, auth, names) for e in rows], counts=counts,
        next_cursor=rows[-1].created_at.isoformat() if more and rows else None,
    )


@router.get("/events.csv")
def export_events(auth: CurrentAuth, db: Db, category: str | None = None, q: str | None = None) -> StreamingResponse:
    names = {u.id: u.name for u in db.scalars(select(User).where(User.workspace_id == auth.workspace_id))}
    rows = db.scalars(_query(auth, category, q).order_by(Event.created_at.desc()))
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["time_utc", "category", "title", "detail", "tag", "user", "ip"])
    for e in rows:
        w.writerow([e.created_at.isoformat(timespec="seconds"), e.category, e.title, e.detail, e.tag or "",
                    names.get(e.user_id or "", ""), e.ip or ""])
    data = "﻿" + buf.getvalue()  # BOM so Excel opens UTF-8 correctly
    return StreamingResponse(
        iter([data]), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="aiwithrc-rag-history.csv"'},
    )
