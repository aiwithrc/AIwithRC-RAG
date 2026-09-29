"""Queue every document in a workspace for re-indexing (after chunking or embedding-model changes)."""

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.jobs import queue
from app.models import Document, KnowledgeBase
from app.rag import store


def reindex_workspace(db: DbSession, workspace_id: str, *, drop_vectors: bool) -> int:
    """Mark every document queued and enqueue an ingest job. The caller commits, then calls queue.notify().

    drop_vectors: delete each KB's Chroma collection first (needed when the embedding size changes).
    """
    kb_ids = list(db.scalars(select(KnowledgeBase.id).where(KnowledgeBase.workspace_id == workspace_id)))
    if drop_vectors:
        for kb_id in kb_ids:
            store.delete_collection(kb_id)
    docs = list(db.scalars(select(Document).where(Document.kb_id.in_(kb_ids)))) if kb_ids else []
    for d in docs:
        d.status, d.progress, d.error = "queued", 0, None
        queue.enqueue(db, "ingest", {"document_id": d.id})
    return len(docs)
