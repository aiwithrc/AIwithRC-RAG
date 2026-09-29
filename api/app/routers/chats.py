"""Chats and streaming answers.

POST /chats/{id}/messages and POST /messages/{id}/regenerate answer over Server-Sent Events:
  event: start   {"user": MessageOut}              (ask only)
  event: status  {"stage": "searching" | "thinking" | "answering"}
  event: token   {"t": "..."}                        (answer text as it streams, <think> removed)
  event: done    {"message": MessageOut}             (final content with renumbered citations)
  event: followups {"message_id", "followups": [...]} (after done; suggested next questions)
  event: error   {"message": MessageOut, "detail"}   (saved with its error so the thread can show it)
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from app.db import SessionLocal, utcnow
from app.deps import CurrentAuth, Db
from app.models import Chat, Event, KnowledgeBase, Message, ProviderConnection, WorkspaceSettings
from app.providers.auto import resolve_model
from app.providers.base import ProviderError, runtime_for
from app.providers.chat import ChatTarget
from app.rag import answer
from app.routers.kbs import get_kb_or_404
from app.schemas.chat import AskIn, ChatCreate, ChatDetail, ChatOut, MessageOut, RegenerateIn
from app.security.crypto import decrypt
from app.security.sessions import client_ip
from app.services import events

router = APIRouter(tags=["chats"])
log = logging.getLogger("aiwithrc.chat")

HISTORY_MESSAGES = 4


# ---- serialisation ----

def message_out(m: Message, conns: dict[str, ProviderConnection] | None = None) -> MessageOut:
    conn = (conns or {}).get(m.connection_id or "")
    return MessageOut(
        id=m.id, role=m.role, content=m.content, model=m.model, connection_id=m.connection_id,
        connection_name=conn.name if conn else None, runtime=runtime_for(conn.api_base) if conn else None,
        confidence=m.confidence, citations=json.loads(m.citations_json or "[]"),
        followups=json.loads(m.followups_json or "[]"), error=m.error, created_at=m.created_at,
    )


def _conns(db: Db, workspace_id: str) -> dict[str, ProviderConnection]:
    return {c.id: c for c in db.scalars(select(ProviderConnection).where(ProviderConnection.workspace_id == workspace_id))}


def chat_out(db: Db, chat: Chat) -> ChatOut:
    kb = db.get(KnowledgeBase, chat.kb_id) if chat.kb_id else None
    n = db.scalar(select(func.count()).select_from(Message).where(Message.chat_id == chat.id)) or 0
    return ChatOut(
        id=chat.id, title=chat.title, kb_id=chat.kb_id, kb_name=kb.name if kb else None, message_count=n,
        created_at=chat.created_at, updated_at=chat.updated_at,
    )


def _chat_or_404(db: Db, auth: CurrentAuth, chat_id: str) -> Chat:
    chat = db.get(Chat, chat_id)
    if chat is None or chat.user_id != auth.user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat not found.")
    return chat


# ---- CRUD ----

@router.get("/chats", response_model=list[ChatOut])
def list_chats(auth: CurrentAuth, db: Db, limit: int = 50) -> list[ChatOut]:
    chats = db.scalars(
        select(Chat).where(Chat.user_id == auth.user.id).order_by(Chat.updated_at.desc()).limit(min(limit, 200))
    )
    return [chat_out(db, c) for c in chats]


@router.post("/chats", response_model=ChatOut, status_code=status.HTTP_201_CREATED)
def create_chat(body: ChatCreate, auth: CurrentAuth, db: Db) -> ChatOut:
    kb = get_kb_or_404(db, auth.workspace_id, body.kb_id)
    chat = Chat(workspace_id=auth.workspace_id, user_id=auth.user.id, kb_id=kb.id, title="New chat")
    db.add(chat)
    db.commit()
    return chat_out(db, chat)


@router.get("/chats/{chat_id}", response_model=ChatDetail)
def get_chat(chat_id: str, auth: CurrentAuth, db: Db) -> ChatDetail:
    chat = _chat_or_404(db, auth, chat_id)
    msgs = db.scalars(select(Message).where(Message.chat_id == chat.id).order_by(Message.created_at, Message.role.desc()))
    conns = _conns(db, auth.workspace_id)
    return ChatDetail(chat=chat_out(db, chat), messages=[message_out(m, conns) for m in msgs])


@router.delete("/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(chat_id: str, auth: CurrentAuth, db: Db) -> Response:
    chat = _chat_or_404(db, auth, chat_id)
    for ev in db.scalars(select(Event).where(Event.ref_type == "chat", Event.ref_id == chat.id)):
        db.delete(ev)
    db.delete(chat)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---- answering ----

def _resolve_target(
    db: Db, auth: CurrentAuth, kb: KnowledgeBase, connection_id: str | None, model: str | None
) -> tuple[ProviderConnection, str, ChatTarget]:
    conns = list(
        db.scalars(
            select(ProviderConnection)
            .where(ProviderConnection.workspace_id == auth.workspace_id)
            .order_by(ProviderConnection.created_at)
        )
    )
    if not conns:
        raise HTTPException(status.HTTP_409_CONFLICT, "Connect a model on the API keys screen first.")
    wanted = connection_id or kb.default_connection_id
    conn = next((c for c in conns if c.id == wanted), None) if wanted else None
    if conn is None and connection_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That model provider isn't connected any more.")
    conn = conn or next((c for c in conns if json.loads(c.models_json or "[]")), conns[0])
    models = json.loads(conn.models_json or "[]")
    chosen = model or resolve_model(conn.selected_model, models)
    if not chosen:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{conn.name} has no models. Refresh it on the API keys screen.")

    ws = db.get(WorkspaceSettings, auth.workspace_id)
    if kb.runtime == "local" and (ws is None or ws.keep_local) and runtime_for(conn.api_base) == "cloud":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{kb.name} is a Local knowledge base and \"Keep local knowledge bases local\" is on, so its passages "
            f"can't be sent to {conn.name}. Pick a local model, or change the setting.",
        )
    try:
        key = decrypt(conn.api_key_enc) if conn.api_key_enc else ""
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, f"The saved key for {conn.name} can't be read. Add it again.") from e
    target = ChatTarget(
        api_base=conn.api_base, api_key=key, kind=conn.kind, model=chosen, local=runtime_for(conn.api_base) == "local"
    )
    return conn, chosen, target


def _settings(db: Db, workspace_id: str) -> answer.Settings:
    ws = db.get(WorkspaceSettings, workspace_id)
    if ws is None:
        return answer.Settings()
    return answer.Settings(top_k=ws.top_k, hybrid=ws.hybrid, rerank=ws.rerank, embedding_model=ws.embedding_model)


def _history(db: Db, chat_id: str, before: Message | None = None) -> list[dict]:
    q = select(Message).where(Message.chat_id == chat_id, Message.error.is_(None))
    if before is not None:
        q = q.where(Message.created_at < before.created_at)
    rows = list(db.scalars(q.order_by(Message.created_at.desc()).limit(HISTORY_MESSAGES)))
    return [{"role": m.role, "content": m.content} for m in reversed(rows) if m.content]


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _touch_chat_event(db, chat: Chat, kb_name: str, ip: str) -> None:
    """One History row per chat, kept current: title, KB and message count."""
    n = db.scalar(select(func.count()).select_from(Message).where(Message.chat_id == chat.id)) or 0
    detail = f"{kb_name} · {n} message{'s' if n != 1 else ''}"
    ev = db.scalars(select(Event).where(Event.ref_type == "chat", Event.ref_id == chat.id)).first()
    if ev is None:
        events.record(
            db, workspace_id=chat.workspace_id, user_id=chat.user_id, category="chat", title=chat.title,
            detail=detail, ref_type="chat", ref_id=chat.id, ip=ip,
        )
    else:
        ev.title, ev.detail, ev.created_at = chat.title, detail, utcnow()


async def _answer_stream(
    *, chat_id: str, kb_id: str, kb_name: str, question: str, history: list[dict], settings: answer.Settings,
    target: ChatTarget, conn: ProviderConnection, assistant_id: str | None, ip: str, first: dict | None,
) -> AsyncIterator[str]:
    """Runs the pipeline and saves the assistant message (new, or updated in place when regenerating)."""
    if first:
        yield _sse("start", first)
    streamed = ""
    result: answer.Result | None = None
    error: str | None = None
    saved: MessageOut | None = None
    try:
        async for kind, data in answer.run(target, kb_id, kb_name, question, history, settings):
            if kind == "token":
                streamed += str(data)
                yield _sse("token", {"t": data})
            elif kind == "status":
                yield _sse("status", data)  # type: ignore[arg-type]
            elif kind == "result":
                result = data  # type: ignore[assignment]
                saved = await run_in_threadpool(
                    _save, chat_id, assistant_id, conn, target.model, result, streamed, None, kb_name, ip
                )
                yield _sse("done", {"message": saved.model_dump(mode="json")})
            elif kind == "followups" and saved is not None and data:
                await run_in_threadpool(_save_followups, saved.id, data)
                yield _sse("followups", {"message_id": saved.id, "followups": data})
        if saved is not None:
            return
    except ProviderError as e:
        error = str(e)
    except asyncio.CancelledError:  # client went away: keep what we have
        if saved is None:
            error = "Stopped before the answer finished."
            await run_in_threadpool(_save, chat_id, assistant_id, conn, target.model, None, streamed, error, kb_name, ip)
        raise
    except Exception:
        log.exception("Answering failed")
        error = "Something went wrong while answering. Try again."

    if saved is not None:  # answer already delivered; only the follow-up suggestions failed
        return
    saved = await run_in_threadpool(_save, chat_id, assistant_id, conn, target.model, result, streamed, error, kb_name, ip)
    if error:
        yield _sse("error", {"detail": error, "message": saved.model_dump(mode="json")})
    else:
        yield _sse("done", {"message": saved.model_dump(mode="json")})


def _save(
    chat_id: str, assistant_id: str | None, conn: ProviderConnection, model: str, result: "answer.Result | None",
    streamed: str, error: str | None, kb_name: str, ip: str,
) -> MessageOut:
    with SessionLocal() as db:
        msg = db.get(Message, assistant_id) if assistant_id else None
        if msg is None:
            msg = Message(chat_id=chat_id, role="assistant")
            db.add(msg)
        msg.model, msg.connection_id = model, conn.id
        if result is not None and error is None:
            msg.content, msg.confidence, msg.error = result.content, result.confidence, None
            msg.citations_json, msg.followups_json = json.dumps(result.citations), json.dumps(result.followups)
        else:
            from app.rag.cite import strip_think

            msg.content, msg.confidence, msg.error = strip_think(streamed), None, error
            msg.citations_json, msg.followups_json = "[]", "[]"
        chat = db.get(Chat, chat_id)
        if chat is not None:
            chat.updated_at = utcnow()
            db.flush()
            _touch_chat_event(db, chat, kb_name, ip)
        db.commit()
        db.refresh(msg)
        return message_out(msg, {conn.id: conn})


def _save_followups(message_id: str, followups: list[str]) -> None:
    with SessionLocal() as db:
        msg = db.get(Message, message_id)
        if msg is not None:
            msg.followups_json = json.dumps(followups)
            db.commit()


def _streaming(gen: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        gen, media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.post("/chats/{chat_id}/messages")
def ask(chat_id: str, body: AskIn, auth: CurrentAuth, request: Request, db: Db) -> StreamingResponse:
    chat = _chat_or_404(db, auth, chat_id)
    if chat.kb_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This chat's knowledge base was deleted. Start a new chat.")
    kb = get_kb_or_404(db, auth.workspace_id, chat.kb_id)
    question = body.content.strip()
    if not question:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Type a question.")
    conn, _, target = _resolve_target(db, auth, kb, body.connection_id, body.model)

    history = _history(db, chat.id)
    user = Message(chat_id=chat.id, role="user", content=question)
    db.add(user)
    if chat.title == "New chat":
        chat.title = question if len(question) <= 60 else question[:57].rstrip() + "…"
    chat.updated_at = utcnow()
    db.commit()
    return _streaming(
        _answer_stream(
            chat_id=chat.id, kb_id=kb.id, kb_name=kb.name, question=question, history=history,
            settings=_settings(db, auth.workspace_id), target=target, conn=conn, assistant_id=None,
            ip=client_ip(request), first={"user": message_out(user).model_dump(mode="json")},
        )
    )


@router.post("/messages/{message_id}/regenerate")
def regenerate(message_id: str, body: RegenerateIn, auth: CurrentAuth, request: Request, db: Db) -> StreamingResponse:
    msg = db.get(Message, message_id)
    if msg is None or msg.role != "assistant":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Answer not found.")
    chat = _chat_or_404(db, auth, msg.chat_id)
    if chat.kb_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This chat's knowledge base was deleted. Start a new chat.")
    kb = get_kb_or_404(db, auth.workspace_id, chat.kb_id)
    question_msg = db.scalars(
        select(Message)
        .where(Message.chat_id == chat.id, Message.role == "user", Message.created_at <= msg.created_at)
        .order_by(Message.created_at.desc())
    ).first()
    if question_msg is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Couldn't find the question for this answer.")
    conn, _, target = _resolve_target(db, auth, kb, body.connection_id, body.model)
    return _streaming(
        _answer_stream(
            chat_id=chat.id, kb_id=kb.id, kb_name=kb.name, question=question_msg.content,
            history=_history(db, chat.id, before=question_msg), settings=_settings(db, auth.workspace_id),
            target=target, conn=conn, assistant_id=msg.id, ip=client_ip(request), first=None,
        )
    )
