"""Retrieval: vector top 20 (+ FTS5 BM25 top 20 when hybrid) → Reciprocal Rank Fusion → optional
cross-encoder rerank → keep top_k. Every passage carries a 0–1 relevance score for the UI.

Relevance: sigmoid of the cross-encoder score when reranking; otherwise cosine similarity between
the question and the passage embeddings.
"""

import math
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.models import Chunk, Document
from app.rag import store
from app.rag.chunk import with_context
from app.rag.embed import get_embedder
from app.rag.rerank import get_reranker, sigmoid

CANDIDATES = 20
RRF_K = 60


@dataclass
class Passage:
    chunk_id: str
    document_id: str
    filename: str
    page: int | None
    section: str | None
    text: str
    ordinal: int
    doc_chunks: int
    score: float  # 0–1 relevance

    def location(self) -> str:
        """"Page 14 · §11.2 Termination" / "Rollback" / "" — used in prompts and the UI."""
        parts = []
        if self.page is not None:
            parts.append(f"Page {self.page}")
        if self.section:
            parts.append(self.section)
        return " · ".join(parts)


def rrf(rankings: list[list[str]], k: int = RRF_K) -> list[tuple[str, float]]:
    """Reciprocal Rank Fusion: score(id) = Σ 1 / (k + rank), ranks starting at 1."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return max(0.0, min(1.0, dot / (na * nb)))


def retrieve(
    db: DbSession,
    kb_id: str,
    question: str,
    *,
    top_k: int = 5,
    hybrid: bool = True,
    rerank: bool = True,
    embedding_model: str | None = None,
) -> list[Passage]:
    total = db.scalar(select(func.count()).select_from(Chunk).where(Chunk.kb_id == kb_id)) or 0
    if total == 0:
        return []

    embedder = get_embedder(embedding_model)
    qv = embedder.embed_query(question)
    col = store.collection(kb_id)
    n = min(CANDIDATES, col.count() or total)
    vec = col.query(query_embeddings=[qv], n_results=max(1, n)) if n else {"ids": [[]]}
    vector_ids: list[str] = list(vec["ids"][0])
    rankings = [vector_ids]
    if hybrid:
        rankings.append([cid for cid, _ in store.fts_search(db, kb_id, question, limit=CANDIDATES)])
    fused = [cid for cid, _ in rrf(rankings)][:CANDIDATES]
    if not fused:
        return []

    rows = db.execute(
        select(Chunk, Document.filename).join(Document, Document.id == Chunk.document_id).where(Chunk.id.in_(fused))
    ).all()
    by_id = {c.id: (c, fname) for c, fname in rows}
    fused = [cid for cid in fused if cid in by_id]  # vectors can outlive a just-deleted document
    doc_counts = dict(
        db.execute(
            select(Chunk.document_id, func.count())
            .where(Chunk.document_id.in_({by_id[c][0].document_id for c in fused}))
            .group_by(Chunk.document_id)
        ).all()
    )

    if rerank:
        raw = get_reranker().scores(
            question, [with_context(by_id[c][1], by_id[c][0].section, by_id[c][0].text) for c in fused]
        )
        rel = {cid: sigmoid(s) for cid, s in zip(fused, raw, strict=True)}
    else:
        got = col.get(ids=fused, include=["embeddings"])
        embs = dict(zip(got["ids"], got["embeddings"], strict=False))
        rel = {cid: _cosine(qv, list(embs[cid])) if cid in embs else 0.0 for cid in fused}

    order = sorted(fused, key=lambda cid: -rel[cid])[: max(1, top_k)]
    out = []
    for cid in order:
        c, fname = by_id[cid]
        out.append(
            Passage(
                chunk_id=c.id, document_id=c.document_id, filename=fname, page=c.page, section=c.section,
                text=c.text, ordinal=c.ordinal, doc_chunks=doc_counts.get(c.document_id, 1), score=round(rel[cid], 4),
            )
        )
    return out
