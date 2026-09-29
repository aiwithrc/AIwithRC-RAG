"""Retrieval: vector top 40 (+ FTS5 BM25 top 40 when hybrid) → Reciprocal Rank Fusion → optional
cross-encoder rerank → keep the best passages that fit the token budget (at most top_k), then widen the
strongest ones with their neighbouring chunks so answers aren't cut off at a chunk boundary.
Every passage carries a 0–1 relevance score for the UI.

Overview questions ("summarise this document") use `coverage` instead: chunks spread evenly across the
whole document, in reading order.

Relevance: calibrated cross-encoder score (see rerank.relevance) when reranking; otherwise cosine similarity between
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
from app.rag.rerank import get_reranker, relevance

CANDIDATES = 40
MIN_KEEP = 0.15  # below this a passage is noise, once a few passages are in
EXPAND_TOP = 3  # widen this many of the best passages with their neighbours
EXPAND_MIN = 0.5
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
    top_k: int = 8,
    hybrid: bool = True,
    rerank: bool = True,
    embedding_model: str | None = None,
    token_budget: int | None = None,
    expand: bool = True,
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
        rel = {cid: relevance(s) for cid, s in zip(fused, raw, strict=True)}
    else:
        got = col.get(ids=fused, include=["embeddings"])
        embs = dict(zip(got["ids"], got["embeddings"], strict=False))
        rel = {cid: _cosine(qv, list(embs[cid])) if cid in embs else 0.0 for cid in fused}

    order = sorted(fused, key=lambda cid: -rel[cid])
    chosen: list[str] = []
    used = 0
    for cid in order:
        c = by_id[cid][0]
        if len(chosen) >= max(1, top_k):
            break
        if len(chosen) >= 3 and rel[cid] < MIN_KEEP:
            break
        if token_budget and chosen and used + c.token_count > token_budget:
            break
        chosen.append(cid)
        used += c.token_count
    out = [_passage(by_id[cid][0], by_id[cid][1], doc_counts, rel[cid]) for cid in chosen]
    if expand and token_budget:
        _expand_neighbours(db, out, token_budget - used)
    return out


def _passage(c: Chunk, fname: str, doc_counts: dict, score: float) -> Passage:
    return Passage(
        chunk_id=c.id, document_id=c.document_id, filename=fname, page=c.page, section=c.section,
        text=c.text, ordinal=c.ordinal, doc_chunks=doc_counts.get(c.document_id, 1), score=round(score, 4),
    )


def join_overlapping(a: str, b: str) -> str:
    """Join two consecutive chunks, dropping the sentences they share (chunks overlap by whole sentences)."""
    a, b = a.rstrip(), b.lstrip()
    for i in range(min(len(a), len(b)), 20, -1):
        if a.endswith(b[:i]):
            return a + b[i:]
    return f"{a}\n\n{b}"


def _expand_neighbours(db: DbSession, passages: list[Passage], budget: int) -> None:
    """Widen the strongest passages with the chunk before and after, while the budget lasts."""
    taken = {(p.document_id, p.ordinal) for p in passages}
    for p in passages[:EXPAND_TOP]:
        if budget <= 0 or p.score < EXPAND_MIN:
            break
        rows = db.scalars(
            select(Chunk).where(Chunk.document_id == p.document_id, Chunk.ordinal.in_((p.ordinal - 1, p.ordinal + 1)))
        ).all()
        for n in sorted(rows, key=lambda r: r.ordinal):
            if (n.document_id, n.ordinal) in taken or n.token_count > budget:
                continue
            taken.add((n.document_id, n.ordinal))
            budget -= n.token_count
            p.text = join_overlapping(n.text, p.text) if n.ordinal < p.ordinal else join_overlapping(p.text, n.text)


def coverage(
    db: DbSession, document_id: str, question: str, *, token_budget: int, rerank: bool = True
) -> list[Passage]:
    """Chunks spread evenly over one document, in reading order: context for overviews and summaries."""
    rows = list(
        db.execute(
            select(Chunk, Document.filename).join(Document, Document.id == Chunk.document_id)
            .where(Chunk.document_id == document_id).order_by(Chunk.ordinal)
        ).all()
    )
    if not rows:
        return []
    avg = max(1, sum(c.token_count for c, _ in rows) // len(rows))
    n = max(1, min(len(rows), token_budget // avg))
    step = len(rows) / n
    picked = [rows[int(i * step)] for i in range(n)]
    if rerank:
        raw = get_reranker().scores(question, [with_context(f, c.section, c.text) for c, f in picked])
        scores = [relevance(s) for s in raw]
    else:
        scores = [0.5] * len(picked)
    counts = {document_id: len(rows)}
    return [_passage(c, f, counts, s) for (c, f), s in zip(picked, scores, strict=True)]
