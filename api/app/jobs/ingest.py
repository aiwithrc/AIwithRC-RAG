"""Ingest job: parse → chunk → embed → index, updating documents.status/progress as it goes.

Progress bands match the prototype: parsing 0–30, chunking 30–55, embedding 55–100.
"""

import logging

from sqlalchemy import delete, select, update

from app.db import SessionLocal, utcnow
from app.jobs.queue import handler
from app.models import Chunk, Document, Event, KnowledgeBase, WorkspaceSettings
from app.rag import store
from app.rag.chunk import chunk_blocks
from app.rag.embed import BATCH_SIZE, get_embedder
from app.rag.parse import ParseError, parse
from app.services import events
from app.services.files import upload_path

log = logging.getLogger("aiwithrc.ingest")

GENERIC_FAILURE = "Something went wrong while indexing this file. Try again."


def _set(document_id: str, **values) -> bool:
    """Update a document's status fields in their own short transaction. False if it was deleted."""
    with SessionLocal() as db:
        n = db.execute(update(Document).where(Document.id == document_id).values(**values)).rowcount
        db.commit()
        return bool(n)


def _finish_events(document_id: str, *, ok: bool, detail: str) -> None:
    """Flip the "Uploaded …" History row's tag, and log a failure row when indexing fails."""
    with SessionLocal() as db:
        doc = db.get(Document, document_id)
        if doc is None:
            return
        kb = db.get(KnowledgeBase, doc.kb_id)
        upload_ev = db.scalars(
            select(Event)
            .where(Event.ref_type == "document", Event.ref_id == document_id, Event.title.startswith("Uploaded"))
            .order_by(Event.created_at.desc())
        ).first()
        if upload_ev is not None:
            upload_ev.tag, upload_ev.tone = ("Indexed", "ok") if ok else ("Failed", "err")
            if ok and kb is not None:
                upload_ev.detail = f"{kb.name} · {detail}"
        if not ok and kb is not None:
            events.record(
                db, workspace_id=kb.workspace_id, user_id=upload_ev.user_id if upload_ev else None,
                category="doc", title=f"{doc.filename} failed to index", detail=detail,
                tone="err", tag="Failed", ref_type="document", ref_id=doc.id,
            )
        db.commit()


def _fail(document_id: str, reason: str) -> None:
    if _set(document_id, status="failed", error=reason, progress=0):
        _finish_events(document_id, ok=False, detail=reason)


@handler("ingest")
def run_ingest(payload: dict) -> None:
    document_id = payload["document_id"]
    with SessionLocal() as db:
        doc = db.get(Document, document_id)
        if doc is None:
            return
        kb = db.get(KnowledgeBase, doc.kb_id)
        assert kb is not None
        ws = db.get(WorkspaceSettings, kb.workspace_id)
        chunk_size, overlap, ocr = (ws.chunk_size, ws.chunk_overlap, ws.ocr) if ws else (800, 120, False)
        embedding_model = ws.embedding_model if ws else None
        kb_id, filename, sha = kb.id, doc.filename, doc.sha256

    try:
        _set(document_id, status="parsing", progress=5, error=None)
        path = upload_path(kb_id, sha)
        if not path.exists():
            raise ParseError("The uploaded file is missing from the server. Upload it again.")
        blocks = parse(path, filename, ocr=ocr)

        if not _set(document_id, status="chunking", progress=30):
            return
        drafts = chunk_blocks(blocks, chunk_size=chunk_size, overlap=overlap)
        if not drafts:
            raise ParseError("This file has no text to index.")

        if not _set(document_id, status="embedding", progress=55):
            return
        embedder = get_embedder(embedding_model)
        vectors: list[list[float]] = []
        for i in range(0, len(drafts), BATCH_SIZE):
            vectors += embedder.embed_passages([d.text for d in drafts[i : i + BATCH_SIZE]])
            done = min(len(drafts), i + BATCH_SIZE)
            if not _set(document_id, progress=55 + int(44 * done / len(drafts))):
                return  # deleted while embedding
    except ParseError as e:
        _fail(document_id, str(e))
        return
    except Exception:
        log.exception("Indexing %s failed", document_id)
        _fail(document_id, GENERIC_FAILURE)
        return

    # Write everything in one transaction, replacing any chunks from a previous attempt.
    with SessionLocal() as db:
        doc = db.get(Document, document_id)
        if doc is None:
            return
        store.fts_delete_document(db, document_id)
        db.execute(delete(Chunk).where(Chunk.document_id == document_id))
        store.delete_document_vectors(kb_id, document_id)

        first_rowid = store.next_fts_rowid(db)
        rows = [
            Chunk(
                document_id=document_id, kb_id=kb_id, ordinal=i, text=d.text, page=d.page, section=d.section,
                token_count=d.token_count, fts_rowid=first_rowid + i,
            )
            for i, d in enumerate(drafts)
        ]
        db.add_all(rows)
        db.flush()
        store.fts_insert(db, [(c.fts_rowid, kb_id, c.text) for c in rows])
        try:
            store.upsert_vectors(kb_id, [c.id for c in rows], vectors, document_id)
        except Exception:
            db.rollback()
            log.exception("Writing vectors for %s failed", document_id)
            _fail(document_id, GENERIC_FAILURE)
            return
        doc.status, doc.progress, doc.error, doc.chunk_count = "indexed", 100, None, len(rows)
        kb = db.get(KnowledgeBase, kb_id)
        if kb is not None:
            kb.updated_at = utcnow()
        db.commit()

    n = len(drafts)
    _finish_events(document_id, ok=True, detail=f"{n} chunk{'' if n == 1 else 's'}")
