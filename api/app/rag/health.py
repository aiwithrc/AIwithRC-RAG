"""Index QA: checks that every document's chunks, vectors and keyword rows agree and look sane.

Run with `python -m app.cli check`. Read-only.
"""

import math
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.orm import Session as DbSession

from app.models import Chunk, Document, KnowledgeBase
from app.rag import store
from app.rag.chunk import with_context
from app.rag.embed import get_embedder

TINY_TOKENS = 20


@dataclass
class DocReport:
    kb: str
    filename: str
    status: str
    chunks: int
    vectors: int
    keyword_rows: int
    min_tokens: int
    max_tokens: int
    sections: int
    self_retrieval: tuple[int, int]  # (found themselves first, checked)
    bad_dims: int
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)  # worth a look, not a failure

    @property
    def ok(self) -> bool:
        return not self.problems


def check_document(db: DbSession, kb: KnowledgeBase, doc: Document, *, sample: int = 25) -> DocReport:
    chunks = list(db.scalars(select(Chunk).where(Chunk.document_id == doc.id).order_by(Chunk.ordinal)))
    ids = [c.id for c in chunks]
    col = store.collection(kb.id)
    got = col.get(ids=ids, include=["embeddings"]) if ids else {"ids": [], "embeddings": []}
    fts = 0
    if store.fts_enabled(db) and ids:
        fts = db.execute(
            text("SELECT COUNT(*) FROM chunks_fts WHERE rowid IN (SELECT fts_rowid FROM chunks WHERE document_id = :d)"),
            {"d": doc.id},
        ).scalar() or 0
    toks = [c.token_count for c in chunks] or [0]
    rep = DocReport(
        kb=kb.name, filename=doc.filename, status=doc.status, chunks=len(chunks), vectors=len(got["ids"]),
        keyword_rows=fts, min_tokens=min(toks), max_tokens=max(toks),
        sections=len({c.section for c in chunks if c.section}), self_retrieval=(0, 0), bad_dims=0,
    )
    if doc.status == "failed":
        rep.problems.append(f"failed to index: {doc.error}")
        return rep
    if doc.status != "indexed":
        rep.problems.append(f"still {doc.status}")
        return rep
    if not chunks:
        rep.problems.append("indexed but has no chunks")
        return rep
    if rep.vectors != rep.chunks:
        rep.problems.append(f"{rep.chunks - rep.vectors} chunk(s) missing a vector")
    if store.fts_enabled(db) and rep.keyword_rows != rep.chunks:
        rep.problems.append(f"{rep.chunks - rep.keyword_rows} chunk(s) missing from keyword search")
    if doc.chunk_count != len(chunks):
        rep.problems.append(f"document says {doc.chunk_count} chunks, found {len(chunks)}")
    if (tiny := sum(t < TINY_TOKENS for t in toks)) and len(chunks) > 1:
        rep.warnings.append(f"{tiny} short chunk(s) under {TINY_TOKENS} tokens")

    embedder = get_embedder()
    dim = embedder.dim
    vecs = dict(zip(got["ids"], got["embeddings"], strict=False))
    for v in vecs.values():
        norm = math.sqrt(sum(x * x for x in v))
        if len(v) != dim or not 0.9 < norm < 1.1:
            rep.bad_dims += 1
    if rep.bad_dims:
        rep.problems.append(f"{rep.bad_dims} vector(s) with the wrong size or length (model changed? re-index)")

    # Self-retrieval: searching with a chunk's own (context-prefixed) text should find it first.
    step = max(1, len(chunks) // sample)
    checked = found = 0
    for c in chunks[::step][:sample]:
        q = embedder.embed_query(with_context(doc.filename, c.section, c.text)[:2000])
        r = col.query(query_embeddings=[q], n_results=1, where={"document_id": doc.id})
        checked += 1
        found += bool(r["ids"][0]) and r["ids"][0][0] == c.id
    rep.self_retrieval = (found, checked)
    if checked and found / checked < 0.8:
        rep.problems.append(f"only {found}/{checked} chunks find themselves (near-duplicate chunks or stale vectors)")
    return rep


def check_all(db: DbSession, kb_id: str | None = None) -> list[DocReport]:
    q = select(KnowledgeBase).order_by(KnowledgeBase.created_at)
    if kb_id:
        q = q.where(KnowledgeBase.id == kb_id)
    reports = []
    for kb in db.scalars(q):
        for doc in db.scalars(select(Document).where(Document.kb_id == kb.id).order_by(Document.created_at)):
            reports.append(check_document(db, kb, doc))
    return reports
