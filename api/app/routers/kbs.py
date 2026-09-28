from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from app.deps import CurrentAuth, Db
from app.models import Chunk, Document, KnowledgeBase

router = APIRouter(prefix="/kbs", tags=["kbs"])


class KbOut(BaseModel):
    id: str
    name: str
    description: str
    runtime: str
    default_model: str
    doc_count: int
    chunk_count: int
    updated_at: datetime


@router.get("", response_model=list[KbOut])
def list_kbs(auth: CurrentAuth, db: Db) -> list[KbOut]:
    docs = (
        select(Document.kb_id, func.count().label("n")).group_by(Document.kb_id).subquery()
    )
    chunks = select(Chunk.kb_id, func.count().label("n")).group_by(Chunk.kb_id).subquery()
    rows = db.execute(
        select(KnowledgeBase, func.coalesce(docs.c.n, 0), func.coalesce(chunks.c.n, 0))
        .outerjoin(docs, docs.c.kb_id == KnowledgeBase.id)
        .outerjoin(chunks, chunks.c.kb_id == KnowledgeBase.id)
        .where(KnowledgeBase.workspace_id == auth.workspace_id)
        .order_by(KnowledgeBase.created_at)
    ).all()
    return [
        KbOut(
            id=kb.id, name=kb.name, description=kb.description, runtime=kb.runtime,
            default_model=kb.default_model, doc_count=d, chunk_count=c, updated_at=kb.updated_at,
        )
        for kb, d, c in rows
    ]
