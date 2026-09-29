"""Workspace settings: retrieval, chunking, privacy, embedding model and the answering prompt."""

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator

from app.deps import CurrentAuth, Db
from app.jobs import queue
from app.models import WorkspaceSettings
from app.rag.answer import MAX_INSTRUCTIONS, SYSTEM
from app.security.sessions import client_ip
from app.services import events
from app.services.reindex import reindex_workspace

router = APIRouter(prefix="/settings", tags=["settings"])

# fastembed models offered in Settings (all run locally on CPU). The first is baked into the Docker image;
# the others download on first use (needs internet once).
EMBEDDING_MODELS: dict[str, int] = {
    "BAAI/bge-small-en-v1.5": 384,
    "BAAI/bge-base-en-v1.5": 768,
    "sentence-transformers/all-MiniLM-L6-v2": 384,
    "nomic-ai/nomic-embed-text-v1.5": 768,
}

TOGGLE_NAMES = {
    "hybrid": "Hybrid search",
    "rerank": "Rerank results",
    "keep_local": "Keep local knowledge bases local",
    "ocr": "OCR for scanned PDFs",
}


class SettingsOut(BaseModel):
    chunk_size: int
    chunk_overlap: int
    top_k: int
    hybrid: bool
    rerank: bool
    keep_local: bool
    ocr: bool
    embedding_provider: str
    embedding_model: str
    embedding_dims: int | None
    embedding_models: dict[str, int]
    custom_instructions: str
    built_in_prompt: str  # read-only: the rules every answer follows
    max_instructions: int
    can_edit: bool
    reindexing: int = 0  # documents queued by this change


class SettingsPatch(BaseModel):
    chunk_size: int | None = Field(default=None, ge=200, le=2000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=400)
    top_k: int | None = Field(default=None, ge=1, le=20)
    hybrid: bool | None = None
    rerank: bool | None = None
    keep_local: bool | None = None
    ocr: bool | None = None
    embedding_model: str | None = None
    custom_instructions: str | None = Field(default=None, max_length=MAX_INSTRUCTIONS)

    @model_validator(mode="after")
    def _check(self):
        if self.embedding_model is not None and self.embedding_model not in EMBEDDING_MODELS:
            raise ValueError("Unknown embedding model.")
        return self


def _get(db: Db, workspace_id: str) -> WorkspaceSettings:
    ws = db.get(WorkspaceSettings, workspace_id)
    if ws is None:  # older workspaces
        ws = WorkspaceSettings(workspace_id=workspace_id)
        db.add(ws)
        db.flush()
    return ws


def _out(ws: WorkspaceSettings, can_edit: bool, reindexing: int = 0) -> SettingsOut:
    return SettingsOut(
        chunk_size=ws.chunk_size, chunk_overlap=ws.chunk_overlap, top_k=ws.top_k, hybrid=ws.hybrid,
        rerank=ws.rerank, keep_local=ws.keep_local, ocr=ws.ocr, embedding_provider=ws.embedding_provider,
        embedding_model=ws.embedding_model, embedding_dims=EMBEDDING_MODELS.get(ws.embedding_model),
        embedding_models=EMBEDDING_MODELS, custom_instructions=ws.custom_instructions or "",
        built_in_prompt=SYSTEM, max_instructions=MAX_INSTRUCTIONS, can_edit=can_edit, reindexing=reindexing,
    )


@router.get("", response_model=SettingsOut)
def get_settings(auth: CurrentAuth, db: Db) -> SettingsOut:
    ws = _get(db, auth.workspace_id)
    db.commit()
    return _out(ws, auth.user.role == "owner")


def _require_owner(auth: CurrentAuth) -> None:
    if auth.user.role != "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the workspace owner can change settings.")


@router.patch("", response_model=SettingsOut)
def patch_settings(body: SettingsPatch, auth: CurrentAuth, request: Request, db: Db) -> SettingsOut:
    _require_owner(auth)
    ws = _get(db, auth.workspace_id)
    ip = client_ip(request)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)

    def log(title: str, detail: str = "Workspace settings") -> None:
        events.record(db, workspace_id=auth.workspace_id, user_id=auth.user.id, category="settings",
                      title=title, detail=detail, ip=ip)

    size = changes.get("chunk_size", ws.chunk_size)
    overlap = changes.get("chunk_overlap", ws.chunk_overlap)
    if overlap >= size // 2:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Overlap must be less than half the chunk size.")

    reindex_reason: list[str] = []
    for field, label, unit in (("chunk_size", "Chunk size", " tokens"), ("chunk_overlap", "Overlap", " tokens"),
                               ("top_k", "Passages per answer", "")):
        if field in changes and changes[field] != getattr(ws, field):
            old = getattr(ws, field)
            setattr(ws, field, changes[field])
            if field == "top_k":
                log(f"{label} changed", f"{old} → {changes[field]}")
            else:
                reindex_reason.append(f"{label} {old} → {changes[field]}{unit}")
    for field, label in TOGGLE_NAMES.items():
        if field in changes and changes[field] != getattr(ws, field):
            setattr(ws, field, changes[field])
            log(f"{label} turned {'on' if changes[field] else 'off'}")
    model_changed = "embedding_model" in changes and changes["embedding_model"] != ws.embedding_model
    if model_changed:
        reindex_reason.append(f"Embedding model {ws.embedding_model} → {changes['embedding_model']}")
        ws.embedding_model = changes["embedding_model"]
    if "custom_instructions" in changes:
        new = changes["custom_instructions"].strip()
        old = ws.custom_instructions or ""
        if new != old:
            ws.custom_instructions = new
            log("Prompt instructions cleared" if not new else "Prompt instructions updated",
                f"{len(old.split())} → {len(new.split())} words")

    reindexing = 0
    if reindex_reason:
        reindexing = reindex_workspace(db, auth.workspace_id, drop_vectors=model_changed)
        title = "Embedding model changed" if model_changed else "Chunking changed"
        log(title, " · ".join(reindex_reason) + f" · {reindexing} document{'s' if reindexing != 1 else ''} re-indexed")
    db.commit()
    if reindexing:
        queue.notify()
    return _out(ws, True, reindexing)


@router.post("/reindex", response_model=SettingsOut)
def reindex(auth: CurrentAuth, request: Request, db: Db) -> SettingsOut:
    _require_owner(auth)
    ws = _get(db, auth.workspace_id)
    n = reindex_workspace(db, auth.workspace_id, drop_vectors=False)
    events.record(db, workspace_id=auth.workspace_id, user_id=auth.user.id, category="settings",
                  title="Re-index started", detail=f"{n} document{'s' if n != 1 else ''}", ip=client_ip(request))
    db.commit()
    queue.notify()
    return _out(ws, True, n)
