"""Index storage: vectors in Chroma (one collection per knowledge base) and keywords in SQLite FTS5.

Chunk rows in SQL are the source of truth; Chroma and FTS hold the same chunk ids.
"""

import threading

from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings

_client = None
_client_lock = threading.Lock()


def chroma():
    global _client
    with _client_lock:
        if _client is None:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            path = get_settings().data_dir / "chroma"
            path.mkdir(parents=True, exist_ok=True)
            _client = chromadb.PersistentClient(
                path=str(path), settings=ChromaSettings(anonymized_telemetry=False, allow_reset=False)
            )
        return _client


def reset_chroma_client() -> None:
    """Forget the cached client (tests point DATA_DIR somewhere new)."""
    global _client
    with _client_lock:
        _client = None


def collection_name(kb_id: str) -> str:
    return f"kb_{kb_id}"


def collection(kb_id: str):
    return chroma().get_or_create_collection(collection_name(kb_id), metadata={"hnsw:space": "cosine"})


def upsert_vectors(kb_id: str, ids: list[str], vectors: list[list[float]], document_id: str) -> None:
    if ids:
        collection(kb_id).upsert(ids=ids, embeddings=vectors, metadatas=[{"document_id": document_id}] * len(ids))


def delete_document_vectors(kb_id: str, document_id: str) -> None:
    try:
        collection(kb_id).delete(where={"document_id": document_id})
    except Exception:  # collection may not exist yet
        pass


def delete_collection(kb_id: str) -> None:
    try:
        chroma().delete_collection(collection_name(kb_id))
    except Exception:
        pass


# ---- FTS5 (SQLite only) ----

def fts_enabled(db: DbSession) -> bool:
    return db.get_bind().dialect.name == "sqlite"


def fts_insert(db: DbSession, rows: list[tuple[int, str, str]]) -> None:
    """rows: (fts_rowid, kb_id, text)"""
    if rows and fts_enabled(db):
        db.execute(
            text("INSERT INTO chunks_fts(rowid, text, kb_id) VALUES (:rowid, :text, :kb_id)"),
            [{"rowid": r, "kb_id": k, "text": t} for r, k, t in rows],
        )


def fts_delete_document(db: DbSession, document_id: str) -> None:
    if fts_enabled(db):
        db.execute(
            text("DELETE FROM chunks_fts WHERE rowid IN (SELECT fts_rowid FROM chunks WHERE document_id = :d)"),
            {"d": document_id},
        )


def fts_delete_kb(db: DbSession, kb_id: str) -> None:
    if fts_enabled(db):
        db.execute(
            text("DELETE FROM chunks_fts WHERE rowid IN (SELECT fts_rowid FROM chunks WHERE kb_id = :k)"),
            {"k": kb_id},
        )


def next_fts_rowid(db: DbSession) -> int:
    return (db.execute(text("SELECT COALESCE(MAX(fts_rowid), 0) FROM chunks")).scalar() or 0) + 1


def fts_query(question: str) -> str:
    """Turn free text into a safe FTS5 query: OR of quoted terms (so punctuation can't break syntax)."""
    import re

    terms = [t for t in re.findall(r"\w+", question.lower()) if len(t) > 1]
    stop = {"the", "and", "for", "with", "what", "which", "who", "how", "are", "was", "is", "of", "to", "in",
            "on", "a", "an", "does", "do", "can", "this", "that", "it", "be", "by", "or", "as", "at", "from"}
    terms = [t for t in dict.fromkeys(terms) if t not in stop] or terms
    return " OR ".join(f'"{t}"' for t in terms[:32])


def fts_search(db: DbSession, kb_id: str, question: str, limit: int = 20) -> list[tuple[str, float]]:
    """BM25 keyword search. Returns (chunk_id, bm25) best first; lower bm25 is better in SQLite."""
    q = fts_query(question)
    if not q or not fts_enabled(db):
        return []
    rows = db.execute(
        text(
            "SELECT c.id, bm25(chunks_fts) AS score FROM chunks_fts "
            "JOIN chunks c ON c.fts_rowid = chunks_fts.rowid "
            "WHERE chunks_fts MATCH :q AND chunks_fts.kb_id = :kb ORDER BY score LIMIT :n"
        ),
        {"q": q, "kb": kb_id, "n": limit},
    ).all()
    return [(r[0], float(r[1])) for r in rows]
