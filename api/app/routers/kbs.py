from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import case, func, select

from app.deps import CurrentAuth, Db
from app.models import Chunk, Document, KnowledgeBase, ProviderConnection
from app.rag import store
from app.schemas.kb import KbCreate, KbOut, KbPatch
from app.security.sessions import client_ip
from app.services import events
from app.services.files import delete_kb_files

router = APIRouter(prefix="/kbs", tags=["kbs"])


def _kb_rows(db: Db, workspace_id: str, kb_id: str | None = None) -> list[KbOut]:
    docs = (
        select(
            Document.kb_id,
            func.count().label("n"),
            func.sum(case((Document.status == "indexed", 1), else_=0)).label("indexed"),
        )
        .group_by(Document.kb_id)
        .subquery()
    )
    chunks = select(Chunk.kb_id, func.count().label("n")).group_by(Chunk.kb_id).subquery()
    q = (
        select(KnowledgeBase, func.coalesce(docs.c.n, 0), func.coalesce(docs.c.indexed, 0), func.coalesce(chunks.c.n, 0))
        .outerjoin(docs, docs.c.kb_id == KnowledgeBase.id)
        .outerjoin(chunks, chunks.c.kb_id == KnowledgeBase.id)
        .where(KnowledgeBase.workspace_id == workspace_id)
        .order_by(KnowledgeBase.created_at)
    )
    if kb_id is not None:
        q = q.where(KnowledgeBase.id == kb_id)
    return [
        KbOut(
            id=kb.id, name=kb.name, description=kb.description, runtime=kb.runtime, default_model=kb.default_model,
            default_connection_id=kb.default_connection_id, doc_count=d, indexed_count=i, chunk_count=c,
            created_at=kb.created_at, updated_at=kb.updated_at,
        )
        for kb, d, i, c in db.execute(q).all()
    ]


def get_kb_or_404(db: Db, workspace_id: str, kb_id: str) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    if kb is None or kb.workspace_id != workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Knowledge base not found.")
    return kb


@router.get("", response_model=list[KbOut])
def list_kbs(auth: CurrentAuth, db: Db) -> list[KbOut]:
    return _kb_rows(db, auth.workspace_id)


@router.post("", response_model=KbOut, status_code=status.HTTP_201_CREATED)
def create_kb(body: KbCreate, auth: CurrentAuth, request: Request, db: Db) -> KbOut:
    kb = KnowledgeBase(
        workspace_id=auth.workspace_id, name=body.name, description=body.description, runtime=body.runtime
    )
    db.add(kb)
    db.flush()
    events.record(
        db, workspace_id=auth.workspace_id, user_id=auth.user.id, category="doc",
        title=f"Created knowledge base {kb.name}", detail="Local" if kb.runtime == "local" else "Cloud",
        ref_type="kb", ref_id=kb.id, ip=client_ip(request),
    )
    db.commit()
    return _kb_rows(db, auth.workspace_id, kb.id)[0]


@router.get("/{kb_id}", response_model=KbOut)
def get_kb(kb_id: str, auth: CurrentAuth, db: Db) -> KbOut:
    get_kb_or_404(db, auth.workspace_id, kb_id)
    return _kb_rows(db, auth.workspace_id, kb_id)[0]


@router.patch("/{kb_id}", response_model=KbOut)
def patch_kb(kb_id: str, body: KbPatch, auth: CurrentAuth, request: Request, db: Db) -> KbOut:
    kb = get_kb_or_404(db, auth.workspace_id, kb_id)
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Give the knowledge base a name.")
    if changes.get("default_connection_id"):
        conn = db.get(ProviderConnection, changes["default_connection_id"])
        if conn is None or conn.workspace_id != auth.workspace_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Provider connection not found.")
    details = []
    for field, value in changes.items():
        if value is None and field != "default_connection_id":
            continue
        old = getattr(kb, field)
        if old != value:
            setattr(kb, field, value)
            if field in ("name", "runtime"):
                details.append(f"{field}: {old} → {value}")
    if details:
        events.record(
            db, workspace_id=auth.workspace_id, user_id=auth.user.id, category="doc",
            title=f"Updated knowledge base {kb.name}", detail=" · ".join(details),
            ref_type="kb", ref_id=kb.id, ip=client_ip(request),
        )
    db.commit()
    return _kb_rows(db, auth.workspace_id, kb.id)[0]


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_kb(kb_id: str, auth: CurrentAuth, request: Request, db: Db) -> Response:
    kb = get_kb_or_404(db, auth.workspace_id, kb_id)
    name = kb.name
    store.fts_delete_kb(db, kb.id)
    db.delete(kb)  # cascades to documents and chunks
    events.record(
        db, workspace_id=auth.workspace_id, user_id=auth.user.id, category="doc",
        title=f"Deleted knowledge base {name}", tone="err", ip=client_ip(request),
    )
    db.commit()
    store.delete_collection(kb_id)
    delete_kb_files(kb_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
