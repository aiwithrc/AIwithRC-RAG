"""Shared answers: an unguessable public link to a frozen snapshot of one answer (+ its sources).

Only the snapshot is ever exposed: never the chat, other messages or other documents.
"""

import html
import json
import re
import secrets
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.config import get_settings
from app.db import utcnow
from app.deps import CurrentAuth, Db
from app.models import Chat, KnowledgeBase, Message, Share
from app.security.sessions import client_ip
from app.services import events

router = APIRouter(tags=["shares"])
public = APIRouter(tags=["public"])


class ShareIn(BaseModel):
    include_sources: bool = True


class ShareOut(BaseModel):
    id: str
    token: str
    url: str
    include_sources: bool


class PublicShare(BaseModel):
    question: str
    answer: str
    confidence: str | None
    model: str | None
    kb_name: str | None
    answered_at: str
    citations: list[dict]
    include_sources: bool
    project_url: str


def share_url(token: str) -> str:
    return f"{get_settings().public_url}/s/{token}"


def _out(s: Share) -> ShareOut:
    return ShareOut(id=s.id, token=s.token, url=share_url(s.token), include_sources=s.include_sources)


def _owned_share(db: Db, auth: CurrentAuth, share_id: str) -> Share:
    s = db.get(Share, share_id)
    msg = db.get(Message, s.message_id) if s and s.message_id else None
    chat = db.get(Chat, msg.chat_id) if msg else None
    if s is None or s.revoked_at is not None or chat is None or chat.user_id != auth.user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Share not found.")
    return s


@router.post("/messages/{message_id}/share", response_model=ShareOut)
def share_message(message_id: str, body: ShareIn, auth: CurrentAuth, request: Request, db: Db) -> ShareOut:
    msg = db.get(Message, message_id)
    chat = db.get(Chat, msg.chat_id) if msg else None
    if msg is None or chat is None or chat.user_id != auth.user.id or msg.role != "assistant":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Answer not found.")
    if msg.error or not msg.content:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only finished answers can be shared.")

    existing = db.scalars(
        select(Share).where(Share.message_id == msg.id, Share.revoked_at.is_(None)).order_by(Share.created_at.desc())
    ).first()
    if existing is not None:
        existing.include_sources = body.include_sources
        db.commit()
        return _out(existing)

    question = db.scalars(
        select(Message)
        .where(Message.chat_id == chat.id, Message.role == "user", Message.created_at <= msg.created_at)
        .order_by(Message.created_at.desc())
    ).first()
    kb = db.get(KnowledgeBase, chat.kb_id) if chat.kb_id else None
    snapshot = {
        "question": question.content if question else chat.title,
        "answer": msg.content,
        "confidence": msg.confidence,
        "model": msg.model,
        "kb_name": kb.name if kb else None,
        "answered_at": msg.created_at.isoformat(),
        "citations": json.loads(msg.citations_json or "[]"),
    }
    share = Share(
        token=secrets.token_urlsafe(9), message_id=msg.id, include_sources=body.include_sources,
        snapshot_json=json.dumps(snapshot),
    )
    db.add(share)
    db.flush()
    events.record(
        db, workspace_id=auth.workspace_id, user_id=auth.user.id, category="chat", title="Shared an answer",
        detail=f"{chat.title} · {share_url(share.token)}", ref_type="chat", ref_id=chat.id, ip=client_ip(request),
    )
    db.commit()
    return _out(share)


@router.patch("/shares/{share_id}", response_model=ShareOut)
def update_share(share_id: str, body: ShareIn, auth: CurrentAuth, db: Db) -> ShareOut:
    s = _owned_share(db, auth, share_id)
    s.include_sources = body.include_sources
    db.commit()
    return _out(s)


@router.delete("/shares/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share(share_id: str, auth: CurrentAuth, request: Request, db: Db) -> Response:
    s = _owned_share(db, auth, share_id)
    s.revoked_at = utcnow()
    events.record(
        db, workspace_id=auth.workspace_id, user_id=auth.user.id, category="chat", title="Stopped sharing an answer",
        detail=share_url(s.token), ip=client_ip(request),
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def load_public(db: Db, token: str) -> PublicShare | None:
    s = db.scalar(select(Share).where(Share.token == token, Share.revoked_at.is_(None)))
    if s is None:
        return None
    snap = json.loads(s.snapshot_json)
    return PublicShare(
        question=snap.get("question", ""), answer=snap.get("answer", ""), confidence=snap.get("confidence"),
        model=snap.get("model"), kb_name=snap.get("kb_name"), answered_at=snap.get("answered_at", ""),
        citations=snap.get("citations", []) if s.include_sources else [],
        include_sources=s.include_sources, project_url=get_settings().project_url,
    )


@router.get("/public/shares/{token}", response_model=PublicShare)
def get_public_share(token: str, db: Db, response: Response) -> PublicShare:
    """No auth: the shared snapshot only."""
    response.headers["X-Robots-Tag"] = "noindex"
    share = load_public(db, token)
    if share is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This shared answer isn't available.")
    return share


def _plain(markdown: str) -> str:
    text = re.sub(r"\[\d+\]", "", markdown)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


@public.get("/s/{token}", include_in_schema=False)
def public_share_page(token: str, db: Db) -> HTMLResponse:
    """The SPA page for /s/{token}, with OpenGraph tags so links preview nicely. Never indexed."""
    settings = get_settings()
    share = load_public(db, token)
    if share:
        title = share.question[:120]
        desc = _plain(share.answer)[:200]
    else:
        title, desc = "Shared answer not available", "This shared answer was removed or the link is wrong."
    meta = (
        f'<meta name="robots" content="noindex, nofollow" />'
        f'<meta property="og:type" content="article" />'
        f'<meta property="og:site_name" content="AIwithRC-RAG" />'
        f'<meta property="og:title" content="{html.escape(title)}" />'
        f'<meta property="og:description" content="{html.escape(desc)}" />'
        f'<meta property="og:url" content="{html.escape(share_url(token))}" />'
        f'<meta name="twitter:card" content="summary" />'
    )
    index = Path(settings.web_dist) / "index.html"
    page = (
        index.read_text(encoding="utf-8")
        if index.exists()
        else "<!doctype html><html><head><title>AIwithRC-RAG</title></head><body><div id=root></div></body></html>"
    )
    page = page.replace("<title>AIwithRC-RAG</title>", f"<title>{html.escape(title)} · AIwithRC-RAG</title>{meta}", 1)
    return HTMLResponse(page, status_code=200 if share else 404, headers={"X-Robots-Tag": "noindex", "Cache-Control": "no-cache"})
